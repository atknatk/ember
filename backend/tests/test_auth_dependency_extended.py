"""Extended integration tests for the get_current_user dependency.

Covers edge cases NOT addressed by the backend-dev's test_auth_dependency.py:

- DB session error handling (database exception during profile lookup)
- HTTPBearer edge cases (empty Bearer value, whitespace-only token)
- WWW-Authenticate header on dependency-level 401 responses
- Verify 'User not found' response includes WWW-Authenticate header
- Multiple sequential authenticated requests (token caching behavior)

All tests use locally generated RSA keys -- no network access required.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicNumbers
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.main import app
from app.models.profile import Profile

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_REGION = "eu-west-1"
TEST_POOL_ID = "eu-west-1_TestPool"
TEST_CLIENT_ID = "test-client-id-123"
TEST_KID = "test-kid-001"
TEST_ISSUER = f"https://cognito-idp.{TEST_REGION}.amazonaws.com/{TEST_POOL_ID}"


# ---------------------------------------------------------------------------
# RSA key helpers
# ---------------------------------------------------------------------------


def _generate_rsa_key() -> RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _private_key_to_jwk(private_key: RSAPrivateKey, kid: str) -> dict[str, Any]:
    import base64

    pub_numbers: RSAPublicNumbers = private_key.public_key().public_numbers()

    def _int_to_base64url(value: int) -> str:
        byte_length = (value.bit_length() + 7) // 8
        value_bytes = value.to_bytes(byte_length, byteorder="big")
        return base64.urlsafe_b64encode(value_bytes).rstrip(b"=").decode("ascii")

    return {
        "kty": "RSA",
        "kid": kid,
        "alg": "RS256",
        "use": "sig",
        "n": _int_to_base64url(pub_numbers.n),
        "e": _int_to_base64url(pub_numbers.e),
    }


def _private_key_to_pem(private_key: RSAPrivateKey) -> str:
    pem_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem_bytes.decode("ascii")


def _make_token(
    private_key: RSAPrivateKey,
    kid: str,
    *,
    sub: str | None = None,
    aud: str | None = None,
    iss: str | None = None,
    token_use: str = "id",
    exp_delta: timedelta | None = None,
) -> str:
    from jose import jwt as jose_jwt

    now = datetime.now(tz=UTC)
    exp = now + (exp_delta if exp_delta is not None else timedelta(hours=1))
    claims: dict[str, Any] = {
        "sub": sub or str(uuid.uuid4()),
        "aud": aud or TEST_CLIENT_ID,
        "iss": iss or TEST_ISSUER,
        "token_use": token_use,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "email": "test@ember.ai",
    }
    return jose_jwt.encode(
        claims,
        _private_key_to_pem(private_key),
        algorithm="RS256",
        headers={"kid": kid},
    )


def _create_mock_profile(user_id: str) -> Profile:
    profile = MagicMock(spec=Profile)
    profile.id = uuid.UUID(user_id)
    profile.email = "test@ember.ai"
    profile.name = "Test User"
    return profile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rsa_key() -> RSAPrivateKey:
    return _generate_rsa_key()


@pytest.fixture(scope="module")
def test_sub() -> str:
    return str(uuid.uuid4())


# Ensure the test protected route is registered (same as test_auth_dependency.py)
from fastapi import APIRouter, Depends

_test_router = APIRouter()


@_test_router.get("/api/v1/_test_protected")
async def _protected_endpoint(
    current_user: Profile = Depends(get_current_user),
) -> dict[str, str]:
    return {"user_id": str(current_user.id)}


_route_paths = {r.path for r in app.routes}
if "/api/v1/_test_protected" not in _route_paths:
    app.include_router(_test_router)


# ---------------------------------------------------------------------------
# DB session error handling
# ---------------------------------------------------------------------------


class TestDBSessionErrorHandling:
    """Tests for database errors during profile lookup."""

    @pytest_asyncio.fixture
    async def client_with_db_error(
        self,
        rsa_key: RSAPrivateKey,
    ) -> AsyncGenerator[AsyncClient, None]:
        """Client where DB raises an exception during profile lookup."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock(
            side_effect=Exception("Database connection lost"),
        )

        async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
            yield mock_db

        app.dependency_overrides[get_db] = _override_get_db

        jwk = _private_key_to_jwk(rsa_key, TEST_KID)

        with patch("app.core.auth._jwks_provider") as mock_provider, \
             patch("app.core.auth.settings") as mock_settings:
            mock_provider.get_signing_key = AsyncMock(return_value=jwk)
            mock_provider.issuer_url = TEST_ISSUER
            mock_settings.cognito_app_client_id = TEST_CLIENT_ID

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_db_error_propagates_exception(
        self,
        client_with_db_error: AsyncClient,
        rsa_key: RSAPrivateKey,
    ) -> None:
        """Database exception during profile lookup propagates as an error.

        When using httpx's ASGI transport, unhandled exceptions in
        dependencies propagate to the test. In production, the ASGI
        server (uvicorn) would return HTTP 500.
        """
        token = _make_token(rsa_key, TEST_KID, sub=str(uuid.uuid4()))
        with pytest.raises(Exception, match="Database connection lost"):
            await client_with_db_error.get(
                "/api/v1/_test_protected",
                headers={"Authorization": f"Bearer {token}"},
            )


