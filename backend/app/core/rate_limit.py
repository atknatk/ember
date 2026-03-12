"""In-memory token bucket rate limiter for the Ember backend.

Provides per-user rate limiting keyed by JWT ``sub`` claim (authenticated users)
or client IP address (unauthenticated requests). Three rate limit groups provide
differentiated limits: chat (expensive LLM calls), write (standard mutations),
and read (cheap queries).

The ``RateLimiter`` class manages token buckets and provides rate limiting
decisions. The ``extract_user_key`` function extracts the rate limit key from
an incoming request without performing full JWT verification.
"""

from __future__ import annotations

import base64
import json
import logging
import math
import re
import time

from starlette.requests import Request

logger = logging.getLogger("ember")

# Pre-compiled regex for chat endpoint path matching
_CHAT_PATH_RE = re.compile(r"^/api/v1/characters/[^/]+/messages(/stream)?$")


class TokenBucket:
    """A single token bucket for one (user, group) pair.

    Attributes:
        tokens: Current token count (starts at max_tokens).
        last_refill: ``time.monotonic()`` of last refill calculation.
        max_tokens: Maximum tokens (equals the rate limit per minute).
        refill_rate: Tokens added per second (max_tokens / 60).
    """

    __slots__ = ("tokens", "last_refill", "max_tokens", "refill_rate")

    def __init__(self, max_tokens: int) -> None:
        self.max_tokens = max_tokens
        self.refill_rate = max_tokens / 60.0
        self.tokens = float(max_tokens)
        self.last_refill = time.monotonic()

    def consume(self) -> tuple[bool, float]:
        """Refill tokens based on elapsed time, then attempt to consume one.

        Returns:
            A tuple of (allowed, retry_after_seconds).
            ``retry_after_seconds`` is 0.0 if allowed, otherwise the time
            in seconds until the next token becomes available.
        """
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True, 0.0

        retry_after = (1.0 - self.tokens) / self.refill_rate
        return False, retry_after


class RateLimiter:
    """Manages token buckets for all users across rate limit groups.

    Each (user_id_or_ip, group) pair has its own ``TokenBucket``.
    Stale buckets are cleaned up periodically to prevent unbounded
    memory growth.

    Attributes:
        _buckets: Mapping from ``"{key}:{group}"`` to ``TokenBucket``.
        _group_limits: Mapping from group name to max requests per minute.
        _exempt_paths: Paths that bypass rate limiting entirely.
        _cleanup_interval: Seconds between stale bucket cleanup runs.
        _last_cleanup: ``time.monotonic()`` of last cleanup run.
    """

    def __init__(
        self,
        group_limits: dict[str, int],
        exempt_paths: set[str],
        cleanup_interval: float = 300.0,
    ) -> None:
        self._buckets: dict[str, TokenBucket] = {}
        self._group_limits = group_limits
        self._exempt_paths = exempt_paths
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.monotonic()

    def check(self, key: str, group: str) -> tuple[bool, dict[str, str]]:
        """Check if a request is allowed under the rate limit.

        Args:
            key: The user identifier (JWT sub or ``ip:{address}``).
            group: The rate limit group (``chat``, ``write``, or ``read``).

        Returns:
            A tuple of (allowed, headers_dict). ``headers_dict`` always
            contains ``X-RateLimit-Limit``, ``X-RateLimit-Remaining``,
            and ``X-RateLimit-Reset``. If not allowed, also contains
            ``Retry-After``.
        """
        self._maybe_cleanup()

        bucket_key = f"{key}:{group}"
        max_tokens = self._group_limits.get(group, 20)

        if bucket_key not in self._buckets:
            self._buckets[bucket_key] = TokenBucket(max_tokens)

        bucket = self._buckets[bucket_key]
        allowed, retry_after = bucket.consume()

        # Calculate seconds until full refill for X-RateLimit-Reset
        tokens_deficit = bucket.max_tokens - bucket.tokens
        seconds_to_full = tokens_deficit / bucket.refill_rate if bucket.refill_rate > 0 else 0
        reset_timestamp = int(time.time()) + int(math.ceil(seconds_to_full))

        headers: dict[str, str] = {
            "X-RateLimit-Limit": str(max_tokens),
            "X-RateLimit-Remaining": str(max(0, int(bucket.tokens))),
            "X-RateLimit-Reset": str(reset_timestamp),
        }

        if not allowed:
            headers["Retry-After"] = str(max(1, int(math.ceil(retry_after))))

        return allowed, headers

    def classify_request(self, method: str, path: str) -> str | None:
        """Determine which rate limit group a request belongs to.

        Args:
            method: The HTTP method (GET, POST, PUT, DELETE, etc.).
            path: The request URL path.

        Returns:
            The group name (``chat``, ``write``, ``read``) or ``None``
            if the path is exempt from rate limiting.
        """
        if path in self._exempt_paths:
            return None

        if method == "POST" and _CHAT_PATH_RE.match(path):
            return "chat"

        if method in ("POST", "PUT", "DELETE", "PATCH"):
            return "write"

        if method == "GET":
            return "read"

        # Default to write for uncommon methods (e.g., PATCH)
        return "write"

    def _maybe_cleanup(self) -> None:
        """Remove stale buckets if the cleanup interval has elapsed."""
        now = time.monotonic()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now
        self._cleanup_stale_buckets()

    def _cleanup_stale_buckets(self) -> None:
        """Remove buckets that are fully refilled (inactive).

        A bucket is considered stale if its tokens equal max_tokens,
        meaning no requests have been made recently enough to consume
        tokens faster than the refill rate.
        """
        stale_keys = [
            key
            for key, bucket in self._buckets.items()
            if bucket.tokens >= bucket.max_tokens
        ]
        for key in stale_keys:
            del self._buckets[key]

        if stale_keys:
            logger.debug("Rate limiter cleanup: removed %d stale buckets", len(stale_keys))


def extract_user_key(request: Request) -> str:
    """Extract the rate limit key from an incoming request.

    Attempts lightweight JWT parsing (base64 decode only, no signature
    verification) to extract the ``sub`` claim. Falls back to client
    IP address on any failure.

    Args:
        request: The Starlette/FastAPI request object.

    Returns:
        The JWT ``sub`` value (for authenticated requests) or
        ``ip:{client_ip}`` (for unauthenticated or unparseable requests).
    """
    try:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return _ip_key(request)

        token = auth_header[7:]  # Strip "Bearer " prefix
        parts = token.split(".")
        if len(parts) != 3:  # noqa: PLR2004
            return _ip_key(request)

        # base64url decode the payload (second part)
        payload_b64 = parts[1]
        # Add padding if needed
        padding = 4 - len(payload_b64) % 4
        if padding != 4:  # noqa: PLR2004
            payload_b64 += "=" * padding

        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes)
        sub = payload.get("sub")
        if sub and isinstance(sub, str):
            result: str = sub
            return result

        return _ip_key(request)
    except Exception:
        return _ip_key(request)


def _ip_key(request: Request) -> str:
    """Build an IP-based rate limit key from the request.

    Args:
        request: The Starlette/FastAPI request object.

    Returns:
        A string in the format ``ip:{client_ip}``.
    """
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"
