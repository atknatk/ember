"""Unit tests for AuthService — Cognito and DB interactions.

All external calls (boto3 Cognito, database) are mocked. Tests verify
that the service orchestrates Cognito calls correctly, builds the right
DB rows, and maps errors to HTTPExceptions.
"""

from __future__ import annotations

import os
import uuid

# Ensure test environment is set before any app imports.
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
    """Create a properly configured mock AsyncSession.

    Returns the mock_db and a list that collects all db.add() calls.
    """
    mock_db = AsyncMock()
    added_objects: list[object] = []
    mock_db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))

    # Configure execute -> scalar_one_or_none for _get_profile
    mock_result = MagicMock()
    if profile_exists:
        mock_result.scalar_one_or_none.return_value = _mock_profile()
    else:
        mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    # Configure refresh to set created_at on the object
    async def _fake_refresh(obj: object) -> None:
        if not hasattr(obj, "created_at") or obj.created_at is None:  # type: ignore[union-attr]
            object.__setattr__(obj, "created_at", datetime.now(tz=UTC))

    mock_db.refresh = AsyncMock(side_effect=_fake_refresh)
    mock_db.commit = AsyncMock()

    return mock_db, added_objects


def _mock_profile() -> MagicMock:
    """Create a mock Profile with all required fields."""
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
# Registration tests
# ---------------------------------------------------------------------------


class TestRegister:
    """Tests for AuthService.register()."""

    @pytest.mark.asyncio
    async def test_register_calls_cognito_in_order(self) -> None:
        """sign_up, admin_confirm_sign_up, initiate_auth called in sequence."""
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
            result = await svc.register("test@ember.ai", "Pass1234!", "Test")

        mock_cognito.sign_up.assert_called_once()
        mock_cognito.admin_confirm_sign_up.assert_called_once()
        mock_cognito.initiate_auth.assert_called_once()
        assert result.token == FAKE_ID_TOKEN
        assert result.refresh_token == FAKE_REFRESH_TOKEN

    @pytest.mark.asyncio
    async def test_register_creates_profile_character_conversation(self) -> None:
        """All three DB rows are added and committed in a single transaction."""
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
            await svc.register("test@ember.ai", "Pass1234!", "Test")

        assert len(added_objects) == 3
        assert isinstance(added_objects[0], Profile)
        assert isinstance(added_objects[1], Character)
        assert isinstance(added_objects[2], Conversation)
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_sets_mem0_ids_correctly(self) -> None:
        """Profile.mem0_user_id and Character.mem0_agent_id use correct format."""
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
            await svc.register("test@ember.ai", "Pass1234!", "Test")

        profile: Profile = added_objects[0]  # type: ignore[assignment]
        character: Character = added_objects[1]  # type: ignore[assignment]
        assert profile.mem0_user_id == f"user_{FAKE_SUB}"
        assert character.mem0_agent_id == f"companion_{FAKE_SUB}"

    @pytest.mark.asyncio
    async def test_register_character_name_and_prompt(self) -> None:
        """Default character is named 'Ember' with user_name substituted in prompt."""
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
            await svc.register("test@ember.ai", "Pass1234!", "TestUser")

        character: Character = added_objects[1]  # type: ignore[assignment]
        assert character.name == "Ember"
        assert character.template == "companion"
        assert character.is_default is True
        expected_prompt = DEFAULT_COMPANION_PROMPT.format(user_name="TestUser")
        assert character.system_prompt == expected_prompt


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------


class TestLogin:
    """Tests for AuthService.login()."""

    @pytest.mark.asyncio
    async def test_login_success(self) -> None:
        """Login returns tokens and user profile when credentials are valid."""
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
            result = await svc.login("test@ember.ai", "Pass1234!")

        assert result.token == FAKE_ID_TOKEN
        assert result.refresh_token == FAKE_REFRESH_TOKEN
        assert result.user.email == "test@ember.ai"

    @pytest.mark.asyncio
    async def test_login_no_profile_raises_401(self) -> None:
        """Login with valid Cognito auth but no DB profile returns 401."""
        mock_cognito = _make_cognito_mock()
        mock_db, _added = _make_mock_db(profile_exists=False)

        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            svc = AuthService(db=mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await svc.login("test@ember.ai", "Pass1234!")

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid email or password"

    @pytest.mark.asyncio
    async def test_login_wrong_password_raises_401(self) -> None:
        """Login with wrong password returns 401."""
        mock_cognito = _make_cognito_mock()
        mock_cognito.initiate_auth.side_effect = _make_client_error(
            "NotAuthorizedException",
        )
        mock_db, _added = _make_mock_db()

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            svc = AuthService(db=mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await svc.login("test@ember.ai", "wrong")

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid email or password"

    @pytest.mark.asyncio
    async def test_login_user_not_confirmed(self) -> None:
        """Login with unconfirmed user returns 401."""
        mock_cognito = _make_cognito_mock()
        mock_cognito.initiate_auth.side_effect = _make_client_error(
            "UserNotConfirmedException",
        )
        mock_db, _added = _make_mock_db()

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            svc = AuthService(db=mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await svc.login("test@ember.ai", "Pass1234!")

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "User is not confirmed"


# ---------------------------------------------------------------------------
# Refresh tests
# ---------------------------------------------------------------------------


class TestRefresh:
    """Tests for AuthService.refresh()."""

    @pytest.mark.asyncio
    async def test_refresh_success(self) -> None:
        """Refresh returns a new ID token."""
        mock_cognito = _make_cognito_mock()
        # For refresh, Cognito does not return RefreshToken
        mock_cognito.initiate_auth.return_value = {
            "AuthenticationResult": {
                "IdToken": "new-id-token",
                "AccessToken": "new-access-token",
                "ExpiresIn": 3600,
            },
        }

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            svc = AuthService(db=None)  # type: ignore[arg-type]
            result = await svc.refresh("valid-refresh-token")

        assert result.token == "new-id-token"
        mock_cognito.initiate_auth.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_invalid_token_raises_401(self) -> None:
        """Refresh with invalid token returns 401."""
        mock_cognito = _make_cognito_mock()
        mock_cognito.initiate_auth.side_effect = _make_client_error(
            "NotAuthorizedException",
        )

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            svc = AuthService(db=None)  # type: ignore[arg-type]
            with pytest.raises(HTTPException) as exc_info:
                await svc.refresh("expired-token")

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid or expired refresh token"

    @pytest.mark.asyncio
    async def test_refresh_cognito_unavailable_raises_503(self) -> None:
        """Refresh raises 503 when Cognito is unavailable."""
        mock_cognito = _make_cognito_mock()
        mock_cognito.initiate_auth.side_effect = _make_client_error(
            "InternalErrorException",
        )

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            svc = AuthService(db=None)  # type: ignore[arg-type]
            with pytest.raises(HTTPException) as exc_info:
                await svc.refresh("some-token")

        assert exc_info.value.status_code == 503
