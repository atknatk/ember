"""Pydantic request/response schemas for authentication endpoints.

Covers register, login, and refresh flows. Email validation requires
the ``email-validator`` package.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    """Request body for POST /api/v1/auth/register."""

    email: EmailStr
    password: str = Field(..., min_length=8)
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        """Remove leading/trailing whitespace from the name."""
        stripped = v.strip()
        if not stripped:
            msg = "Name must not be empty after trimming whitespace"
            raise ValueError(msg)
        return stripped

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        """Normalise email to lowercase."""
        return v.lower().strip()


class LoginRequest(BaseModel):
    """Request body for POST /api/v1/auth/login."""

    email: EmailStr
    password: str = Field(..., min_length=1)

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        """Normalise email to lowercase."""
        return v.lower().strip()


class RefreshRequest(BaseModel):
    """Request body for POST /api/v1/auth/refresh."""

    refresh_token: str = Field(..., min_length=1)


class UserResponse(BaseModel):
    """User profile data returned from auth endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    onboarding_completed: bool
    subscription_tier: str
    preferred_language: str
    timezone: str
    avatar_url: str | None
    created_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id_to_str(cls, v: object) -> str:
        """Convert UUID or other types to string for API output."""
        return str(v)


class AuthResponse(BaseModel):
    """Response for register and login: tokens + user profile."""

    token: str
    refresh_token: str
    user: UserResponse


class RefreshResponse(BaseModel):
    """Response for token refresh: new ID token only."""

    token: str
