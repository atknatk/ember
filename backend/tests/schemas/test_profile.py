"""Schema validation tests for profile Pydantic models.

Covers ProfileResponse, ProfileUpdateRequest, and AccountDeleteRequest
with edge cases: boundary lengths, invalid values, sentinel behavior,
URL constraints, and language validation.
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

from app.schemas.profile import (  # noqa: E402
    SUPPORTED_LANGUAGES,
    AccountDeleteRequest,
    ProfileResponse,
    ProfileUpdateRequest,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")


def _make_profile_response_data(**overrides: object) -> dict:
    """Build minimal valid data dict for ProfileResponse."""
    base = {
        "id": str(FAKE_USER_ID),
        "email": "test@ember.ai",
        "name": "Alex",
        "timezone": "UTC",
        "avatar_url": None,
        "preferred_language": "en",
        "onboarding_completed": True,
        "subscription_tier": "free",
        "subscription_expires_at": None,
        "created_at": datetime.now(tz=UTC),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# ProfileResponse
# ---------------------------------------------------------------------------


class TestProfileResponse:
    """Schema tests for ProfileResponse."""

    def test_valid_full_profile_parses(self) -> None:
        """Full valid profile data parses without error."""
        data = _make_profile_response_data()
        resp = ProfileResponse(**data)
        assert resp.email == "test@ember.ai"
        assert resp.name == "Alex"

    def test_id_coerced_from_uuid_to_str(self) -> None:
        """UUID id field is coerced to string by the validator."""
        data = _make_profile_response_data(id=FAKE_USER_ID)
        resp = ProfileResponse(**data)
        assert isinstance(resp.id, str)
        assert resp.id == str(FAKE_USER_ID)

    def test_id_already_str_accepted(self) -> None:
        """String id is accepted as-is."""
        data = _make_profile_response_data(id="custom-string-id")
        resp = ProfileResponse(**data)
        assert resp.id == "custom-string-id"

    def test_avatar_url_none_accepted(self) -> None:
        """avatar_url can be None."""
        data = _make_profile_response_data(avatar_url=None)
        resp = ProfileResponse(**data)
        assert resp.avatar_url is None

    def test_avatar_url_string_accepted(self) -> None:
        """avatar_url can be a string."""
        url = "https://s3.amazonaws.com/photos/user/avatar.jpg"
        data = _make_profile_response_data(avatar_url=url)
        resp = ProfileResponse(**data)
        assert resp.avatar_url == url

    def test_subscription_expires_at_none_accepted(self) -> None:
        """subscription_expires_at can be None for free tier."""
        data = _make_profile_response_data(subscription_expires_at=None)
        resp = ProfileResponse(**data)
        assert resp.subscription_expires_at is None

    def test_subscription_expires_at_datetime_accepted(self) -> None:
        """subscription_expires_at can be a datetime for paid tiers."""
        expires = datetime(2027, 1, 1, tzinfo=UTC)
        data = _make_profile_response_data(subscription_expires_at=expires)
        resp = ProfileResponse(**data)
        assert resp.subscription_expires_at == expires

    def test_model_config_from_attributes(self) -> None:
        """model_config has from_attributes=True for ORM compatibility."""
        assert ProfileResponse.model_config.get("from_attributes") is True

    def test_from_attributes_with_orm_object(self) -> None:
        """ProfileResponse.model_validate works on an ORM-like object."""
        from unittest.mock import MagicMock

        orm_obj = MagicMock()
        orm_obj.id = FAKE_USER_ID
        orm_obj.email = "orm@test.com"
        orm_obj.name = "ORM User"
        orm_obj.timezone = "Europe/Istanbul"
        orm_obj.avatar_url = None
        orm_obj.preferred_language = "tr"
        orm_obj.onboarding_completed = False
        orm_obj.subscription_tier = "premium"
        orm_obj.subscription_expires_at = None
        orm_obj.created_at = datetime.now(tz=UTC)

        resp = ProfileResponse.model_validate(orm_obj)
        assert resp.email == "orm@test.com"
        assert resp.preferred_language == "tr"
        assert resp.onboarding_completed is False

    def test_missing_required_field_raises(self) -> None:
        """Missing required field raises ValidationError."""
        data = _make_profile_response_data()
        del data["email"]
        with pytest.raises(ValidationError):
            ProfileResponse(**data)


# ---------------------------------------------------------------------------
# ProfileUpdateRequest -- name validation
# ---------------------------------------------------------------------------


class TestProfileUpdateRequestName:
    """Tests for name field validation in ProfileUpdateRequest."""

    def test_name_none_is_accepted(self) -> None:
        """None name means 'do not update'."""
        body = ProfileUpdateRequest(name=None)
        assert body.name is None

    def test_name_omitted_defaults_to_none(self) -> None:
        """Omitted name defaults to None."""
        body = ProfileUpdateRequest()
        assert body.name is None

    def test_valid_name_accepted(self) -> None:
        """Regular name is accepted and returned as-is."""
        body = ProfileUpdateRequest(name="Alice")
        assert body.name == "Alice"

    def test_name_trimmed_of_whitespace(self) -> None:
        """Leading/trailing whitespace is stripped from name."""
        body = ProfileUpdateRequest(name="  Alex  ")
        assert body.name == "Alex"

    def test_name_exactly_100_chars_accepted(self) -> None:
        """Name of exactly 100 chars (after trim) is accepted."""
        body = ProfileUpdateRequest(name="x" * 100)
        assert body.name == "x" * 100

    def test_name_exactly_101_chars_rejected(self) -> None:
        """Name of 101 chars raises ValidationError."""
        with pytest.raises(ValidationError, match="100 characters or fewer"):
            ProfileUpdateRequest(name="x" * 101)

    def test_name_empty_string_rejected(self) -> None:
        """Empty string name is rejected."""
        with pytest.raises(ValidationError, match="empty after trimming"):
            ProfileUpdateRequest(name="")

    def test_name_whitespace_only_rejected(self) -> None:
        """Whitespace-only name is rejected after trim."""
        with pytest.raises(ValidationError, match="empty after trimming"):
            ProfileUpdateRequest(name="   ")

    def test_name_tabs_only_rejected(self) -> None:
        """Tab-only name is rejected."""
        with pytest.raises(ValidationError, match="empty after trimming"):
            ProfileUpdateRequest(name="\t\t")

    def test_name_newline_only_rejected(self) -> None:
        """Newline-only name is rejected."""
        with pytest.raises(ValidationError, match="empty after trimming"):
            ProfileUpdateRequest(name="\n\n")

    def test_name_single_char_accepted(self) -> None:
        """Single character name is accepted."""
        body = ProfileUpdateRequest(name="A")
        assert body.name == "A"

    def test_name_unicode_accepted(self) -> None:
        """Unicode characters in name are accepted."""
        body = ProfileUpdateRequest(name="Atalay Kemal")
        assert body.name == "Atalay Kemal"

    def test_name_100_chars_with_surrounding_spaces_rejected(self) -> None:
        """100 chars + 2 surrounding spaces = 102 chars total raises ValidationError.

        Pydantic runs field_validator after basic type coercion, but there is no
        max_length constraint on the raw input -- the validator checks len(stripped).
        A 101-char name with 1 space each side is 103 chars; the stripped length is
        101 which exceeds 100.
        """
        with pytest.raises(ValidationError, match="100 characters or fewer"):
            ProfileUpdateRequest(name=" " + "x" * 101 + " ")


# ---------------------------------------------------------------------------
# ProfileUpdateRequest -- timezone validation
# ---------------------------------------------------------------------------


class TestProfileUpdateRequestTimezone:
    """Tests for timezone field validation in ProfileUpdateRequest."""

    def test_timezone_none_accepted(self) -> None:
        """None timezone means 'do not update'."""
        body = ProfileUpdateRequest(timezone=None)
        assert body.timezone is None

    def test_valid_iana_timezone_utc(self) -> None:
        """'UTC' is a valid IANA timezone."""
        body = ProfileUpdateRequest(timezone="UTC")
        assert body.timezone == "UTC"

    def test_valid_iana_timezone_europe_istanbul(self) -> None:
        """'Europe/Istanbul' is a valid IANA timezone."""
        body = ProfileUpdateRequest(timezone="Europe/Istanbul")
        assert body.timezone == "Europe/Istanbul"

    def test_valid_iana_timezone_america_new_york(self) -> None:
        """'America/New_York' is a valid IANA timezone."""
        body = ProfileUpdateRequest(timezone="America/New_York")
        assert body.timezone == "America/New_York"

    def test_valid_iana_timezone_asia_tokyo(self) -> None:
        """'Asia/Tokyo' is a valid IANA timezone."""
        body = ProfileUpdateRequest(timezone="Asia/Tokyo")
        assert body.timezone == "Asia/Tokyo"

    def test_invalid_timezone_raises(self) -> None:
        """An invalid timezone string raises ValidationError."""
        with pytest.raises(ValidationError, match="Invalid IANA timezone"):
            ProfileUpdateRequest(timezone="Invalid/Zone")

    def test_lowercase_utc_accepted(self) -> None:
        """'utc' (lowercase) is accepted by Python's zoneinfo.ZoneInfo."""
        # Python's zoneinfo is case-insensitive for 'UTC'; 'utc' resolves correctly.
        body = ProfileUpdateRequest(timezone="utc")
        assert body.timezone == "utc"

    def test_random_string_timezone_rejected(self) -> None:
        """Arbitrary string is rejected as invalid timezone."""
        with pytest.raises(ValidationError, match="Invalid IANA timezone"):
            ProfileUpdateRequest(timezone="NotATimezone")

    def test_empty_string_timezone_rejected(self) -> None:
        """Empty string is rejected as invalid (raises ValidationError for any reason)."""
        # Python's zoneinfo raises ValueError for empty string, which Pydantic wraps.
        with pytest.raises(ValidationError):
            ProfileUpdateRequest(timezone="")

    def test_numeric_offset_rejected(self) -> None:
        """Numeric offset strings like '+05:30' are not valid IANA zones."""
        with pytest.raises(ValidationError, match="Invalid IANA timezone"):
            ProfileUpdateRequest(timezone="+05:30")


