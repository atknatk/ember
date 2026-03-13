"""Edge-case route tests for DELETE /api/v1/memories/{memory_id}.

Covers gaps not addressed by test_memories_global_delete.py:
- Empty and unusual memory_id values in the path
- Mem0 response format variations (uppercase error, exact '404' string)
- Ownership validation with missing/null user_id in Mem0 response
- Concurrent/repeated deletion (idempotency at route level)
- Delete failure after successful get (race-condition 503 path)
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import uuid  # noqa: E402
from collections.abc import AsyncGenerator  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.dependencies import get_current_user, get_db  # noqa: E402
from app.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
FAKE_MEM0_USER_ID = f"user_{FAKE_USER_ID}"
OTHER_MEM0_USER_ID = "user_770e8400-e29b-41d4-a716-446655440099"

MEMORY_RESPONSE = {
    "id": "mem-1",
    "memory": "Works as a freelance engineer",
    "user_id": FAKE_MEM0_USER_ID,
    "created_at": "2026-02-15T08:00:00Z",
}


def _make_fake_profile(
    user_id: uuid.UUID = FAKE_USER_ID,
) -> MagicMock:
    profile = MagicMock()
    profile.id = user_id
    profile.email = "test@ember.ai"
    profile.name = "Alex"
    profile.mem0_user_id = f"user_{user_id}"
    profile.timezone = "UTC"
    profile.preferred_language = "en"
    profile.created_at = datetime.now(tz=UTC)
    profile.updated_at = datetime.now(tz=UTC)
    return profile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Authenticated client with mocked DB and auth."""
    fake_profile = _make_fake_profile()

    async def override_user() -> MagicMock:
        return fake_profile

    async def override_db() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Edge cases: memory_id path parameter values
# ---------------------------------------------------------------------------


class TestDeleteGlobalMemoryPathEdgeCases:
    """Edge cases for the memory_id path parameter."""

    @pytest.mark.asyncio
    async def test_memory_id_with_hyphens_succeeds(self, client: AsyncClient) -> None:
        """UUID-like memory_id with hyphens is accepted as a string path param."""
        memory_id = "550e8400-e29b-41d4-a716-446655440abc"
        memory = {**MEMORY_RESPONSE, "id": memory_id}

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = memory
            mock_client.delete.return_value = None
            mock_cls.return_value = mock_client

            resp = await client.delete(f"/api/v1/memories/{memory_id}")

        assert resp.status_code == 204
        mock_client.get.assert_called_once_with(memory_id)
        mock_client.delete.assert_called_once_with(memory_id)

    @pytest.mark.asyncio
    async def test_memory_id_with_underscores_succeeds(self, client: AsyncClient) -> None:
        """Memory IDs containing underscores are passed through unchanged."""
        memory_id = "mem_abc_123"
        memory = {**MEMORY_RESPONSE, "id": memory_id}

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = memory
            mock_client.delete.return_value = None
            mock_cls.return_value = mock_client

            resp = await client.delete(f"/api/v1/memories/{memory_id}")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_very_long_memory_id_is_passed_to_mem0(self, client: AsyncClient) -> None:
        """A 200-character memory_id is forwarded verbatim to Mem0 (no truncation)."""
        memory_id = "m" * 200
        memory = {**MEMORY_RESPONSE, "id": memory_id}

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = memory
            mock_client.delete.return_value = None
            mock_cls.return_value = mock_client

            resp = await client.delete(f"/api/v1/memories/{memory_id}")

        assert resp.status_code == 204
        args, _ = mock_client.get.call_args
        assert args[0] == memory_id


# ---------------------------------------------------------------------------
# Edge cases: Mem0 response format variations
# ---------------------------------------------------------------------------


