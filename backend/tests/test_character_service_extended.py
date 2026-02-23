"""Extended unit tests for CharacterService business logic.

Covers additional scenarios not in the base test_character_service.py:
- Conversation auto-creation verification (correct fields)
- Claude Haiku call parameters (model, max_tokens)
- Meta-prompt content for all built-in templates
- Update with all fields at once
- Soft delete verification (no db.delete call)
- Multiple Claude error types (timeout, rate limit)
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

from app.models.character import Character  # noqa: E402
from app.models.conversation import Conversation  # noqa: E402
from app.services.character_service import (  # noqa: E402
    TEMPLATE_ROLES,
    CharacterService,
    _build_meta_prompt,
)

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
    name: str = "Sarah",
    is_default: bool = False,
    is_active: bool = True,
) -> MagicMock:
    """Create a MagicMock that looks like a Character ORM instance."""
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


def _make_db_mock() -> AsyncMock:
    """Create a base AsyncMock for the database session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _make_db_mock_for_create() -> AsyncMock:
    """Create a DB mock suitable for create_character calls."""
    db = _make_db_mock()
    # No existing agent_id conflict
    mock_agent_result = MagicMock()
    mock_agent_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_agent_result)

    async def _fake_refresh(obj: object) -> None:
        if not hasattr(obj, "created_at") or getattr(obj, "created_at", None) is None:
            object.__setattr__(obj, "created_at", datetime.now(tz=UTC))

    db.refresh = AsyncMock(side_effect=_fake_refresh)
    return db


# ---------------------------------------------------------------------------
# _build_meta_prompt tests
# ---------------------------------------------------------------------------


class TestBuildMetaPrompt:
    """Tests for the _build_meta_prompt helper function."""

    def test_built_in_template_includes_role_description(self) -> None:
        """Built-in template meta-prompt includes the correct role description."""
        for template_name, role_desc in TEMPLATE_ROLES.items():
            prompt = _build_meta_prompt(
                character_name="Test",
                user_name="Alex",
                template=template_name,
                description=None,
            )
            assert role_desc in prompt, (
                f"Role description missing for template '{template_name}'"
            )

    def test_built_in_template_includes_character_name(self) -> None:
        """Built-in template meta-prompt includes the character name."""
        prompt = _build_meta_prompt(
            character_name="Sarah",
            user_name="Alex",
            template="english_teacher",
            description=None,
        )
        assert "Sarah" in prompt

    def test_built_in_template_includes_user_name(self) -> None:
        """Built-in template meta-prompt includes the user name."""
        prompt = _build_meta_prompt(
            character_name="Sarah",
            user_name="Alex",
            template="english_teacher",
            description=None,
        )
        assert "Alex" in prompt

    def test_custom_template_includes_user_description(self) -> None:
        """Custom template meta-prompt includes the user's description."""
        desc = "An Italian language teacher who only speaks Italian"
        prompt = _build_meta_prompt(
            character_name="Marco",
            user_name="Alex",
            template="custom",
            description=desc,
        )
        assert desc in prompt

    def test_custom_template_includes_character_name_and_user_name(self) -> None:
        """Custom template meta-prompt includes both names."""
        prompt = _build_meta_prompt(
            character_name="Marco",
            user_name="Alex",
            template="custom",
            description="A custom character description here",
        )
        assert "Marco" in prompt
        assert "Alex" in prompt

    def test_built_in_template_does_not_include_description_field(self) -> None:
        """Built-in template meta-prompt uses Role, not description."""
        prompt = _build_meta_prompt(
            character_name="Sarah",
            user_name="Alex",
            template="english_teacher",
            description=None,
        )
        assert "Role:" in prompt
        assert "Character description (provided by the user):" not in prompt

    def test_custom_template_does_not_include_role_field(self) -> None:
        """Custom template meta-prompt uses description, not Role."""
        prompt = _build_meta_prompt(
            character_name="Marco",
            user_name="Alex",
            template="custom",
            description="Custom desc for testing",
        )
        assert "Character description (provided by the user):" in prompt
        assert "Role:" not in prompt

    def test_meta_prompt_instructions_present(self) -> None:
        """All meta-prompts include the required generation instructions."""
        prompt = _build_meta_prompt(
            character_name="Test",
            user_name="Alex",
            template="companion",
            description=None,
        )
        assert "second person" in prompt
        assert "100-300 words" in prompt
        assert "Output ONLY the system prompt text" in prompt


# ---------------------------------------------------------------------------
# Create Character extended tests
# ---------------------------------------------------------------------------