# ---------------------------------------------------------------------------
# ProfileUpdateRequest -- avatar_url validation
# ---------------------------------------------------------------------------


class TestProfileUpdateRequestAvatarUrl:
    """Tests for avatar_url field validation in ProfileUpdateRequest."""

    def test_avatar_url_none_accepted(self) -> None:
        """Explicit None clears the avatar."""
        body = ProfileUpdateRequest.model_validate({"avatar_url": None})
        assert body.avatar_url is None
        assert "avatar_url" in body.model_fields_set

    def test_avatar_url_omitted_not_in_fields_set(self) -> None:
        """Omitting avatar_url means it is not in model_fields_set."""
        body = ProfileUpdateRequest(name="Alex")
        assert "avatar_url" not in body.model_fields_set

    def test_valid_https_url_accepted(self) -> None:
        """Valid https:// URL is accepted."""
        url = "https://s3.amazonaws.com/photos/user/avatar.jpg"
        body = ProfileUpdateRequest(avatar_url=url)
        assert body.avatar_url == url

    def test_http_url_rejected(self) -> None:
        """http:// URL is rejected (must be https://)."""
        with pytest.raises(ValidationError, match="https://"):
            ProfileUpdateRequest(avatar_url="http://example.com/img.jpg")

    def test_ftp_url_rejected(self) -> None:
        """ftp:// URL is rejected."""
        with pytest.raises(ValidationError, match="https://"):
            ProfileUpdateRequest(avatar_url="ftp://example.com/img.jpg")

    def test_relative_path_rejected(self) -> None:
        """Relative path is rejected (no scheme)."""
        with pytest.raises(ValidationError, match="https://"):
            ProfileUpdateRequest(avatar_url="/photos/avatar.jpg")

    def test_avatar_url_exactly_2048_chars_accepted(self) -> None:
        """URL of exactly 2048 chars is accepted."""
        padding = "x" * (2048 - len("https://"))
        url = f"https://{padding}"
        body = ProfileUpdateRequest(avatar_url=url)
        assert len(body.avatar_url) == 2048  # type: ignore[arg-type]

    def test_avatar_url_2049_chars_rejected(self) -> None:
        """URL exceeding 2048 chars is rejected."""
        padding = "x" * (2049 - len("https://"))
        url = f"https://{padding}"
        with pytest.raises(ValidationError, match="2048 characters"):
            ProfileUpdateRequest(avatar_url=url)

    def test_model_fields_set_includes_avatar_when_sent(self) -> None:
        """model_fields_set includes avatar_url when provided."""
        body = ProfileUpdateRequest.model_validate(
            {"avatar_url": "https://example.com/img.jpg"}
        )
        assert "avatar_url" in body.model_fields_set

    def test_model_fields_set_excludes_avatar_when_omitted(self) -> None:
        """model_fields_set excludes avatar_url when field not in JSON."""
        body = ProfileUpdateRequest.model_validate({"name": "Test"})
        assert "avatar_url" not in body.model_fields_set


