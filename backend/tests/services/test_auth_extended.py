"""Extended unit tests for AuthService.

Covers scenarios NOT in the backend-dev's initial test suite:
- Idempotent registration (Cognito user exists, DB profile missing)
- DB transaction rollback on failure
- Cognito error code mapping completeness (all _raise_cognito_error branches)
- _handle_existing_cognito_user non-401 re-raise
- Login Cognito 503 fallback
- asyncio.to_thread wrapping verification
- Conversation/Character field validation during registration
- _extract_sub edge cases
- Refresh with UserNotFoundException
- DEFAULT_COMPANION_PROMPT constant
"""

from __future__ import annotations

import os
import uuid

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

from datetime import UTC, datetime  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.models.character import Character  # noqa: E402
from app.models.conversation import Conversation  # noqa: E402
from app.models.profile import Profile  # noqa: E402
from app.services.auth_service import DEFAULT_COMPANION_PROMPT, AuthService  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_SUB = "550e8400-e29b-41d4-a716-446655440000"
FAKE_ID_TOKEN = "fake-id-token"
FAKE_REFRESH_TOKEN = "fake-refresh-token"


def _cognito_auth_result() -> dict[str, object]:
    return {
        "AuthenticationResult": {
            "IdToken": FAKE_ID_TOKEN,
            "RefreshToken": FAKE_REFRESH_TOKEN,
            "AccessToken": "fake-access-token",
            "ExpiresIn": 3600,
        },
    }


def _make_cognito_mock() -> MagicMock:
    mock = MagicMock()
    mock.sign_up.return_value = {"UserSub": FAKE_SUB}
    mock.admin_confirm_sign_up.return_value = {}
    mock.initiate_auth.return_value = _cognito_auth_result()
    return mock


def _make_client_error(code: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": f"Mocked {code}"}},
        "TestOp",
    )


def _make_mock_db(
    *,
    profile_exists: bool = False,
) -> tuple[AsyncMock, list[object]]:
    mock_db = AsyncMock()
    added_objects: list[object] = []
    mock_db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    mock_result = MagicMock()
    if profile_exists:
        mock_result.scalar_one_or_none.return_value = _mock_profile()
    else:
        mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def _fake_refresh(obj: object) -> None:
        if not hasattr(obj, "created_at") or obj.created_at is None:  # type: ignore[union-attr]
            object.__setattr__(obj, "created_at", datetime.now(tz=UTC))

    mock_db.refresh = AsyncMock(side_effect=_fake_refresh)
    mock_db.commit = AsyncMock()

    return mock_db, added_objects


def _mock_profile() -> MagicMock:
    p = MagicMock(spec=Profile)
    p.id = uuid.UUID(FAKE_SUB)
    p.email = "test@ember.ai"
    p.name = "Test"
    p.mem0_user_id = f"user_{FAKE_SUB}"
    p.onboarding_completed = False
    p.subscription_tier = "free"
    p.preferred_language = "en"
    p.timezone = "UTC"
    p.avatar_url = None
    p.created_at = datetime.now(tz=UTC)
    return p


# ---------------------------------------------------------------------------
# Idempotent Registration (Service Level)
# ---------------------------------------------------------------------------