class TestCreateCharacterExtended:
    """Extended tests for CharacterService.create_character."""

    @pytest.mark.asyncio
    async def test_conversation_has_correct_character_id(self) -> None:
        """Auto-created Conversation row references the new character's id."""
        db = _make_db_mock_for_create()
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

        added_objects = [call.args[0] for call in db.add.call_args_list]
        character_obj = next(
            obj for obj in added_objects if isinstance(obj, Character)
        )
        conversation_obj = next(
            obj for obj in added_objects if isinstance(obj, Conversation)
        )

        assert conversation_obj.character_id == character_obj.id
        assert conversation_obj.user_id == FAKE_USER_ID

    @pytest.mark.asyncio
    async def test_conversation_has_null_last_message_at(self) -> None:
        """Auto-created Conversation starts with last_message_at=None."""
        db = _make_db_mock_for_create()
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

        added_objects = [call.args[0] for call in db.add.call_args_list]
        conversation_obj = next(
            obj for obj in added_objects if isinstance(obj, Conversation)
        )
        assert conversation_obj.last_message_at is None

    @pytest.mark.asyncio
    async def test_claude_called_with_correct_model(self) -> None:
        """Claude Haiku is called with settings.claude_haiku_model."""
        db = _make_db_mock_for_create()
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

        call_kwargs = mock_client.messages.create.call_args.kwargs
        # The model should be from settings, which defaults to claude-haiku-4-5
        assert call_kwargs["model"] == "claude-haiku-4-5"

    @pytest.mark.asyncio
    async def test_claude_called_with_max_tokens_512(self) -> None:
        """Claude Haiku is called with max_tokens=512."""
        db = _make_db_mock_for_create()
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

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 512

    @pytest.mark.asyncio
    async def test_character_avatar_style_defaults_to_default(self) -> None:
        """New character avatar_style is always 'default'."""
        db = _make_db_mock_for_create()
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

        assert result.avatar_style == "default"

    @pytest.mark.asyncio
    async def test_character_description_null_for_non_custom(self) -> None:
        """Non-custom character has description=None in the result."""
        db = _make_db_mock_for_create()
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

        assert result.description is None

    @pytest.mark.asyncio
    async def test_character_description_set_for_custom(self) -> None:
        """Custom character preserves the user-provided description."""
        db = _make_db_mock_for_create()
        mock_response = _mock_claude_response()
        desc = "An Italian language teacher who only speaks Italian"

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
                description=desc,
            )

        assert result.description == desc

    @pytest.mark.asyncio
    async def test_raises_503_on_timeout_error(self) -> None:
        """Timeout errors from Claude API are caught and produce 503."""
        db = _make_db_mock()

        with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=TimeoutError("Connection timed out"),
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

    @pytest.mark.asyncio
    async def test_raises_503_on_runtime_error(self) -> None:
        """RuntimeError from Claude API is caught and produces 503."""
        db = _make_db_mock()

        with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=RuntimeError("Rate limit exceeded"),
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

    @pytest.mark.asyncio
    async def test_mem0_agent_id_fallback_includes_short_uuid(self) -> None:
        """When agent_id conflicts, fallback includes 8-char UUID prefix."""
        db = _make_db_mock()

        # Simulate existing agent_id conflict
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

        added_objects = [call.args[0] for call in db.add.call_args_list]
        character_obj = next(
            obj for obj in added_objects if isinstance(obj, Character)
        )

        agent_id = character_obj.mem0_agent_id
        # Format: {template}_{short_uuid}_{user_id}
        parts = agent_id.split("_")
        # The short_uuid should be 8 characters
        # Agent id pattern: english_teacher_{8chars}_{user_id}
        assert agent_id.startswith("english_teacher_")
        assert str(FAKE_USER_ID) in agent_id
        # The middle segment (short uuid) should be 8 chars from the character UUID
        short_uuid_part = agent_id.replace(f"english_teacher_", "").replace(
            f"_{FAKE_USER_ID}", ""
        )
        assert len(short_uuid_part) == 8

    @pytest.mark.asyncio
    async def test_create_each_built_in_template(self) -> None:
        """All five built-in templates can be created successfully."""
        templates = [
            "companion", "english_teacher", "therapist",
            "fitness_coach", "career_coach",
        ]

        for template in templates:
            db = _make_db_mock_for_create()
            mock_response = _mock_claude_response(f"You are a {template}...")

            with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
                mock_client = AsyncMock()
                mock_client.messages.create = AsyncMock(return_value=mock_response)
                mock_cls.return_value = mock_client

                service = CharacterService(db)
                result = await service.create_character(
                    user_id=FAKE_USER_ID,
                    user_name=FAKE_USER_NAME,
                    name="TestChar",
                    template=template,
                    description=None,
                )

            assert result.template == template
            assert result.system_prompt == f"You are a {template}..."


# ---------------------------------------------------------------------------
# Update Character extended tests
# ---------------------------------------------------------------------------