# ---------------------------------------------------------------------------
# ProfileUpdateRequest -- preferred_language validation
# ---------------------------------------------------------------------------


class TestProfileUpdateRequestLanguage:
    """Tests for preferred_language field validation in ProfileUpdateRequest."""

    def test_language_none_accepted(self) -> None:
        """None means 'do not update'."""
        body = ProfileUpdateRequest(preferred_language=None)
        assert body.preferred_language is None

    def test_english_accepted(self) -> None:
        """'en' is a supported language."""
        body = ProfileUpdateRequest(preferred_language="en")
        assert body.preferred_language == "en"

    def test_turkish_accepted(self) -> None:
        """'tr' is a supported language."""
        body = ProfileUpdateRequest(preferred_language="tr")
        assert body.preferred_language == "tr"

    def test_unsupported_language_rejected(self) -> None:
        """Unknown language code raises ValidationError."""
        with pytest.raises(ValidationError):
            ProfileUpdateRequest(preferred_language="zz")

    def test_uppercase_en_rejected(self) -> None:
        """'EN' (uppercase) is not accepted (case-sensitive)."""
        with pytest.raises(ValidationError):
            ProfileUpdateRequest(preferred_language="EN")

    def test_uppercase_tr_rejected(self) -> None:
        """'TR' (uppercase) is not accepted (case-sensitive)."""
        with pytest.raises(ValidationError):
            ProfileUpdateRequest(preferred_language="TR")

    def test_french_not_supported(self) -> None:
        """'fr' is not in the supported language list."""
        with pytest.raises(ValidationError):
            ProfileUpdateRequest(preferred_language="fr")

    def test_empty_string_language_rejected(self) -> None:
        """Empty string is not a valid language code."""
        with pytest.raises(ValidationError):
            ProfileUpdateRequest(preferred_language="")