# ---------------------------------------------------------------------------
# HTTPBearer edge cases via integration tests
# ---------------------------------------------------------------------------


class TestHTTPBearerEdgeCases:
    """Tests for HTTPBearer edge cases via the FastAPI test client."""

    @pytest_asyncio.fixture
    async def basic_client(self) -> AsyncGenerator[AsyncClient, None]:
        """Minimal client with DB override only (no auth mocking)."""
        async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
            yield AsyncMock()

        app.dependency_overrides[get_db] = _override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_empty_bearer_value_returns_401(
        self,
        basic_client: AsyncClient,
    ) -> None:
        """Authorization: Bearer (with empty token) returns 401/403."""
        response = await basic_client.get(
            "/api/v1/_test_protected",
            headers={"Authorization": "Bearer "},
        )
        # HTTPBearer may return 401 or 403 depending on FastAPI version
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_bearer_with_only_whitespace_returns_error(
        self,
        basic_client: AsyncClient,
    ) -> None:
        """Authorization: Bearer with whitespace-only value returns error."""
        response = await basic_client.get(
            "/api/v1/_test_protected",
            headers={"Authorization": "Bearer    "},
        )
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_no_authorization_header_response_body(
        self,
        basic_client: AsyncClient,
    ) -> None:
        """Missing Authorization header returns expected JSON body."""
        response = await basic_client.get("/api/v1/_test_protected")
        assert response.status_code in (401, 403)
        body = response.json()
        assert "detail" in body
        assert body["detail"] == "Not authenticated"

    @pytest.mark.asyncio
    async def test_malformed_authorization_header(
        self,
        basic_client: AsyncClient,
    ) -> None:
        """Authorization header with random text (no scheme) returns 401/403."""
        response = await basic_client.get(
            "/api/v1/_test_protected",
            headers={"Authorization": "JustSomeRandomText"},
        )
        assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# WWW-Authenticate header on dependency-level 401s
# ---------------------------------------------------------------------------


