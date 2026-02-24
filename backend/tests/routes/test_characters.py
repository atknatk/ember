"""Route-level integration tests for character CRUD endpoints.

Uses the FastAPI test client with mocked CharacterService and dependencies
to test HTTP status codes, response structure, and request validation.
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
FAKE_CHARACTER_ID_2 = uuid.UUID("660e8400-e29b-41d4-a716-446655440002")


def _make_fake_profile(
    user_id: uuid.UUID = FAKE_USER_ID,
) -> MagicMock:
    """Create a fake Profile-like object for auth dependency override."""
    profile = MagicMock()
    profile.id = user_id
    profile.email = "test@ember.ai"
    profile.name = "Alex"
    profile.mem0_user_id = f"user_{user_id}"
    profile.fcm_token = None
    profile.timezone = "UTC"
    profile.avatar_url = None
    profile.preferred_language = "en"
    profile.onboarding_completed = False
    profile.subscription_tier = "free"
    profile.subscription_expires_at = None
    profile.created_at = datetime.now(tz=UTC)
    profile.updated_at = datetime.now(tz=UTC)
    return profile


def _make_mock_character(
    character_id: uuid.UUID = FAKE_CHARACTER_ID,
    user_id: uuid.UUID = FAKE_USER_ID,
    name: str = "Sarah",
    template: str = "english_teacher",
    is_default: bool = False,
    is_active: bool = True,
) -> MagicMock:
    """Create a MagicMock resembling a Character ORM object."""
    char = MagicMock()
    char.id = character_id
    char.user_id = user_id
    char.name = name
    char.template = template
    char.description = None
    char.system_prompt = "You are Sarah..."
    char.mem0_agent_id = f"{template}_{user_id}"
    char.avatar_style = "default"
    char.is_default = is_default
    char.is_active = is_active
    char.created_at = datetime.now(tz=UTC)
    char.updated_at = datetime.now(tz=UTC)
    return char


def _mock_claude_response(text: str = "Generated system prompt...") -> MagicMock:
    """Create a mock Claude Haiku response."""
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = text
    mock_response.content = [mock_content]
    return mock_response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
    """Yield a mock database session."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    async def _fake_refresh(obj: object) -> None:
        if not hasattr(obj, "created_at") or getattr(obj, "created_at", None) is None:
            object.__setattr__(obj, "created_at", datetime.now(tz=UTC))

    mock_db.refresh = AsyncMock(side_effect=_fake_refresh)
    yield mock_db


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client with mocked DB and auth."""
    fake_profile = _make_fake_profile()

    async def override_user() -> MagicMock:
        return fake_profile

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unauthed_client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client without auth override (for 401/403 tests)."""
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/v1/characters tests
# ---------------------------------------------------------------------------


class TestListCharacters:
    """Tests for GET /api/v1/characters."""

    @pytest.mark.asyncio
    async def test_list_empty(self, client: AsyncClient) -> None:
        """Returns 200 with empty characters list."""
        resp = await client.get("/api/v1/characters")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"characters": []}

    @pytest.mark.asyncio
    async def test_list_with_characters(self, client: AsyncClient) -> None:
        """Returns 200 with characters sorted by last_message_at DESC NULLS LAST."""
        now = datetime.now(tz=UTC)
        char1 = _make_mock_character(is_default=True, name="Ember", template="companion")
        char2 = _make_mock_character(
            character_id=FAKE_CHARACTER_ID_2,
            name="Sarah",
            template="english_teacher",
        )

        async def _override_db_with_chars() -> AsyncGenerator[AsyncMock, None]:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.all.return_value = [
                (char1, now),
                (char2, None),
            ]
            mock_db.execute = AsyncMock(return_value=mock_result)
            yield mock_db

        app.dependency_overrides[get_db] = _override_db_with_chars

        resp = await client.get("/api/v1/characters")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["characters"]) == 2
        assert data["characters"][0]["name"] == "Ember"
        assert data["characters"][0]["is_default"] is True
        assert data["characters"][0]["last_message_at"] is not None
        assert data["characters"][1]["name"] == "Sarah"
        assert data["characters"][1]["last_message_at"] is None

    @pytest.mark.asyncio
    async def test_list_excludes_inactive_characters(self, client: AsyncClient) -> None:
        """Only active characters appear in the list."""
        char_active = _make_mock_character(name="Active")

        async def _override_db_active_only() -> AsyncGenerator[AsyncMock, None]:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            # The service query filters is_active=true, so only active chars returned
            mock_result.all.return_value = [(char_active, None)]
            mock_db.execute = AsyncMock(return_value=mock_result)
            yield mock_db

        app.dependency_overrides[get_db] = _override_db_active_only

        resp = await client.get("/api/v1/characters")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["characters"]) == 1
        assert data["characters"][0]["name"] == "Active"

    @pytest.mark.asyncio
    async def test_list_includes_last_message_at(self, client: AsyncClient) -> None:
        """Each character includes the last_message_at from conversations."""
        now = datetime.now(tz=UTC)
        char = _make_mock_character()

        async def _override_db() -> AsyncGenerator[AsyncMock, None]:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.all.return_value = [(char, now)]
            mock_db.execute = AsyncMock(return_value=mock_result)
            yield mock_db

        app.dependency_overrides[get_db] = _override_db

        resp = await client.get("/api/v1/characters")
        assert resp.status_code == 200
        data = resp.json()
        assert data["characters"][0]["last_message_at"] is not None

    @pytest.mark.asyncio
    async def test_list_excludes_system_prompt(self, client: AsyncClient) -> None:
        """system_prompt and mem0_agent_id are not in the list response."""
        char = _make_mock_character()

        async def _override_db() -> AsyncGenerator[AsyncMock, None]:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.all.return_value = [(char, None)]
            mock_db.execute = AsyncMock(return_value=mock_result)
            yield mock_db

        app.dependency_overrides[get_db] = _override_db

        resp = await client.get("/api/v1/characters")
        assert resp.status_code == 200
        char_data = resp.json()["characters"][0]
        assert "system_prompt" not in char_data
        assert "mem0_agent_id" not in char_data

    @pytest.mark.asyncio
    async def test_list_without_auth(self, unauthed_client: AsyncClient) -> None:
        """Returns 401/403 when no auth header is provided."""
        resp = await unauthed_client.get("/api/v1/characters")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# POST /api/v1/characters tests