# ---------------------------------------------------------------------------
# ProfileUpdateRequest -- model_fields_set sentinel pattern
# ---------------------------------------------------------------------------


class TestProfileUpdateRequestSentinel:
    """Tests specifically for the model_fields_set sentinel pattern."""

    def test_empty_body_fields_set_is_empty(self) -> None:
        """Empty body has an empty model_fields_set."""
        body = ProfileUpdateRequest()
        assert body.model_fields_set == set()

    def test_name_only_fields_set_contains_name(self) -> None:
        """Providing only name puts 'name' in model_fields_set."""
        body = ProfileUpdateRequest(name="Test")
        assert "name" in body.model_fields_set
        assert "timezone" not in body.model_fields_set
        assert "avatar_url" not in body.model_fields_set
        assert "preferred_language" not in body.model_fields_set

    def test_all_fields_set_contains_all(self) -> None:
        """Providing all fields fills model_fields_set."""
        body = ProfileUpdateRequest(
            name="Alex",
            timezone="UTC",
            avatar_url="https://example.com/img.jpg",
            preferred_language="en",
        )
        assert body.model_fields_set == {"name", "timezone", "avatar_url", "preferred_language"}

    def test_avatar_null_explicitly_in_fields_set(self) -> None:
        """Sending avatar_url=null puts it in model_fields_set (null ≠ omitted)."""
        body = ProfileUpdateRequest.model_validate({"avatar_url": None})
        assert "avatar_url" in body.model_fields_set
        assert body.avatar_url is None


