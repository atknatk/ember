"""Mem0 circuit breaker — protects the chat system from cascading failures.

Implements a three-state circuit breaker (CLOSED, OPEN, HALF_OPEN) that wraps
all Mem0 API calls. When Mem0 is down, chat continues with cached or empty
memories. Failed mem0.add() operations are queued for retry when the circuit
closes.

See docs/05-ai-bellek.md "Mem0 Degradation Stratejisi" and
shared/feature-specs/mem0-circuit-breaker.md for full design.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import TypeVar

from app.config import settings

logger = logging.getLogger("ember")

T = TypeVar("T")


class CircuitState(StrEnum):
    """Possible states for the circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a call is attempted while the circuit is open."""


@dataclass
class CacheEntry:
    """Cached memory search results for a single agent_id or global key."""

    memories: list[str]
    cached_at: float  # time.monotonic


@dataclass
class RetryItem:
    """A queued mem0.add() operation for retry when the circuit closes."""

    messages: list[dict[str, str]]
    user_id: str
    agent_id: str
    created_at: float = field(default_factory=time.monotonic)


class Mem0CircuitBreaker:
    """Singleton circuit breaker for all Mem0 API calls.

    Thread-safe for asyncio (single-threaded event loop, no locks needed).
    Uses time.monotonic() for all internal timing.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        cache_ttl: float = 300.0,
        max_retry_queue_size: int = 100,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.cache_ttl = cache_ttl

        self.state: CircuitState = CircuitState.CLOSED
        self.failure_count: int = 0
        self.last_failure_at: datetime | None = None
        self.last_success_at: datetime | None = None
        self._opened_at: float | None = None

        self._cache: dict[str, CacheEntry] = {}
        self._retry_queue: deque[RetryItem] = deque(maxlen=max_retry_queue_size)

    async def call_with_breaker(
        self,
        func: Callable[[], Awaitable[T]],
    ) -> T:
        """Execute a Mem0 operation through the circuit breaker.

        Args:
            func: An async zero-arg callable (closure) wrapping a Mem0 call.

        Returns:
            The result of func().

        Raises:
            CircuitOpenError: If the circuit is open and recovery timeout
                has not elapsed.
            Exception: Re-raises the original exception from func on failure.
        """
        if self.state == CircuitState.OPEN:
            if self._is_recovery_timeout_elapsed():
                # Transition to HALF_OPEN and attempt a probe
                self.state = CircuitState.HALF_OPEN
                logger.warning("Mem0 circuit breaker half-open, probing...")
            else:
                raise CircuitOpenError("Circuit breaker is open")

        # CLOSED or HALF_OPEN: attempt the call
        try:
            result = await func()
        except Exception:
            self.record_failure()
            raise

        self.record_success()
        return result

    def record_success(self) -> None:
        """Record a successful Mem0 call."""
        self.failure_count = 0
        self.last_success_at = datetime.now(tz=UTC)

        if self.state == CircuitState.HALF_OPEN:
            queue_size = len(self._retry_queue)
            self.state = CircuitState.CLOSED
            self._opened_at = None
            logger.warning(
                "Mem0 circuit breaker closed, draining %d queued operations",
                queue_size,
            )
            # Drain retry queue in background
            if queue_size > 0:
                asyncio.create_task(self.drain_retry_queue())  # noqa: RUF006

    def record_failure(self) -> None:
        """Record a failed Mem0 call."""
        self.failure_count += 1
        self.last_failure_at = datetime.now(tz=UTC)

        if self.state == CircuitState.HALF_OPEN:
            # Probe failed — reopen
            self.state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning("Mem0 circuit breaker probe failed, reopening")
        elif (
            self.state == CircuitState.CLOSED
            and self.failure_count >= self.failure_threshold
        ):
            self.state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning(
                "Mem0 circuit breaker opened after %d consecutive failures",
                self.failure_count,
            )

    def get_cached_memories(self, cache_key: str) -> list[str] | None:
        """Return cached memory search results if within TTL.

        Returns None if not cached or expired.
        """
        entry = self._cache.get(cache_key)
        if entry is None:
            return None

        elapsed = time.monotonic() - entry.cached_at
        if elapsed > self.cache_ttl:
            # Expired — remove and return None
            del self._cache[cache_key]
            return None

        logger.debug("Mem0 cache hit for key=%s", cache_key)
        return entry.memories

    def set_cached_memories(
        self,
        cache_key: str,
        memories: list[str],
    ) -> None:
        """Store memory search results in cache with current timestamp."""
        self._cache[cache_key] = CacheEntry(
            memories=memories,
            cached_at=time.monotonic(),
        )

    def enqueue_retry(
        self,
        messages: list[dict[str, str]],
        user_id: str,
        agent_id: str,
    ) -> None:
        """Add a mem0.add() operation to the retry queue.

        If the queue is at max size, the oldest entry is dropped
        automatically by the deque's maxlen behavior.
        """
        self._retry_queue.append(
            RetryItem(
                messages=messages,
                user_id=user_id,
                agent_id=agent_id,
            ),
        )

    async def drain_retry_queue(self) -> None:
        """Process all items in the retry queue by calling mem0.add().

        Failures during drain are logged but do not re-open the circuit.
        Called as a background task after the circuit transitions to CLOSED.
        """
        from mem0 import MemoryClient

        from app.utils.timing import log_external_call

        drained = 0
        failed = 0

        while self._retry_queue:
            item = self._retry_queue.popleft()
            try:
                client = MemoryClient(api_key=settings.mem0_api_key)
                async with log_external_call("mem0", "add"):
                    await asyncio.to_thread(
                        client.add,
                        item.messages,
                        user_id=item.user_id,
                        agent_id=item.agent_id,
                    )
                drained += 1
            except Exception:
                logger.warning(
                    "Retry queue drain: mem0.add failed for agent_id=%s",
                    item.agent_id,
                    exc_info=True,
                )
                failed += 1

        if drained > 0 or failed > 0:
            logger.info(
                "Retry queue drain complete: %d succeeded, %d failed",
                drained,
                failed,
            )

    def get_status(self) -> dict[str, str | int | None]:
        """Return circuit breaker status for the health endpoint."""
        # Count non-expired cache entries
        now = time.monotonic()
        cache_entries = sum(
            1
            for entry in self._cache.values()
            if (now - entry.cached_at) <= self.cache_ttl
        )

        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure_at": (
                self.last_failure_at.isoformat() if self.last_failure_at else None
            ),
            "last_success_at": (
                self.last_success_at.isoformat() if self.last_success_at else None
            ),
            "retry_queue_size": len(self._retry_queue),
            "cache_entries": cache_entries,
        }

    def _is_recovery_timeout_elapsed(self) -> bool:
        """Check if enough time has passed to attempt a probe."""
        if self._opened_at is None:
            return True
        return (time.monotonic() - self._opened_at) >= self.recovery_timeout


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_breaker: Mem0CircuitBreaker | None = None


def get_mem0_circuit_breaker() -> Mem0CircuitBreaker:
    """Return the module-level circuit breaker singleton."""
    global _breaker  # noqa: PLW0603
    if _breaker is None:
        _breaker = Mem0CircuitBreaker(
            failure_threshold=settings.mem0_circuit_failure_threshold,
            recovery_timeout=settings.mem0_circuit_recovery_timeout,
            cache_ttl=settings.mem0_cache_ttl,
            max_retry_queue_size=settings.mem0_retry_queue_max_size,
        )
    return _breaker
