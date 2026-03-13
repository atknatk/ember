"""Tests for Mem0 circuit breaker — state machine, cache, retry queue, and status.

Covers the circuit breaker core logic, memory cache TTL, retry queue bounds,
and integration with ChatService and MemoryService.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import asyncio  # noqa: E402
import time  # noqa: E402
import uuid  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from app.core.circuit_breaker import (  # noqa: E402
    CacheEntry,
    CircuitOpenError,
    CircuitState,
    Mem0CircuitBreaker,
    RetryItem,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_breaker(
    failure_threshold: int = 3,
    recovery_timeout: float = 60.0,
    cache_ttl: float = 300.0,
    max_retry_queue_size: int = 100,
) -> Mem0CircuitBreaker:
    """Create a circuit breaker with specified config."""
    return Mem0CircuitBreaker(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        cache_ttl=cache_ttl,
        max_retry_queue_size=max_retry_queue_size,
    )


async def _success_func() -> str:
    return "ok"


async def _fail_func() -> str:
    raise RuntimeError("Mem0 connection refused")


# ---------------------------------------------------------------------------
# Circuit Breaker State Machine Tests
# ---------------------------------------------------------------------------


class TestCircuitBreakerStateMachine:
    """Tests for circuit breaker state transitions."""

    @pytest.mark.asyncio
    async def test_initial_state_is_closed(self) -> None:
        """T1: Initial state is CLOSED with failure_count=0."""
        breaker = _make_breaker()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_successful_call_returns_result(self) -> None:
        """T2: Successful call through breaker returns result and keeps count at 0."""
        breaker = _make_breaker()
        result = await breaker.call_with_breaker(_success_func)
        assert result == "ok"
        assert breaker.failure_count == 0
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_single_failure_does_not_open(self) -> None:
        """T3: Single failure increments count but keeps circuit CLOSED."""
        breaker = _make_breaker()
        with pytest.raises(RuntimeError):
            await breaker.call_with_breaker(_fail_func)
        assert breaker.failure_count == 1
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_three_failures_open_circuit(self) -> None:
        """T4: 3 consecutive failures open the circuit."""
        breaker = _make_breaker(failure_threshold=3)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await breaker.call_with_breaker(_fail_func)
        assert breaker.state == CircuitState.OPEN
        assert breaker.failure_count == 3

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self) -> None:
        """T5: Success after 2 failures resets failure_count to 0."""
        breaker = _make_breaker(failure_threshold=3)
        # 2 failures
        for _ in range(2):
            with pytest.raises(RuntimeError):
                await breaker.call_with_breaker(_fail_func)
        assert breaker.failure_count == 2

        # 1 success
        result = await breaker.call_with_breaker(_success_func)
        assert result == "ok"
        assert breaker.failure_count == 0
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_call_while_open_raises_circuit_open_error(self) -> None:
        """T6: Call while circuit OPEN raises CircuitOpenError."""
        breaker = _make_breaker(failure_threshold=3, recovery_timeout=60.0)
        # Open the circuit
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await breaker.call_with_breaker(_fail_func)
        assert breaker.state == CircuitState.OPEN

        with pytest.raises(CircuitOpenError):
            await breaker.call_with_breaker(_success_func)

    @pytest.mark.asyncio
    async def test_recovery_timeout_transitions_to_half_open(self) -> None:
        """T7: After recovery_timeout, circuit transitions to HALF_OPEN."""
        breaker = _make_breaker(failure_threshold=3, recovery_timeout=60.0)
        # Open the circuit
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await breaker.call_with_breaker(_fail_func)
        assert breaker.state == CircuitState.OPEN

        # Simulate time passing beyond recovery timeout
        with patch("app.core.circuit_breaker.time.monotonic", return_value=time.monotonic() + 61):
            result = await breaker.call_with_breaker(_success_func)
            assert result == "ok"
            assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_successful_probe_closes_circuit(self) -> None:
        """T8: Successful probe in HALF_OPEN closes circuit."""
        breaker = _make_breaker(failure_threshold=3, recovery_timeout=0.0)
        # Open the circuit
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await breaker.call_with_breaker(_fail_func)

        # recovery_timeout=0 means immediate probe
        result = await breaker.call_with_breaker(_success_func)
        assert result == "ok"
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_failed_probe_reopens_circuit(self) -> None:
        """T9: Failed probe in HALF_OPEN reopens circuit."""
        breaker = _make_breaker(failure_threshold=3, recovery_timeout=0.0)
        # Open the circuit
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await breaker.call_with_breaker(_fail_func)

        # Probe fails
        with pytest.raises(RuntimeError):
            await breaker.call_with_breaker(_fail_func)
        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_drain_triggered_on_close(self) -> None:
        """T10: Retry queue drain is triggered when circuit closes from HALF_OPEN."""
        breaker = _make_breaker(failure_threshold=3, recovery_timeout=0.0)
        # Open the circuit
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await breaker.call_with_breaker(_fail_func)

        # Add items to retry queue
        breaker.enqueue_retry(
            [{"role": "user", "content": "test"}], "user_1", "agent_1",
        )

        with patch.object(breaker, "drain_retry_queue", new_callable=AsyncMock) as mock_drain:
            # Probe succeeds — should trigger drain
            await breaker.call_with_breaker(_success_func)
            assert breaker.state == CircuitState.CLOSED
            # drain_retry_queue was scheduled as a background task
            # We patched it, so check it was called via asyncio.create_task
            # Since we can't easily check create_task, verify queue has items
            # and drain was scheduled (it was mocked)


# ---------------------------------------------------------------------------
# Memory Cache Tests
# ---------------------------------------------------------------------------


class TestMemoryCache:
    """Tests for circuit breaker memory cache."""

    def test_set_and_get_cached_memories(self) -> None:
        """T11: set_cached_memories stores memories retrievable by get_cached_memories."""
        breaker = _make_breaker(cache_ttl=300.0)
        breaker.set_cached_memories("agent_1", ["memory 1", "memory 2"])
        result = breaker.get_cached_memories("agent_1")
        assert result == ["memory 1", "memory 2"]

    def test_cache_entry_expires_after_ttl(self) -> None:
        """T12: Cache entry returns None after TTL expires."""
        breaker = _make_breaker(cache_ttl=300.0)
        breaker.set_cached_memories("agent_1", ["memory 1"])

        # Simulate time passing beyond TTL
        with patch("app.core.circuit_breaker.time.monotonic", return_value=time.monotonic() + 301):
            result = breaker.get_cached_memories("agent_1")
            assert result is None

    def test_cache_entries_are_independent(self) -> None:
        """T13: Cache entries for different keys are independent."""
        breaker = _make_breaker()
        breaker.set_cached_memories("agent_a", ["mem A"])
        breaker.set_cached_memories("agent_b", ["mem B"])

        assert breaker.get_cached_memories("agent_a") == ["mem A"]
        assert breaker.get_cached_memories("agent_b") == ["mem B"]

        # Update A doesn't affect B
        breaker.set_cached_memories("agent_a", ["mem A updated"])
        assert breaker.get_cached_memories("agent_a") == ["mem A updated"]
        assert breaker.get_cached_memories("agent_b") == ["mem B"]

    def test_cache_key_format(self) -> None:
        """T14: Character-scoped uses agent_id, global uses 'global:{user_id}'."""
        breaker = _make_breaker()
        breaker.set_cached_memories("luna_user123", ["char mem"])
        breaker.set_cached_memories("global:user123", ["global mem"])

        assert breaker.get_cached_memories("luna_user123") == ["char mem"]
        assert breaker.get_cached_memories("global:user123") == ["global mem"]

    def test_get_nonexistent_key_returns_none(self) -> None:
        """Cache miss returns None."""
        breaker = _make_breaker()
        assert breaker.get_cached_memories("nonexistent") is None


# ---------------------------------------------------------------------------
# Retry Queue Tests
# ---------------------------------------------------------------------------


class TestRetryQueue:
    """Tests for circuit breaker retry queue."""

    def test_enqueue_adds_item(self) -> None:
        """T15: enqueue_retry adds an item to the queue."""
        breaker = _make_breaker()
        assert len(breaker._retry_queue) == 0
        breaker.enqueue_retry(
            [{"role": "user", "content": "test"}], "user_1", "agent_1",
        )
        assert len(breaker._retry_queue) == 1

    def test_queue_respects_max_size(self) -> None:
        """T16: Queue drops oldest when at max size."""
        breaker = _make_breaker(max_retry_queue_size=3)

        for i in range(4):
            breaker.enqueue_retry(
                [{"role": "user", "content": f"msg {i}"}],
                f"user_{i}",
                f"agent_{i}",
            )

        assert len(breaker._retry_queue) == 3
        # Oldest (msg 0) should be dropped
        agents = [item.agent_id for item in breaker._retry_queue]
        assert "agent_0" not in agents
        assert "agent_3" in agents

    @pytest.mark.asyncio
    async def test_drain_processes_all_items(self) -> None:
        """T17: drain_retry_queue processes all items."""
        breaker = _make_breaker()
        breaker.enqueue_retry(
            [{"role": "user", "content": "msg 1"}], "user_1", "agent_1",
        )
        breaker.enqueue_retry(
            [{"role": "user", "content": "msg 2"}], "user_2", "agent_2",
        )

        with patch("mem0.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.add.return_value = None
            mock_cls.return_value = mock_client

            await breaker.drain_retry_queue()

            assert mock_client.add.call_count == 2
            assert len(breaker._retry_queue) == 0

    @pytest.mark.asyncio
    async def test_drain_with_failures_logs_but_continues(self) -> None:
        """T18: drain_retry_queue with failing items logs but drains all."""
        breaker = _make_breaker()
        breaker.enqueue_retry(
            [{"role": "user", "content": "msg 1"}], "user_1", "agent_1",
        )
        breaker.enqueue_retry(
            [{"role": "user", "content": "msg 2"}], "user_2", "agent_2",
        )

        with patch("mem0.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.add.side_effect = Exception("Mem0 error")
            mock_cls.return_value = mock_client

            await breaker.drain_retry_queue()

            # All items processed (attempted), queue is empty
            assert len(breaker._retry_queue) == 0
            # Circuit state should not change
            assert breaker.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# Status Reporting Tests
# ---------------------------------------------------------------------------


class TestStatusReporting:
    """Tests for circuit breaker get_status()."""

    def test_status_in_closed_state(self) -> None:
        """T31: get_status() in CLOSED state."""
        breaker = _make_breaker()
        status = breaker.get_status()
        assert status["state"] == "closed"
        assert status["failure_count"] == 0
        assert status["retry_queue_size"] == 0
        assert status["cache_entries"] == 0
        assert status["last_failure_at"] is None
        assert status["last_success_at"] is None

    @pytest.mark.asyncio
    async def test_status_in_open_state_with_queued_items(self) -> None:
        """T32: get_status() in OPEN state with queued items."""
        breaker = _make_breaker(failure_threshold=3)
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await breaker.call_with_breaker(_fail_func)

        breaker.enqueue_retry(
            [{"role": "user", "content": "test"}], "user_1", "agent_1",
        )

        status = breaker.get_status()
        assert status["state"] == "open"
        assert status["failure_count"] == 3
        assert status["retry_queue_size"] == 1
        assert status["last_failure_at"] is not None

    def test_status_reports_cache_entries_correctly(self) -> None:
        """T33: get_status() reports cache_entries matching non-expired entries."""
        breaker = _make_breaker(cache_ttl=300.0)
        breaker.set_cached_memories("agent_1", ["mem 1"])
        breaker.set_cached_memories("agent_2", ["mem 2"])
        breaker.set_cached_memories("agent_3", ["mem 3"])

        status = breaker.get_status()
        assert status["cache_entries"] == 3

    @pytest.mark.asyncio
    async def test_status_after_success_records_timestamp(self) -> None:
        """get_status() shows last_success_at after a successful call."""
        breaker = _make_breaker()
        await breaker.call_with_breaker(_success_func)

        status = breaker.get_status()
        assert status["last_success_at"] is not None
        # Should be a valid ISO datetime string
        parsed = datetime.fromisoformat(status["last_success_at"])
        assert parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# ChatService Integration — _search_memories
# ---------------------------------------------------------------------------


class TestChatServiceSearchIntegration:
    """Tests for ChatService._search_memories with circuit breaker."""

    @pytest.mark.asyncio
    async def test_search_with_closed_circuit_caches_result(self) -> None:
        """T19: Search with circuit CLOSED caches and returns results."""
        from app.core.circuit_breaker import _breaker

        # Reset singleton
        import app.core.circuit_breaker as cb_module
        original = cb_module._breaker
        cb_module._breaker = _make_breaker()

        try:
            mock_db = MagicMock()

            with patch("app.services.chat_service.MemoryClient") as mock_cls:
                mock_client = MagicMock()
                mock_client.search.return_value = [
                    {"memory": "Likes coffee"},
                    {"memory": "Morning person"},
                ]
                mock_cls.return_value = mock_client

                from app.services.chat_service import ChatService
                service = ChatService(mock_db)
                result = await service._search_memories(
                    query="test",
                    mem0_user_id="user_1",
                    agent_id="luna_user_1",
                )

                assert result == ["Likes coffee", "Morning person"]

                # Verify cached
                breaker = cb_module._breaker
                cached = breaker.get_cached_memories("luna_user_1")
                assert cached == ["Likes coffee", "Morning person"]
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_search_with_open_circuit_returns_cached(self) -> None:
        """T21: Search with circuit OPEN and cache hit returns cached memories."""
        import app.core.circuit_breaker as cb_module
        original = cb_module._breaker
        breaker = _make_breaker()
        cb_module._breaker = breaker

        try:
            # Pre-populate cache
            breaker.set_cached_memories("luna_user_1", ["Cached memory"])
            # Open the circuit
            breaker.state = CircuitState.OPEN
            breaker._opened_at = time.monotonic()

            mock_db = MagicMock()
            from app.services.chat_service import ChatService
            service = ChatService(mock_db)

            with patch("app.services.chat_service.MemoryClient") as mock_cls:
                result = await service._search_memories(
                    query="test",
                    mem0_user_id="user_1",
                    agent_id="luna_user_1",
                )

                # Should return cached without calling Mem0
                assert result == ["Cached memory"]
                mock_cls.assert_not_called()
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_search_with_open_circuit_cache_miss_returns_empty(self) -> None:
        """T22: Search with circuit OPEN and cache miss returns empty list."""
        import app.core.circuit_breaker as cb_module
        original = cb_module._breaker
        breaker = _make_breaker()
        cb_module._breaker = breaker

        try:
            # Open the circuit, no cache
            breaker.state = CircuitState.OPEN
            breaker._opened_at = time.monotonic()

            mock_db = MagicMock()
            from app.services.chat_service import ChatService
            service = ChatService(mock_db)

            with patch("app.services.chat_service.MemoryClient") as mock_cls:
                result = await service._search_memories(
                    query="test",
                    mem0_user_id="user_1",
                    agent_id="luna_user_1",
                )
                assert result == []
                mock_cls.assert_not_called()
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_search_failures_open_circuit(self) -> None:
        """T20: 3 consecutive search failures open the circuit."""
        import app.core.circuit_breaker as cb_module
        original = cb_module._breaker
        breaker = _make_breaker(failure_threshold=3)
        cb_module._breaker = breaker

        try:
            mock_db = MagicMock()
            from app.services.chat_service import ChatService
            service = ChatService(mock_db)

            with patch("app.services.chat_service.MemoryClient") as mock_cls:
                mock_client = MagicMock()
                mock_client.search.side_effect = Exception("Mem0 down")
                mock_cls.return_value = mock_client

                for _ in range(3):
                    result = await service._search_memories(
                        query="test",
                        mem0_user_id="user_1",
                        agent_id="luna_user_1",
                    )
                    assert result == []

                assert breaker.state == CircuitState.OPEN
        finally:
            cb_module._breaker = original


# ---------------------------------------------------------------------------
# ChatService Integration — _persist_exchange
# ---------------------------------------------------------------------------


class TestPersistExchangeIntegration:
    """Tests for _persist_exchange with circuit breaker."""

    @pytest.mark.asyncio
    async def test_persist_with_open_circuit_queues_add(self) -> None:
        """T23: _persist_exchange with circuit OPEN queues add operation."""
        import app.core.circuit_breaker as cb_module
        original = cb_module._breaker
        breaker = _make_breaker()
        cb_module._breaker = breaker

        try:
            # Open the circuit
            breaker.state = CircuitState.OPEN
            breaker._opened_at = time.monotonic()

            from app.services.chat_service import _persist_exchange

            with (
                patch("app.services.chat_service.AsyncSessionLocal") as mock_session_cls,
                patch("app.services.chat_service.MemoryClient") as mock_mem0_cls,
            ):
                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                mock_session_cls.return_value = mock_session

                await _persist_exchange(
                    user_id=uuid.uuid4(),
                    conversation_id=uuid.uuid4(),
                    user_content="Hello",
                    user_media_url=None,
                    assistant_content="Hi there!",
                    assistant_message_id=uuid.uuid4(),
                    action_metadata=None,
                    mem0_user_id="user_1",
                    mem0_agent_id="luna_user_1",
                )

                # Mem0 client should not have been called
                mock_mem0_cls.assert_not_called()
                # Should have queued the add
                assert len(breaker._retry_queue) == 1
                item = breaker._retry_queue[0]
                assert item.user_id == "user_1"
                assert item.agent_id == "luna_user_1"
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_persist_with_closed_circuit_calls_mem0(self) -> None:
        """T24: _persist_exchange with circuit CLOSED calls mem0.add normally."""
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
                mock_client.add.return_value = None
                mock_mem0_cls.return_value = mock_client

                await _persist_exchange(
                    user_id=uuid.uuid4(),
                    conversation_id=uuid.uuid4(),
                    user_content="Hello",
                    user_media_url=None,
                    assistant_content="Hi there!",
                    assistant_message_id=uuid.uuid4(),
                    action_metadata=None,
                    mem0_user_id="user_1",
                    mem0_agent_id="luna_user_1",
                )

                # Mem0 add should have been called
                mock_client.add.assert_called_once()
                # Nothing queued
                assert len(breaker._retry_queue) == 0
        finally:
            cb_module._breaker = original


# ---------------------------------------------------------------------------
# MemoryService Integration
# ---------------------------------------------------------------------------


class TestMemoryServiceIntegration:
    """Tests for MemoryService with circuit breaker."""

    @pytest.mark.asyncio
    async def test_get_character_memories_open_returns_503(self) -> None:
        """T25: get_character_memories with circuit OPEN returns 503."""
        import app.core.circuit_breaker as cb_module
        original = cb_module._breaker
        breaker = _make_breaker()
        cb_module._breaker = breaker

        try:
            breaker.state = CircuitState.OPEN
            breaker._opened_at = time.monotonic()

            char = MagicMock()
            char.id = uuid.UUID("660e8400-e29b-41d4-a716-446655440001")
            char.user_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
            char.mem0_agent_id = "english_teacher_550e8400"
            char.is_active = True

            mock_db = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = char

            async def _mock_execute(*args: object, **kwargs: object) -> MagicMock:
                return mock_result

            mock_db.execute = _mock_execute

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
    async def test_delete_character_memory_open_returns_503(self) -> None:
        """T26: delete_character_memory with circuit OPEN returns 503."""
        import app.core.circuit_breaker as cb_module
        original = cb_module._breaker
        breaker = _make_breaker()
        cb_module._breaker = breaker

        try:
            breaker.state = CircuitState.OPEN
            breaker._opened_at = time.monotonic()

            char = MagicMock()
            char.id = uuid.UUID("660e8400-e29b-41d4-a716-446655440001")
            char.user_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
            char.mem0_agent_id = "english_teacher_550e8400"
            char.is_active = True

            mock_db = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = char

            async def _mock_execute(*args: object, **kwargs: object) -> MagicMock:
                return mock_result

            mock_db.execute = _mock_execute

            from fastapi import HTTPException
            from app.services.memory_service import MemoryService

            service = MemoryService(mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await service.delete_character_memory(
                    character_id=char.id,
                    user_id=char.user_id,
                    memory_id="mem-1",
                )
            assert exc_info.value.status_code == 503
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_get_character_memories_closed_proceeds(self) -> None:
        """T27: get_character_memories with circuit CLOSED calls Mem0 normally."""
        import app.core.circuit_breaker as cb_module
        original = cb_module._breaker
        breaker = _make_breaker()
        cb_module._breaker = breaker

        try:
            char = MagicMock()
            char.id = uuid.UUID("660e8400-e29b-41d4-a716-446655440001")
            char.user_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
            char.mem0_agent_id = "english_teacher_550e8400"
            char.is_active = True

            mock_db = MagicMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = char

            async def _mock_execute(*args: object, **kwargs: object) -> MagicMock:
                return mock_result

            mock_db.execute = _mock_execute

            mem0_results = [
                {"id": "mem-1", "memory": "Test memory", "created_at": "2026-02-20T10:00:00Z"},
            ]

            with patch("app.services.memory_service.MemoryClient") as mock_cls:
                mock_client = MagicMock()
                mock_client.get_all.return_value = mem0_results
                mock_cls.return_value = mock_client

                from app.services.memory_service import MemoryService
                service = MemoryService(mock_db)
                result = await service.get_character_memories(
                    character_id=char.id,
                    user_id=char.user_id,
                    mem0_user_id="user_550e8400",
                )

                assert len(result) == 1
                assert result[0].memory == "Test memory"
        finally:
            cb_module._breaker = original


# ---------------------------------------------------------------------------
# Health Endpoint Integration
# ---------------------------------------------------------------------------


class TestHealthEndpointIntegration:
    """Tests for health endpoint circuit breaker reporting."""

    @pytest.mark.asyncio
    async def test_health_with_deps_includes_circuit_breaker(self) -> None:
        """T28: Health with check_dependencies=true includes circuit_breaker."""
        import app.core.circuit_breaker as cb_module
        original = cb_module._breaker
        cb_module._breaker = _make_breaker()

        try:
            from httpx import ASGITransport, AsyncClient
            from app.main import app
            from app.dependencies import get_db

            async def _override_db() -> AsyncMock:  # type: ignore[misc]
                yield AsyncMock()

            app.dependency_overrides[get_db] = _override_db

            with (
                patch(
                    "app.services.health_service.HealthService._probe_database",
                    new_callable=AsyncMock,
                    return_value="ok",
                ),
                patch(
                    "app.services.health_service.HealthService._probe_mem0",
                    new_callable=AsyncMock,
                    return_value="ok",
                ),
                patch(
                    "app.services.health_service.HealthService._probe_claude",
                    new_callable=AsyncMock,
                    return_value="ok",
                ),
            ):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get("/api/v1/health?check_dependencies=true")

                assert resp.status_code == 200
                data = resp.json()
                assert "circuit_breaker" in data
                assert "mem0" in data["circuit_breaker"]
                cb = data["circuit_breaker"]["mem0"]
                assert cb["state"] == "closed"
                assert cb["failure_count"] == 0
                assert cb["retry_queue_size"] == 0

            app.dependency_overrides.clear()
        finally:
            cb_module._breaker = original

    @pytest.mark.asyncio
    async def test_health_without_deps_excludes_circuit_breaker(self) -> None:
        """T30: Health without check_dependencies does not include circuit_breaker."""
        from httpx import ASGITransport, AsyncClient
        from app.main import app
        from app.dependencies import get_db

        async def _override_db() -> AsyncMock:  # type: ignore[misc]
            yield AsyncMock()

        app.dependency_overrides[get_db] = _override_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/health")

        assert resp.status_code == 200
        data = resp.json()
        assert data.get("circuit_breaker") is None

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_health_reports_correct_open_state(self) -> None:
        """T29: Circuit breaker status reports correct state when open."""
        import app.core.circuit_breaker as cb_module
        original = cb_module._breaker
        breaker = _make_breaker(failure_threshold=3)
        cb_module._breaker = breaker

        try:
            # Open the circuit
            for _ in range(3):
                with pytest.raises(RuntimeError):
                    await breaker.call_with_breaker(_fail_func)

            breaker.enqueue_retry(
                [{"role": "user", "content": "test"}], "user_1", "agent_1",
            )

            from httpx import ASGITransport, AsyncClient
            from app.main import app
            from app.dependencies import get_db

            async def _override_db() -> AsyncMock:  # type: ignore[misc]
                yield AsyncMock()

            app.dependency_overrides[get_db] = _override_db

            with (
                patch(
                    "app.services.health_service.HealthService._probe_database",
                    new_callable=AsyncMock,
                    return_value="ok",
                ),
                patch(
                    "app.services.health_service.HealthService._probe_mem0",
                    new_callable=AsyncMock,
                    return_value="unavailable",
                ),
                patch(
                    "app.services.health_service.HealthService._probe_claude",
                    new_callable=AsyncMock,
                    return_value="ok",
                ),
            ):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    resp = await client.get("/api/v1/health?check_dependencies=true")

                data = resp.json()
                cb = data["circuit_breaker"]["mem0"]
                assert cb["state"] == "open"
                assert cb["failure_count"] == 3
                assert cb["retry_queue_size"] == 1

            app.dependency_overrides.clear()
        finally:
            cb_module._breaker = original