class TestDependencyWWWAuthenticate:
    """Verify WWW-Authenticate header on 401 responses from get_current_user."""

    @pytest_asyncio.fixture
    async def auth_client_no_profile(
        self,
        rsa_key: RSAPrivateKey,
    ) -> AsyncGenerator[AsyncClient, None]:
        """Client where token is valid but no profile exists."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
            yield mock_db

        app.dependency_overrides[get_db] = _override_get_db

        jwk = _private_key_to_jwk(rsa_key, TEST_KID)

        with patch("app.core.auth._jwks_provider") as mock_provider, \
             patch("app.core.auth.settings") as mock_settings:
            mock_provider.get_signing_key = AsyncMock(return_value=jwk)
            mock_provider.issuer_url = TEST_ISSUER
            mock_settings.cognito_app_client_id = TEST_CLIENT_ID

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_user_not_found_has_www_authenticate_header(
        self,
        auth_client_no_profile: AsyncClient,
        rsa_key: RSAPrivateKey,
    ) -> None:
        """'User not found' 401 includes WWW-Authenticate: Bearer header."""
        token = _make_token(rsa_key, TEST_KID, sub=str(uuid.uuid4()))
        response = await auth_client_no_profile.get(
            "/api/v1/_test_protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "User not found"
        # FastAPI includes WWW-Authenticate when the HTTPException headers are set
        assert "www-authenticate" in {k.lower() for k in response.headers}
        assert response.headers.get("www-authenticate") == "Bearer"

    @pytest.mark.asyncio
    async def test_user_not_found_exact_response_shape(
        self,
        auth_client_no_profile: AsyncClient,
        rsa_key: RSAPrivateKey,
    ) -> None:
        """'User not found' response has exact expected shape."""
        token = _make_token(rsa_key, TEST_KID, sub=str(uuid.uuid4()))
        response = await auth_client_no_profile.get(
            "/api/v1/_test_protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        body = response.json()
        assert body == {"detail": "User not found"}


# ---------------------------------------------------------------------------
# Multiple sequential authenticated requests
# ---------------------------------------------------------------------------


class TestMultipleSequentialRequests:
    """Tests for multiple authenticated requests in sequence."""

    @pytest_asyncio.fixture
    async def auth_client(
        self,
        rsa_key: RSAPrivateKey,
        test_sub: str,
    ) -> AsyncGenerator[AsyncClient, None]:
        """Client with valid auth setup."""
        mock_profile = _create_mock_profile(test_sub)

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_profile
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
            yield mock_db

        app.dependency_overrides[get_db] = _override_get_db

        jwk = _private_key_to_jwk(rsa_key, TEST_KID)

        with patch("app.core.auth._jwks_provider") as mock_provider, \
             patch("app.core.auth.settings") as mock_settings:
            mock_provider.get_signing_key = AsyncMock(return_value=jwk)
            mock_provider.issuer_url = TEST_ISSUER
            mock_settings.cognito_app_client_id = TEST_CLIENT_ID

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_two_sequential_requests_both_succeed(
        self,
        auth_client: AsyncClient,
        rsa_key: RSAPrivateKey,
        test_sub: str,
    ) -> None:
        """Two sequential authenticated requests both return 200."""
        token = _make_token(rsa_key, TEST_KID, sub=test_sub)
        headers = {"Authorization": f"Bearer {token}"}

        response1 = await auth_client.get("/api/v1/_test_protected", headers=headers)
        assert response1.status_code == 200
        assert response1.json()["user_id"] == test_sub

        response2 = await auth_client.get("/api/v1/_test_protected", headers=headers)
        assert response2.status_code == 200
        assert response2.json()["user_id"] == test_sub

    @pytest.mark.asyncio
    async def test_tokens_with_different_expiry_same_user(
        self,
        auth_client: AsyncClient,
        rsa_key: RSAPrivateKey,
        test_sub: str,
    ) -> None:
        """Two tokens with different exp for the same sub both authenticate."""
        token1 = _make_token(
            rsa_key, TEST_KID, sub=test_sub, exp_delta=timedelta(hours=1),
        )
        token2 = _make_token(
            rsa_key, TEST_KID, sub=test_sub, exp_delta=timedelta(hours=2),
        )
        # Tokens differ due to different exp values
        assert token1 != token2

        resp1 = await auth_client.get(
            "/api/v1/_test_protected",
            headers={"Authorization": f"Bearer {token1}"},
        )
        resp2 = await auth_client.get(
            "/api/v1/_test_protected",
            headers={"Authorization": f"Bearer {token2}"},
        )

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["user_id"] == resp2.json()["user_id"]


# ---------------------------------------------------------------------------
# Health endpoint accessibility
# ---------------------------------------------------------------------------


class TestHealthEndpointAccessibility:
    """Verify health endpoint remains public regardless of auth state."""

    @pytest.mark.asyncio
    async def test_health_with_invalid_bearer_still_returns_200(self) -> None:
        """Health endpoint ignores invalid Bearer tokens."""
        async def _no_db() -> AsyncGenerator[AsyncMock, None]:
            yield AsyncMock()

        app.dependency_overrides[get_db] = _no_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get(
                "/api/v1/health",
                headers={"Authorization": "Bearer some-invalid-token"},
            )

        app.dependency_overrides.clear()
        assert response.status_code == 200