class TestIdempotentRegistration:
    """Service-level tests for idempotent registration when Cognito user exists
    but DB profile is missing."""

    @pytest.mark.asyncio
    async def test_idempotent_creates_profile_when_missing(self) -> None:
        """When Cognito user exists and auth succeeds but no profile in DB,
        creates profile/character/conversation."""
        mock_cognito = MagicMock()
        mock_cognito.sign_up.side_effect = _make_client_error("UsernameExistsException")
        mock_cognito.initiate_auth.return_value = _cognito_auth_result()

        mock_db, added_objects = _make_mock_db(profile_exists=False)

        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            svc = AuthService(db=mock_db)
            result = await svc.register("test@ember.ai", "Pass1234!", "Test")

        # Cognito sign_up was attempted then failed
        mock_cognito.sign_up.assert_called_once()
        # admin_confirm was NOT called (user already exists)
        mock_cognito.admin_confirm_sign_up.assert_not_called()
        # initiate_auth was called for authentication
        mock_cognito.initiate_auth.assert_called_once()
        # DB rows were created
        assert len(added_objects) == 3
        assert isinstance(added_objects[0], Profile)
        assert isinstance(added_objects[1], Character)
        assert isinstance(added_objects[2], Conversation)
        # Result has tokens
        assert result.token == FAKE_ID_TOKEN
        assert result.refresh_token == FAKE_REFRESH_TOKEN

    @pytest.mark.asyncio
    async def test_idempotent_skips_creation_when_profile_exists(self) -> None:
        """When Cognito user exists and profile already in DB, returns existing
        profile without creating new rows."""
        mock_cognito = MagicMock()
        mock_cognito.sign_up.side_effect = _make_client_error("UsernameExistsException")
        mock_cognito.initiate_auth.return_value = _cognito_auth_result()

        mock_db, added_objects = _make_mock_db(profile_exists=True)

        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            svc = AuthService(db=mock_db)
            result = await svc.register("test@ember.ai", "Pass1234!", "Test")

        # No new DB rows created
        assert len(added_objects) == 0
        # Existing profile data returned
        assert result.user.email == "test@ember.ai"
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_idempotent_wrong_password_raises_400(self) -> None:
        """When Cognito user exists but password is wrong, return 400."""
        mock_cognito = MagicMock()
        mock_cognito.sign_up.side_effect = _make_client_error("UsernameExistsException")
        mock_cognito.initiate_auth.side_effect = _make_client_error(
            "NotAuthorizedException",
        )

        mock_db, _added = _make_mock_db()

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            svc = AuthService(db=mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await svc.register("test@ember.ai", "WrongPass!", "Test")

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "An account with this email already exists"


# ---------------------------------------------------------------------------
# DB Transaction Rollback
# ---------------------------------------------------------------------------


class TestDBTransactionRollback:
    """Verify DB commit failure is properly handled."""

    @pytest.mark.asyncio
    async def test_commit_failure_propagates_error(self) -> None:
        """When db.commit() raises, the error propagates (SQLAlchemy auto-rollback)."""
        mock_cognito = _make_cognito_mock()
        mock_db, _added = _make_mock_db()
        mock_db.commit = AsyncMock(side_effect=Exception("DB commit failed"))

        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            svc = AuthService(db=mock_db)
            with pytest.raises(Exception, match="DB commit failed"):
                await svc.register("test@ember.ai", "Pass1234!", "Test")

        # The commit was attempted
        mock_db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Cognito Error Mapping (Service Level)
# ---------------------------------------------------------------------------


class TestRaiseCognitoError:
    """Tests for _raise_cognito_error mapping completeness."""

    @pytest.mark.asyncio
    async def test_invalid_parameter_exception(self) -> None:
        """InvalidParameterException maps to 400."""
        mock_cognito = MagicMock()
        mock_cognito.sign_up.side_effect = _make_client_error(
            "InvalidParameterException",
        )
        mock_db, _added = _make_mock_db()

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            svc = AuthService(db=mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await svc.register("test@ember.ai", "Pass1234!", "Test")

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Invalid request parameters"

    @pytest.mark.asyncio
    async def test_too_many_requests_exception(self) -> None:
        """TooManyRequestsException maps to 429."""
        mock_cognito = MagicMock()
        mock_cognito.sign_up.side_effect = _make_client_error(
            "TooManyRequestsException",
        )
        mock_db, _added = _make_mock_db()

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            svc = AuthService(db=mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await svc.register("test@ember.ai", "Pass1234!", "Test")

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == "Too many requests, please try again later"

    @pytest.mark.asyncio
    async def test_unknown_error_code_maps_to_503(self) -> None:
        """Unknown error code maps to 503."""
        mock_cognito = MagicMock()
        mock_cognito.sign_up.side_effect = _make_client_error(
            "SomeUnknownException",
        )
        mock_db, _added = _make_mock_db()

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            svc = AuthService(db=mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await svc.register("test@ember.ai", "Pass1234!", "Test")

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Authentication service unavailable"


# ---------------------------------------------------------------------------
# Handle Existing Cognito User — Non-401 Error Re-raise
# ---------------------------------------------------------------------------


class TestHandleExistingCognitoUserNon401:
    """Test the re-raise path in _handle_existing_cognito_user when
    the HTTPException is NOT a 401."""

    @pytest.mark.asyncio
    async def test_503_during_idempotent_recovery_propagates(self) -> None:
        """If Cognito returns 503 during idempotent auth attempt, it propagates."""
        mock_cognito = MagicMock()
        mock_cognito.sign_up.side_effect = _make_client_error("UsernameExistsException")
        # Cognito unavailable during auth attempt
        mock_cognito.initiate_auth.side_effect = _make_client_error(
            "InternalErrorException",
        )

        mock_db, _added = _make_mock_db()

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            svc = AuthService(db=mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await svc.register("test@ember.ai", "Pass1234!", "Test")

        # The 503 should propagate, not be converted to 400
        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Authentication service unavailable"


# ---------------------------------------------------------------------------
# Login Cognito 503 Fallback
# ---------------------------------------------------------------------------


class TestLoginCognitoFallback:
    """Test login error paths not yet covered."""

    @pytest.mark.asyncio
    async def test_login_cognito_unavailable_raises_503(self) -> None:
        """Generic Cognito error during login maps to 503."""
        mock_cognito = MagicMock()
        mock_cognito.initiate_auth.side_effect = _make_client_error(
            "InternalErrorException",
        )
        mock_db, _added = _make_mock_db()

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            svc = AuthService(db=mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await svc.login("test@ember.ai", "Pass1234!")

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Authentication service unavailable"

    @pytest.mark.asyncio
    async def test_login_user_not_found_raises_401(self) -> None:
        """UserNotFoundException during login maps to 401 with generic message."""
        mock_cognito = MagicMock()
        mock_cognito.initiate_auth.side_effect = _make_client_error(
            "UserNotFoundException",
        )
        mock_db, _added = _make_mock_db()

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            svc = AuthService(db=mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await svc.login("nobody@ember.ai", "Pass1234!")

        assert exc_info.value.status_code == 401
        # Must be generic to prevent email enumeration
        assert exc_info.value.detail == "Invalid email or password"


# ---------------------------------------------------------------------------
# Refresh Error Paths
# ---------------------------------------------------------------------------


class TestRefreshErrors:
    """Extended refresh error tests."""

    @pytest.mark.asyncio
    async def test_refresh_user_not_found_raises_401(self) -> None:
        """UserNotFoundException during refresh maps to 401."""
        mock_cognito = MagicMock()
        mock_cognito.initiate_auth.side_effect = _make_client_error(
            "UserNotFoundException",
        )

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            svc = AuthService(db=None)  # type: ignore[arg-type]
            with pytest.raises(HTTPException) as exc_info:
                await svc.refresh("some-token")

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid or expired refresh token"


# ---------------------------------------------------------------------------
# Character and Conversation Field Validation
# ---------------------------------------------------------------------------


class TestRegistrationDBRows:
    """Verify all fields on created DB rows match the spec."""

    @pytest.mark.asyncio
    async def test_profile_fields(self) -> None:
        """Profile has correct fields: id=sub, email, name, mem0_user_id, defaults."""
        mock_cognito = _make_cognito_mock()
        mock_db, added_objects = _make_mock_db()

        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            svc = AuthService(db=mock_db)
            await svc.register("user@ember.ai", "Pass1234!", "UserName")

        profile: Profile = added_objects[0]  # type: ignore[assignment]
        assert profile.id == uuid.UUID(FAKE_SUB)
        assert profile.email == "user@ember.ai"
        assert profile.name == "UserName"
        assert profile.mem0_user_id == f"user_{FAKE_SUB}"
        assert profile.timezone == "UTC"
        assert profile.preferred_language == "en"
        assert profile.onboarding_completed is False
        assert profile.subscription_tier == "free"

    @pytest.mark.asyncio
    async def test_character_fields(self) -> None:
        """Character has correct fields: template=companion, is_default=True, etc."""
        mock_cognito = _make_cognito_mock()
        mock_db, added_objects = _make_mock_db()

        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            svc = AuthService(db=mock_db)
            await svc.register("user@ember.ai", "Pass1234!", "CharUser")

        character: Character = added_objects[1]  # type: ignore[assignment]
        assert character.user_id == uuid.UUID(FAKE_SUB)
        assert character.name == "Ember"
        assert character.template == "companion"
        assert character.description is None
        assert character.mem0_agent_id == f"companion_{FAKE_SUB}"
        assert character.avatar_style == "default"
        assert character.is_default is True
        assert character.is_active is True
        # System prompt contains user's name
        assert "CharUser" in character.system_prompt
        expected_prompt = DEFAULT_COMPANION_PROMPT.format(user_name="CharUser")
        assert character.system_prompt == expected_prompt

    @pytest.mark.asyncio
    async def test_conversation_fields(self) -> None:
        """Conversation links to correct user and character, last_message_at is None."""
        mock_cognito = _make_cognito_mock()
        mock_db, added_objects = _make_mock_db()

        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            svc = AuthService(db=mock_db)
            await svc.register("user@ember.ai", "Pass1234!", "ConvUser")

        character: Character = added_objects[1]  # type: ignore[assignment]
        conversation: Conversation = added_objects[2]  # type: ignore[assignment]

        assert conversation.user_id == uuid.UUID(FAKE_SUB)
        assert conversation.character_id == character.id
        assert conversation.last_message_at is None

    @pytest.mark.asyncio
    async def test_character_id_is_valid_uuid(self) -> None:
        """Character.id is a valid UUID4."""
        mock_cognito = _make_cognito_mock()
        mock_db, added_objects = _make_mock_db()

        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            svc = AuthService(db=mock_db)
            await svc.register("user@ember.ai", "Pass1234!", "Test")

        character: Character = added_objects[1]  # type: ignore[assignment]
        conversation: Conversation = added_objects[2]  # type: ignore[assignment]

        # Character and conversation IDs are valid UUIDs
        assert isinstance(character.id, uuid.UUID)
        assert isinstance(conversation.id, uuid.UUID)
        # They are different UUIDs
        assert character.id != conversation.id

    @pytest.mark.asyncio
    async def test_db_commit_called_once(self) -> None:
        """Only one db.commit() call during registration (single transaction)."""
        mock_cognito = _make_cognito_mock()
        mock_db, _added = _make_mock_db()

        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            svc = AuthService(db=mock_db)
            await svc.register("user@ember.ai", "Pass1234!", "Test")

        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_db_refresh_called_on_profile(self) -> None:
        """db.refresh() is called after commit to populate server-generated fields."""
        mock_cognito = _make_cognito_mock()
        mock_db, added_objects = _make_mock_db()

        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            svc = AuthService(db=mock_db)
            await svc.register("user@ember.ai", "Pass1234!", "Test")

        mock_db.refresh.assert_called_once()
        # The argument to refresh should be the Profile object
        refresh_arg = mock_db.refresh.call_args[0][0]
        assert isinstance(refresh_arg, Profile)


# ---------------------------------------------------------------------------
# asyncio.to_thread Wrapping
# ---------------------------------------------------------------------------


class TestAsyncioToThread:
    """Verify Cognito calls go through asyncio.to_thread."""

    @pytest.mark.asyncio
    async def test_register_uses_to_thread_for_cognito_calls(self) -> None:
        """Registration wraps Cognito calls in asyncio.to_thread."""
        mock_cognito = _make_cognito_mock()
        mock_db, _added = _make_mock_db()

        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
            patch(
                "app.services.auth_service.asyncio.to_thread",
                wraps=__import__("asyncio").to_thread,
            ) as mock_to_thread,
        ):
            svc = AuthService(db=mock_db)
            await svc.register("test@ember.ai", "Pass1234!", "Test")

        # to_thread should be called for sign_up, admin_confirm, and initiate_auth
        assert mock_to_thread.call_count == 3

    @pytest.mark.asyncio
    async def test_login_uses_to_thread(self) -> None:
        """Login wraps Cognito initiate_auth in asyncio.to_thread."""
        mock_cognito = _make_cognito_mock()
        mock_db, _added = _make_mock_db(profile_exists=True)

        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
            patch(
                "app.services.auth_service.asyncio.to_thread",
                wraps=__import__("asyncio").to_thread,
            ) as mock_to_thread,
        ):
            svc = AuthService(db=mock_db)
            await svc.login("test@ember.ai", "Pass1234!")

        # to_thread called once for initiate_auth
        assert mock_to_thread.call_count == 1

    @pytest.mark.asyncio
    async def test_refresh_uses_to_thread(self) -> None:
        """Refresh wraps Cognito initiate_auth in asyncio.to_thread."""
        mock_cognito = MagicMock()
        mock_cognito.initiate_auth.return_value = {
            "AuthenticationResult": {
                "IdToken": "new-id-token",
                "AccessToken": "new-access-token",
                "ExpiresIn": 3600,
            },
        }

        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.asyncio.to_thread",
                wraps=__import__("asyncio").to_thread,
            ) as mock_to_thread,
        ):
            svc = AuthService(db=None)  # type: ignore[arg-type]
            await svc.refresh("valid-token")

        assert mock_to_thread.call_count == 1


# ---------------------------------------------------------------------------
# DEFAULT_COMPANION_PROMPT Constant
# ---------------------------------------------------------------------------


class TestDefaultCompanionPrompt:
    """Tests for the DEFAULT_COMPANION_PROMPT constant."""

    def test_prompt_contains_placeholder(self) -> None:
        """Prompt template contains {user_name} placeholder."""
        assert "{user_name}" in DEFAULT_COMPANION_PROMPT

    def test_prompt_can_be_formatted(self) -> None:
        """Prompt template can be formatted with user_name."""
        result = DEFAULT_COMPANION_PROMPT.format(user_name="Alex")
        assert "Alex" in result
        assert "{user_name}" not in result

    def test_prompt_contains_key_personality_traits(self) -> None:
        """Prompt contains essential personality descriptors from the spec."""
        assert "warm" in DEFAULT_COMPANION_PROMPT.lower()
        assert "honest" in DEFAULT_COMPANION_PROMPT.lower()
        assert "genuine" in DEFAULT_COMPANION_PROMPT.lower()
        assert "concise" in DEFAULT_COMPANION_PROMPT.lower()


# ---------------------------------------------------------------------------
# _extract_sub Edge Cases
# ---------------------------------------------------------------------------


class TestExtractSub:
    """Tests for AuthService._extract_sub static method."""

    def test_extract_sub_returns_uuid(self) -> None:
        """_extract_sub returns a UUID from a JWT with sub claim."""
        with patch(
            "app.services.auth_service.jwt.get_unverified_claims",
            return_value={"sub": FAKE_SUB},
        ):
            result = AuthService._extract_sub("any-token")

        assert isinstance(result, uuid.UUID)
        assert str(result) == FAKE_SUB

    def test_extract_sub_with_different_uuid(self) -> None:
        """_extract_sub works with different UUID values."""
        other_sub = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        with patch(
            "app.services.auth_service.jwt.get_unverified_claims",
            return_value={"sub": other_sub},
        ):
            result = AuthService._extract_sub("any-token")

        assert str(result) == other_sub


# ---------------------------------------------------------------------------
# Cognito Lazy Initialization
# ---------------------------------------------------------------------------


class TestCognitoLazyInit:
    """Tests for the lazy initialization of the Cognito client."""

    def test_cognito_client_initially_none(self) -> None:
        """The _cognito_client attribute starts as None."""
        svc = AuthService(db=AsyncMock())
        assert svc._cognito_client is None

    def test_cognito_property_creates_client(self) -> None:
        """Accessing the cognito property initializes the boto3 client."""
        with patch("app.services.auth_service.boto3.client") as mock_boto:
            mock_boto.return_value = MagicMock()
            svc = AuthService(db=AsyncMock())
            client = svc.cognito

        mock_boto.assert_called_once_with(
            "cognito-idp",
            region_name=__import__("app.config", fromlist=["settings"]).settings.aws_region,
        )
        assert client is not None

    def test_cognito_property_reuses_client(self) -> None:
        """Accessing the cognito property twice returns the same client."""
        with patch("app.services.auth_service.boto3.client") as mock_boto:
            mock_boto.return_value = MagicMock()
            svc = AuthService(db=AsyncMock())
            client1 = svc.cognito
            client2 = svc.cognito

        # Only called once (lazy)
        mock_boto.assert_called_once()
        assert client1 is client2


# ---------------------------------------------------------------------------
# Login DB Query Verification
# ---------------------------------------------------------------------------


class TestLoginDBQuery:
    """Verify login queries the database correctly."""

    @pytest.mark.asyncio
    async def test_login_calls_db_execute_once(self) -> None:
        """Login calls db.execute exactly once to look up the profile."""
        mock_cognito = _make_cognito_mock()
        mock_db, _added = _make_mock_db(profile_exists=True)

        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            svc = AuthService(db=mock_db)
            await svc.login("test@ember.ai", "Pass1234!")

        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_does_not_modify_db(self) -> None:
        """Login does not call db.add, db.commit, or db.refresh."""
        mock_cognito = _make_cognito_mock()
        mock_db, added_objects = _make_mock_db(profile_exists=True)

        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            svc = AuthService(db=mock_db)
            await svc.login("test@ember.ai", "Pass1234!")

        assert len(added_objects) == 0
        mock_db.commit.assert_not_called()
        mock_db.refresh.assert_not_called()
