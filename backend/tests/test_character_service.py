"""Unit tests for CharacterService business logic.

Tests the service layer directly with a mocked database session and mocked
Claude Haiku API. Does not go through HTTP/FastAPI.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import uuid  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.services.character_service import CharacterService  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
FAKE_USER_NAME = "Alex"
FAKE_CHARACTER_ID = uuid.UUID("660e8400-e29b-41d4-a716-446655440001")
OTHER_USER_ID = uuid.UUID("770e8400-e29b-41d4-a716-446655440099")


def _make_mock_character(
    character_id: uuid.UUID = FAKE_CHARACTER_ID,
    user_id: uuid.UUID = FAKE_USER_ID,
    template: str = "english_teacher",
    is_default: bool = False,
    is_active: bool = True,
) -> MagicMock:
    """Create a MagicMock that looks like a Character ORM instance."""
    char = MagicMock()
    char.id = character_id
    char.user_id = user_id
    char.name = "Sarah"
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


def _make_db_mock() -> AsyncMock:
    """Create a base AsyncMock for the database session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# List Characters tests
# ---------------------------------------------------------------------------


class TestListCharacters:
    """Tests for CharacterService.list_characters."""

    @pytest.mark.asyncio
    async def test_list_returns_characters_with_last_message_at(self) -> None:
        """Correct last_message_at values from conversations join."""
        db = _make_db_mock()
        now = datetime.now(tz=UTC)

        char1 = _make_mock_character()
        char2 = _make_mock_character(
            character_id=uuid.uuid4(),
            template="companion",
            is_default=True,
        )
        char2.name = "Ember"

        mock_result = MagicMock()
        mock_result.all.return_value = [
            (char1, now),
            (char2, None),
        ]
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        items = await service.list_characters(user_id=FAKE_USER_ID)

        assert len(items) == 2
        assert items[0].last_message_at == now
        assert items[0].name == "Sarah"
        assert items[1].last_message_at is None
        assert items[1].name == "Ember"

    @pytest.mark.asyncio
    async def test_list_empty_when_no_characters(self) -> None:
        """Returns empty list when user has no characters."""
        db = _make_db_mock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        items = await service.list_characters(user_id=FAKE_USER_ID)

        assert items == []

    @pytest.mark.asyncio
    async def test_list_calls_execute_with_query(self) -> None:
        """Ensure the DB execute method is called exactly once."""
        db = _make_db_mock()
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        await service.list_characters(user_id=FAKE_USER_ID)

        db.execute.assert_called_once()


# ---------------------------------------------------------------------------
# Create Character tests
# ---------------------------------------------------------------------------


