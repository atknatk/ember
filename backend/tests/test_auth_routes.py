"""Route-level integration tests for authentication endpoints.

Uses the FastAPI test client with mocked AuthService to test request
validation, HTTP status codes, and response structure without touching
Cognito or a real database.
"""

from __future__ import annotations

import os
import uuid

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
    """Create a sync MagicMock for the boto3 Cognito client.

    MUST be MagicMock (not AsyncMock) because the Cognito calls are
    synchronous methods invoked via asyncio.to_thread.
    """
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
    # Configure execute -> scalar_one_or_none -> None  (no profile found)
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
    """Provide an async HTTP client with mocked DB."""
    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Register endpoint tests
# ---------------------------------------------------------------------------


class TestRegisterEndpoint:
    """Tests for POST /api/v1/auth/register."""

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient) -> None:
        """Valid registration returns 201 with token, refresh_token, user."""
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
                    "email": "new@ember.ai",
                    "password": "SecurePass123!",
                    "name": "Alex",
                },
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["token"] == FAKE_ID_TOKEN
        assert data["refresh_token"] == FAKE_REFRESH_TOKEN
        assert data["user"]["email"] == "new@ember.ai"
        assert data["user"]["name"] == "Alex"
        assert data["user"]["onboarding_completed"] is False
        assert data["user"]["subscription_tier"] == "free"
        assert data["user"]["preferred_language"] == "en"
        assert data["user"]["timezone"] == "UTC"
        assert data["user"]["avatar_url"] is None
        assert "created_at" in data["user"]
        assert "id" in data["user"]

    @pytest.mark.asyncio
    async def test_register_email_already_exists(self, client: AsyncClient) -> None:
        """Registration with existing email returns 400."""
        mock_cognito = MagicMock()
        mock_cognito.sign_up.side_effect = _make_client_error("UsernameExistsException")
        # When trying to authenticate with wrong password
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
    async def test_register_invalid_password(self, client: AsyncClient) -> None:
        """Password not meeting Cognito policy returns 400."""
        mock_cognito = MagicMock()
        mock_cognito.sign_up.side_effect = _make_client_error("InvalidPasswordException")

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "new@ember.ai",
                    "password": "weakpass1",
                    "name": "Alex",
                },
            )

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Password does not meet requirements"

    @pytest.mark.asyncio
    async def test_register_missing_email(self, client: AsyncClient) -> None:
        """Missing email field returns 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"password": "Pass1234!", "name": "Alex"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_missing_name(self, client: AsyncClient) -> None:
        """Missing name field returns 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "a@b.com", "password": "Pass1234!"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_invalid_email_format(self, client: AsyncClient) -> None:
        """Invalid email format returns 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": "Pass1234!", "name": "Alex"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_short_password(self, client: AsyncClient) -> None:
        """Password shorter than 8 chars returns 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "a@b.com", "password": "short", "name": "Alex"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_whitespace_only_name(self, client: AsyncClient) -> None:
        """Name that is only whitespace returns 422."""
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "a@b.com", "password": "Pass1234!", "name": "   "},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_cognito_unavailable(self, client: AsyncClient) -> None:
        """Cognito service unavailable returns 503."""
        mock_cognito = MagicMock()
        mock_cognito.sign_up.side_effect = _make_client_error(
            "ServiceUnavailableException",
        )

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            resp = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": "new@ember.ai",
                    "password": "SecurePass123!",
                    "name": "Alex",
                },
            )

        assert resp.status_code == 503
        assert resp.json()["detail"] == "Authentication service unavailable"


# ---------------------------------------------------------------------------
# Login endpoint tests
# ---------------------------------------------------------------------------


class TestLoginEndpoint:
    """Tests for POST /api/v1/auth/login."""

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient) -> None:
        """Valid login returns 200 with token, refresh_token, user."""
        mock_cognito = _make_cognito_mock()
        mock_profile = MagicMock()
        mock_profile.id = uuid.UUID(FAKE_SUB)
        mock_profile.email = "test@ember.ai"
        mock_profile.name = "Alex"
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
                "/api/v1/auth/login",
                json={"email": "test@ember.ai", "password": "Pass1234!"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["token"] == FAKE_ID_TOKEN
        assert data["refresh_token"] == FAKE_REFRESH_TOKEN
        assert data["user"]["email"] == "test@ember.ai"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient) -> None:
        """Wrong password returns 401."""
        mock_cognito = MagicMock()
        mock_cognito.initiate_auth.side_effect = _make_client_error(
            "NotAuthorizedException",
        )

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": "test@ember.ai", "password": "wrong"},
            )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid email or password"

    @pytest.mark.asyncio
    async def test_login_nonexistent_email(self, client: AsyncClient) -> None:
        """Non-existent email returns 401 with generic message."""
        mock_cognito = MagicMock()
        mock_cognito.initiate_auth.side_effect = _make_client_error(
            "UserNotFoundException",
        )

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": "nobody@ember.ai", "password": "Pass1234!"},
            )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid email or password"

    @pytest.mark.asyncio
    async def test_login_user_not_confirmed(self, client: AsyncClient) -> None:
        """Unconfirmed user returns 401."""
        mock_cognito = MagicMock()
        mock_cognito.initiate_auth.side_effect = _make_client_error(
            "UserNotConfirmedException",
        )

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": "test@ember.ai", "password": "Pass1234!"},
            )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "User is not confirmed"

    @pytest.mark.asyncio
    async def test_login_no_profile_in_db(self, client: AsyncClient) -> None:
        """Valid Cognito auth but no profile row returns 401."""
        mock_cognito = _make_cognito_mock()

        with (
            patch("app.services.auth_service.boto3.client", return_value=mock_cognito),
            patch(
                "app.services.auth_service.jwt.get_unverified_claims",
                return_value={"sub": FAKE_SUB},
            ),
        ):
            # Default _override_get_db returns None for scalar_one_or_none
            resp = await client.post(
                "/api/v1/auth/login",
                json={"email": "test@ember.ai", "password": "Pass1234!"},
            )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid email or password"


# ---------------------------------------------------------------------------
# Refresh endpoint tests
# ---------------------------------------------------------------------------


class TestRefreshEndpoint:
    """Tests for POST /api/v1/auth/refresh."""

    @pytest.mark.asyncio
    async def test_refresh_success(self, client: AsyncClient) -> None:
        """Valid refresh token returns 200 with new token."""
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
                json={"refresh_token": "valid-refresh-token"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["token"] == "new-id-token"
        assert "refresh_token" not in data

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, client: AsyncClient) -> None:
        """Invalid refresh token returns 401."""
        mock_cognito = MagicMock()
        mock_cognito.initiate_auth.side_effect = _make_client_error(
            "NotAuthorizedException",
        )

        with patch("app.services.auth_service.boto3.client", return_value=mock_cognito):
            resp = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": "expired-token"},
            )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid or expired refresh token"

    @pytest.mark.asyncio
    async def test_refresh_missing_field(self, client: AsyncClient) -> None:
        """Missing refresh_token field returns 422."""
        resp = await client.post("/api/v1/auth/refresh", json={})
        assert resp.status_code == 422
