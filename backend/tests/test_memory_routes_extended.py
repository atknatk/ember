"""Extended route-level tests for memory endpoints.

Covers edge cases not in the base test_memory_routes.py:
- Response body shape validation (created_at field, content-type header)
- Invalid character_id format (non-UUID returns 422)
- Special characters in memory_id path parameter
- Idempotent delete with "404" in Mem0 exception message
- Global endpoint does not require character lookup
- Mem0 get_all called with correct params at the route level
- Delete all with empty memory set succeeds silently
- Response JSON structure for single-item memory list
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
# GET /api/v1/characters/:id/memories — extended tests
# ---------------------------------------------------------------------------


class TestGetCharacterMemoriesExtended:
    """Extended tests for GET /api/v1/characters/:id/memories."""

    @pytest.mark.asyncio
    async def test_response_contains_created_at_field(self, client: AsyncClient) -> None:
        """Response items include the created_at field when Mem0 provides it."""
        char = _make_mock_character()
        app.dependency_overrides[get_db] = _create_db_override(char)

        mem0_data = [
            {"id": "mem-1", "memory": "Test", "created_at": "2026-02-20T10:00:00Z"},
        ]

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = mem0_data
            mock_cls.return_value = mock_client

            resp = await client.get(f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories")

        assert resp.status_code == 200
        item = resp.json()["memories"][0]
        assert "created_at" in item
        assert item["created_at"] is not None

    @pytest.mark.asyncio
    async def test_response_created_at_null_when_absent(self, client: AsyncClient) -> None:
        """Response created_at is null when Mem0 does not return it."""
        char = _make_mock_character()
        app.dependency_overrides[get_db] = _create_db_override(char)

        mem0_data = [
            {"id": "mem-1", "memory": "Test"},
        ]

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = mem0_data
            mock_cls.return_value = mock_client

            resp = await client.get(f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories")

        assert resp.status_code == 200
        item = resp.json()["memories"][0]
        assert item["created_at"] is None

    @pytest.mark.asyncio
    async def test_response_content_type_is_json(self, client: AsyncClient) -> None:
        """Response Content-Type header is application/json."""
        char = _make_mock_character()
        app.dependency_overrides[get_db] = _create_db_override(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = []
            mock_cls.return_value = mock_client

            resp = await client.get(f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories")

        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_invalid_character_id_format_returns_422(self, client: AsyncClient) -> None:
        """Non-UUID character_id in path returns 422 validation error."""
        resp = await client.get("/api/v1/characters/not-a-uuid/memories")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_single_memory_response_shape(self, client: AsyncClient) -> None:
        """Single-item response has correct top-level structure."""
        char = _make_mock_character()
        app.dependency_overrides[get_db] = _create_db_override(char)

        mem0_data = [
            {"id": "mem-1", "memory": "Single memory", "created_at": "2026-01-01T00:00:00Z"},
        ]

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = mem0_data
            mock_cls.return_value = mock_client

            resp = await client.get(f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories")

        data = resp.json()
        assert set(data.keys()) == {"memories"}
        assert len(data["memories"]) == 1
        item_keys = set(data["memories"][0].keys())
        assert item_keys == {"id", "memory", "created_at"}

    @pytest.mark.asyncio
    async def test_large_memory_list_returned(self, client: AsyncClient) -> None:
        """Endpoint can return a large list of memories without pagination."""
        char = _make_mock_character()
        app.dependency_overrides[get_db] = _create_db_override(char)

        mem0_data = [
            {"id": f"mem-{i}", "memory": f"Memory number {i}"}
            for i in range(100)
        ]

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = mem0_data
            mock_cls.return_value = mock_client

            resp = await client.get(f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories")

        assert resp.status_code == 200
        assert len(resp.json()["memories"]) == 100

    @pytest.mark.asyncio
    async def test_mem0_called_with_correct_agent_id(self, client: AsyncClient) -> None:
        """Mem0 get_all receives the character's mem0_agent_id."""
        char = _make_mock_character()
        app.dependency_overrides[get_db] = _create_db_override(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = []
            mock_cls.return_value = mock_client

            await client.get(f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories")

            mock_client.get_all.assert_called_once_with(
                user_id=FAKE_MEM0_USER_ID,
                agent_id=FAKE_MEM0_AGENT_ID,
            )


# ---------------------------------------------------------------------------
# DELETE /api/v1/characters/:id/memories/:memory_id — extended tests
# ---------------------------------------------------------------------------


class TestDeleteCharacterMemoryExtended:
    """Extended tests for DELETE /api/v1/characters/:id/memories/:memory_id."""

    @pytest.mark.asyncio
    async def test_idempotent_delete_with_404_in_exception(self, client: AsyncClient) -> None:
        """Mem0 raising exception with '404' in message returns 204."""
        char = _make_mock_character()
        app.dependency_overrides[get_db] = _create_db_override(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.delete.side_effect = Exception("404 resource not found")
            mock_cls.return_value = mock_client

            resp = await client.delete(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories/mem-gone",
            )

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_memory_id_with_special_characters(self, client: AsyncClient) -> None:
        """Memory ID with hyphens and underscores is accepted."""
        char = _make_mock_character()
        app.dependency_overrides[get_db] = _create_db_override(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.delete.return_value = None
            mock_cls.return_value = mock_client

            resp = await client.delete(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories/mem_abc-def_123",
            )

        assert resp.status_code == 204
        mock_client.delete.assert_called_once_with("mem_abc-def_123")

    @pytest.mark.asyncio
    async def test_memory_id_uuid_format(self, client: AsyncClient) -> None:
        """Memory ID in UUID format is accepted as-is (string, not coerced to UUID)."""
        char = _make_mock_character()
        app.dependency_overrides[get_db] = _create_db_override(char)
        mem_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.delete.return_value = None
            mock_cls.return_value = mock_client

            resp = await client.delete(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories/{mem_uuid}",
            )

        assert resp.status_code == 204
        mock_client.delete.assert_called_once_with(mem_uuid)

    @pytest.mark.asyncio
    async def test_invalid_character_id_format_returns_422(self, client: AsyncClient) -> None:
        """Non-UUID character_id in delete path returns 422."""
        resp = await client.delete("/api/v1/characters/bad-uuid/memories/mem-1")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_no_response_body(self, client: AsyncClient) -> None:
        """Successful delete returns completely empty body."""
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
        assert len(resp.text) == 0


# ---------------------------------------------------------------------------
# DELETE /api/v1/characters/:id/memories (clear all) — extended tests
# ---------------------------------------------------------------------------


class TestDeleteAllCharacterMemoriesExtended:
    """Extended tests for DELETE /api/v1/characters/:id/memories (clear all)."""

    @pytest.mark.asyncio
    async def test_delete_all_calls_mem0_with_correct_params(
        self, client: AsyncClient,
    ) -> None:
        """delete_all is called with correct user_id and agent_id."""
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
            mock_client.delete_all.assert_called_once_with(
                user_id=FAKE_MEM0_USER_ID,
                agent_id=FAKE_MEM0_AGENT_ID,
            )

    @pytest.mark.asyncio
    async def test_delete_all_empty_body(self, client: AsyncClient) -> None:
        """Clear all returns completely empty body."""
        char = _make_mock_character()
        app.dependency_overrides[get_db] = _create_db_override(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.delete_all.return_value = None
            mock_cls.return_value = mock_client

            resp = await client.delete(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories",
            )

        assert resp.content == b""

    @pytest.mark.asyncio
    async def test_invalid_character_id_returns_422(self, client: AsyncClient) -> None:
        """Non-UUID character_id in delete-all path returns 422."""
        resp = await client.delete("/api/v1/characters/invalid-uuid/memories")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_mem0_timeout_error_returns_503(self, client: AsyncClient) -> None:
        """Timeout error from Mem0 surfaces as 503."""
        char = _make_mock_character()
        app.dependency_overrides[get_db] = _create_db_override(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.delete_all.side_effect = TimeoutError("Connection timed out")
            mock_cls.return_value = mock_client

            resp = await client.delete(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/memories",
            )

        assert resp.status_code == 503
        assert resp.json()["detail"] == "Memory service unavailable"


# ---------------------------------------------------------------------------
# GET /api/v1/memories (global) — extended tests
# ---------------------------------------------------------------------------


class TestGetGlobalMemoriesExtended:
    """Extended tests for GET /api/v1/memories."""

    @pytest.mark.asyncio
    async def test_global_endpoint_does_not_require_character_id(
        self, client: AsyncClient,
    ) -> None:
        """Global memories endpoint has no character_id in path."""
        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = []
            mock_cls.return_value = mock_client

            resp = await client.get("/api/v1/memories")

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_global_mem0_called_without_agent_id(self, client: AsyncClient) -> None:
        """Global endpoint calls Mem0 get_all with user_id only, no agent_id."""
        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = []
            mock_cls.return_value = mock_client

            await client.get("/api/v1/memories")

            mock_client.get_all.assert_called_once_with(
                user_id=FAKE_MEM0_USER_ID,
            )
            # Ensure agent_id was NOT passed
            call_kwargs = mock_client.get_all.call_args.kwargs
            assert "agent_id" not in call_kwargs

    @pytest.mark.asyncio
    async def test_global_response_shape(self, client: AsyncClient) -> None:
        """Global memories response has the same shape as character memories."""
        mem0_data = [
            {"id": "glob-1", "memory": "Works remotely", "created_at": "2026-01-15T08:00:00Z"},
        ]

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = mem0_data
            mock_cls.return_value = mock_client

            resp = await client.get("/api/v1/memories")

        data = resp.json()
        assert set(data.keys()) == {"memories"}
        assert len(data["memories"]) == 1
        item_keys = set(data["memories"][0].keys())
        assert item_keys == {"id", "memory", "created_at"}
        assert data["memories"][0]["id"] == "glob-1"

    @pytest.mark.asyncio
    async def test_global_content_type_is_json(self, client: AsyncClient) -> None:
        """Global endpoint Content-Type header is application/json."""
        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = []
            mock_cls.return_value = mock_client

            resp = await client.get("/api/v1/memories")

        assert "application/json" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_global_mem0_timeout_returns_503(self, client: AsyncClient) -> None:
        """Timeout error on global memories surfaces as 503."""
        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.side_effect = TimeoutError("timeout")
            mock_cls.return_value = mock_client

            resp = await client.get("/api/v1/memories")

        assert resp.status_code == 503
        assert resp.json()["detail"] == "Memory service unavailable"

    @pytest.mark.asyncio
    async def test_global_large_memory_list(self, client: AsyncClient) -> None:
        """Global endpoint can return a large list without pagination."""
        mem0_data = [
            {"id": f"glob-{i}", "memory": f"Global fact #{i}"}
            for i in range(50)
        ]

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = mem0_data
            mock_cls.return_value = mock_client

            resp = await client.get("/api/v1/memories")

        assert resp.status_code == 200
        assert len(resp.json()["memories"]) == 50