class TestUpdateCharacterExtended:
    """Extended tests for CharacterService.update_character."""

    @pytest.mark.asyncio
    async def test_update_all_three_fields(self) -> None:
        """Updating name, system_prompt, and avatar_style all at once succeeds."""
        db = _make_db_mock()
        char = _make_mock_character()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = char
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        await service.update_character(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            name="New Name",
            system_prompt="New prompt text",
            avatar_style="red",
        )

        assert char.name == "New Name"
        assert char.system_prompt == "New prompt text"
        assert char.avatar_style == "red"
        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_only_system_prompt(self) -> None:
        """Updating only system_prompt leaves name and avatar_style unchanged."""
        db = _make_db_mock()
        char = _make_mock_character()
        original_name = char.name
        original_avatar = char.avatar_style

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = char
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        await service.update_character(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            name=None,
            system_prompt="Updated prompt",
            avatar_style=None,
        )

        assert char.name == original_name
        assert char.system_prompt == "Updated prompt"
        assert char.avatar_style == original_avatar

    @pytest.mark.asyncio
    async def test_update_only_avatar_style(self) -> None:
        """Updating only avatar_style leaves name and system_prompt unchanged."""
        db = _make_db_mock()
        char = _make_mock_character()
        original_name = char.name
        original_prompt = char.system_prompt

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = char
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        await service.update_character(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            name=None,
            system_prompt=None,
            avatar_style="blue",
        )

        assert char.name == original_name
        assert char.system_prompt == original_prompt
        assert char.avatar_style == "blue"

    @pytest.mark.asyncio
    async def test_update_commits_transaction(self) -> None:
        """Update commits the transaction to the database."""
        db = _make_db_mock()
        char = _make_mock_character()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = char
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        await service.update_character(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            name="Updated",
            system_prompt=None,
            avatar_style=None,
        )

        db.commit.assert_called_once()
        db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_returns_character_detail(self) -> None:
        """Update returns a CharacterDetail response schema object."""
        db = _make_db_mock()
        char = _make_mock_character()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = char
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        result = await service.update_character(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            name="Updated",
            system_prompt=None,
            avatar_style=None,
        )

        from app.schemas.character import CharacterDetail
        assert isinstance(result, CharacterDetail)
        assert result.name == "Updated"


# ---------------------------------------------------------------------------
# Delete Character extended tests
# ---------------------------------------------------------------------------


class TestDeleteCharacterExtended:
    """Extended tests for CharacterService.delete_character."""

    @pytest.mark.asyncio
    async def test_soft_delete_does_not_call_db_delete(self) -> None:
        """Soft delete sets is_active=False, does NOT call db.delete()."""
        db = _make_db_mock()
        char = _make_mock_character()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = char
        db.execute = AsyncMock(return_value=mock_result)
        db.delete = AsyncMock()

        service = CharacterService(db)
        await service.delete_character(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
        )

        # The row should NOT be physically deleted
        db.delete.assert_not_called()
        # But is_active should be set to False
        assert char.is_active is False

    @pytest.mark.asyncio
    async def test_delete_commits_transaction(self) -> None:
        """Delete commits the transaction to persist the soft delete."""
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

        db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_ownership_checked_before_default_check(self) -> None:
        """When character belongs to another user who has is_default=True, ownership fails first."""
        db = _make_db_mock()
        # Character belongs to another user AND is default
        char = _make_mock_character(user_id=OTHER_USER_ID, is_default=True)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = char
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        with pytest.raises(HTTPException) as exc_info:
            await service.delete_character(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
            )

        # The ownership check should run first, producing 403 ownership error
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Character does not belong to user"

    @pytest.mark.asyncio
    async def test_delete_returns_none(self) -> None:
        """Delete returns None (no response body for 204)."""
        db = _make_db_mock()
        char = _make_mock_character()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = char
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        result = await service.delete_character(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
        )

        assert result is None


# ---------------------------------------------------------------------------
# List Characters extended tests
# ---------------------------------------------------------------------------


class TestListCharactersExtended:
    """Extended tests for CharacterService.list_characters."""

    @pytest.mark.asyncio
    async def test_list_returns_character_list_item_objects(self) -> None:
        """Items returned are CharacterListItem schema objects."""
        db = _make_db_mock()
        char = _make_mock_character()

        mock_result = MagicMock()
        mock_result.all.return_value = [(char, None)]
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        items = await service.list_characters(user_id=FAKE_USER_ID)

        from app.schemas.character import CharacterListItem
        assert len(items) == 1
        assert isinstance(items[0], CharacterListItem)

    @pytest.mark.asyncio
    async def test_list_item_id_is_string(self) -> None:
        """Character id in list items is coerced to string."""
        db = _make_db_mock()
        char = _make_mock_character()

        mock_result = MagicMock()
        mock_result.all.return_value = [(char, None)]
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        items = await service.list_characters(user_id=FAKE_USER_ID)

        assert isinstance(items[0].id, str)
        assert items[0].id == str(FAKE_CHARACTER_ID)

    @pytest.mark.asyncio
    async def test_list_maps_all_fields_correctly(self) -> None:
        """All fields are correctly mapped from the query result."""
        db = _make_db_mock()
        now = datetime.now(tz=UTC)
        char = _make_mock_character(is_default=True, template="companion")
        char.name = "Ember"
        char.description = None
        char.avatar_style = "warm"

        mock_result = MagicMock()
        mock_result.all.return_value = [(char, now)]
        db.execute = AsyncMock(return_value=mock_result)

        service = CharacterService(db)
        items = await service.list_characters(user_id=FAKE_USER_ID)

        item = items[0]
        assert item.name == "Ember"
        assert item.template == "companion"
        assert item.description is None
        assert item.avatar_style == "warm"
        assert item.is_default is True
        assert item.last_message_at == now
