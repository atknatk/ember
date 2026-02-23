"""Extended route-level tests for authentication endpoints.

Covers scenarios NOT in the backend-dev's initial test suite:
- Idempotent registration (Cognito user exists, DB profile missing)
- Cognito error code mapping completeness
- Response schema field validation
- Email normalization edge cases at the route level
- Login Cognito unavailable (503)
- Refresh UserNotFoundException
- Password edge cases
- Name edge cases
- Missing/extra fields
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

from collections.abc import AsyncGenerator  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.dependencies import get_db  # noqa: E402
from app.main import app  # noqa: E402

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.add = MagicMock()

    async def _fake_refresh(obj: object) -> None:
        if not hasattr(obj, "created_at") or getattr(obj, "created_at", None) is None:
            object.__setattr__(obj, "created_at", datetime.now(tz=UTC))

    mock_db.refresh = AsyncMock(side_effect=_fake_refresh)
    mock_db.commit = AsyncMock()
    yield mock_db


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Idempotent Registration Tests
# ---------------------------------------------------------------------------


class TestRegisterIdempotent:
    """Tests for idempotent registration when Cognito user exists but DB profile is missing."""

    @pytest.mark.asyncio
    async def test_register_idempotent_recovery_creates_profile(
        self, client: AsyncClient,
    ) -> None:
        """When Cognito user exists but DB profile is missing, registration
        should authenticate and create the missing DB rows."""
        mock_cognito = MagicMock()
        # sign_up raises UsernameExistsException
        mock_cognito.sign_up.side_effect = _make_client_error("UsernameExistsException")
        # But initiate_auth succeeds with correct password
        mock_cognito.initiate_auth.return_value = _cognito_auth_result()

        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "recover@ember.ai",
                    "password": "CorrectPass123!",
                    "name": "Recovery",
                },
            )

        # Should succeed since auth works and profile gets created
        assert resp.status_code == 201
        data = resp.json()
        assert data["token"] == FAKE_ID_TOKEN
        assert data["refresh_token"] == FAKE_REFRESH_TOKEN
        assert data["user"]["email"] == "recover@ember.ai"
        assert data["user"]["name"] == "Recovery"

    @pytest.mark.asyncio
    async def test_register_existing_user_wrong_password_returns_400(
        self, client: AsyncClient,
    ) -> None:
        """When Cognito user exists and password is wrong, return 400."""
        mock_cognito = MagicMock()
        mock_cognito.sign_up.side_effect = _make_client_error("UsernameExistsException")
        mock_cognito.initiate_auth.side_effect = _make_client_error(
            "NotAuthorizedException",
        )

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "existing@ember.ai",
                    "password": "WrongPass123!",
                    "name": "Alex",
                },
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "An account with this email already exists"

    @pytest.mark.asyncio
    async def test_register_idempotent_recovery_skips_if_profile_exists(
        self, client: AsyncClient,
    ) -> None:
        """When Cognito user AND DB profile both exist, registration still
        succeeds by returning the existing profile."""
        mock_cognito = MagicMock()
        mock_cognito.sign_up.side_effect = _make_client_error("UsernameExistsException")
        mock_cognito.initiate_auth.return_value = _cognito_auth_result()

        # Profile exists in DB
        import uuid

        mock_profile = MagicMock()
        mock_profile.id = uuid.UUID(FAKE_SUB)
        mock_profile.email = "existing@ember.ai"
        mock_profile.name = "Existing"
        mock_profile.onboarding_completed = False
        mock_profile.subscription_tier = "free"
        mock_profile.preferred_language = "en"
        mock_profile.timezone = "UTC"
        mock_profile.avatar_url = None
        mock_profile.created_at = datetime.now(tz=UTC)

        async def _override_db_with_profile() -> AsyncGenerator[AsyncMock, None]:
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_profile
            mock_db.execute = AsyncMock(return_value=mock_result)
            mock_db.add = MagicMock()
            mock_db.commit = AsyncMock()
            mock_db.refresh = AsyncMock()
            yield mock_db

        app.dependency_overrides[get_db] = _override_db_with_profile

        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "existing@ember.ai",
                    "password": "CorrectPass123!",
                    "name": "NewName",
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        # Returns the existing profile data
        assert data["user"]["name"] == "Existing"


# ---------------------------------------------------------------------------
# Cognito Error Mapping Completeness
# ---------------------------------------------------------------------------


class TestRegisterCognitoErrors:
    """Tests for Cognito error code mapping during registration."""

    @pytest.mark.asyncio
    async def test_register_invalid_parameter_returns_400(
        self, client: AsyncClient,
    ) -> None:
        """InvalidParameterException from Cognito returns 400."""
        mock_cognito = MagicMock()
        mock_cognito.sign_up.side_effect = _make_client_error(
            "InvalidParameterException",
        )

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "test@ember.ai",
                    "password": "Pass1234!",
                    "name": "Alex",
                },
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid request parameters"

    @pytest.mark.asyncio
    async def test_register_too_many_requests_returns_429(
        self, client: AsyncClient,
    ) -> None:
        """TooManyRequestsException from Cognito returns 429."""
        mock_cognito = MagicMock()
        mock_cognito.sign_up.side_effect = _make_client_error(
            "TooManyRequestsException",
        )

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "test@ember.ai",
                    "password": "Pass1234!",
                    "name": "Alex",
                },
            )

        assert resp.status_code == 429
        assert resp.json()["detail"] == "Too many requests, please try again later"

    @pytest.mark.asyncio
    async def test_register_unknown_cognito_error_returns_503(
        self, client: AsyncClient,
    ) -> None:
        """Unknown Cognito error code falls back to 503."""
        mock_cognito = MagicMock()
        mock_cognito.sign_up.side_effect = _make_client_error(
            "LimitExceededException",
        )

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "test@ember.ai",
                    "password": "Pass1234!",
                    "name": "Alex",
                },
            )

        assert resp.status_code == 503
        assert resp.json()["detail"] == "Authentication service unavailable"


class TestLoginCognitoErrors:
    """Tests for Cognito error mapping during login."""

    @pytest.mark.asyncio
    async def test_login_cognito_unavailable_returns_503(
        self, client: AsyncClient,
    ) -> None:
        """Generic Cognito error during login returns 503."""
        mock_cognito = MagicMock()
        mock_cognito.initiate_auth.side_effect = _make_client_error(
            "InternalErrorException",
        )

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": "test@ember.ai", "password": "Pass1234!"},
            )

        assert resp.status_code == 503
        assert resp.json()["detail"] == "Authentication service unavailable"

    @pytest.mark.asyncio
    async def test_login_missing_email_returns_422(
        self, client: AsyncClient,
    ) -> None:
        """Missing email in login body returns 422."""
        resp = await client.post(
            "/api/v1/auth/login",
            json={"password": "Pass1234!"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_login_missing_password_returns_422(
        self, client: AsyncClient,
    ) -> None:
        """Missing password in login body returns 422."""
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "test@ember.ai"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_login_invalid_email_format_returns_422(
        self, client: AsyncClient,
    ) -> None:
        """Invalid email format in login returns 422."""
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "not-an-email", "password": "Pass1234!"},
        )
        assert resp.status_code == 422


class TestRefreshCognitoErrors:
    """Tests for Cognito error mapping during refresh."""

    @pytest.mark.asyncio
    async def test_refresh_user_not_found_returns_401(
        self, client: AsyncClient,
    ) -> None:
        """UserNotFoundException during refresh returns 401."""
        mock_cognito = MagicMock()
        mock_cognito.initiate_auth.side_effect = _make_client_error(
            "UserNotFoundException",
        )

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            resp = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "some-token"},
            )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid or expired refresh token"

    @pytest.mark.asyncio
    async def test_refresh_cognito_unavailable_returns_503(
        self, client: AsyncClient,
    ) -> None:
        """Cognito unavailable during refresh returns 503."""
        mock_cognito = MagicMock()
        mock_cognito.initiate_auth.side_effect = _make_client_error(
            "ServiceUnavailableException",
        )

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            resp = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "some-token"},
            )

        assert resp.status_code == 503
        assert resp.json()["detail"] == "Authentication service unavailable"

    @pytest.mark.asyncio
    async def test_refresh_empty_token_returns_422(
        self, client: AsyncClient,
    ) -> None:
        """Empty refresh_token string returns 422."""
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": ""},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Response Schema Validation
# ---------------------------------------------------------------------------


class TestResponseSchemaValidation:
    """Verify response payloads have the exact fields and types from the spec."""

    @pytest.mark.asyncio
    async def test_register_response_has_all_user_fields(
        self, client: AsyncClient,
    ) -> None:
        """Register response user object has all spec-required fields."""
        mock_cognito = _make_cognito_mock()
        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "schema@ember.ai",
                    "password": "Pass1234!",
                    "name": "SchemaTest",
                },
            )

        assert resp.status_code == 201
        data = resp.json()

        # Top-level fields
        assert set(data.keys()) == {"token", "refresh_token", "user"}
        assert isinstance(data["token"], str)
        assert isinstance(data["refresh_token"], str)

        # User object required fields
        user = data["user"]
        required_keys = {
            "id", "email", "name", "onboarding_completed",
            "subscription_tier", "preferred_language", "timezone",
            "avatar_url", "created_at",
        }
        assert required_keys.issubset(set(user.keys()))

        # Type checks
        assert isinstance(user["id"], str)
        assert isinstance(user["email"], str)
        assert isinstance(user["name"], str)
        assert isinstance(user["onboarding_completed"], bool)
        assert isinstance(user["subscription_tier"], str)
        assert isinstance(user["preferred_language"], str)
        assert isinstance(user["timezone"], str)
        assert user["avatar_url"] is None
        assert isinstance(user["created_at"], str)

    @pytest.mark.asyncio
    async def test_register_response_default_values(
        self, client: AsyncClient,
    ) -> None:
        """Register response user has correct default values per spec."""
        mock_cognito = _make_cognito_mock()
        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "defaults@ember.ai",
                    "password": "Pass1234!",
                    "name": "Defaults",
                },
            )

        user = resp.json()["user"]
        assert user["onboarding_completed"] is False
        assert user["subscription_tier"] == "free"
        assert user["preferred_language"] == "en"
        assert user["timezone"] == "UTC"
        assert user["avatar_url"] is None

    @pytest.mark.asyncio
    async def test_refresh_response_has_no_refresh_token(
        self, client: AsyncClient,
    ) -> None:
        """Refresh response must contain only 'token', not 'refresh_token'."""
        mock_cognito = MagicMock()
        mock_cognito.initiate_auth.return_value = {
            "AuthenticationResult": {
                "IdToken": "new-id-token",
                "AccessToken": "new-access-token",
                "ExpiresIn": 3600,
            },
        }

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            resp = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "valid-token"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "refresh_token" not in data
        assert set(data.keys()) == {"token"}


# ---------------------------------------------------------------------------
# Email Normalization Edge Cases at Route Level
# ---------------------------------------------------------------------------


class TestEmailNormalizationRoutes:
    """Verify email normalization works end-to-end through routes."""

    @pytest.mark.asyncio
    async def test_register_uppercase_email_normalized(
        self, client: AsyncClient,
    ) -> None:
        """Email with mixed case is lowercased in response."""
        mock_cognito = _make_cognito_mock()
        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "TeSt@EXAMPLE.COM",
                    "password": "Pass1234!",
                    "name": "Alex",
                },
            )

        assert resp.status_code == 201
        assert resp.json()["user"]["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_register_email_with_leading_trailing_spaces(
        self, client: AsyncClient,
    ) -> None:
        """Email with surrounding whitespace is trimmed and lowercased."""
        mock_cognito = _make_cognito_mock()
        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "  User@Example.COM  ",
                    "password": "Pass1234!",
                    "name": "Alex",
                },
            )

        # EmailStr + lowercase_email validator should handle this.
        # Note: leading/trailing whitespace may be rejected by EmailStr
        # validation. If so, this would be 422 -- either outcome is acceptable.
        assert resp.status_code in (201, 422)
        if resp.status_code == 201:
            assert resp.json()["user"]["email"] == "user@example.com"


# ---------------------------------------------------------------------------
# Password Edge Cases
# ---------------------------------------------------------------------------


class TestPasswordEdgeCases:
    """Test password validation edge cases."""

    @pytest.mark.asyncio
    async def test_register_password_exactly_8_chars_accepted(
        self, client: AsyncClient,
    ) -> None:
        """Password of exactly 8 characters passes Pydantic validation."""
        mock_cognito = _make_cognito_mock()
        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "pass8@ember.ai",
                    "password": "12345678",
                    "name": "Alex",
                },
            )

        # Should pass Pydantic validation (min_length=8).
        # Cognito may still reject it, but we get past the 422 check.
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_register_password_7_chars_rejected(
        self, client: AsyncClient,
    ) -> None:
        """Password of 7 characters is rejected with 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "pass7@ember.ai",
                "password": "1234567",
                "name": "Alex",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_missing_password_field(
        self, client: AsyncClient,
    ) -> None:
        """Missing password field returns 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "a@b.com", "name": "Alex"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_login_password_min_1_char_accepted(
        self, client: AsyncClient,
    ) -> None:
        """Login accepts any non-empty password (min_length=1)."""
        mock_cognito = MagicMock()
        mock_cognito.initiate_auth.side_effect = _make_client_error(
            "NotAuthorizedException",
        )

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": "test@ember.ai", "password": "x"},
            )

        # Should pass validation but fail at Cognito
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Name Edge Cases
# ---------------------------------------------------------------------------


class TestNameEdgeCases:
    """Test name field validation edge cases."""

    @pytest.mark.asyncio
    async def test_register_name_with_only_spaces_rejected(
        self, client: AsyncClient,
    ) -> None:
        """Name consisting of only spaces (after strip becomes empty) is rejected."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "a@b.com",
                "password": "Pass1234!",
                "name": "     ",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_name_with_tabs_stripped(
        self, client: AsyncClient,
    ) -> None:
        """Name with tabs and spaces is stripped."""
        mock_cognito = _make_cognito_mock()
        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "tabs@ember.ai",
                    "password": "Pass1234!",
                    "name": "\t Alex \t",
                },
            )

        assert resp.status_code == 201
        assert resp.json()["user"]["name"] == "Alex"

    @pytest.mark.asyncio
    async def test_register_single_char_name_accepted(
        self, client: AsyncClient,
    ) -> None:
        """Single character name is accepted (min_length=1 after strip)."""
        mock_cognito = _make_cognito_mock()
        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "singlechar@ember.ai",
                    "password": "Pass1234!",
                    "name": "A",
                },
            )

        assert resp.status_code == 201
        assert resp.json()["user"]["name"] == "A"

    @pytest.mark.asyncio
    async def test_register_name_101_chars_rejected(
        self, client: AsyncClient,
    ) -> None:
        """Name over 100 chars is rejected with 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "a@b.com",
                "password": "Pass1234!",
                "name": "A" * 101,
            },
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Request Body Edge Cases
# ---------------------------------------------------------------------------


class TestRequestBodyEdgeCases:
    """Test unusual request body scenarios."""

    @pytest.mark.asyncio
    async def test_register_empty_body_returns_422(
        self, client: AsyncClient,
    ) -> None:
        """Completely empty JSON body returns 422."""
        resp = await client.post("/api/v1/auth/register", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_login_empty_body_returns_422(
        self, client: AsyncClient,
    ) -> None:
        """Completely empty JSON body for login returns 422."""
        resp = await client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_extra_fields_ignored(
        self, client: AsyncClient,
    ) -> None:
        """Extra fields in request body are silently ignored by Pydantic."""
        mock_cognito = _make_cognito_mock()
        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "extra@ember.ai",
                    "password": "Pass1234!",
                    "name": "Alex",
                    "extra_field": "should be ignored",
                    "is_admin": True,
                },
            )

        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_register_null_name_returns_422(
        self, client: AsyncClient,
    ) -> None:
        """Null value for name returns 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "a@b.com",
                "password": "Pass1234!",
                "name": None,
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_null_password_returns_422(
        self, client: AsyncClient,
    ) -> None:
        """Null value for password returns 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "a@b.com",
                "password": None,
                "name": "Alex",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_refresh_null_token_returns_422(
        self, client: AsyncClient,
    ) -> None:
        """Null value for refresh_token returns 422."""
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": None},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_no_content_type_returns_422(
        self, client: AsyncClient,
    ) -> None:
        """Request without JSON content type returns 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            content=b"not json",
            headers={"content-type": "text/plain"},
        )
        assert resp.status_code == 422
