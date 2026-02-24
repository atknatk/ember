"""Extended schema tests for character Pydantic schemas.

Covers boundary conditions, edge cases, and structural validation not
covered by the base test_character_schemas.py file.
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

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.schemas.character import (  # noqa: E402
    CharacterDetail,
    CharacterListItem,
    CharacterListResponse,
    CreateCharacterRequest,
    UpdateCharacterRequest,
)

# ---------------------------------------------------------------------------
# CreateCharacterRequest boundary tests
# ---------------------------------------------------------------------------


class TestCreateCharacterRequestBoundaries:
    """Boundary and edge case tests for CreateCharacterRequest."""

    def test_name_exactly_one_char(self) -> None:
        """Single-character name is accepted (min_length=1)."""
        req = CreateCharacterRequest(name="A", template="companion")
        assert req.name == "A"

    def test_name_exactly_100_chars(self) -> None:
        """Name at the maximum length boundary (100 chars) is accepted."""
        long_name = "A" * 100
        req = CreateCharacterRequest(name=long_name, template="companion")
        assert req.name == long_name
        assert len(req.name) == 100

    def test_name_over_100_chars_rejected(self) -> None:
        """Name exceeding 100 characters is rejected."""
        with pytest.raises(ValidationError):
            CreateCharacterRequest(name="A" * 101, template="companion")

    def test_empty_string_name_rejected(self) -> None:
        """Empty string name is rejected (min_length=1)."""
        with pytest.raises(ValidationError):
            CreateCharacterRequest(name="", template="companion")

    def test_name_with_unicode_chars_accepted(self) -> None:
        """Name with unicode characters is accepted."""
        req = CreateCharacterRequest(name="Ayse", template="companion")
        assert req.name == "Ayse"

    def test_name_with_special_chars_accepted(self) -> None:
        """Name with special characters and dashes is accepted."""
        req = CreateCharacterRequest(
            name="Dr. Sarah O'Brien-Smith",
            template="companion",
        )
        assert req.name == "Dr. Sarah O'Brien-Smith"

    def test_name_with_leading_trailing_spaces_stripped(self) -> None:
        """Whitespace-padded name with content is stripped but accepted."""
        req = CreateCharacterRequest(
            name="  Sarah  ",
            template="therapist",
        )
        assert req.name == "Sarah"

    def test_custom_description_exactly_10_chars(self) -> None:
        """Custom template with description of exactly 10 chars (min boundary) is accepted."""
        req = CreateCharacterRequest(
            name="Test",
            template="custom",
            description="A" * 10,
        )
        assert len(req.description) == 10

    def test_custom_description_9_chars_rejected(self) -> None:
        """Custom template with description under 10 chars is rejected."""
        with pytest.raises(
            ValidationError,
            match="Description is required for custom characters",
        ):
            CreateCharacterRequest(
                name="Test",
                template="custom",
                description="A" * 9,
            )

    def test_custom_description_exactly_1000_chars(self) -> None:
        """Custom template with description at max length (1000 chars) is accepted."""
        desc = "A" * 1000
        req = CreateCharacterRequest(
            name="Test",
            template="custom",
            description=desc,
        )
        assert len(req.description) == 1000

    def test_custom_description_over_1000_chars_rejected(self) -> None:
        """Custom template with description exceeding 1000 chars is rejected."""
        with pytest.raises(ValidationError):
            CreateCharacterRequest(
                name="Test",
                template="custom",
                description="A" * 1001,
            )

    def test_custom_description_whitespace_only_rejected(self) -> None:
        """Custom template with whitespace-only description is rejected."""
        with pytest.raises(
            ValidationError,
            match="Description is required for custom characters",
        ):
            CreateCharacterRequest(
                name="Test",
                template="custom",
                description="          ",  # 10 spaces -- strip results in empty
            )

    def test_custom_description_stripped(self) -> None:
        """Custom template description has whitespace stripped."""
        req = CreateCharacterRequest(
            name="Test",
            template="custom",
            description="   A valid description here   ",
        )
        assert req.description == "A valid description here"
        assert not req.description.startswith(" ")
        assert not req.description.endswith(" ")

    def test_custom_with_empty_string_description_rejected(self) -> None:
        """Custom template with empty string description is rejected."""
        with pytest.raises(ValidationError):
            CreateCharacterRequest(
                name="Test",
                template="custom",
                description="",
            )

    def test_non_custom_with_null_description_accepted(self) -> None:
        """Non-custom template with explicit null description is accepted."""
        req = CreateCharacterRequest(
            name="Sarah",
            template="english_teacher",
            description=None,
        )
        assert req.description is None

    def test_missing_name_rejected(self) -> None:
        """Request without name field raises ValidationError."""
        with pytest.raises(ValidationError):
            CreateCharacterRequest(template="companion")  # type: ignore[call-arg]

    def test_missing_template_rejected(self) -> None:
        """Request without template field raises ValidationError."""
        with pytest.raises(ValidationError):
            CreateCharacterRequest(name="Test")  # type: ignore[call-arg]

    def test_template_case_sensitive(self) -> None:
        """Template validation is case-sensitive."""
        with pytest.raises(ValidationError, match="Invalid template"):
            CreateCharacterRequest(name="Test", template="Companion")

        with pytest.raises(ValidationError, match="Invalid template"):
            CreateCharacterRequest(name="Test", template="ENGLISH_TEACHER")


# ---------------------------------------------------------------------------
# UpdateCharacterRequest boundary tests
# ---------------------------------------------------------------------------


class TestUpdateCharacterRequestBoundaries:
    """Boundary and edge case tests for UpdateCharacterRequest."""

    def test_empty_string_name_rejected(self) -> None:
        """Empty string name is rejected (min_length=1)."""
        with pytest.raises(ValidationError):
            UpdateCharacterRequest(name="")

    def test_name_at_max_length(self) -> None:
        """Name at exactly 100 chars is accepted."""
        long_name = "B" * 100
        req = UpdateCharacterRequest(name=long_name)
        assert req.name == long_name

    def test_name_over_max_length_rejected(self) -> None:
        """Name exceeding 100 chars is rejected."""
        with pytest.raises(ValidationError):
            UpdateCharacterRequest(name="B" * 101)

    def test_system_prompt_at_max_length(self) -> None:
        """System prompt at exactly 10000 chars is accepted."""
        prompt = "X" * 10000
        req = UpdateCharacterRequest(system_prompt=prompt)
        assert req.system_prompt == prompt
        assert len(req.system_prompt) == 10000

    def test_system_prompt_over_max_length_rejected(self) -> None:
        """System prompt exceeding 10000 chars is rejected."""
        with pytest.raises(ValidationError):
            UpdateCharacterRequest(system_prompt="X" * 10001)

    def test_system_prompt_empty_string_rejected(self) -> None:
        """Empty string system_prompt is rejected (min_length=1)."""
        with pytest.raises(ValidationError):
            UpdateCharacterRequest(system_prompt="")

    def test_avatar_style_at_max_length(self) -> None:
        """Avatar style at exactly 50 chars is accepted."""
        style = "z" * 50
        req = UpdateCharacterRequest(avatar_style=style)
        assert req.avatar_style == style

    def test_avatar_style_over_max_length_rejected(self) -> None:
        """Avatar style exceeding 50 chars is rejected."""
        with pytest.raises(ValidationError):
            UpdateCharacterRequest(avatar_style="z" * 51)

    def test_only_system_prompt_provided(self) -> None:
        """Providing only system_prompt succeeds."""
        req = UpdateCharacterRequest(system_prompt="You are a test character")
        assert req.system_prompt == "You are a test character"
        assert req.name is None
        assert req.avatar_style is None

    def test_only_avatar_style_provided(self) -> None:
        """Providing only avatar_style succeeds."""
        req = UpdateCharacterRequest(avatar_style="blue")
        assert req.avatar_style == "blue"
        assert req.name is None
        assert req.system_prompt is None

    def test_explicit_null_for_all_fields_rejected(self) -> None:
        """Explicitly setting all fields to null is rejected."""
        with pytest.raises(
            ValidationError,
            match="At least one field must be provided for update",
        ):
            UpdateCharacterRequest(
                name=None,
                system_prompt=None,
                avatar_style=None,
            )

    def test_name_with_internal_whitespace_preserved(self) -> None:
        """Internal whitespace in name is preserved (only leading/trailing stripped)."""
        req = UpdateCharacterRequest(name="  Sarah Jane  ")
        assert req.name == "Sarah Jane"


# ---------------------------------------------------------------------------
# CharacterListItem structural tests
# ---------------------------------------------------------------------------


class TestCharacterListItemStructure:
    """Structural validation for CharacterListItem response schema."""

    def test_does_not_include_system_prompt(self) -> None:
        """CharacterListItem schema fields do not include system_prompt."""
        field_names = set(CharacterListItem.model_fields.keys())
        assert "system_prompt" not in field_names

    def test_does_not_include_mem0_agent_id(self) -> None:
        """CharacterListItem schema fields do not include mem0_agent_id."""
        field_names = set(CharacterListItem.model_fields.keys())
        assert "mem0_agent_id" not in field_names

    def test_does_not_include_is_active(self) -> None:
        """CharacterListItem schema fields do not include is_active."""
        field_names = set(CharacterListItem.model_fields.keys())
        assert "is_active" not in field_names

    def test_includes_all_expected_fields(self) -> None:
        """CharacterListItem has all fields specified in the feature spec."""
        expected = {
            "id", "name", "template", "description", "avatar_style",
            "is_default", "last_message_at", "created_at",
        }
        actual = set(CharacterListItem.model_fields.keys())
        assert expected == actual

    def test_last_message_at_null_accepted(self) -> None:
        """CharacterListItem allows null last_message_at."""
        item = CharacterListItem(
            id=str(uuid.uuid4()),
            name="Test",
            template="companion",
            description=None,
            avatar_style="default",
            is_default=False,
            last_message_at=None,
            created_at=datetime.now(tz=UTC),
        )
        assert item.last_message_at is None

    def test_last_message_at_datetime_accepted(self) -> None:
        """CharacterListItem accepts a datetime for last_message_at."""
        now = datetime.now(tz=UTC)
        item = CharacterListItem(
            id=str(uuid.uuid4()),
            name="Test",
            template="companion",
            description=None,
            avatar_style="default",
            is_default=False,
            last_message_at=now,
            created_at=now,
        )
        assert item.last_message_at == now


# ---------------------------------------------------------------------------
# CharacterDetail structural tests
# ---------------------------------------------------------------------------


class TestCharacterDetailStructure:
    """Structural validation for CharacterDetail response schema."""

    def test_does_not_include_last_message_at(self) -> None:
        """CharacterDetail does not include last_message_at (that is for list only)."""
        field_names = set(CharacterDetail.model_fields.keys())
        assert "last_message_at" not in field_names

    def test_does_not_include_mem0_agent_id(self) -> None:
        """CharacterDetail does not include mem0_agent_id (backend-internal)."""
        field_names = set(CharacterDetail.model_fields.keys())
        assert "mem0_agent_id" not in field_names

    def test_does_not_include_is_active(self) -> None:
        """CharacterDetail does not include is_active."""
        field_names = set(CharacterDetail.model_fields.keys())
        assert "is_active" not in field_names

    def test_includes_system_prompt(self) -> None:
        """CharacterDetail includes system_prompt (unlike CharacterListItem)."""
        field_names = set(CharacterDetail.model_fields.keys())
        assert "system_prompt" in field_names

    def test_includes_all_expected_fields(self) -> None:
        """CharacterDetail has all fields specified in the feature spec."""
        expected = {
            "id", "name", "template", "description", "system_prompt",
            "avatar_style", "is_default", "created_at",
        }
        actual = set(CharacterDetail.model_fields.keys())
        assert expected == actual


# ---------------------------------------------------------------------------
# CharacterListResponse tests
# ---------------------------------------------------------------------------


class TestCharacterListResponse:
    """Tests for CharacterListResponse wrapper schema."""

    def test_wraps_list_of_items(self) -> None:
        """CharacterListResponse wraps a list of CharacterListItem objects."""
        items = [
            CharacterListItem(
                id=str(uuid.uuid4()),
                name="Ember",
                template="companion",
                description=None,
                avatar_style="default",
                is_default=True,
                last_message_at=None,
                created_at=datetime.now(tz=UTC),
            ),
        ]
        resp = CharacterListResponse(characters=items)
        assert len(resp.characters) == 1
        assert resp.characters[0].name == "Ember"

    def test_empty_characters_list(self) -> None:
        """CharacterListResponse with empty list is valid."""
        resp = CharacterListResponse(characters=[])
        assert resp.characters == []
