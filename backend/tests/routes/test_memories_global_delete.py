"""Route-level tests for DELETE /api/v1/memories/{memory_id}.

Tests the global memory delete endpoint with mocked MemoryService,
database, and auth dependencies.
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
    """Create a fake Profile-like object for auth dependency override."""
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
    """Provide an async HTTP client with mocked DB and auth."""
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


@pytest_asyncio.fixture
async def unauthed_client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client without auth override (for 401 tests)."""

    async def override_db() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# DELETE /api/v1/memories/{memory_id} tests
# ---------------------------------------------------------------------------


class TestDeleteGlobalMemory:
    """Tests for DELETE /api/v1/memories/{memory_id}."""

    @pytest.mark.asyncio
    async def test_delete_returns_204(self, client: AsyncClient) -> None:
        """R1: Valid deletion of a memory belonging to user returns 204."""
        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = MEMORY_RESPONSE
            mock_client.delete.return_value = None
            mock_cls.return_value = mock_client

            resp = await client.delete("/api/v1/memories/mem-1")

        assert resp.status_code == 204
        assert resp.content == b""

    @pytest.mark.asyncio
    async def test_without_auth_returns_401(self, unauthed_client: AsyncClient) -> None:
        """R2: Request without auth header returns 401 or 403."""
        resp = await unauthed_client.delete("/api/v1/memories/mem-1")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_wrong_user_returns_403(self, client: AsyncClient) -> None:
        """R3: Memory belonging to another user returns 403."""
        other_memory = {**MEMORY_RESPONSE, "user_id": OTHER_MEM0_USER_ID}

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = other_memory
            mock_cls.return_value = mock_client

            resp = await client.delete("/api/v1/memories/mem-1")

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Memory does not belong to user"

    @pytest.mark.asyncio
    async def test_nonexistent_memory_returns_204(self, client: AsyncClient) -> None:
        """R4: Non-existent memory returns 204 (idempotent)."""
        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.side_effect = Exception("Memory not found")
            mock_cls.return_value = mock_client

            resp = await client.delete("/api/v1/memories/nonexistent")

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_mem0_failure_returns_503(self, client: AsyncClient) -> None:
        """R5: Mem0 API failure returns 503."""
        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.side_effect = Exception("Connection timeout")
            mock_cls.return_value = mock_client

            resp = await client.delete("/api/v1/memories/mem-1")

        assert resp.status_code == 503
        assert resp.json()["detail"] == "Memory service temporarily unavailable"

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_returns_503(self, client: AsyncClient) -> None:
        """R6: Circuit breaker OPEN state returns 503 immediately."""
        with patch("app.services.memory_service.get_mem0_circuit_breaker") as mock_cb:
            mock_breaker = MagicMock()
            mock_breaker.state = "open"
            mock_cb.return_value = mock_breaker

            resp = await client.delete("/api/v1/memories/mem-1")

        assert resp.status_code == 503
        assert resp.json()["detail"] == "Memory service temporarily unavailable"
