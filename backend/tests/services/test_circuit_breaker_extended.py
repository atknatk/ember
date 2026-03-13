"""Extended tests for Mem0 circuit breaker — additional coverage for
uncovered paths: singleton factory, memory service delete/global operations,
chat service global search fallback, HALF_OPEN state in memory service,
and drain retry queue circuit-state-preservation.

Adds coverage for lines not reached by the 35 existing tests in
tests/services/test_circuit_breaker.py.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import time  # noqa: E402
import uuid  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from app.core.circuit_breaker import (  # noqa: E402
    CircuitState,
    Mem0CircuitBreaker,
    get_mem0_circuit_breaker,
)


# ---------------------------------------------------------------------------
# Helpers (same pattern as existing test file)
# ---------------------------------------------------------------------------


def _make_breaker(
    failure_threshold: int = 3,
    recovery_timeout: float = 60.0,
    cache_ttl: float = 300.0,
    max_retry_queue_size: int = 100,
) -> Mem0CircuitBreaker:
    return Mem0CircuitBreaker(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        cache_ttl=cache_ttl,
        max_retry_queue_size=max_retry_queue_size,
    )


def _make_char_mock(
    char_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    mem0_agent_id: str = "english_teacher_550e8400",
) -> MagicMock:
    char = MagicMock()
    char.id = char_id or uuid.UUID("660e8400-e29b-41d4-a716-446655440001")
    char.user_id = user_id or uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
    char.mem0_agent_id = mem0_agent_id
    char.is_active = True
    return char


def _make_mock_db(char: MagicMock) -> MagicMock:
    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = char

    async def _mock_execute(*args: object, **kwargs: object) -> MagicMock:
        return mock_result

    mock_db.execute = _mock_execute
    return mock_db


# ---------------------------------------------------------------------------
# Singleton Factory Tests
# ---------------------------------------------------------------------------


class TestSingletonFactory:
    """Tests for get_mem0_circuit_breaker() singleton factory."""

    def test_returns_same_instance_across_calls(self) -> None:
        """get_mem0_circuit_breaker() returns the same instance when called twice."""
        import app.core.circuit_breaker as cb_module

        # conftest autouse resets _breaker = None before each test
        instance_a = get_mem0_circuit_breaker()
        instance_b = get_mem0_circuit_breaker()
        assert instance_a is instance_b

    def test_singleton_respects_config_defaults(self) -> None:
        """Singleton is created with values from settings."""
        import app.core.circuit_breaker as cb_module

        instance = get_mem0_circuit_breaker()
        assert isinstance(instance, Mem0CircuitBreaker)
        # Config defaults: failure_threshold=3, recovery_timeout=60.0
        assert instance.failure_threshold >= 1
        assert instance.recovery_timeout >= 0

    def test_reset_singleton_creates_fresh_instance(self) -> None:
        """Resetting _breaker to None creates a fresh instance on next call."""
        import app.core.circuit_breaker as cb_module

        first = get_mem0_circuit_breaker()
        cb_module._breaker = None
        second = get_mem0_circuit_breaker()
        assert first is not second

    def test_injected_singleton_is_returned(self) -> None:
        """A pre-injected _breaker is returned directly without creating a new one."""
        import app.core.circuit_breaker as cb_module

        custom = _make_breaker(failure_threshold=99)
        cb_module._breaker = custom
        returned = get_mem0_circuit_breaker()
        assert returned is custom
        assert returned.failure_threshold == 99


# ---------------------------------------------------------------------------
# Circuit Breaker State Machine — Additional Edge Cases
# ---------------------------------------------------------------------------


class TestCircuitBreakerEdgeCases:
    """Additional state machine tests for edge cases not in existing suite."""

    @pytest.mark.asyncio
    async def test_threshold_of_one_opens_immediately(self) -> None:
        """With failure_threshold=1, first failure opens the circuit."""
        breaker = _make_breaker(failure_threshold=1)

        with pytest.raises(RuntimeError):
            await breaker.call_with_breaker(self._fail)

        assert breaker.state == CircuitState.OPEN
        assert breaker.failure_count == 1

    @pytest.mark.asyncio
    async def test_failure_count_beyond_threshold_stays_open(self) -> None:
        """Circuit stays OPEN (not re-increments threshold) on multiple failures."""
        breaker = _make_breaker(failure_threshold=2, recovery_timeout=9999.0)
        # Open the circuit
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await breaker.call_with_breaker(self._fail)

        assert breaker.state == CircuitState.OPEN
        # Further calls should raise CircuitOpenError, not RuntimeError
        with pytest.raises(Exception) as exc_info:
            await breaker.call_with_breaker(self._fail)
        from app.core.circuit_breaker import CircuitOpenError
        assert isinstance(exc_info.value, CircuitOpenError)

    @pytest.mark.asyncio
    async def test_half_open_state_is_set_before_probe_executes(self) -> None:
        """Verify state is HALF_OPEN when the probe callable runs."""
        breaker = _make_breaker(failure_threshold=3, recovery_timeout=0.0)

        for _ in range(3):
            with pytest.raises(RuntimeError):
                await breaker.call_with_breaker(self._fail)

        state_during_probe: list[CircuitState] = []

        async def _probe() -> str:
            state_during_probe.append(breaker.state)
            return "ok"

        await breaker.call_with_breaker(_probe)
        assert state_during_probe == [CircuitState.HALF_OPEN]

    @pytest.mark.asyncio
    async def test_opened_at_reset_after_close(self) -> None:
        """_opened_at is set to None when circuit closes from HALF_OPEN."""
        breaker = _make_breaker(failure_threshold=3, recovery_timeout=0.0)

        for _ in range(3):
            with pytest.raises(RuntimeError):
                await breaker.call_with_breaker(self._fail)

        assert breaker._opened_at is not None

        await breaker.call_with_breaker(self._succeed)

        assert breaker.state == CircuitState.CLOSED
        assert breaker._opened_at is None

    @pytest.mark.asyncio
    async def test_opened_at_reset_on_half_open_failure(self) -> None:
        """_opened_at is updated (new timer) when probe fails in HALF_OPEN."""
        breaker = _make_breaker(failure_threshold=3, recovery_timeout=0.0)

        for _ in range(3):
            with pytest.raises(RuntimeError):
                await breaker.call_with_breaker(self._fail)

        old_opened_at = breaker._opened_at

        # Probe fails
        with pytest.raises(RuntimeError):
            await breaker.call_with_breaker(self._fail)

        assert breaker.state == CircuitState.OPEN
        # Timer was reset — new _opened_at >= old
        assert breaker._opened_at >= old_opened_at  # type: ignore[operator]

    def test_record_failure_sets_last_failure_at(self) -> None:
        """record_failure() updates last_failure_at to a UTC datetime."""
        from datetime import UTC, datetime

        breaker = _make_breaker()
        assert breaker.last_failure_at is None
        breaker.record_failure()
        assert breaker.last_failure_at is not None
        assert breaker.last_failure_at.tzinfo is not None

    def test_record_success_sets_last_success_at(self) -> None:
        """record_success() updates last_success_at to a UTC datetime."""
        from datetime import UTC, datetime

        breaker = _make_breaker()
        assert breaker.last_success_at is None
        breaker.record_success()
        assert breaker.last_success_at is not None
        assert breaker.last_success_at.tzinfo is not None

    def test_is_recovery_timeout_elapsed_returns_true_when_opened_at_is_none(self) -> None:
        """_is_recovery_timeout_elapsed() returns True when _opened_at is None."""
        breaker = _make_breaker()
        assert breaker._opened_at is None
        assert breaker._is_recovery_timeout_elapsed() is True

    def test_is_recovery_timeout_not_elapsed_within_window(self) -> None:
        """_is_recovery_timeout_elapsed() returns False within the timeout window."""
        breaker = _make_breaker(recovery_timeout=9999.0)
        breaker._opened_at = time.monotonic()
        assert breaker._is_recovery_timeout_elapsed() is False

    # Helpers

    @staticmethod
    async def _succeed() -> str:
        return "ok"

    @staticmethod
    async def _fail() -> str:
        raise RuntimeError("Mem0 down")


# ---------------------------------------------------------------------------
# Memory Cache — Additional Edge Cases
# ---------------------------------------------------------------------------


class TestMemoryCacheEdgeCases:
    """Additional cache tests: eviction, expired entry removal from dict."""

    def test_expired_entry_is_removed_from_cache_dict(self) -> None:
        """Expired entries are deleted from _cache on read, not just skipped."""
        breaker = _make_breaker(cache_ttl=300.0)
        breaker.set_cached_memories("agent_x", ["mem x"])

        assert "agent_x" in breaker._cache

        with patch(
            "app.core.circuit_breaker.time.monotonic",
            return_value=time.monotonic() + 400,
        ):
            result = breaker.get_cached_memories("agent_x")

        assert result is None
        assert "agent_x" not in breaker._cache

    def test_cache_at_exactly_ttl_boundary_returns_none(self) -> None:
        """An entry at exactly TTL+epsilon is expired; strictly within TTL is valid."""
        breaker = _make_breaker(cache_ttl=10.0)
        base = time.monotonic()
        breaker._cache["key"] = __import__(
            "app.core.circuit_breaker", fromlist=["CacheEntry"]
        ).CacheEntry(memories=["m"], cached_at=base)

        # At exactly TTL: elapsed == 10.0, condition is elapsed > 10.0 → False → valid
        with patch("app.core.circuit_breaker.time.monotonic", return_value=base + 10.0):
            result = breaker.get_cached_memories("key")
        assert result == ["m"]  # still valid at exactly TTL

        # At TTL+epsilon: elapsed > 10.0 → expired
        with patch("app.core.circuit_breaker.time.monotonic", return_value=base + 10.1):
            result = breaker.get_cached_memories("key")
        assert result is None

    def test_get_status_excludes_expired_cache_entries(self) -> None:
        """get_status() cache_entries count excludes expired entries."""
        from app.core.circuit_breaker import CacheEntry

        breaker = _make_breaker(cache_ttl=300.0)
        base = time.monotonic()

        # 2 fresh entries, 1 already expired
        breaker._cache["fresh_1"] = CacheEntry(memories=["a"], cached_at=base)
        breaker._cache["fresh_2"] = CacheEntry(memories=["b"], cached_at=base)
        breaker._cache["expired"] = CacheEntry(memories=["c"], cached_at=base - 400)

        status = breaker.get_status()
        assert status["cache_entries"] == 2

    def test_set_overwrites_existing_cache_entry(self) -> None:
        """set_cached_memories on an existing key updates, not duplicates."""
        breaker = _make_breaker()
        breaker.set_cached_memories("agent_1", ["old"])
        breaker.set_cached_memories("agent_1", ["new"])

        result = breaker.get_cached_memories("agent_1")
        assert result == ["new"]
        assert len(breaker._cache) == 1


# ---------------------------------------------------------------------------
# Retry Queue — Additional Edge Cases
# ---------------------------------------------------------------------------


class TestRetryQueueEdgeCases:
    """Additional retry queue tests."""

    def test_enqueue_stores_correct_fields(self) -> None:
        """enqueue_retry stores user_id, agent_id, and messages correctly."""
        breaker = _make_breaker()
        msgs = [{"role": "user", "content": "hello"}]
        breaker.enqueue_retry(msgs, "user_abc", "agent_xyz")

        item = breaker._retry_queue[0]
        assert item.user_id == "user_abc"
        assert item.agent_id == "agent_xyz"
        assert item.messages == msgs
        assert item.created_at > 0

    def test_queue_at_max_size_drops_oldest_on_single_overflow(self) -> None:
        """Single overflow drops exactly the oldest item."""
        breaker = _make_breaker(max_retry_queue_size=2)
        breaker.enqueue_retry([{"role": "user", "content": "first"}], "u1", "a1")
        breaker.enqueue_retry([{"role": "user", "content": "second"}], "u2", "a2")
        breaker.enqueue_retry([{"role": "user", "content": "third"}], "u3", "a3")

        assert len(breaker._retry_queue) == 2
        agents = [item.agent_id for item in breaker._retry_queue]
        assert agents == ["a2", "a3"]

    @pytest.mark.asyncio
    async def test_drain_empty_queue_is_noop(self) -> None:
        """Draining an empty queue does not raise and makes no Mem0 calls."""
        breaker = _make_breaker()
        assert len(breaker._retry_queue) == 0

        with patch("mem0.MemoryClient") as mock_cls:
            await breaker.drain_retry_queue()
            mock_cls.assert_not_called()

        assert len(breaker._retry_queue) == 0

    @pytest.mark.asyncio
    async def test_drain_circuit_state_unchanged_after_partial_failure(self) -> None:
        """Circuit stays CLOSED after drain even when some items fail."""
        breaker = _make_breaker()
        breaker.enqueue_retry([{"role": "user", "content": "msg"}], "u1", "a1")
        breaker.enqueue_retry([{"role": "user", "content": "msg2"}], "u2", "a2")

        call_count = 0

        with patch("mem0.MemoryClient") as mock_cls:
            mock_client = MagicMock()

            def _add_side_effect(*args: object, **kwargs: object) -> None:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise Exception("Mem0 flaky")

            mock_client.add.side_effect = _add_side_effect
            mock_cls.return_value = mock_client

            await breaker.drain_retry_queue()

        assert len(breaker._retry_queue) == 0
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_drain_does_not_reopen_circuit_on_failure(self) -> None:
        """Failures during drain do NOT call record_failure() or change state."""
        breaker = _make_breaker(failure_threshold=1)
        breaker.enqueue_retry([{"role": "user", "content": "msg"}], "u1", "a1")

        with patch("mem0.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.add.side_effect = Exception("fail")
            mock_cls.return_value = mock_client

            await breaker.drain_retry_queue()

        # Despite failure_threshold=1, drain failures must NOT open the circuit
        assert breaker.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# MemoryService — delete_all, get_global, error paths, HALF_OPEN pass-through
# ---------------------------------------------------------------------------


class TestMemoryServiceAdditionalCoverage:
    """Tests for MemoryService operations not covered in existing tests."""

    @pytest.mark.asyncio
    async def test_delete_all_character_memories_open_returns_503(self) -> None:
        """delete_all_character_memories with circuit OPEN returns 503."""
        import app.core.circuit_breaker as cb_module

        original = cb_module._breaker
        breaker = _make_breaker()
        cb_module._breaker = breaker

        try:
            breaker.state = CircuitState.OPEN
            breaker._opened_at = time.monotonic()

            char = _make_char_mock()
            mock_db = _make_mock_db(char)

            from fastapi import HTTPException
            from app.services.memory_service import MemoryService

            service = MemoryService(mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await service.delete_all_character_memories(
                    character_id=char.id,
                    user_id=char.user_id,
                    mem0_user_id="user_550e8400",
                )
            assert exc_info.value.status_code == 503
            assert "temporarily unavailable" in exc_info.value.detail
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_get_global_memories_open_returns_503(self) -> None:
        """get_global_memories with circuit OPEN returns 503."""
        import app.core.circuit_breaker as cb_module

        original = cb_module._breaker
        breaker = _make_breaker()
        cb_module._breaker = breaker

        try:
            breaker.state = CircuitState.OPEN
            breaker._opened_at = time.monotonic()

            mock_db = MagicMock()
            from fastapi import HTTPException
            from app.services.memory_service import MemoryService

            service = MemoryService(mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await service.get_global_memories(mem0_user_id="user_abc")
            assert exc_info.value.status_code == 503
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_get_global_memories_closed_calls_mem0(self) -> None:
        """get_global_memories with circuit CLOSED calls Mem0 normally."""
        import app.core.circuit_breaker as cb_module

        original = cb_module._breaker
        cb_module._breaker = _make_breaker()

        try:
            mem0_results = [
                {"id": "g-1", "memory": "Global memory", "created_at": "2026-02-20T10:00:00Z"},
            ]

            with patch("app.services.memory_service.MemoryClient") as mock_cls:
                mock_client = MagicMock()
                mock_client.get_all.return_value = mem0_results
                mock_cls.return_value = mock_client

                from app.services.memory_service import MemoryService

                service = MemoryService(MagicMock())
                result = await service.get_global_memories(mem0_user_id="user_abc")

            assert len(result) == 1
            assert result[0].memory == "Global memory"
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_delete_character_memory_closed_succeeds(self) -> None:
        """delete_character_memory with circuit CLOSED calls mem0.delete."""
        import app.core.circuit_breaker as cb_module

        original = cb_module._breaker
        cb_module._breaker = _make_breaker()

        try:
            char = _make_char_mock()
            mock_db = _make_mock_db(char)

            with patch("app.services.memory_service.MemoryClient") as mock_cls:
                mock_client = MagicMock()
                mock_client.delete.return_value = None
                mock_cls.return_value = mock_client

                from app.services.memory_service import MemoryService

                service = MemoryService(mock_db)
                # Should not raise
                await service.delete_character_memory(
                    character_id=char.id,
                    user_id=char.user_id,
                    memory_id="mem-abc",
                )

            mock_client.delete.assert_called_once_with("mem-abc")
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_delete_character_memory_not_found_is_idempotent(self) -> None:
        """delete_character_memory returns None (no error) when mem0 says 404."""
        import app.core.circuit_breaker as cb_module

        original = cb_module._breaker
        cb_module._breaker = _make_breaker()

        try:
            char = _make_char_mock()
            mock_db = _make_mock_db(char)

            with patch("app.services.memory_service.MemoryClient") as mock_cls:
                mock_client = MagicMock()
                mock_client.delete.side_effect = Exception("memory not found in Mem0")
                mock_cls.return_value = mock_client

                from app.services.memory_service import MemoryService

                service = MemoryService(mock_db)
                # Should NOT raise — idempotent
                result = await service.delete_character_memory(
                    character_id=char.id,
                    user_id=char.user_id,
                    memory_id="mem-gone",
                )
                assert result is None
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_delete_character_memory_404_string_is_idempotent(self) -> None:
        """delete_character_memory treats '404' in exception message as success."""
        import app.core.circuit_breaker as cb_module

        original = cb_module._breaker
        cb_module._breaker = _make_breaker()

        try:
            char = _make_char_mock()
            mock_db = _make_mock_db(char)

            with patch("app.services.memory_service.MemoryClient") as mock_cls:
                mock_client = MagicMock()
                mock_client.delete.side_effect = Exception("HTTP 404 from Mem0")
                mock_cls.return_value = mock_client

                from app.services.memory_service import MemoryService

                service = MemoryService(mock_db)
                result = await service.delete_character_memory(
                    character_id=char.id,
                    user_id=char.user_id,
                    memory_id="mem-404",
                )
                assert result is None
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_delete_character_memory_other_error_returns_503(self) -> None:
        """delete_character_memory raises 503 for non-404 Mem0 exceptions."""
        import app.core.circuit_breaker as cb_module

        original = cb_module._breaker
        cb_module._breaker = _make_breaker()

        try:
            char = _make_char_mock()
            mock_db = _make_mock_db(char)

            with patch("app.services.memory_service.MemoryClient") as mock_cls:
                mock_client = MagicMock()
                mock_client.delete.side_effect = Exception("Connection timeout")
                mock_cls.return_value = mock_client

                from fastapi import HTTPException
                from app.services.memory_service import MemoryService

                service = MemoryService(mock_db)
                with pytest.raises(HTTPException) as exc_info:
                    await service.delete_character_memory(
                        character_id=char.id,
                        user_id=char.user_id,
                        memory_id="mem-fail",
                    )
                assert exc_info.value.status_code == 503
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_delete_all_character_memories_closed_succeeds(self) -> None:
        """delete_all_character_memories with circuit CLOSED calls mem0.delete_all."""
        import app.core.circuit_breaker as cb_module

        original = cb_module._breaker
        cb_module._breaker = _make_breaker()

        try:
            char = _make_char_mock()
            mock_db = _make_mock_db(char)

            with patch("app.services.memory_service.MemoryClient") as mock_cls:
                mock_client = MagicMock()
                mock_client.delete_all.return_value = None
                mock_cls.return_value = mock_client

                from app.services.memory_service import MemoryService

                service = MemoryService(mock_db)
                await service.delete_all_character_memories(
                    character_id=char.id,
                    user_id=char.user_id,
                    mem0_user_id="user_550e8400",
                )

            mock_client.delete_all.assert_called_once()
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_delete_all_character_memories_mem0_error_returns_503(self) -> None:
        """delete_all_character_memories returns 503 when Mem0 raises."""
        import app.core.circuit_breaker as cb_module

        original = cb_module._breaker
        cb_module._breaker = _make_breaker()

        try:
            char = _make_char_mock()
            mock_db = _make_mock_db(char)

            with patch("app.services.memory_service.MemoryClient") as mock_cls:
                mock_client = MagicMock()
                mock_client.delete_all.side_effect = Exception("Mem0 timeout")
                mock_cls.return_value = mock_client

                from fastapi import HTTPException
                from app.services.memory_service import MemoryService

                service = MemoryService(mock_db)
                with pytest.raises(HTTPException) as exc_info:
                    await service.delete_all_character_memories(
                        character_id=char.id,
                        user_id=char.user_id,
                        mem0_user_id="user_550e8400",
                    )
                assert exc_info.value.status_code == 503
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_get_character_memories_mem0_error_returns_503(self) -> None:
        """get_character_memories returns 503 when Mem0 raises a non-circuit error."""
        import app.core.circuit_breaker as cb_module

        original = cb_module._breaker
        cb_module._breaker = _make_breaker()

        try:
            char = _make_char_mock()
            mock_db = _make_mock_db(char)

            with patch("app.services.memory_service.MemoryClient") as mock_cls:
                mock_client = MagicMock()
                mock_client.get_all.side_effect = Exception("Mem0 server error")
                mock_cls.return_value = mock_client

                from fastapi import HTTPException
                from app.services.memory_service import MemoryService

                service = MemoryService(mock_db)
                with pytest.raises(HTTPException) as exc_info:
                    await service.get_character_memories(
                        character_id=char.id,
                        user_id=char.user_id,
                        mem0_user_id="user_550e8400",
                    )
                assert exc_info.value.status_code == 503
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_check_circuit_allows_half_open_through(self) -> None:
        """_check_circuit does NOT block calls when state is HALF_OPEN."""
        import app.core.circuit_breaker as cb_module

        original = cb_module._breaker
        breaker = _make_breaker()
        cb_module._breaker = breaker

        try:
            breaker.state = CircuitState.HALF_OPEN

            from app.services.memory_service import MemoryService

            service = MemoryService(MagicMock())
            # _check_circuit should not raise for HALF_OPEN
            service._check_circuit()  # no exception expected
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_character_not_found_raises_404(self) -> None:
        """get_character_memories raises 404 when character doesn't exist."""
        import app.core.circuit_breaker as cb_module

        original = cb_module._breaker
        cb_module._breaker = _make_breaker()

        try:
            mock_db = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None  # not found

            async def _mock_execute(*args: object, **kwargs: object) -> MagicMock:
                return mock_result

            mock_db.execute = _mock_execute

            from fastapi import HTTPException
            from app.services.memory_service import MemoryService

            service = MemoryService(mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await service.get_character_memories(
                    character_id=uuid.UUID("660e8400-e29b-41d4-a716-446655440001"),
                    user_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                    mem0_user_id="user_550e8400",
                )
            assert exc_info.value.status_code == 404
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_character_wrong_owner_raises_403(self) -> None:
        """get_character_memories raises 403 when character belongs to another user."""
        import app.core.circuit_breaker as cb_module

        original = cb_module._breaker
        cb_module._breaker = _make_breaker()

        try:
            char = _make_char_mock(
                user_id=uuid.UUID("AAAAAAAA-e29b-41d4-a716-446655440000"),
            )
            mock_db = _make_mock_db(char)

            from fastapi import HTTPException
            from app.services.memory_service import MemoryService

            service = MemoryService(mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await service.get_character_memories(
                    character_id=char.id,
                    user_id=uuid.UUID("BBBBBBBB-e29b-41d4-a716-446655440000"),  # different
                    mem0_user_id="user_other",
                )
            assert exc_info.value.status_code == 403
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_get_global_memories_mem0_error_returns_503(self) -> None:
        """get_global_memories returns 503 when Mem0 raises."""
        import app.core.circuit_breaker as cb_module

        original = cb_module._breaker
        cb_module._breaker = _make_breaker()

        try:
            with patch("app.services.memory_service.MemoryClient") as mock_cls:
                mock_client = MagicMock()
                mock_client.get_all.side_effect = Exception("Mem0 gone")
                mock_cls.return_value = mock_client

                from fastapi import HTTPException
                from app.services.memory_service import MemoryService

                service = MemoryService(MagicMock())
                with pytest.raises(HTTPException) as exc_info:
                    await service.get_global_memories(mem0_user_id="user_abc")
                assert exc_info.value.status_code == 503
        finally:
            cb_module._breaker = original


# ---------------------------------------------------------------------------
# ChatService — global search path (agent_id=None), failure fallback cache
# ---------------------------------------------------------------------------


class TestChatServiceGlobalSearchAndFallback:
    """Tests for _search_memories with agent_id=None (global) and cache fallback."""

    @pytest.mark.asyncio
    async def test_global_search_uses_global_cache_key(self) -> None:
        """_search_memories with agent_id=None caches under 'global:{user_id}'."""
        import app.core.circuit_breaker as cb_module

        original = cb_module._breaker
        breaker = _make_breaker()
        cb_module._breaker = breaker

        try:
            mock_db = MagicMock()

            with patch("app.services.chat_service.MemoryClient") as mock_cls:
                mock_client = MagicMock()
                mock_client.search.return_value = [{"memory": "Global pref"}]
                mock_cls.return_value = mock_client

                from app.services.chat_service import ChatService

                service = ChatService(mock_db)
                result = await service._search_memories(
                    query="test",
                    mem0_user_id="user_abc",
                    agent_id=None,  # global search
                )

            assert result == ["Global pref"]
            cached = breaker.get_cached_memories("global:user_abc")
            assert cached == ["Global pref"]
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_search_uses_cache_fallback_on_mem0_failure(self) -> None:
        """On Mem0 failure with pre-cached data, returns cached memories."""
        import app.core.circuit_breaker as cb_module

        original = cb_module._breaker
        breaker = _make_breaker(failure_threshold=99)  # won't open after 1 failure
        cb_module._breaker = breaker

        try:
            # Pre-populate cache
            breaker.set_cached_memories("luna_user_1", ["Cached fallback"])

            mock_db = MagicMock()

            with patch("app.services.chat_service.MemoryClient") as mock_cls:
                mock_client = MagicMock()
                mock_client.search.side_effect = Exception("Mem0 connection error")
                mock_cls.return_value = mock_client

                from app.services.chat_service import ChatService

                service = ChatService(mock_db)
                result = await service._search_memories(
                    query="test",
                    mem0_user_id="user_1",
                    agent_id="luna_user_1",
                )

            # Should return cached fallback despite Mem0 failure
            assert result == ["Cached fallback"]
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_failure_and_no_cache(self) -> None:
        """On Mem0 failure with no cache, returns empty list."""
        import app.core.circuit_breaker as cb_module

        original = cb_module._breaker
        breaker = _make_breaker(failure_threshold=99)
        cb_module._breaker = breaker

        try:
            mock_db = MagicMock()

            with patch("app.services.chat_service.MemoryClient") as mock_cls:
                mock_client = MagicMock()
                mock_client.search.side_effect = Exception("Mem0 down")
                mock_cls.return_value = mock_client

                from app.services.chat_service import ChatService

                service = ChatService(mock_db)
                result = await service._search_memories(
                    query="test",
                    mem0_user_id="user_1",
                    agent_id="luna_user_1",
                )

            assert result == []
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_global_search_open_circuit_with_cache(self) -> None:
        """Global search with circuit OPEN and cache hit returns cached memories."""
        import app.core.circuit_breaker as cb_module

        original = cb_module._breaker
        breaker = _make_breaker()
        cb_module._breaker = breaker

        try:
            breaker.set_cached_memories("global:user_abc", ["Global cached"])
            breaker.state = CircuitState.OPEN
            breaker._opened_at = time.monotonic()

            mock_db = MagicMock()

            with patch("app.services.chat_service.MemoryClient") as mock_cls:
                from app.services.chat_service import ChatService

                service = ChatService(mock_db)
                result = await service._search_memories(
                    query="test",
                    mem0_user_id="user_abc",
                    agent_id=None,
                )

            assert result == ["Global cached"]
            mock_cls.assert_not_called()
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_persist_exchange_circuit_opens_during_call_queues(self) -> None:
        """_persist_exchange queues add when CircuitOpenError raised during call."""
        import app.core.circuit_breaker as cb_module
        from app.core.circuit_breaker import CircuitOpenError

        original = cb_module._breaker
        breaker = _make_breaker()
        cb_module._breaker = breaker

        try:
            from app.services.chat_service import _persist_exchange

            with (
                patch("app.services.chat_service.AsyncSessionLocal") as mock_session_cls,
                patch("app.services.chat_service.MemoryClient") as mock_mem0_cls,
            ):
                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_session_cls.return_value = mock_session

                # Simulate circuit opening during the call_with_breaker
                with patch.object(
                    breaker,
                    "call_with_breaker",
                    side_effect=CircuitOpenError("opened mid-call"),
                ):
                    await _persist_exchange(
                        user_id=uuid.uuid4(),
                        conversation_id=uuid.uuid4(),
                        user_content="Hello",
                        user_media_url=None,
                        assistant_content="Hi!",
                        assistant_message_id=uuid.uuid4(),
                        action_metadata=None,
                        mem0_user_id="user_1",
                        mem0_agent_id="luna_user_1",
                    )

                # CircuitOpenError path → should enqueue
                assert len(breaker._retry_queue) == 1
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_persist_exchange_mem0_error_queues(self) -> None:
        """_persist_exchange queues add when mem0.add raises a non-circuit exception."""
        import app.core.circuit_breaker as cb_module

        original = cb_module._breaker
        breaker = _make_breaker()
        cb_module._breaker = breaker

        try:
            from app.services.chat_service import _persist_exchange

            with (
                patch("app.services.chat_service.AsyncSessionLocal") as mock_session_cls,
                patch("app.services.chat_service.MemoryClient") as mock_mem0_cls,
            ):
                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_session_cls.return_value = mock_session

                mock_client = MagicMock()
                mock_client.add.side_effect = Exception("Mem0 error during add")
                mock_mem0_cls.return_value = mock_client

                await _persist_exchange(
                    user_id=uuid.uuid4(),
                    conversation_id=uuid.uuid4(),
                    user_content="Hello",
                    user_media_url=None,
                    assistant_content="Hi!",
                    assistant_message_id=uuid.uuid4(),
                    action_metadata=None,
                    mem0_user_id="user_1",
                    mem0_agent_id="luna_user_1",
                )

                # Generic exception path → should enqueue for retry
                assert len(breaker._retry_queue) == 1
        finally:
            cb_module._breaker = original


# ---------------------------------------------------------------------------
# Config — circuit breaker config fields
# ---------------------------------------------------------------------------


class TestCircuitBreakerConfig:
    """Tests for the four new config fields."""

    def test_config_has_failure_threshold(self) -> None:
        """Settings has mem0_circuit_failure_threshold with sensible default."""
        from app.config import settings

        assert hasattr(settings, "mem0_circuit_failure_threshold")
        assert isinstance(settings.mem0_circuit_failure_threshold, int)
        assert settings.mem0_circuit_failure_threshold >= 1

    def test_config_has_recovery_timeout(self) -> None:
        """Settings has mem0_circuit_recovery_timeout with sensible default."""
        from app.config import settings

        assert hasattr(settings, "mem0_circuit_recovery_timeout")
        assert isinstance(settings.mem0_circuit_recovery_timeout, float)
        assert settings.mem0_circuit_recovery_timeout >= 0

    def test_config_has_cache_ttl(self) -> None:
        """Settings has mem0_cache_ttl with sensible default."""
        from app.config import settings

        assert hasattr(settings, "mem0_cache_ttl")
        assert isinstance(settings.mem0_cache_ttl, float)
        assert settings.mem0_cache_ttl > 0

    def test_config_has_retry_queue_max_size(self) -> None:
        """Settings has mem0_retry_queue_max_size with sensible default."""
        from app.config import settings

        assert hasattr(settings, "mem0_retry_queue_max_size")
        assert isinstance(settings.mem0_retry_queue_max_size, int)
        assert settings.mem0_retry_queue_max_size >= 1

    def test_config_defaults_match_spec(self) -> None:
        """Default config values match the spec: threshold=3, timeout=60, ttl=300, queue=100."""
        from app.config import settings

        # Per spec Section 4 / Table of new config fields
        assert settings.mem0_circuit_failure_threshold == 3
        assert settings.mem0_circuit_recovery_timeout == 60.0
        assert settings.mem0_cache_ttl == 300.0
        assert settings.mem0_retry_queue_max_size == 100


# ---------------------------------------------------------------------------
# Health Schemas — CircuitBreakerStatus and CircuitBreakerReport
# ---------------------------------------------------------------------------


class TestHealthSchemas:
    """Tests for CircuitBreakerStatus and CircuitBreakerReport Pydantic models."""

    def test_circuit_breaker_status_valid_closed(self) -> None:
        """CircuitBreakerStatus accepts a closed-state dict."""
        from app.schemas.health import CircuitBreakerStatus

        status = CircuitBreakerStatus(
            state="closed",
            failure_count=0,
            last_failure_at=None,
            last_success_at=None,
            retry_queue_size=0,
            cache_entries=0,
        )
        assert status.state == "closed"
        assert status.failure_count == 0
        assert status.retry_queue_size == 0
        assert status.cache_entries == 0

    def test_circuit_breaker_status_valid_open(self) -> None:
        """CircuitBreakerStatus accepts an open-state dict with timestamps."""
        from app.schemas.health import CircuitBreakerStatus

        status = CircuitBreakerStatus(
            state="open",
            failure_count=3,
            last_failure_at="2026-03-13T10:00:00+00:00",
            last_success_at="2026-03-13T09:00:00+00:00",
            retry_queue_size=5,
            cache_entries=2,
        )
        assert status.state == "open"
        assert status.failure_count == 3
        assert status.retry_queue_size == 5

    def test_circuit_breaker_status_half_open(self) -> None:
        """CircuitBreakerStatus accepts half_open state."""
        from app.schemas.health import CircuitBreakerStatus

        status = CircuitBreakerStatus(
            state="half_open",
            failure_count=0,
            retry_queue_size=0,
            cache_entries=0,
        )
        assert status.state == "half_open"

    def test_circuit_breaker_report_contains_mem0(self) -> None:
        """CircuitBreakerReport wraps a mem0 CircuitBreakerStatus."""
        from app.schemas.health import CircuitBreakerReport, CircuitBreakerStatus

        cb_status = CircuitBreakerStatus(
            state="closed",
            failure_count=0,
            retry_queue_size=0,
            cache_entries=0,
        )
        report = CircuitBreakerReport(mem0=cb_status)
        assert report.mem0.state == "closed"

    def test_health_response_circuit_breaker_is_optional(self) -> None:
        """HealthResponse without circuit_breaker field defaults to None."""
        from app.schemas.health import HealthResponse

        resp = HealthResponse(status="ok", version="1.0.0")
        assert resp.circuit_breaker is None

    def test_get_status_result_populates_circuit_breaker_status(self) -> None:
        """get_status() dict can be used directly to construct CircuitBreakerStatus."""
        from app.schemas.health import CircuitBreakerStatus

        breaker = _make_breaker()
        status_dict = breaker.get_status()
        cb = CircuitBreakerStatus(**status_dict)
        assert cb.state == "closed"
        assert cb.failure_count == 0
        assert cb.retry_queue_size == 0
        assert cb.cache_entries == 0


# ---------------------------------------------------------------------------
# MemoryService — CircuitOpenError from call_with_breaker (HALF_OPEN race path)
# ---------------------------------------------------------------------------


class TestMemoryServiceCircuitOpenErrorFromBreaker:
    """Tests for the CircuitOpenError paths inside memory service methods.

    These are triggered when _check_circuit() passes (circuit CLOSED/HALF_OPEN)
    but call_with_breaker raises CircuitOpenError (race: circuit opened mid-call).
    """

    @pytest.mark.asyncio
    async def test_get_character_memories_circuit_open_error_from_breaker_returns_503(
        self,
    ) -> None:
        """get_character_memories: CircuitOpenError from call_with_breaker → 503."""
        import app.core.circuit_breaker as cb_module
        from app.core.circuit_breaker import CircuitOpenError

        original = cb_module._breaker
        breaker = _make_breaker()
        cb_module._breaker = breaker

        try:
            char = _make_char_mock()
            mock_db = _make_mock_db(char)

            with patch.object(
                breaker, "call_with_breaker", side_effect=CircuitOpenError("race condition"),
            ):
                from fastapi import HTTPException
                from app.services.memory_service import MemoryService

                service = MemoryService(mock_db)
                with pytest.raises(HTTPException) as exc_info:
                    await service.get_character_memories(
                        character_id=char.id,
                        user_id=char.user_id,
                        mem0_user_id="user_550e8400",
                    )
                assert exc_info.value.status_code == 503
                assert "temporarily unavailable" in exc_info.value.detail
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_delete_character_memory_circuit_open_error_from_breaker_returns_503(
        self,
    ) -> None:
        """delete_character_memory: CircuitOpenError from call_with_breaker → 503."""
        import app.core.circuit_breaker as cb_module
        from app.core.circuit_breaker import CircuitOpenError

        original = cb_module._breaker
        breaker = _make_breaker()
        cb_module._breaker = breaker

        try:
            char = _make_char_mock()
            mock_db = _make_mock_db(char)

            with patch.object(
                breaker, "call_with_breaker", side_effect=CircuitOpenError("race condition"),
            ):
                from fastapi import HTTPException
                from app.services.memory_service import MemoryService

                service = MemoryService(mock_db)
                with pytest.raises(HTTPException) as exc_info:
                    await service.delete_character_memory(
                        character_id=char.id,
                        user_id=char.user_id,
                        memory_id="mem-race",
                    )
                assert exc_info.value.status_code == 503
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_delete_all_circuit_open_error_from_breaker_returns_503(self) -> None:
        """delete_all_character_memories: CircuitOpenError from call_with_breaker → 503."""
        import app.core.circuit_breaker as cb_module
        from app.core.circuit_breaker import CircuitOpenError

        original = cb_module._breaker
        breaker = _make_breaker()
        cb_module._breaker = breaker

        try:
            char = _make_char_mock()
            mock_db = _make_mock_db(char)

            with patch.object(
                breaker, "call_with_breaker", side_effect=CircuitOpenError("race"),
            ):
                from fastapi import HTTPException
                from app.services.memory_service import MemoryService

                service = MemoryService(mock_db)
                with pytest.raises(HTTPException) as exc_info:
                    await service.delete_all_character_memories(
                        character_id=char.id,
                        user_id=char.user_id,
                        mem0_user_id="user_550e8400",
                    )
                assert exc_info.value.status_code == 503
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_get_global_memories_circuit_open_error_from_breaker_returns_503(
        self,
    ) -> None:
        """get_global_memories: CircuitOpenError from call_with_breaker → 503."""
        import app.core.circuit_breaker as cb_module
        from app.core.circuit_breaker import CircuitOpenError

        original = cb_module._breaker
        breaker = _make_breaker()
        cb_module._breaker = breaker

        try:
            with patch.object(
                breaker, "call_with_breaker", side_effect=CircuitOpenError("race"),
            ):
                from fastapi import HTTPException
                from app.services.memory_service import MemoryService

                service = MemoryService(MagicMock())
                with pytest.raises(HTTPException) as exc_info:
                    await service.get_global_memories(mem0_user_id="user_abc")
                assert exc_info.value.status_code == 503
        finally:
            cb_module._breaker = original