class TestDeleteGlobalMemoryResponseFormats:
    """Mem0 response format variations for ownership and error detection."""

    @pytest.mark.asyncio
    async def test_get_raises_uppercase_not_found_is_idempotent(
        self, client: AsyncClient
    ) -> None:
        """'NOT FOUND' (uppercase) in exception message is treated as success."""
        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.side_effect = Exception("NOT FOUND: memory does not exist")
            mock_cls.return_value = mock_client

            resp = await client.delete("/api/v1/memories/mem-upper")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_get_raises_exact_404_string_is_idempotent(
        self, client: AsyncClient
    ) -> None:
        """Exception message that is just '404' (no surrounding text) is idempotent."""
        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.side_effect = Exception("404")
            mock_cls.return_value = mock_client

            resp = await client.delete("/api/v1/memories/mem-404")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_raises_uppercase_not_found_is_idempotent(
        self, client: AsyncClient
    ) -> None:
        """'NOT FOUND' on client.delete() is treated as success (race condition)."""
        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = MEMORY_RESPONSE
            mock_client.delete.side_effect = Exception("NOT FOUND: already deleted")
            mock_cls.return_value = mock_client

            resp = await client.delete("/api/v1/memories/mem-1")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_raises_exact_404_string_is_idempotent(
        self, client: AsyncClient
    ) -> None:
        """'404' in client.delete() exception message is treated as success."""
        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = MEMORY_RESPONSE
            mock_client.delete.side_effect = Exception("HTTP 404")
            mock_cls.return_value = mock_client

            resp = await client.delete("/api/v1/memories/mem-1")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_mem0_response_with_extra_fields_succeeds(
        self, client: AsyncClient
    ) -> None:
        """Mem0 response containing unexpected extra fields does not break ownership check."""
        memory_with_extras = {
            **MEMORY_RESPONSE,
            "agent_id": None,
            "run_id": "run-xyz",
            "metadata": {"source": "chat"},
            "score": 0.95,
        }

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = memory_with_extras
            mock_client.delete.return_value = None
            mock_cls.return_value = mock_client

            resp = await client.delete("/api/v1/memories/mem-1")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_mem0_response_missing_user_id_key_returns_403(
        self, client: AsyncClient
    ) -> None:
        """Mem0 response dict with no 'user_id' key is treated as ownership mismatch (403).

        memory.get('user_id') returns None, which does not equal FAKE_MEM0_USER_ID.
        """
        memory_no_user_id = {
            "id": "mem-1",
            "memory": "Some memory text",
            "created_at": "2026-02-15T08:00:00Z",
            # 'user_id' key intentionally omitted
        }

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = memory_no_user_id
            mock_cls.return_value = mock_client

            resp = await client.delete("/api/v1/memories/mem-1")

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Memory does not belong to user"

    @pytest.mark.asyncio
    async def test_mem0_response_with_null_user_id_returns_403(
        self, client: AsyncClient
    ) -> None:
        """Mem0 response with user_id=None is treated as ownership mismatch (403)."""
        memory_null_user = {**MEMORY_RESPONSE, "user_id": None}

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = memory_null_user
            mock_cls.return_value = mock_client

            resp = await client.delete("/api/v1/memories/mem-1")

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Memory does not belong to user"

    @pytest.mark.asyncio
    async def test_mem0_response_with_empty_string_user_id_returns_403(
        self, client: AsyncClient
    ) -> None:
        """Mem0 response with user_id='' is treated as ownership mismatch (403)."""
        memory_empty_user = {**MEMORY_RESPONSE, "user_id": ""}

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = memory_empty_user
            mock_cls.return_value = mock_client

            resp = await client.delete("/api/v1/memories/mem-1")

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Memory does not belong to user"


# ---------------------------------------------------------------------------
# Concurrent / repeated deletion (idempotency)
# ---------------------------------------------------------------------------


class TestDeleteGlobalMemoryIdempotency:
    """Verifies idempotent behaviour at the route level."""

    @pytest.mark.asyncio
    async def test_second_delete_of_same_memory_returns_204(
        self, client: AsyncClient
    ) -> None:
        """Deleting the same memory_id twice both return 204 (idempotent).

        First call: get succeeds, delete succeeds.
        Second call: get raises 'not found' (memory gone), returns 204.
        """
        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            # First call: memory exists
            mock_client.get.return_value = MEMORY_RESPONSE
            mock_client.delete.return_value = None
            mock_cls.return_value = mock_client

            resp1 = await client.delete("/api/v1/memories/mem-1")
            assert resp1.status_code == 204

        # Second call: memory already deleted — Mem0 raises not found
        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client2 = MagicMock()
            mock_client2.get.side_effect = Exception("not found")
            mock_cls.return_value = mock_client2

            resp2 = await client.delete("/api/v1/memories/mem-1")
            assert resp2.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_race_condition_get_succeeds_delete_not_found(
        self, client: AsyncClient
    ) -> None:
        """Simulates race: ownership check passes but memory is deleted before client.delete().

        get() returns owned memory, delete() raises not found — should still be 204.
        """
        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = MEMORY_RESPONSE
            mock_client.delete.side_effect = Exception("Memory not found (404)")
            mock_cls.return_value = mock_client

            resp = await client.delete("/api/v1/memories/mem-1")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_does_not_call_mem0_when_circuit_open(
        self, client: AsyncClient
    ) -> None:
        """When circuit breaker is OPEN, no Mem0 call is attempted."""
        with (
            patch("app.services.memory_service.get_mem0_circuit_breaker") as mock_cb,
            patch("app.services.memory_service.MemoryClient") as mock_cls,
        ):
            mock_breaker = MagicMock()
            mock_breaker.state = "open"
            mock_cb.return_value = mock_breaker
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            resp = await client.delete("/api/v1/memories/mem-1")

        assert resp.status_code == 503
        # No Mem0 client methods should have been called
        mock_client.get.assert_not_called()
        mock_client.delete.assert_not_called()
