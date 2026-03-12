"""Pydantic request/response schemas for profile endpoints.

Covers GET /api/v1/profile, PUT /api/v1/profile, and
DELETE /api/v1/profile/account.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Supported languages (extendable)
# ---------------------------------------------------------------------------

SUPPORTED_LANGUAGES: frozenset[str] = frozenset({"en", "tr"})

# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ProfileResponse(BaseModel):
    """Full profile data returned from GET and PUT profile endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    timezone: str
    avatar_url: str | None
    preferred_language: str
    onboarding_completed: bool
    subscription_tier: str
    subscription_expires_at: datetime | None
    created_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id_to_str(cls, v: object) -> str:
        """Convert UUID or other types to string for API output."""
        return str(v)


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

_UNSET = object()


class ProfileUpdateRequest(BaseModel):
    """Request body for PUT /api/v1/profile.

    All fields are optional. Only provided fields are updated.
    ``avatar_url`` uses ``model_fields_set`` to distinguish between
    "field not sent" and "field explicitly set to null".
    """

    name: str | None = None
    timezone: str | None = None
    avatar_url: str | None = Field(default=None)
    preferred_language: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        """Trim whitespace and enforce length constraints on name."""
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            msg = "Name must not be empty after trimming whitespace"
            raise ValueError(msg)
        if len(stripped) > 100:
            msg = "Name must be 100 characters or fewer"
            raise ValueError(msg)
        return stripped

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        """Validate that the timezone is a valid IANA timezone."""
        if v is None:
            return None
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, KeyError):
            msg = "Invalid IANA timezone"
            raise ValueError(msg)  # noqa: B904
        return v

    @field_validator("avatar_url")
    @classmethod
    def validate_avatar_url(cls, v: str | None) -> str | None:
        """Validate avatar_url starts with https:// if non-null."""
        if v is None:
            return None
        if len(v) > 2048:
            msg = "avatar_url must be 2048 characters or fewer"
            raise ValueError(msg)
        if not v.startswith("https://"):
            msg = "avatar_url must start with https://"
            raise ValueError(msg)
        return v

    @field_validator("preferred_language")
    @classmethod
    def validate_preferred_language(cls, v: str | None) -> str | None:
        """Validate preferred_language is in the supported list."""
        if v is None:
            return None
        if v not in SUPPORTED_LANGUAGES:
            msg = f"preferred_language must be one of: {', '.join(sorted(SUPPORTED_LANGUAGES))}"
            raise ValueError(msg)
        return v


class AccountDeleteRequest(BaseModel):
    """Request body for DELETE /api/v1/profile/account.

    The ``confirmation`` field must be exactly ``"DELETE MY ACCOUNT"``
    (case-sensitive) to prevent accidental deletions.
    """

    confirmation: str = Field(..., min_length=1)
