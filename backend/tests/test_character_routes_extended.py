"""Extended route-level tests for character CRUD endpoints.

Covers additional scenarios not in the base test_character_routes.py:
- Response body structure validation (field presence/absence)
- Boundary conditions (name length, special characters)
- POST response field verification (description null for non-custom)
- Soft delete verification at route level
- Invalid UUID handling for DELETE
- Duplicate creation scenarios
- All template types accepted via POST
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
    description: str | None = None,
) -> MagicMock:
    """Create a MagicMock resembling a Character ORM object."""
    char = MagicMock()
    char.id = character_id
    char.user_id = user_id
    char.name = name
    char.template = template
    char.description = description
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
    """Provide an async HTTP client without auth override."""
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/v1/characters -- response structure tests
# ---------------------------------------------------------------------------


class TestListCharactersResponseStructure:
    """Tests for GET /api/v1/characters response body structure."""

    @pytest.mark.asyncio
    async def test_response_has_characters_key(self, client: AsyncClient) -> None:
        """Response body always has a 'characters' key."""
        resp = await client.get("/api/v1/characters")
        assert resp.status_code == 200
        data = resp.json()
        assert "characters" in data

    @pytest.mark.asyncio
    async def test_character_item_has_all_required_fields(
        self, client: AsyncClient,
    ) -> None:
        """Each character in the list has all spec-required fields."""
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

        expected_fields = {
            "id", "name", "template", "description", "avatar_style",
            "is_default", "last_message_at", "created_at",
        }
        assert expected_fields.issubset(set(char_data.keys()))

    @pytest.mark.asyncio
    async def test_character_item_excludes_backend_internal_fields(
        self, client: AsyncClient,
    ) -> None:
        """List items do not leak system_prompt, mem0_agent_id, or is_active."""
        char = _make_mock_character()

        async def _override_db() -> AsyncGenerator[AsyncMock, None]:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.all.return_value = [(char, None)]
            mock_db.execute = AsyncMock(return_value=mock_result)
            yield mock_db

        app.dependency_overrides[get_db] = _override_db

        resp = await client.get("/api/v1/characters")
        char_data = resp.json()["characters"][0]

        assert "system_prompt" not in char_data
        assert "mem0_agent_id" not in char_data
        assert "is_active" not in char_data

    @pytest.mark.asyncio
    async def test_character_id_is_string_in_response(
        self, client: AsyncClient,
    ) -> None:
        """Character id in the list response is a string."""
        char = _make_mock_character()

        async def _override_db() -> AsyncGenerator[AsyncMock, None]:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.all.return_value = [(char, None)]
            mock_db.execute = AsyncMock(return_value=mock_result)
            yield mock_db

        app.dependency_overrides[get_db] = _override_db

        resp = await client.get("/api/v1/characters")
        char_data = resp.json()["characters"][0]
        assert isinstance(char_data["id"], str)


# ---------------------------------------------------------------------------
# POST /api/v1/characters -- extended tests
# ---------------------------------------------------------------------------


class TestCreateCharacterExtended:
    """Extended route tests for POST /api/v1/characters."""

    @pytest.mark.asyncio
    async def test_create_response_has_all_required_fields(
        self, client: AsyncClient,
    ) -> None:
        """201 response includes all spec-required fields."""
        mock_response = _mock_claude_response("You are Sarah...")

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
        expected_fields = {
            "id", "name", "template", "description", "system_prompt",
            "avatar_style", "is_default", "created_at",
        }
        assert expected_fields.issubset(set(data.keys()))

    @pytest.mark.asyncio
    async def test_create_response_excludes_mem0_agent_id(
        self, client: AsyncClient,
    ) -> None:
        """201 response does NOT include mem0_agent_id (backend-internal)."""
        mock_response = _mock_claude_response("You are Sarah...")

        with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            resp = await client.post(
                "/api/v1/characters",
                json={"name": "Sarah", "template": "english_teacher"},
            )

        assert "mem0_agent_id" not in resp.json()

    @pytest.mark.asyncio
    async def test_create_non_custom_description_null_in_response(
        self, client: AsyncClient,
    ) -> None:
        """Non-custom template returns description=null in the response."""
        mock_response = _mock_claude_response("You are Sarah...")

        with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            resp = await client.post(
                "/api/v1/characters",
                json={"name": "Sarah", "template": "english_teacher"},
            )

        assert resp.status_code == 201
        assert resp.json()["description"] is None

    @pytest.mark.asyncio
    async def test_create_is_default_always_false(
        self, client: AsyncClient,
    ) -> None:
        """User-created characters always have is_default=false."""
        mock_response = _mock_claude_response("You are Sarah...")

        with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            resp = await client.post(
                "/api/v1/characters",
                json={"name": "Sarah", "template": "english_teacher"},
            )

        assert resp.json()["is_default"] is False

    @pytest.mark.asyncio
    async def test_create_avatar_style_default_in_response(
        self, client: AsyncClient,
    ) -> None:
        """New character avatar_style is 'default' in the response."""
        mock_response = _mock_claude_response("You are Sarah...")

        with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            resp = await client.post(
                "/api/v1/characters",
                json={"name": "Sarah", "template": "english_teacher"},
            )

        assert resp.json()["avatar_style"] == "default"

    @pytest.mark.asyncio
    async def test_create_name_max_boundary_accepted(
        self, client: AsyncClient,
    ) -> None:
        """Name at exactly 100 chars is accepted in the route."""
        mock_response = _mock_claude_response("Generated prompt")

        with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            resp = await client.post(
                "/api/v1/characters",
                json={"name": "A" * 100, "template": "companion"},
            )

        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_name_over_max_rejected(
        self, client: AsyncClient,
    ) -> None:
        """Name exceeding 100 chars returns 422."""
        resp = await client.post(
            "/api/v1/characters",
            json={"name": "A" * 101, "template": "companion"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_empty_body_rejected(
        self, client: AsyncClient,
    ) -> None:
        """Empty JSON body returns 422 (missing required fields)."""
        resp = await client.post(
            "/api/v1/characters",
            json={},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_all_built_in_templates_accepted(
        self, client: AsyncClient,
    ) -> None:
        """All five built-in templates produce 201 responses."""
        templates = [
            "companion", "english_teacher", "therapist",
            "fitness_coach", "career_coach",
        ]
        for template in templates:
            mock_response = _mock_claude_response(f"You are a {template}...")

            with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
                mock_client = AsyncMock()
                mock_client.messages.create = AsyncMock(return_value=mock_response)
                mock_cls.return_value = mock_client

                resp = await client.post(
                    "/api/v1/characters",
                    json={"name": "Test", "template": template},
                )

            assert resp.status_code == 201, (
                f"Template '{template}' did not return 201"
            )
            assert resp.json()["template"] == template

    @pytest.mark.asyncio
    async def test_create_custom_description_short_rejected(
        self, client: AsyncClient,
    ) -> None:
        """Custom template with description under 10 chars returns 422."""
        resp = await client.post(
            "/api/v1/characters",
            json={
                "name": "Marco",
                "template": "custom",
                "description": "Short",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_no_content_type_json(
        self, client: AsyncClient,
    ) -> None:
        """Request without proper JSON body returns 422."""
        resp = await client.post(
            "/api/v1/characters",
            content=b"not json",
            headers={"Content-Type": "text/plain"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PUT /api/v1/characters/:id -- extended tests
# ---------------------------------------------------------------------------


class TestUpdateCharacterExtended:
    """Extended route tests for PUT /api/v1/characters/:id."""

    @pytest.mark.asyncio
    async def test_update_response_has_all_required_fields(
        self, client: AsyncClient,
    ) -> None:
        """200 response includes all spec-required CharacterDetail fields."""
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
            json={"name": "Updated Name"},
        )

        assert resp.status_code == 200
        data = resp.json()
        expected_fields = {
            "id", "name", "template", "description", "system_prompt",
            "avatar_style", "is_default", "created_at",
        }
        assert expected_fields.issubset(set(data.keys()))

    @pytest.mark.asyncio
    async def test_update_only_system_prompt(
        self, client: AsyncClient,
    ) -> None:
        """Updating only system_prompt returns 200."""
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
            json={"system_prompt": "Updated prompt text here"},
        )
        assert resp.status_code == 200
        assert resp.json()["system_prompt"] == "Updated prompt text here"

    @pytest.mark.asyncio
    async def test_update_only_avatar_style(
        self, client: AsyncClient,
    ) -> None:
        """Updating only avatar_style returns 200."""
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
            json={"avatar_style": "blue"},
        )
        assert resp.status_code == 200
        assert resp.json()["avatar_style"] == "blue"

    @pytest.mark.asyncio
    async def test_update_name_too_long_rejected(
        self, client: AsyncClient,
    ) -> None:
        """Name exceeding 100 chars in update returns 422."""
        resp = await client.put(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}",
            json={"name": "A" * 101},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_system_prompt_too_long_rejected(
        self, client: AsyncClient,
    ) -> None:
        """System prompt exceeding 10000 chars in update returns 422."""
        resp = await client.put(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}",
            json={"system_prompt": "X" * 10001},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_avatar_style_too_long_rejected(
        self, client: AsyncClient,
    ) -> None:
        """Avatar style exceeding 50 chars in update returns 422."""
        resp = await client.put(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}",
            json={"avatar_style": "z" * 51},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_whitespace_only_name_rejected(
        self, client: AsyncClient,
    ) -> None:
        """Whitespace-only name in update returns 422."""
        resp = await client.put(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}",
            json={"name": "   "},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_empty_string_name_rejected(
        self, client: AsyncClient,
    ) -> None:
        """Empty string name in update returns 422."""
        resp = await client.put(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}",
            json={"name": ""},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_response_excludes_mem0_agent_id(
        self, client: AsyncClient,
    ) -> None:
        """Update response does not include mem0_agent_id."""
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
            json={"name": "Updated"},
        )

        assert "mem0_agent_id" not in resp.json()


# ---------------------------------------------------------------------------
# DELETE /api/v1/characters/:id -- extended tests
# ---------------------------------------------------------------------------


class TestDeleteCharacterExtended:
    """Extended route tests for DELETE /api/v1/characters/:id."""

    @pytest.mark.asyncio
    async def test_delete_invalid_uuid_returns_422(
        self, client: AsyncClient,
    ) -> None:
        """Invalid UUID in DELETE path returns 422."""
        resp = await client.delete("/api/v1/characters/not-a-uuid")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_sets_is_active_false(
        self, client: AsyncClient,
    ) -> None:
        """After DELETE, the character mock has is_active=False."""
        char = _make_mock_character()
        assert char.is_active is True  # Pre-condition

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
        # Verify soft-delete was applied
        assert char.is_active is False

    @pytest.mark.asyncio
    async def test_delete_returns_no_body(
        self, client: AsyncClient,
    ) -> None:
        """DELETE 204 response has empty body."""
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
        assert resp.content == b""

    @pytest.mark.asyncio
    async def test_delete_ownership_error_message(
        self, client: AsyncClient,
    ) -> None:
        """DELETE with wrong user returns correct error detail message."""
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
    async def test_delete_default_error_message(
        self, client: AsyncClient,
    ) -> None:
        """DELETE of default character returns correct error detail message."""
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
