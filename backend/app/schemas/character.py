"""Pydantic request/response schemas for character CRUD endpoints.

Covers create, update, list, and detail operations on AI characters.
"""

from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ALLOWED_TEMPLATES = frozenset({
    "companion",
    "english_teacher",
    "therapist",
    "fitness_coach",
    "career_coach",
    "custom",
})


class CreateCharacterRequest(BaseModel):
    """Request body for POST /api/v1/characters."""

    name: str = Field(..., min_length=1, max_length=100)
    template: str = Field(...)
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        """Remove leading/trailing whitespace from the name."""
        stripped = v.strip()
        if not stripped:
            msg = "Name must not be empty after trimming whitespace"
            raise ValueError(msg)
        return stripped

    @field_validator("template")
    @classmethod
    def validate_template(cls, v: str) -> str:
        """Validate that the template is in the allowed set."""
        if v not in ALLOWED_TEMPLATES:
            msg = (
                "Invalid template. Must be one of: companion, english_teacher, "
                "therapist, fitness_coach, career_coach, custom"
            )
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def validate_description_for_template(self) -> Self:
        """Require description for custom template, reject for non-custom."""
        if self.template == "custom":
            if not self.description or len(self.description.strip()) < 10:
                msg = "Description is required for custom characters (min 10 chars)"
                raise ValueError(msg)
            self.description = self.description.strip()
        elif self.description is not None:
            msg = "Description is only allowed for custom characters"
            raise ValueError(msg)
        return self


class UpdateCharacterRequest(BaseModel):
    """Request body for PUT /api/v1/characters/:id."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=10000)
    avatar_style: str | None = Field(default=None, max_length=50)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        """Remove leading/trailing whitespace from the name."""
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            msg = "Name must not be empty after trimming whitespace"
            raise ValueError(msg)
        return stripped

    @model_validator(mode="after")
    def check_at_least_one_field(self) -> Self:
        """Ensure at least one updatable field is provided."""
        if self.name is None and self.system_prompt is None and self.avatar_style is None:
            msg = "At least one field must be provided for update"
            raise ValueError(msg)
        return self


class CharacterListItem(BaseModel):
    """A single character in the list response (excludes system_prompt)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    template: str
    description: str | None
    avatar_style: str
    is_default: bool
    last_message_at: datetime | None
    created_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id_to_str(cls, v: object) -> str:
        """Convert UUID or other types to string for API output."""
        return str(v)


class CharacterListResponse(BaseModel):
    """Response for GET /api/v1/characters."""

    characters: list[CharacterListItem]


class CharacterDetail(BaseModel):
    """Full character detail returned from POST and PUT (includes system_prompt)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    template: str
    description: str | None
    system_prompt: str
    avatar_style: str
    is_default: bool
    created_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id_to_str(cls, v: object) -> str:
        """Convert UUID or other types to string for API output."""
        return str(v)
