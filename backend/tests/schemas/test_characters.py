"""Unit tests for character Pydantic schemas.

Validates request/response schema behaviour including field validation,
template constraints, and ORM-to-response mapping.
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
from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.schemas.character import (  # noqa: E402
    CharacterDetail,
    CharacterListItem,
    CreateCharacterRequest,
    UpdateCharacterRequest,
)

# ---------------------------------------------------------------------------
# CreateCharacterRequest tests
# ---------------------------------------------------------------------------


class TestCreateCharacterRequest:
    """Tests for CreateCharacterRequest schema validation."""

    def test_valid_built_in_template(self) -> None:
        """A valid built-in template without description succeeds."""
        req = CreateCharacterRequest(
            name="Sarah",
            template="english_teacher",
        )
        assert req.name == "Sarah"
        assert req.template == "english_teacher"
        assert req.description is None

    def test_valid_custom_template_with_description(self) -> None:
        """Custom template with a valid description succeeds."""
        req = CreateCharacterRequest(
            name="Marco",
            template="custom",
            description="An Italian language teacher. Only speaks Italian.",
        )
        assert req.template == "custom"
        assert req.description == "An Italian language teacher. Only speaks Italian."

    def test_strip_whitespace_from_name(self) -> None:
        """Leading/trailing whitespace is stripped from the name."""
        req = CreateCharacterRequest(
            name="  Sarah  ",
            template="companion",
        )
        assert req.name == "Sarah"

    def test_whitespace_only_name_rejected(self) -> None:
        """Name consisting only of whitespace is rejected."""
        with pytest.raises(ValidationError, match="Name must not be empty"):
            CreateCharacterRequest(
                name="   ",
                template="companion",
            )

    def test_invalid_template_rejected(self) -> None:
        """An invalid template value raises a ValidationError."""
        with pytest.raises(ValidationError, match="Invalid template"):
            CreateCharacterRequest(
                name="Test",
                template="invalid_template",
            )

    def test_custom_template_requires_description(self) -> None:
        """Custom template without description raises a ValidationError."""
        with pytest.raises(
            ValidationError,
            match="Description is required for custom characters",
        ):
            CreateCharacterRequest(
                name="Marco",
                template="custom",
            )

    def test_custom_template_short_description_rejected(self) -> None:
        """Custom template with description shorter than 10 chars is rejected."""
        with pytest.raises(
            ValidationError,
            match="Description is required for custom characters",
        ):
            CreateCharacterRequest(
                name="Marco",
                template="custom",
                description="Short",
            )

    def test_non_custom_template_rejects_description(self) -> None:
        """Non-custom template with a description raises a ValidationError."""
        with pytest.raises(
            ValidationError,
            match="Description is only allowed for custom characters",
        ):
            CreateCharacterRequest(
                name="Sarah",
                template="english_teacher",
                description="Some extra description",
            )

    def test_all_built_in_templates_accepted(self) -> None:
        """All built-in templates are valid."""
        templates = [
            "companion",
            "english_teacher",
            "therapist",
            "fitness_coach",
            "career_coach",
        ]
        for template in templates:
            req = CreateCharacterRequest(name="Test", template=template)
            assert req.template == template


# ---------------------------------------------------------------------------
# UpdateCharacterRequest tests
# ---------------------------------------------------------------------------


class TestUpdateCharacterRequest:
    """Tests for UpdateCharacterRequest schema validation."""

    def test_valid_name_only(self) -> None:
        """Providing only a new name succeeds."""
        req = UpdateCharacterRequest(name="New Name")
        assert req.name == "New Name"
        assert req.system_prompt is None
        assert req.avatar_style is None

    def test_valid_all_fields(self) -> None:
        """Providing all fields succeeds."""
        req = UpdateCharacterRequest(
            name="New Name",
            system_prompt="You are...",
            avatar_style="blue",
        )
        assert req.name == "New Name"
        assert req.system_prompt == "You are..."
        assert req.avatar_style == "blue"

    def test_at_least_one_field_required(self) -> None:
        """All-null request raises a ValidationError."""
        with pytest.raises(
            ValidationError,
            match="At least one field must be provided for update",
        ):
            UpdateCharacterRequest()

    def test_strip_whitespace_from_name(self) -> None:
        """Leading/trailing whitespace is stripped from the name."""
        req = UpdateCharacterRequest(name="  Trimmed  ")
        assert req.name == "Trimmed"

    def test_whitespace_only_name_rejected(self) -> None:
        """Name consisting only of whitespace is rejected."""
        with pytest.raises(ValidationError, match="Name must not be empty"):
            UpdateCharacterRequest(name="   ")


# ---------------------------------------------------------------------------
# CharacterListItem tests
# ---------------------------------------------------------------------------


class TestCharacterListItem:
    """Tests for CharacterListItem response schema."""

    def test_coerce_uuid_id_to_string(self) -> None:
        """UUID id is coerced to a string."""
        test_uuid = uuid.uuid4()
        item = CharacterListItem(
            id=test_uuid,  # type: ignore[arg-type]
            name="Ember",
            template="companion",
            description=None,
            avatar_style="default",
            is_default=True,
            last_message_at=None,
            created_at=datetime.now(tz=UTC),
        )
        assert item.id == str(test_uuid)
        assert isinstance(item.id, str)

    def test_from_attributes_mapping(self) -> None:
        """CharacterListItem maps from an ORM-like object via from_attributes."""
        mock_obj = MagicMock()
        mock_obj.id = uuid.uuid4()
        mock_obj.name = "Sarah"
        mock_obj.template = "english_teacher"
        mock_obj.description = None
        mock_obj.avatar_style = "blue"
        mock_obj.is_default = False
        mock_obj.last_message_at = datetime.now(tz=UTC)
        mock_obj.created_at = datetime.now(tz=UTC)

        item = CharacterListItem.model_validate(mock_obj)
        assert item.name == "Sarah"
        assert item.id == str(mock_obj.id)


# ---------------------------------------------------------------------------
# CharacterDetail tests
# ---------------------------------------------------------------------------


class TestCharacterDetail:
    """Tests for CharacterDetail response schema."""

    def test_coerce_uuid_id_to_string(self) -> None:
        """UUID id is coerced to a string."""
        test_uuid = uuid.uuid4()
        detail = CharacterDetail(
            id=test_uuid,  # type: ignore[arg-type]
            name="Sarah",
            template="english_teacher",
            description=None,
            system_prompt="You are Sarah...",
            avatar_style="default",
            is_default=False,
            created_at=datetime.now(tz=UTC),
        )
        assert detail.id == str(test_uuid)

    def test_from_attributes_mapping(self) -> None:
        """CharacterDetail maps from an ORM-like object via from_attributes."""
        mock_obj = MagicMock()
        mock_obj.id = uuid.uuid4()
        mock_obj.name = "Sarah"
        mock_obj.template = "english_teacher"
        mock_obj.description = None
        mock_obj.system_prompt = "You are Sarah, an English teacher..."
        mock_obj.avatar_style = "blue"
        mock_obj.is_default = False
        mock_obj.created_at = datetime.now(tz=UTC)

        detail = CharacterDetail.model_validate(mock_obj)
        assert detail.name == "Sarah"
        assert detail.system_prompt == "You are Sarah, an English teacher..."
        assert detail.id == str(mock_obj.id)
