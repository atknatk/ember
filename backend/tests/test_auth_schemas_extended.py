"""Extended schema tests for authentication Pydantic models.

Covers scenarios NOT in the backend-dev's initial test suite:
- Email normalization edge cases
- Password edge cases
- Name edge cases
- RefreshRequest validation
- AuthResponse and RefreshResponse construction
- UserResponse field types and coercion
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    UserResponse,
)


# ---------------------------------------------------------------------------
# RegisterRequest — Email Edge Cases
# ---------------------------------------------------------------------------


class TestRegisterRequestEmailEdgeCases:
    """Email validation and normalization edge cases for RegisterRequest."""

    def test_email_with_plus_addressing(self) -> None:
        """Email with + addressing (subaddressing) is accepted."""
        req = RegisterRequest(
            email="user+tag@example.com",
            password="Pass1234!",
            name="Alex",
        )
        assert req.email == "user+tag@example.com"

    def test_email_with_dots_in_local_part(self) -> None:
        """Email with dots in local part is accepted."""
        req = RegisterRequest(
            email="first.last@example.com",
            password="Pass1234!",
            name="Alex",
        )
        assert req.email == "first.last@example.com"

    def test_email_mixed_case_domain(self) -> None:
        """Email with mixed case domain is lowercased."""
        req = RegisterRequest(
            email="user@EXAMPLE.COM",
            password="Pass1234!",
            name="Alex",
        )
        assert req.email == "user@example.com"

    def test_email_mixed_case_local_part(self) -> None:
        """Email with mixed case local part is lowercased."""
        req = RegisterRequest(
            email="USER@example.com",
            password="Pass1234!",
            name="Alex",
        )
        assert req.email == "user@example.com"

    def test_email_rejects_no_at_sign(self) -> None:
        """Email without @ is rejected."""
        with pytest.raises(ValidationError):
            RegisterRequest(email="userexample.com", password="Pass1234!", name="A")

    def test_email_rejects_no_domain(self) -> None:
        """Email without domain is rejected."""
        with pytest.raises(ValidationError):
            RegisterRequest(email="user@", password="Pass1234!", name="A")

    def test_email_rejects_empty_string(self) -> None:
        """Empty email string is rejected."""
        with pytest.raises(ValidationError):
            RegisterRequest(email="", password="Pass1234!", name="A")


# ---------------------------------------------------------------------------
# RegisterRequest — Password Edge Cases
# ---------------------------------------------------------------------------


class TestRegisterRequestPasswordEdgeCases:
    """Password validation edge cases for RegisterRequest."""

    def test_password_exactly_8_chars(self) -> None:
        """Password of exactly 8 chars passes validation."""
        req = RegisterRequest(email="a@b.com", password="12345678", name="Alex")
        assert req.password == "12345678"

    def test_password_very_long(self) -> None:
        """Very long password is accepted by Pydantic (Cognito may reject)."""
        long_pass = "A" * 256
        req = RegisterRequest(email="a@b.com", password=long_pass, name="Alex")
        assert len(req.password) == 256

    def test_password_with_unicode(self) -> None:
        """Password with unicode characters passes Pydantic validation."""
        req = RegisterRequest(
            email="a@b.com",
            password="P@sswort!",
            name="Alex",
        )
        assert len(req.password) >= 8

    def test_password_with_spaces(self) -> None:
        """Password with spaces is accepted (spaces are valid in passwords)."""
        req = RegisterRequest(
            email="a@b.com",
            password="pass word 1",
            name="Alex",
        )
        assert " " in req.password

    def test_password_rejects_7_chars(self) -> None:
        """Password of 7 chars is rejected."""
        with pytest.raises(ValidationError):
            RegisterRequest(email="a@b.com", password="1234567", name="Alex")

    def test_password_rejects_empty(self) -> None:
        """Empty password is rejected."""
        with pytest.raises(ValidationError):
            RegisterRequest(email="a@b.com", password="", name="Alex")


# ---------------------------------------------------------------------------
# RegisterRequest — Name Edge Cases
# ---------------------------------------------------------------------------


class TestRegisterRequestNameEdgeCases:
    """Name validation edge cases for RegisterRequest."""

    def test_name_single_char(self) -> None:
        """Single character name is accepted (min_length=1)."""
        req = RegisterRequest(email="a@b.com", password="Pass1234!", name="A")
        assert req.name == "A"

    def test_name_exactly_100_chars(self) -> None:
        """Name of exactly 100 chars is accepted."""
        name = "A" * 100
        req = RegisterRequest(email="a@b.com", password="Pass1234!", name=name)
        assert req.name == name

    def test_name_101_chars_rejected(self) -> None:
        """Name of 101 chars is rejected."""
        with pytest.raises(ValidationError):
            RegisterRequest(email="a@b.com", password="Pass1234!", name="A" * 101)

    def test_name_strip_leading_spaces(self) -> None:
        """Leading spaces in name are stripped."""
        req = RegisterRequest(email="a@b.com", password="Pass1234!", name="   Alex")
        assert req.name == "Alex"

    def test_name_strip_trailing_spaces(self) -> None:
        """Trailing spaces in name are stripped."""
        req = RegisterRequest(email="a@b.com", password="Pass1234!", name="Alex   ")
        assert req.name == "Alex"

    def test_name_strip_tabs(self) -> None:
        """Tab characters in name are stripped."""
        req = RegisterRequest(email="a@b.com", password="Pass1234!", name="\tAlex\t")
        assert req.name == "Alex"

    def test_name_strip_newlines(self) -> None:
        """Newline characters in name are stripped."""
        req = RegisterRequest(email="a@b.com", password="Pass1234!", name="\nAlex\n")
        assert req.name == "Alex"

    def test_name_with_only_newlines_rejected(self) -> None:
        """Name with only whitespace characters (tabs, newlines) is rejected."""
        with pytest.raises(ValidationError):
            RegisterRequest(email="a@b.com", password="Pass1234!", name="\t\n ")

    def test_name_internal_spaces_preserved(self) -> None:
        """Internal spaces in name are preserved (only leading/trailing stripped)."""
        req = RegisterRequest(
            email="a@b.com",
            password="Pass1234!",
            name="  John Doe  ",
        )
        assert req.name == "John Doe"

    def test_name_with_unicode(self) -> None:
        """Name with unicode characters is accepted."""
        req = RegisterRequest(email="a@b.com", password="Pass1234!", name="Atakan")
        assert req.name == "Atakan"

    def test_name_with_numbers(self) -> None:
        """Name with numbers is accepted."""
        req = RegisterRequest(email="a@b.com", password="Pass1234!", name="Alex99")
        assert req.name == "Alex99"

    def test_name_with_special_chars(self) -> None:
        """Name with special characters is accepted."""
        req = RegisterRequest(
            email="a@b.com",
            password="Pass1234!",
            name="O'Brien-Smith",
        )
        assert req.name == "O'Brien-Smith"


# ---------------------------------------------------------------------------
# LoginRequest — Additional Cases
# ---------------------------------------------------------------------------


class TestLoginRequestExtended:
    """Extended LoginRequest validation tests."""

    def test_valid_login(self) -> None:
        """Valid login request is accepted."""
        req = LoginRequest(email="user@example.com", password="secret123")
        assert req.email == "user@example.com"
        assert req.password == "secret123"

    def test_email_normalized(self) -> None:
        """Login email is lowercased."""
        req = LoginRequest(email="USER@EXAMPLE.COM", password="secret")
        assert req.email == "user@example.com"

    def test_rejects_missing_email(self) -> None:
        """Missing email raises ValidationError."""
        with pytest.raises(ValidationError):
            LoginRequest(password="secret")  # type: ignore[call-arg]

    def test_rejects_missing_password(self) -> None:
        """Missing password raises ValidationError."""
        with pytest.raises(ValidationError):
            LoginRequest(email="a@b.com")  # type: ignore[call-arg]

    def test_rejects_invalid_email(self) -> None:
        """Invalid email format is rejected."""
        with pytest.raises(ValidationError):
            LoginRequest(email="not-email", password="secret")

    def test_password_single_char(self) -> None:
        """Login password with single char is accepted (min_length=1)."""
        req = LoginRequest(email="a@b.com", password="x")
        assert req.password == "x"

    def test_short_password_accepted(self) -> None:
        """Login accepts short passwords (min_length=1, not 8 like register)."""
        req = LoginRequest(email="a@b.com", password="ab")
        assert req.password == "ab"


# ---------------------------------------------------------------------------
# RefreshRequest
# ---------------------------------------------------------------------------


class TestRefreshRequest:
    """Tests for RefreshRequest schema validation."""

    def test_valid_refresh_request(self) -> None:
        """Valid refresh request with token string."""
        req = RefreshRequest(refresh_token="some-token-value")
        assert req.refresh_token == "some-token-value"

    def test_rejects_empty_token(self) -> None:
        """Empty refresh_token string is rejected (min_length=1)."""
        with pytest.raises(ValidationError):
            RefreshRequest(refresh_token="")

    def test_rejects_missing_token(self) -> None:
        """Missing refresh_token field raises ValidationError."""
        with pytest.raises(ValidationError):
            RefreshRequest()  # type: ignore[call-arg]

    def test_long_token_accepted(self) -> None:
        """Long refresh token string is accepted."""
        long_token = "x" * 2048
        req = RefreshRequest(refresh_token=long_token)
        assert req.refresh_token == long_token


# ---------------------------------------------------------------------------
# UserResponse — Extended
# ---------------------------------------------------------------------------


class TestUserResponseExtended:
    """Extended tests for UserResponse schema."""

    def test_id_coercion_from_uuid(self) -> None:
        """UUID id is coerced to string."""
        uid = uuid.uuid4()
        resp = UserResponse(
            id=uid,  # type: ignore[arg-type]
            email="test@ember.ai",
            name="Test",
            onboarding_completed=False,
            subscription_tier="free",
            preferred_language="en",
            timezone="UTC",
            avatar_url=None,
            created_at=datetime.now(tz=UTC),
        )
        assert resp.id == str(uid)
        assert isinstance(resp.id, str)

    def test_id_coercion_from_string(self) -> None:
        """String id is passed through."""
        uid = "550e8400-e29b-41d4-a716-446655440000"
        resp = UserResponse(
            id=uid,
            email="test@ember.ai",
            name="Test",
            onboarding_completed=False,
            subscription_tier="free",
            preferred_language="en",
            timezone="UTC",
            avatar_url=None,
            created_at=datetime.now(tz=UTC),
        )
        assert resp.id == uid

    def test_avatar_url_can_be_string(self) -> None:
        """avatar_url can be a string (URL)."""
        resp = UserResponse(
            id="some-id",
            email="test@ember.ai",
            name="Test",
            onboarding_completed=False,
            subscription_tier="free",
            preferred_language="en",
            timezone="UTC",
            avatar_url="https://example.com/avatar.png",
            created_at=datetime.now(tz=UTC),
        )
        assert resp.avatar_url == "https://example.com/avatar.png"

    def test_avatar_url_can_be_none(self) -> None:
        """avatar_url can be None."""
        resp = UserResponse(
            id="some-id",
            email="test@ember.ai",
            name="Test",
            onboarding_completed=False,
            subscription_tier="free",
            preferred_language="en",
            timezone="UTC",
            avatar_url=None,
            created_at=datetime.now(tz=UTC),
        )
        assert resp.avatar_url is None

    def test_from_attributes_with_mock_orm(self) -> None:
        """model_validate works with Mock ORM objects using from_attributes."""
        now = datetime.now(tz=UTC)
        profile_id = uuid.uuid4()
        mock_profile = MagicMock()
        mock_profile.id = profile_id
        mock_profile.email = "orm@ember.ai"
        mock_profile.name = "OrmUser"
        mock_profile.onboarding_completed = True
        mock_profile.subscription_tier = "premium"
        mock_profile.preferred_language = "tr"
        mock_profile.timezone = "Europe/Istanbul"
        mock_profile.avatar_url = "https://example.com/pic.jpg"
        mock_profile.created_at = now

        resp = UserResponse.model_validate(mock_profile, from_attributes=True)
        assert resp.id == str(profile_id)
        assert resp.email == "orm@ember.ai"
        assert resp.name == "OrmUser"
        assert resp.onboarding_completed is True
        assert resp.subscription_tier == "premium"
        assert resp.preferred_language == "tr"
        assert resp.timezone == "Europe/Istanbul"
        assert resp.avatar_url == "https://example.com/pic.jpg"
        assert resp.created_at == now

    def test_created_at_serializes_as_iso(self) -> None:
        """created_at datetime is serializable."""
        now = datetime(2026, 2, 23, 14, 30, 0, tzinfo=UTC)
        resp = UserResponse(
            id="some-id",
            email="test@ember.ai",
            name="Test",
            onboarding_completed=False,
            subscription_tier="free",
            preferred_language="en",
            timezone="UTC",
            avatar_url=None,
            created_at=now,
        )
        dumped = resp.model_dump()
        assert dumped["created_at"] == now
        # JSON serialization should produce ISO format
        json_str = resp.model_dump_json()
        assert "2026-02-23" in json_str


# ---------------------------------------------------------------------------
# AuthResponse
# ---------------------------------------------------------------------------


class TestAuthResponse:
    """Tests for AuthResponse schema."""

    def test_construction(self) -> None:
        """AuthResponse can be constructed with required fields."""
        user = UserResponse(
            id="some-id",
            email="test@ember.ai",
            name="Test",
            onboarding_completed=False,
            subscription_tier="free",
            preferred_language="en",
            timezone="UTC",
            avatar_url=None,
            created_at=datetime.now(tz=UTC),
        )
        resp = AuthResponse(
            token="fake-token",
            refresh_token="fake-refresh",
            user=user,
        )
        assert resp.token == "fake-token"
        assert resp.refresh_token == "fake-refresh"
        assert resp.user.email == "test@ember.ai"

    def test_json_serialization(self) -> None:
        """AuthResponse serializes to JSON with all expected keys."""
        user = UserResponse(
            id="some-id",
            email="test@ember.ai",
            name="Test",
            onboarding_completed=False,
            subscription_tier="free",
            preferred_language="en",
            timezone="UTC",
            avatar_url=None,
            created_at=datetime.now(tz=UTC),
        )
        resp = AuthResponse(
            token="fake-token",
            refresh_token="fake-refresh",
            user=user,
        )
        data = resp.model_dump()
        assert "token" in data
        assert "refresh_token" in data
        assert "user" in data
        assert isinstance(data["user"], dict)


# ---------------------------------------------------------------------------
# RefreshResponse
# ---------------------------------------------------------------------------


class TestRefreshResponse:
    """Tests for RefreshResponse schema."""

    def test_construction(self) -> None:
        """RefreshResponse can be constructed with just token."""
        resp = RefreshResponse(token="new-id-token")
        assert resp.token == "new-id-token"

    def test_no_refresh_token_field(self) -> None:
        """RefreshResponse does NOT have a refresh_token field."""
        resp = RefreshResponse(token="new-id-token")
        data = resp.model_dump()
        assert "refresh_token" not in data
        assert set(data.keys()) == {"token"}

    def test_json_serialization(self) -> None:
        """RefreshResponse serializes correctly."""
        resp = RefreshResponse(token="new-id-token")
        json_data = resp.model_dump_json()
        assert "new-id-token" in json_data
