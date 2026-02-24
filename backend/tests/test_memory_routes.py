"""Route-level integration tests for memory endpoints.

Uses the FastAPI test client with mocked MemoryService, database, and
auth dependencies to test HTTP status codes, response structure, and
error handling.
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
OTHER_USER_ID = uuid.UUID("770e8400-e29b-41d4-a716-446655440099")
FAKE_CHARACTER_ID = uuid.UUID("660e8400-e29b-41d4-a716-446655440001")
FAKE_MEM0_USER_ID = f"user_{FAKE_USER_ID}"
FAKE_MEM0_AGENT_ID = f"english_teacher_{FAKE_USER_ID}"

MEM0_RESULTS = [
    {"id": "mem-1", "memory": "Likes morning workouts", "created_at": "2026-02-20T10:00:00Z"},
    {"id": "mem-2", "memory": "Left knee is sensitive", "created_at": "2026-02-18T15:30:00Z"},
]


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


def _make_mock_character(
    character_id: uuid.UUID = FAKE_CHARACTER_ID,
    user_id: uuid.UUID = FAKE_USER_ID,
    is_active: bool = True,
) -> MagicMock:
    """Create a MagicMock resembling a Character ORM object."""
    char = MagicMock()
    char.id = character_id
    char.user_id = user_id
    char.name = "Sarah"
    char.template = "english_teacher"
    char.mem0_agent_id = f"english_teacher_{user_id}"
    char.is_active = is_active
    char.created_at = datetime.now(tz=UTC)
    return char


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _create_db_override(
    character: MagicMock | None = None,
) -> object:
    """Create a get_db override that returns a mock db session."""

    async def _override() -> AsyncGenerator[AsyncMock, None]:
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = character
        mock_db.execute = AsyncMock(return_value=mock_result)
        yield mock_db

    return _override


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client with mocked DB and auth."""
    fake_profile = _make_fake_profile()

    async def override_user() -> MagicMock:
        return fake_profile

    app.dependency_overrides[get_db] = _create_db_override()
    app.dependency_overrides[get_current_user] = override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unauthed_client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client without auth override (for 401 tests)."""
    app.dependency_overrides[get_db] = _create_db_override()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/v1/characters/:id/memories tests
# ---------------------------------------------------------------------------


class TestGetCharacterMemories:
    """Tests for GET /api/v1/characters/:id/memories."""

    @pytest.mark.asyncio
    async def test_returns_memories(self, client: AsyncClient) -> None:
        """R1: Valid character returns 200 with memories list."""
        char = _make_mock_character()
        app.dependency_overrides[get_db] = _create_db_override(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = MEM0_RESULTS
            mock_cls.return_value = mock_client

            resp = await client.get(f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories")

        assert resp.status_code == 200
        data = resp.json()
        assert "memories" in data
        assert len(data["memories"]) == 2
        assert data["memories"][0]["id"] == "mem-1"
        assert data["memories"][0]["memory"] == "Likes morning workouts"
        assert data["memories"][1]["id"] == "mem-2"

    @pytest.mark.asyncio
    async def test_returns_empty_memories(self, client: AsyncClient) -> None:
        """R2: Character with no memories returns 200 with empty list."""
        char = _make_mock_character()
        app.dependency_overrides[get_db] = _create_db_override(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = []
            mock_cls.return_value = mock_client

            resp = await client.get(f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories")

        assert resp.status_code == 200
        assert resp.json() == {"memories": []}

    @pytest.mark.asyncio
    async def test_nonexistent_character_returns_404(self, client: AsyncClient) -> None:
        """R3: Non-existent character returns 404."""
        app.dependency_overrides[get_db] = _create_db_override(None)

        resp = await client.get(f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Character not found"

    @pytest.mark.asyncio
    async def test_wrong_user_returns_403(self, client: AsyncClient) -> None:
        """R4: Character belonging to another user returns 403."""
        char = _make_mock_character(user_id=OTHER_USER_ID)
        app.dependency_overrides[get_db] = _create_db_override(char)

        resp = await client.get(f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories")

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Character does not belong to user"

    @pytest.mark.asyncio
    async def test_inactive_character_returns_404(self, client: AsyncClient) -> None:
        """R5: Inactive character returns 404 (filtered by is_active=true in query)."""
        # The DB query filters is_active=true, so inactive returns None
        app.dependency_overrides[get_db] = _create_db_override(None)

        resp = await client.get(f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Character not found"

    @pytest.mark.asyncio
    async def test_without_auth_returns_401(self, unauthed_client: AsyncClient) -> None:
        """R6: Request without auth header returns 401 or 403."""
        resp = await unauthed_client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories",
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_mem0_failure_returns_503(self, client: AsyncClient) -> None:
        """R7: Mem0 API failure returns 503."""
        char = _make_mock_character()
        app.dependency_overrides[get_db] = _create_db_override(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.side_effect = Exception("Mem0 connection refused")
            mock_cls.return_value = mock_client

            resp = await client.get(f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories")

        assert resp.status_code == 503
        assert resp.json()["detail"] == "Memory service unavailable"


# ---------------------------------------------------------------------------
# DELETE /api/v1/characters/:id/memories/:memory_id tests
# ---------------------------------------------------------------------------


class TestDeleteCharacterMemory:
    """Tests for DELETE /api/v1/characters/:id/memories/:memory_id."""

    @pytest.mark.asyncio
    async def test_delete_returns_204(self, client: AsyncClient) -> None:
        """R8: Valid deletion returns 204 with no body."""
        char = _make_mock_character()
        app.dependency_overrides[get_db] = _create_db_override(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.delete.return_value = None
            mock_cls.return_value = mock_client

            resp = await client.delete(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories/mem-1",
            )

        assert resp.status_code == 204
        assert resp.content == b""

    @pytest.mark.asyncio
    async def test_nonexistent_character_returns_404(self, client: AsyncClient) -> None:
        """R9: Non-existent character returns 404."""
        app.dependency_overrides[get_db] = _create_db_override(None)

        resp = await client.delete(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories/mem-1",
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Character not found"

    @pytest.mark.asyncio
    async def test_wrong_user_returns_403(self, client: AsyncClient) -> None:
        """R10: Character belonging to another user returns 403."""
        char = _make_mock_character(user_id=OTHER_USER_ID)
        app.dependency_overrides[get_db] = _create_db_override(char)

        resp = await client.delete(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories/mem-1",
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Character does not belong to user"

    @pytest.mark.asyncio
    async def test_without_auth_returns_401(self, unauthed_client: AsyncClient) -> None:
        """R11: Request without auth header returns 401 or 403."""
        resp = await unauthed_client.delete(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories/mem-1",
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_mem0_failure_returns_503(self, client: AsyncClient) -> None:
        """R12: Mem0 API failure returns 503."""
        char = _make_mock_character()
        app.dependency_overrides[get_db] = _create_db_override(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.delete.side_effect = Exception("Connection timeout")
            mock_cls.return_value = mock_client

            resp = await client.delete(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories/mem-1",
            )

        assert resp.status_code == 503
        assert resp.json()["detail"] == "Memory service unavailable"

    @pytest.mark.asyncio
    async def test_nonexistent_memory_returns_204(self, client: AsyncClient) -> None:
        """R13: Non-existent memory_id still returns 204 (idempotent)."""
        char = _make_mock_character()
        app.dependency_overrides[get_db] = _create_db_override(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.delete.side_effect = Exception("Memory not found")
            mock_cls.return_value = mock_client

            resp = await client.delete(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories/nonexistent",
            )

        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# DELETE /api/v1/characters/:id/memories (clear all) tests
# ---------------------------------------------------------------------------


class TestDeleteAllCharacterMemories:
    """Tests for DELETE /api/v1/characters/:id/memories (clear all)."""

    @pytest.mark.asyncio
    async def test_delete_all_returns_204(self, client: AsyncClient) -> None:
        """R14: Valid deletion of all memories returns 204."""
        char = _make_mock_character()
        app.dependency_overrides[get_db] = _create_db_override(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.delete_all.return_value = None
            mock_cls.return_value = mock_client

            resp = await client.delete(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories",
            )

        assert resp.status_code == 204
        assert resp.content == b""

    @pytest.mark.asyncio
    async def test_nonexistent_character_returns_404(self, client: AsyncClient) -> None:
        """R15: Non-existent character returns 404."""
        app.dependency_overrides[get_db] = _create_db_override(None)

        resp = await client.delete(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories",
        )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_wrong_user_returns_403(self, client: AsyncClient) -> None:
        """R16: Character belonging to another user returns 403."""
        char = _make_mock_character(user_id=OTHER_USER_ID)
        app.dependency_overrides[get_db] = _create_db_override(char)

        resp = await client.delete(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories",
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_without_auth_returns_401(self, unauthed_client: AsyncClient) -> None:
        """R17: Request without auth header returns 401 or 403."""
        resp = await unauthed_client.delete(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories",
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_mem0_failure_returns_503(self, client: AsyncClient) -> None:
        """R18: Mem0 API failure returns 503."""
        char = _make_mock_character()
        app.dependency_overrides[get_db] = _create_db_override(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.delete_all.side_effect = Exception("Mem0 error")
            mock_cls.return_value = mock_client

            resp = await client.delete(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories",
            )

        assert resp.status_code == 503
        assert resp.json()["detail"] == "Memory service unavailable"


# ---------------------------------------------------------------------------
# GET /api/v1/memories (global) tests
# ---------------------------------------------------------------------------


class TestGetGlobalMemories:
    """Tests for GET /api/v1/memories."""

    @pytest.mark.asyncio
    async def test_returns_global_memories(self, client: AsyncClient) -> None:
        """R19: Returns 200 with global memories list."""
        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = MEM0_RESULTS
            mock_cls.return_value = mock_client

            resp = await client.get("/api/v1/memories")

        assert resp.status_code == 200
        data = resp.json()
        assert "memories" in data
        assert len(data["memories"]) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_global_memories(self, client: AsyncClient) -> None:
        """R20: Returns 200 with empty list when no global memories."""
        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = []
            mock_cls.return_value = mock_client

            resp = await client.get("/api/v1/memories")

        assert resp.status_code == 200
        assert resp.json() == {"memories": []}

    @pytest.mark.asyncio
    async def test_without_auth_returns_401(self, unauthed_client: AsyncClient) -> None:
        """R21: Request without auth header returns 401 or 403."""
        resp = await unauthed_client.get("/api/v1/memories")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_mem0_failure_returns_503(self, client: AsyncClient) -> None:
        """R22: Mem0 API failure returns 503."""
        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.side_effect = Exception("Mem0 error")
            mock_cls.return_value = mock_client

            resp = await client.get("/api/v1/memories")

        assert resp.status_code == 503
        assert resp.json()["detail"] == "Memory service unavailable"