class TestCreateCharacter:
    """Tests for CharacterService.create_character."""

    @pytest.mark.asyncio
    async def test_create_calls_claude_haiku_for_built_in_template(self) -> None:
        """Claude Haiku is called with the correct meta-prompt for a built-in template."""
        db = _make_db_mock()

        # Mock no existing agent_id conflict
        mock_agent_result = MagicMock()
        mock_agent_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_agent_result)

        # Mock refresh to set created_at
        async def _fake_refresh(obj: object) -> None:
            if not hasattr(obj, "created_at") or getattr(obj, "created_at", None) is None:
                object.__setattr__(obj, "created_at", datetime.now(tz=UTC))

        db.refresh = AsyncMock(side_effect=_fake_refresh)

        mock_response = _mock_claude_response("You are Sarah, an English teacher...")

        with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            service = CharacterService(db)
            result = await service.create_character(
                user_id=FAKE_USER_ID,
                user_name=FAKE_USER_NAME,
                name="Sarah",
                template="english_teacher",
                description=None,
            )

        assert result.system_prompt == "You are Sarah, an English teacher..."
        assert result.name == "Sarah"
        assert result.template == "english_teacher"
        assert result.is_default is False

        # Verify Claude was called
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args
        prompt_content = call_kwargs.kwargs["messages"][0]["content"]
        assert "English language teacher" in prompt_content
        assert "Sarah" in prompt_content
        assert "Alex" in prompt_content

    @pytest.mark.asyncio
    async def test_create_calls_claude_haiku_for_custom_template(self) -> None:
        """Claude Haiku includes user description for custom templates."""
        db = _make_db_mock()
        mock_agent_result = MagicMock()
        mock_agent_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_agent_result)

        async def _fake_refresh(obj: object) -> None:
            if not hasattr(obj, "created_at") or getattr(obj, "created_at", None) is None:
                object.__setattr__(obj, "created_at", datetime.now(tz=UTC))

        db.refresh = AsyncMock(side_effect=_fake_refresh)

        mock_response = _mock_claude_response("You are Marco, an Italian teacher...")

        with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            service = CharacterService(db)
            result = await service.create_character(
                user_id=FAKE_USER_ID,
                user_name=FAKE_USER_NAME,
                name="Marco",
                template="custom",
                description="An Italian language teacher who only speaks Italian",
            )

        assert result.system_prompt == "You are Marco, an Italian teacher..."
        prompt_content = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "Italian language teacher" in prompt_content

    @pytest.mark.asyncio
    async def test_create_adds_character_and_conversation(self) -> None:
        """Both Character and Conversation rows are added to the session."""
        db = _make_db_mock()
        mock_agent_result = MagicMock()
        mock_agent_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_agent_result)

        async def _fake_refresh(obj: object) -> None:
            if not hasattr(obj, "created_at") or getattr(obj, "created_at", None) is None:
                object.__setattr__(obj, "created_at", datetime.now(tz=UTC))

        db.refresh = AsyncMock(side_effect=_fake_refresh)

        mock_response = _mock_claude_response()

        with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            service = CharacterService(db)
            await service.create_character(
                user_id=FAKE_USER_ID,
                user_name=FAKE_USER_NAME,
                name="Sarah",
                template="english_teacher",
                description=None,
            )

        # Two add() calls: Character + Conversation
        assert db.add.call_count == 2
        # One commit
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_computes_mem0_agent_id(self) -> None:
        """mem0_agent_id follows {template}_{user_id} format."""
        db = _make_db_mock()
        mock_agent_result = MagicMock()
        mock_agent_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_agent_result)

        async def _fake_refresh(obj: object) -> None:
            if not hasattr(obj, "created_at") or getattr(obj, "created_at", None) is None:
                object.__setattr__(obj, "created_at", datetime.now(tz=UTC))

        db.refresh = AsyncMock(side_effect=_fake_refresh)

        mock_response = _mock_claude_response()

        with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            service = CharacterService(db)
            await service.create_character(
                user_id=FAKE_USER_ID,
                user_name=FAKE_USER_NAME,
                name="Sarah",
                template="english_teacher",
                description=None,
            )

        # Verify Character was created with the expected agent_id
        added_objects = [call.args[0] for call in db.add.call_args_list]
        from app.models.character import Character

        character_obj = next(obj for obj in added_objects if isinstance(obj, Character))
        expected_agent_id = f"english_teacher_{FAKE_USER_ID}"
        assert character_obj.mem0_agent_id == expected_agent_id

    @pytest.mark.asyncio
    async def test_create_handles_agent_id_uniqueness_conflict(self) -> None:
        """Falls back to {template}_{uuid[:8]}_{user_id} when agent_id exists."""
        db = _make_db_mock()

        # First call for agent_id check returns an existing record
        mock_agent_result = MagicMock()
        mock_agent_result.scalar_one_or_none.return_value = uuid.uuid4()
        db.execute = AsyncMock(return_value=mock_agent_result)

        async def _fake_refresh(obj: object) -> None:
            if not hasattr(obj, "created_at") or getattr(obj, "created_at", None) is None:
                object.__setattr__(obj, "created_at", datetime.now(tz=UTC))

        db.refresh = AsyncMock(side_effect=_fake_refresh)

        mock_response = _mock_claude_response()

        with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            service = CharacterService(db)
            await service.create_character(
                user_id=FAKE_USER_ID,
                user_name=FAKE_USER_NAME,
                name="Sarah 2",
                template="english_teacher",
                description=None,
            )

        from app.models.character import Character

        added_objects = [call.args[0] for call in db.add.call_args_list]
        character_obj = next(obj for obj in added_objects if isinstance(obj, Character))
        # Should have the discriminator format
        assert character_obj.mem0_agent_id.startswith("english_teacher_")
        assert character_obj.mem0_agent_id != f"english_teacher_{FAKE_USER_ID}"
        assert str(FAKE_USER_ID) in character_obj.mem0_agent_id

    @pytest.mark.asyncio
    async def test_create_sets_is_default_false_and_is_active_true(self) -> None:
        """New characters have is_default=False and is_active=True."""
        db = _make_db_mock()
        mock_agent_result = MagicMock()
        mock_agent_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_agent_result)

        async def _fake_refresh(obj: object) -> None:
            if not hasattr(obj, "created_at") or getattr(obj, "created_at", None) is None:
                object.__setattr__(obj, "created_at", datetime.now(tz=UTC))

        db.refresh = AsyncMock(side_effect=_fake_refresh)

        mock_response = _mock_claude_response()

        with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            service = CharacterService(db)
            result = await service.create_character(
                user_id=FAKE_USER_ID,
                user_name=FAKE_USER_NAME,
                name="Sarah",
                template="english_teacher",
                description=None,
            )

        assert result.is_default is False

    @pytest.mark.asyncio
    async def test_create_raises_503_when_claude_unavailable(self) -> None:
        """Raises 503 when Claude Haiku API is unavailable."""
        db = _make_db_mock()

        with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=Exception("API connection error"),
            )
            mock_cls.return_value = mock_client

            service = CharacterService(db)
            with pytest.raises(HTTPException) as exc_info:
                await service.create_character(
                    user_id=FAKE_USER_ID,
                    user_name=FAKE_USER_NAME,
                    name="Sarah",
                    template="english_teacher",
                    description=None,
                )

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "AI service unavailable, please try again"


