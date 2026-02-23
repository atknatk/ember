"""Integration tests for the get_current_user dependency.

Tests the full authentication flow through the FastAPI test client, including
token validation, profile lookup, missing auth header, and invalid tokens.

Uses locally generated RSA keys and mock JWKS — no network access required.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi import APIRouter, Depends
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
# RSA key helpers (same as test_auth.py — duplicated to keep tests self-contained)
# ---------------------------------------------------------------------------


def _generate_rsa_key() -> RSAPrivateKey:
    """Generate a 2048-bit RSA private key for testing."""
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )


def _private_key_to_jwk(private_key: RSAPrivateKey, kid: str) -> dict[str, Any]:
    """Convert an RSA private key to a JWK dict (public key only)."""
    import base64

    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers

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
    """Export RSA private key as PEM string."""
    from cryptography.hazmat.primitives import serialization

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
    """Create a signed JWT using the given RSA private key."""
    from datetime import UTC, datetime

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rsa_key() -> RSAPrivateKey:
    """Module-scoped RSA key to avoid regenerating for every test."""
    return _generate_rsa_key()


@pytest.fixture(scope="module")
def test_sub() -> str:
    """Module-scoped test user UUID."""
    return str(uuid.uuid4())


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Provide a mock async database session."""
    return AsyncMock(spec=AsyncSession)


def _create_mock_profile(user_id: str) -> Profile:
    """Create a Profile-like object for testing without a real DB."""
    profile = MagicMock(spec=Profile)
    profile.id = uuid.UUID(user_id)
    profile.email = "test@ember.ai"
    profile.name = "Test User"
    return profile


@pytest_asyncio.fixture
async def auth_client(
    rsa_key: RSAPrivateKey,
    test_sub: str,
) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client with auth mocking configured.

    Patches the JWKS provider and database to allow valid token verification
    and profile lookup.
    """
    mock_profile = _create_mock_profile(test_sub)

    # Mock the database dependency
    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_profile
    mock_db.execute = AsyncMock(return_value=mock_result)

    async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
        yield mock_db

    app.dependency_overrides[get_db] = _override_get_db

    # Patch the JWKS provider to return our test key
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


@pytest_asyncio.fixture
async def auth_client_no_profile(
    rsa_key: RSAPrivateKey,
) -> AsyncGenerator[AsyncClient, None]:
    """Client where token is valid but no matching profile exists in DB."""
    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # No profile found
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


# ---------------------------------------------------------------------------
# Register a protected test route
# ---------------------------------------------------------------------------

_test_router = APIRouter()


@_test_router.get("/api/v1/_test_protected")
async def _protected_endpoint(
    current_user: Profile = Depends(get_current_user),
) -> dict[str, str]:
    return {"user_id": str(current_user.id)}


# Register the test route (idempotent — router check)
_route_paths = {r.path for r in app.routes}
if "/api/v1/_test_protected" not in _route_paths:
    app.include_router(_test_router)


# ---------------------------------------------------------------------------
# Dependency Integration Tests (Spec #18–#24)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_valid_token_and_existing_profile(
    auth_client: AsyncClient,
    rsa_key: RSAPrivateKey,
    test_sub: str,
) -> None:
    """#18: Valid token + existing profile returns the Profile object."""
    token = _make_token(rsa_key, TEST_KID, sub=test_sub)
    response = await auth_client.get(
        "/api/v1/_test_protected",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["user_id"] == test_sub


@pytest.mark.asyncio
async def test_valid_token_but_no_profile(
    auth_client_no_profile: AsyncClient,
    rsa_key: RSAPrivateKey,
) -> None:
    """#19: Valid token but no matching profile returns 401 'User not found'."""
    token = _make_token(rsa_key, TEST_KID, sub=str(uuid.uuid4()))
    response = await auth_client_no_profile.get(
        "/api/v1/_test_protected",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "User not found"


@pytest.mark.asyncio
async def test_no_authorization_header(
    auth_client: AsyncClient,
) -> None:
    """#20: Request without Authorization header returns 401."""
    response = await auth_client.get("/api/v1/_test_protected")
    assert response.status_code in (401, 403)
    assert response.json()["detail"] == "Not authenticated"


@pytest.mark.asyncio
async def test_basic_auth_instead_of_bearer(
    auth_client: AsyncClient,
) -> None:
    """#21: Authorization: Basic returns 401."""
    response = await auth_client.get(
        "/api/v1/_test_protected",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_invalid_bearer_token(
    auth_client: AsyncClient,
) -> None:
    """#22: Invalid Bearer token returns 401."""
    with patch("app.core.auth._jwks_provider") as mock_provider, \
         patch("app.core.auth.settings") as mock_settings:
        from fastapi import HTTPException

        mock_provider.get_signing_key = AsyncMock(
            side_effect=HTTPException(
                status_code=401,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            ),
        )
        mock_provider.issuer_url = TEST_ISSUER
        mock_settings.cognito_app_client_id = TEST_CLIENT_ID

        response = await auth_client.get(
            "/api/v1/_test_protected",
            headers={"Authorization": "Bearer totally-invalid-token"},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_health_endpoint_requires_no_auth() -> None:
    """#23: GET /api/v1/health works without any Authorization header."""
    # Use the base conftest client without auth overrides
    async def _no_db() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    app.dependency_overrides[get_db] = _no_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/health")

    app.dependency_overrides.clear()
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_protected_endpoint_returns_correct_user_context(
    auth_client: AsyncClient,
    rsa_key: RSAPrivateKey,
    test_sub: str,
) -> None:
    """#24: Protected endpoint receives the authenticated Profile object."""
    token = _make_token(rsa_key, TEST_KID, sub=test_sub)
    response = await auth_client.get(
        "/api/v1/_test_protected",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == test_sub