# ---------------------------------------------------------------------------


class TestCreateCharacter:
    """Tests for POST /api/v1/characters."""

    @pytest.mark.asyncio
    async def test_create_with_valid_template(self, client: AsyncClient) -> None:
        """Valid request returns 201 with generated system_prompt."""
        mock_response = _mock_claude_response("You are Sarah, an English teacher...")

        with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            resp = await client.post(
                "/api/v1/characters",
                json={"name": "Sarah", "template": "english_teacher"},
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Sarah"
        assert data["template"] == "english_teacher"
        assert data["system_prompt"] == "You are Sarah, an English teacher..."
        assert data["is_default"] is False
        assert data["avatar_style"] == "default"
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_with_custom_template(self, client: AsyncClient) -> None:
        """Custom template with description returns 201."""
        mock_response = _mock_claude_response("You are Marco, an Italian teacher...")

        with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            resp = await client.post(
                "/api/v1/characters",
                json={
                    "name": "Marco",
                    "template": "custom",
                    "description": "An Italian language teacher who only speaks Italian",
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["template"] == "custom"
        assert data["description"] == "An Italian language teacher who only speaks Italian"

    @pytest.mark.asyncio
    async def test_create_with_invalid_template(self, client: AsyncClient) -> None:
        """Invalid template returns 422."""
        resp = await client.post(
            "/api/v1/characters",
            json={"name": "Test", "template": "invalid_template"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_custom_without_description(self, client: AsyncClient) -> None:
        """Custom template without description returns 422."""
        resp = await client.post(
            "/api/v1/characters",
            json={"name": "Marco", "template": "custom"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_non_custom_with_description(self, client: AsyncClient) -> None:
        """Non-custom template with description returns 422."""
        resp = await client.post(
            "/api/v1/characters",
            json={
                "name": "Sarah",
                "template": "english_teacher",
                "description": "Some extra description text",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_whitespace_only_name(self, client: AsyncClient) -> None:
        """Name that is only whitespace returns 422."""
        resp = await client.post(
            "/api/v1/characters",
            json={"name": "   ", "template": "companion"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_without_auth(self, unauthed_client: AsyncClient) -> None:
        """Returns 401/403 when no auth header is provided."""
        resp = await unauthed_client.post(
            "/api/v1/characters",
            json={"name": "Sarah", "template": "english_teacher"},
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_create_when_claude_unavailable(self, client: AsyncClient) -> None:
        """Returns 503 when Claude Haiku API is unavailable."""
        with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=Exception("API connection error"),
            )
            mock_cls.return_value = mock_client

            resp = await client.post(
                "/api/v1/characters",
                json={"name": "Sarah", "template": "english_teacher"},
            )

        assert resp.status_code == 503
        assert resp.json()["detail"] == "AI service unavailable, please try again"


# ---------------------------------------------------------------------------
# PUT /api/v1/characters/:id tests
# ---------------------------------------------------------------------------


class TestUpdateCharacter:
    """Tests for PUT /api/v1/characters/:id."""

    @pytest.mark.asyncio
    async def test_update_with_valid_fields(self, client: AsyncClient) -> None:
        """Valid update returns 200 with updated character."""
        char = _make_mock_character()

        async def _override_db() -> AsyncGenerator[AsyncMock, None]:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = char
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()
            yield mock_db

        app.dependency_overrides[get_db] = _override_db

        resp = await client.put(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}",
            json={"name": "Sarah the Great", "avatar_style": "blue"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Sarah the Great"
        assert data["avatar_style"] == "blue"

    @pytest.mark.asyncio
    async def test_update_no_fields_provided(self, client: AsyncClient) -> None:
        """All-null update returns 422."""
        resp = await client.put(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}",
            json={},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_wrong_user(self, client: AsyncClient) -> None:
        """Updating another user's character returns 403."""
        char = _make_mock_character(user_id=OTHER_USER_ID)

        async def _override_db() -> AsyncGenerator[AsyncMock, None]:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = char
            mock_db.execute = AsyncMock(return_value=mock_result)
            yield mock_db

        app.dependency_overrides[get_db] = _override_db

        resp = await client.put(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}",
            json={"name": "Hacked Name"},
        )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Character does not belong to user"

    @pytest.mark.asyncio
    async def test_update_nonexistent_character(self, client: AsyncClient) -> None:
        """Updating a non-existent character returns 404."""
        async def _override_db() -> AsyncGenerator[AsyncMock, None]:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)
            yield mock_db

        app.dependency_overrides[get_db] = _override_db

        resp = await client.put(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}",
            json={"name": "New Name"},
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Character not found"

    @pytest.mark.asyncio
    async def test_update_inactive_character(self, client: AsyncClient) -> None:
        """Updating an inactive character returns 404 (treated as not found)."""
        async def _override_db() -> AsyncGenerator[AsyncMock, None]:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            # The query filters is_active=true, so inactive returns None
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)
            yield mock_db

        app.dependency_overrides[get_db] = _override_db

        resp = await client.put(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}",
            json={"name": "New Name"},
        )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_without_auth(self, unauthed_client: AsyncClient) -> None:
        """Returns 401/403 when no auth header is provided."""
        resp = await unauthed_client.put(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}",
            json={"name": "New Name"},
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_update_invalid_uuid(self, client: AsyncClient) -> None:
        """Invalid UUID in path returns 422."""
        resp = await client.put(
            "/api/v1/characters/not-a-uuid",
            json={"name": "New Name"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/v1/characters/:id tests
# ---------------------------------------------------------------------------


class TestDeleteCharacter:
    """Tests for DELETE /api/v1/characters/:id."""

    @pytest.mark.asyncio
    async def test_delete_normal_character(self, client: AsyncClient) -> None:
        """Deleting a normal character returns 204."""
        char = _make_mock_character()

        async def _override_db() -> AsyncGenerator[AsyncMock, None]:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = char
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.commit = AsyncMock()
            yield mock_db

        app.dependency_overrides[get_db] = _override_db

        resp = await client.delete(f"/api/v1/characters/{FAKE_CHARACTER_ID}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_default_character(self, client: AsyncClient) -> None:
        """Deleting the default character returns 403."""
        char = _make_mock_character(is_default=True)

        async def _override_db() -> AsyncGenerator[AsyncMock, None]:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = char
            mock_db.execute = AsyncMock(return_value=mock_result)
            yield mock_db

        app.dependency_overrides[get_db] = _override_db

        resp = await client.delete(f"/api/v1/characters/{FAKE_CHARACTER_ID}")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Default character cannot be deleted"

    @pytest.mark.asyncio
    async def test_delete_wrong_user(self, client: AsyncClient) -> None:
        """Deleting another user's character returns 403."""
        char = _make_mock_character(user_id=OTHER_USER_ID)

        async def _override_db() -> AsyncGenerator[AsyncMock, None]:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = char
            mock_db.execute = AsyncMock(return_value=mock_result)
            yield mock_db

        app.dependency_overrides[get_db] = _override_db

        resp = await client.delete(f"/api/v1/characters/{FAKE_CHARACTER_ID}")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Character does not belong to user"

    @pytest.mark.asyncio
    async def test_delete_nonexistent_character(self, client: AsyncClient) -> None:
        """Deleting a non-existent character returns 404."""
        async def _override_db() -> AsyncGenerator[AsyncMock, None]:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)
            yield mock_db

        app.dependency_overrides[get_db] = _override_db

        resp = await client.delete(f"/api/v1/characters/{FAKE_CHARACTER_ID}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Character not found"

    @pytest.mark.asyncio
    async def test_delete_already_inactive_character(self, client: AsyncClient) -> None:
        """Deleting an already inactive character returns 404."""
        async def _override_db() -> AsyncGenerator[AsyncMock, None]:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            # The query filters is_active=true, so inactive returns None
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=mock_result)
            yield mock_db

        app.dependency_overrides[get_db] = _override_db

        resp = await client.delete(f"/api/v1/characters/{FAKE_CHARACTER_ID}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_without_auth(self, unauthed_client: AsyncClient) -> None:
        """Returns 401/403 when no auth header is provided."""
        resp = await unauthed_client.delete(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}",
        )
        assert resp.status_code in (401, 403)