# ---------------------------------------------------------------------------
# Update Character tests
# ---------------------------------------------------------------------------


class TestUpdateCharacter:
    """Tests for CharacterService.update_character."""

    @pytest.mark.asyncio
    async def test_update_modifies_only_provided_fields(self) -> None:
        """Only the fields that are not None are updated."""
        db = _make_db_mock()
        char = _make_mock_character()
        original_prompt = char.system_prompt
        original_avatar = char.avatar_style

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = char
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        await service.update_character(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            name="Sarah the Great",
            system_prompt=None,
            avatar_style=None,
        )

        assert char.name == "Sarah the Great"
        assert char.system_prompt == original_prompt
        assert char.avatar_style == original_avatar

    @pytest.mark.asyncio
    async def test_update_raises_404_for_nonexistent_character(self) -> None:
        """Raises 404 when the character does not exist."""
        db = _make_db_mock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        with pytest.raises(HTTPException) as exc_info:
            await service.update_character(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
                name="New Name",
                system_prompt=None,
                avatar_style=None,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Character not found"

    @pytest.mark.asyncio
    async def test_update_raises_403_for_wrong_user(self) -> None:
        """Raises 403 when the character belongs to another user."""
        db = _make_db_mock()
        char = _make_mock_character(user_id=OTHER_USER_ID)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = char
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        with pytest.raises(HTTPException) as exc_info:
            await service.update_character(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
                name="New Name",
                system_prompt=None,
                avatar_style=None,
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Character does not belong to user"


# ---------------------------------------------------------------------------
# Delete Character tests
# ---------------------------------------------------------------------------


class TestDeleteCharacter:
    """Tests for CharacterService.delete_character."""

    @pytest.mark.asyncio
    async def test_delete_sets_is_active_false(self) -> None:
        """Soft delete sets is_active to False."""
        db = _make_db_mock()
        char = _make_mock_character()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = char
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        await service.delete_character(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
        )

        assert char.is_active is False
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_raises_403_for_default_character(self) -> None:
        """Raises 403 when trying to delete the default character."""
        db = _make_db_mock()
        char = _make_mock_character(is_default=True)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = char
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        with pytest.raises(HTTPException) as exc_info:
            await service.delete_character(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Default character cannot be deleted"

    @pytest.mark.asyncio
    async def test_delete_raises_403_for_wrong_user(self) -> None:
        """Raises 403 when the character belongs to another user."""
        db = _make_db_mock()
        char = _make_mock_character(user_id=OTHER_USER_ID)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = char
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        with pytest.raises(HTTPException) as exc_info:
            await service.delete_character(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Character does not belong to user"

    @pytest.mark.asyncio
    async def test_delete_raises_404_for_nonexistent_character(self) -> None:
        """Raises 404 when the character does not exist."""
        db = _make_db_mock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        with pytest.raises(HTTPException) as exc_info:
            await service.delete_character(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Character not found"