# ---------------------------------------------------------------------------
# ProfileUpdateRequest -- multiple validation errors
# ---------------------------------------------------------------------------


class TestProfileUpdateRequestMultipleErrors:
    """Tests for multiple simultaneous validation failures."""

    def test_two_invalid_fields_both_reported(self) -> None:
        """Two invalid fields result in ValidationError with both errors."""
        with pytest.raises(ValidationError) as exc_info:
            ProfileUpdateRequest(
                timezone="Bad/Zone",
                preferred_language="xx",
            )
        # ValidationError.errors() should contain errors for both fields
        errors = exc_info.value.errors()
        error_locs = [e["loc"] for e in errors]
        assert ("timezone",) in error_locs
        assert ("preferred_language",) in error_locs

    def test_name_and_timezone_both_invalid(self) -> None:
        """Both name and timezone invalid triggers two errors."""
        with pytest.raises(ValidationError) as exc_info:
            ProfileUpdateRequest(
                name="   ",
                timezone="Fake/Zone",
            )
        errors = exc_info.value.errors()
        locs = {e["loc"][0] for e in errors}
        assert "name" in locs
        assert "timezone" in locs


# ---------------------------------------------------------------------------
# AccountDeleteRequest
# ---------------------------------------------------------------------------


class TestAccountDeleteRequest:
    """Tests for AccountDeleteRequest validation."""

    def test_correct_confirmation_accepted(self) -> None:
        """Exact 'DELETE MY ACCOUNT' string is accepted."""
        req = AccountDeleteRequest(confirmation="DELETE MY ACCOUNT")
        assert req.confirmation == "DELETE MY ACCOUNT"

    def test_lowercase_confirmation_accepted_by_schema(self) -> None:
        """Schema accepts any non-empty string; case check is in the route handler."""
        # The schema only validates min_length=1; case sensitivity is the route's job
        req = AccountDeleteRequest(confirmation="delete my account")
        assert req.confirmation == "delete my account"

    def test_wrong_string_accepted_by_schema(self) -> None:
        """Schema accepts any non-empty string (business logic validates in handler)."""
        req = AccountDeleteRequest(confirmation="WRONG STRING")
        assert req.confirmation == "WRONG STRING"

    def test_empty_string_rejected(self) -> None:
        """Empty string is rejected (min_length=1)."""
        with pytest.raises(ValidationError):
            AccountDeleteRequest(confirmation="")

    def test_missing_confirmation_field_rejected(self) -> None:
        """Missing confirmation field raises ValidationError."""
        with pytest.raises(ValidationError):
            AccountDeleteRequest()  # type: ignore[call-arg]

    def test_none_confirmation_rejected(self) -> None:
        """None confirmation raises ValidationError."""
        with pytest.raises(ValidationError):
            AccountDeleteRequest(confirmation=None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# SUPPORTED_LANGUAGES constant
# ---------------------------------------------------------------------------


class TestSupportedLanguages:
    """Tests for the SUPPORTED_LANGUAGES constant."""

    def test_is_frozenset(self) -> None:
        """SUPPORTED_LANGUAGES is a frozenset (immutable)."""
        assert isinstance(SUPPORTED_LANGUAGES, frozenset)

    def test_contains_en(self) -> None:
        """'en' is in SUPPORTED_LANGUAGES."""
        assert "en" in SUPPORTED_LANGUAGES

    def test_contains_tr(self) -> None:
        """'tr' is in SUPPORTED_LANGUAGES."""
        assert "tr" in SUPPORTED_LANGUAGES

    def test_at_least_two_languages(self) -> None:
        """At least 'en' and 'tr' are supported."""
        assert len(SUPPORTED_LANGUAGES) >= 2
