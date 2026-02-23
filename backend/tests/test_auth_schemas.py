"""Unit tests for authentication Pydantic schemas.

Tests cover field validation, email normalisation, name trimming,
and ORM-to-schema mapping for UserResponse.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest, UserResponse


class TestRegisterRequest:
    """Tests for RegisterRequest schema validation."""

    def test_valid_request(self) -> None:
        req = RegisterRequest(email="User@Example.com", password="Pass1234!", name="Alex")
        assert req.email == "user@example.com"
        assert req.name == "Alex"

    def test_strip_name_whitespace(self) -> None:
        req = RegisterRequest(email="a@b.com", password="Pass1234!", name="  Alex  ")
        assert req.name == "Alex"

    def test_lowercase_email(self) -> None:
        req = RegisterRequest(email="Test@EXAMPLE.COM", password="Pass1234!", name="A")
        assert req.email == "test@example.com"

    def test_rejects_whitespace_only_name(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(email="a@b.com", password="Pass1234!", name="   ")

    def test_rejects_missing_email(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(password="Pass1234!", name="Alex")  # type: ignore[call-arg]

    def test_rejects_missing_name(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(email="a@b.com", password="Pass1234!")  # type: ignore[call-arg]

    def test_rejects_invalid_email(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(email="not-an-email", password="Pass1234!", name="Alex")

    def test_rejects_short_password(self) -> None:
        with pytest.raises(ValidationError):
            RegisterRequest(email="a@b.com", password="short", name="Alex")

    def test_name_max_length(self) -> None:
        long_name = "A" * 101
        with pytest.raises(ValidationError):
            RegisterRequest(email="a@b.com", password="Pass1234!", name=long_name)

    def test_name_at_max_length(self) -> None:
        name = "A" * 100
        req = RegisterRequest(email="a@b.com", password="Pass1234!", name=name)
        assert req.name == name


class TestLoginRequest:
    """Tests for LoginRequest schema validation."""

    def test_lowercase_email(self) -> None:
        req = LoginRequest(email="TEST@EXAMPLE.COM", password="secret")
        assert req.email == "test@example.com"

    def test_rejects_empty_password(self) -> None:
        with pytest.raises(ValidationError):
            LoginRequest(email="a@b.com", password="")


class TestUserResponse:
    """Tests for UserResponse from_attributes mapping."""

    def test_model_validate_from_orm_object(self) -> None:
        profile_id = uuid.uuid4()
        now = datetime.now(tz=UTC)
        mock_profile = MagicMock()
        mock_profile.id = profile_id
        mock_profile.email = "test@ember.ai"
        mock_profile.name = "Test"
        mock_profile.onboarding_completed = False
        mock_profile.subscription_tier = "free"
        mock_profile.preferred_language = "en"
        mock_profile.timezone = "UTC"
        mock_profile.avatar_url = None
        mock_profile.created_at = now

        user_resp = UserResponse.model_validate(mock_profile, from_attributes=True)
        assert user_resp.id == str(profile_id)
        assert user_resp.email == "test@ember.ai"
        assert user_resp.name == "Test"
        assert user_resp.onboarding_completed is False
        assert user_resp.subscription_tier == "free"
        assert user_resp.preferred_language == "en"
        assert user_resp.timezone == "UTC"
        assert user_resp.avatar_url is None
        assert user_resp.created_at == now
