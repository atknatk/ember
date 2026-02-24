"""Tests for the Cognito JWT authentication module (core/auth.py).

Tests JWKS fetching, caching with TTL, force refresh on key rotation,
stale cache fallback, and token verification with RSA key pairs.

All tests use locally generated RSA keys — no network access required.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from fastapi import HTTPException
from jose import jwt as jose_jwt

from app.core.auth import CognitoJWKSProvider, verify_cognito_token

# ---------------------------------------------------------------------------
# RSA key helpers
# ---------------------------------------------------------------------------

TEST_REGION = "eu-west-1"
TEST_POOL_ID = "eu-west-1_TestPool"
TEST_CLIENT_ID = "test-client-id-123"
TEST_KID = "test-kid-001"
TEST_KID_2 = "test-kid-002"
TEST_ISSUER = f"https://cognito-idp.{TEST_REGION}.amazonaws.com/{TEST_POOL_ID}"


def _generate_rsa_key() -> RSAPrivateKey:
    """Generate a 2048-bit RSA private key for testing."""
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )


def _private_key_to_jwk(private_key: RSAPrivateKey, kid: str) -> dict[str, Any]:
    """Convert an RSA private key to a JWK dict (public key only) for JWKS."""
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers

    pub_numbers: RSAPublicNumbers = private_key.public_key().public_numbers()

    def _int_to_base64url(value: int) -> str:
        import base64

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
    """Export RSA private key as PEM string for python-jose signing."""
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
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT using the given RSA private key."""
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
    if extra_claims:
        claims.update(extra_claims)

    return jose_jwt.encode(
        claims,
        _private_key_to_pem(private_key),
        algorithm="RS256",
        headers={"kid": kid},
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rsa_key() -> RSAPrivateKey:
    """Provide a test RSA private key."""
    return _generate_rsa_key()


@pytest.fixture
def rsa_key_2() -> RSAPrivateKey:
    """Provide a second RSA private key (for wrong-signature tests)."""
    return _generate_rsa_key()


@pytest.fixture
def jwks_response(rsa_key: RSAPrivateKey) -> dict[str, Any]:
    """Provide a JWKS JSON response with the test public key."""
    return {"keys": [_private_key_to_jwk(rsa_key, TEST_KID)]}


@pytest.fixture
def provider() -> CognitoJWKSProvider:
    """Provide a fresh CognitoJWKSProvider instance."""
    return CognitoJWKSProvider(
        region=TEST_REGION,
        user_pool_id=TEST_POOL_ID,
        cache_ttl=600.0,
    )


def _mock_httpx_response(
    json_data: dict[str, Any],
    status_code: int = 200,
) -> AsyncMock:
    """Create a mock httpx response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error",
            request=MagicMock(),
            response=resp,
        )
    return resp


# ---------------------------------------------------------------------------
# JWKS Provider Tests (Spec #1–#9)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_jwks_fetches_on_first_call(
    provider: CognitoJWKSProvider,
    jwks_response: dict[str, Any],
) -> None:
    """#1: get_jwks fetches from Cognito URL on first call."""
    mock_get = AsyncMock(return_value=_mock_httpx_response(jwks_response))
    with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
        mock_client_instance = AsyncMock()
        mock_client_instance.get = mock_get
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client_instance

        result = await provider.get_jwks()

    assert result == jwks_response
    mock_get.assert_called_once()
    call_args = mock_get.call_args
    assert provider._jwks_url in str(call_args)


@pytest.mark.asyncio
async def test_get_jwks_returns_cached_within_ttl(
    provider: CognitoJWKSProvider,
    jwks_response: dict[str, Any],
) -> None:
    """#2: get_jwks returns cached keys on second call within TTL."""
    mock_get = AsyncMock(return_value=_mock_httpx_response(jwks_response))
    with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
        mock_client_instance = AsyncMock()
        mock_client_instance.get = mock_get
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client_instance

        await provider.get_jwks()
        result = await provider.get_jwks()

    assert result == jwks_response
    assert mock_get.call_count == 1  # Only one HTTP call total


@pytest.mark.asyncio
async def test_get_jwks_refetches_after_ttl_expiry(
    provider: CognitoJWKSProvider,
    jwks_response: dict[str, Any],
) -> None:
    """#3: get_jwks re-fetches after TTL expiry."""
    mock_get = AsyncMock(return_value=_mock_httpx_response(jwks_response))
    with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
        mock_client_instance = AsyncMock()
        mock_client_instance.get = mock_get
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client_instance

        # First fetch
        await provider.get_jwks()
        assert mock_get.call_count == 1

        # Simulate TTL expiry by setting cache timestamp in the past
        provider._cache_timestamp = time.monotonic() - 700

        # Second fetch — should re-fetch
        await provider.get_jwks()
        assert mock_get.call_count == 2


@pytest.mark.asyncio
async def test_get_jwks_force_refresh_bypasses_cache(
    provider: CognitoJWKSProvider,
    jwks_response: dict[str, Any],
) -> None:
    """#4: get_jwks(force_refresh=True) bypasses cache."""
    mock_get = AsyncMock(return_value=_mock_httpx_response(jwks_response))
    with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
        mock_client_instance = AsyncMock()
        mock_client_instance.get = mock_get
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client_instance

        await provider.get_jwks()
        await provider.get_jwks(force_refresh=True)

    assert mock_get.call_count == 2


@pytest.mark.asyncio
async def test_get_jwks_returns_stale_cache_on_failure(
    provider: CognitoJWKSProvider,
    jwks_response: dict[str, Any],
) -> None:
    """#5: get_jwks returns stale cache when endpoint is unreachable."""
    success_resp = _mock_httpx_response(jwks_response)
    fail_effect = httpx.ConnectError("Connection refused")

    call_count = 0

    async def _mock_get(*args: object, **kwargs: object) -> object:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return success_resp
        raise fail_effect

    with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
        mock_client_instance = AsyncMock()
        mock_client_instance.get = _mock_get
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client_instance

        # First call succeeds
        await provider.get_jwks()

        # Expire cache
        provider._cache_timestamp = time.monotonic() - 700

        # Second call fails but returns stale cache
        result = await provider.get_jwks()

    assert result == jwks_response


@pytest.mark.asyncio
async def test_get_jwks_raises_401_when_no_cache_and_unreachable(
    provider: CognitoJWKSProvider,
) -> None:
    """#6: get_jwks raises 401 when endpoint is unreachable and no cache."""
    with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused"),
        )
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client_instance

        with pytest.raises(HTTPException) as exc_info:
            await provider.get_jwks()

        assert exc_info.value.status_code == 401
        assert "Authentication service unavailable" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_signing_key_returns_matching_key(
    rsa_key: RSAPrivateKey,
    provider: CognitoJWKSProvider,
    jwks_response: dict[str, Any],
) -> None:
    """#7: get_signing_key returns the correct key matching the token's kid."""
    token = _make_token(rsa_key, TEST_KID)

    with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(
            return_value=_mock_httpx_response(jwks_response),
        )
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client_instance

        key = await provider.get_signing_key(token)

    assert key["kid"] == TEST_KID


@pytest.mark.asyncio
async def test_get_signing_key_force_refreshes_on_kid_miss(
    rsa_key: RSAPrivateKey,
    provider: CognitoJWKSProvider,
) -> None:
    """#8: get_signing_key triggers force refresh when kid is not in cache."""
    token = _make_token(rsa_key, TEST_KID)

    # First JWKS response has a different kid, second has the correct one
    old_jwks: dict[str, Any] = {"keys": [_private_key_to_jwk(rsa_key, "old-kid")]}
    new_jwks: dict[str, Any] = {"keys": [_private_key_to_jwk(rsa_key, TEST_KID)]}

    call_count = 0

    async def _mock_get(*args: object, **kwargs: object) -> object:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _mock_httpx_response(old_jwks)
        return _mock_httpx_response(new_jwks)

    with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
        mock_client_instance = AsyncMock()
        mock_client_instance.get = _mock_get
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client_instance

        key = await provider.get_signing_key(token)

    assert key["kid"] == TEST_KID
    assert call_count == 2  # Initial fetch + force refresh


@pytest.mark.asyncio
async def test_get_signing_key_raises_401_kid_not_found_after_refresh(
    rsa_key: RSAPrivateKey,
    provider: CognitoJWKSProvider,
) -> None:
    """#9: get_signing_key raises 401 when kid is not found even after refresh."""
    token = _make_token(rsa_key, "nonexistent-kid")
    jwks: dict[str, Any] = {"keys": [_private_key_to_jwk(rsa_key, TEST_KID)]}

    with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(
            return_value=_mock_httpx_response(jwks),
        )
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client_instance

        with pytest.raises(HTTPException) as exc_info:
            await provider.get_signing_key(token)

        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Token Verification Tests (Spec #10–#17)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_valid_token_returns_claims(
    rsa_key: RSAPrivateKey,
    jwks_response: dict[str, Any],
) -> None:
    """#10: Valid token with correct claims returns claims dict."""
    test_sub = str(uuid.uuid4())
    token = _make_token(rsa_key, TEST_KID, sub=test_sub)

    with patch("app.core.auth._jwks_provider") as mock_provider, \
         patch("app.core.auth.settings") as mock_settings:
        mock_provider.get_signing_key = AsyncMock(
            return_value=_private_key_to_jwk(rsa_key, TEST_KID),
        )
        mock_provider.issuer_url = TEST_ISSUER
        mock_settings.cognito_app_client_id = TEST_CLIENT_ID

        claims = await verify_cognito_token(token)

    assert claims["sub"] == test_sub
    assert claims["token_use"] == "id"
    assert claims["aud"] == TEST_CLIENT_ID


@pytest.mark.asyncio
async def test_expired_token_raises_401(
    rsa_key: RSAPrivateKey,
) -> None:
    """#11: Token with expired exp claim raises 401."""
    token = _make_token(
        rsa_key,
        TEST_KID,
        exp_delta=timedelta(hours=-1),
    )

    with patch("app.core.auth._jwks_provider") as mock_provider, \
         patch("app.core.auth.settings") as mock_settings:
        mock_provider.get_signing_key = AsyncMock(
            return_value=_private_key_to_jwk(rsa_key, TEST_KID),
        )
        mock_provider.issuer_url = TEST_ISSUER
        mock_settings.cognito_app_client_id = TEST_CLIENT_ID

        with pytest.raises(HTTPException) as exc_info:
            await verify_cognito_token(token)

        assert exc_info.value.status_code == 401
        assert "Invalid or expired token" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_wrong_signature_raises_401(
    rsa_key: RSAPrivateKey,
    rsa_key_2: RSAPrivateKey,
) -> None:
    """#12: Token signed with different RSA key raises 401."""
    # Sign with key 2, but provide key 1's public key for verification
    token = _make_token(rsa_key_2, TEST_KID)

    with patch("app.core.auth._jwks_provider") as mock_provider, \
         patch("app.core.auth.settings") as mock_settings:
        mock_provider.get_signing_key = AsyncMock(
            return_value=_private_key_to_jwk(rsa_key, TEST_KID),
        )
        mock_provider.issuer_url = TEST_ISSUER
        mock_settings.cognito_app_client_id = TEST_CLIENT_ID

        with pytest.raises(HTTPException) as exc_info:
            await verify_cognito_token(token)

        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_wrong_audience_raises_401(
    rsa_key: RSAPrivateKey,
) -> None:
    """#13: Token with wrong aud (different client ID) raises 401."""
    token = _make_token(rsa_key, TEST_KID, aud="wrong-client-id")

    with patch("app.core.auth._jwks_provider") as mock_provider, \
         patch("app.core.auth.settings") as mock_settings:
        mock_provider.get_signing_key = AsyncMock(
            return_value=_private_key_to_jwk(rsa_key, TEST_KID),
        )
        mock_provider.issuer_url = TEST_ISSUER
        mock_settings.cognito_app_client_id = TEST_CLIENT_ID

        with pytest.raises(HTTPException) as exc_info:
            await verify_cognito_token(token)

        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_wrong_issuer_raises_401(
    rsa_key: RSAPrivateKey,
) -> None:
    """#14: Token with wrong iss (different issuer URL) raises 401."""
    token = _make_token(
        rsa_key,
        TEST_KID,
        iss="https://cognito-idp.us-east-1.amazonaws.com/us-east-1_WrongPool",
    )

    with patch("app.core.auth._jwks_provider") as mock_provider, \
         patch("app.core.auth.settings") as mock_settings:
        mock_provider.get_signing_key = AsyncMock(
            return_value=_private_key_to_jwk(rsa_key, TEST_KID),
        )
        mock_provider.issuer_url = TEST_ISSUER
        mock_settings.cognito_app_client_id = TEST_CLIENT_ID

        with pytest.raises(HTTPException) as exc_info:
            await verify_cognito_token(token)

        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_access_token_use_raises_401(
    rsa_key: RSAPrivateKey,
) -> None:
    """#15: Token with token_use=access instead of id raises 401."""
    token = _make_token(rsa_key, TEST_KID, token_use="access")

    with patch("app.core.auth._jwks_provider") as mock_provider, \
         patch("app.core.auth.settings") as mock_settings:
        mock_provider.get_signing_key = AsyncMock(
            return_value=_private_key_to_jwk(rsa_key, TEST_KID),
        )
        mock_provider.issuer_url = TEST_ISSUER
        mock_settings.cognito_app_client_id = TEST_CLIENT_ID

        with pytest.raises(HTTPException) as exc_info:
            await verify_cognito_token(token)

        assert exc_info.value.status_code == 401
        assert "Invalid or expired token" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_malformed_token_raises_401() -> None:
    """#16: Completely malformed token string raises 401."""
    with patch("app.core.auth._jwks_provider") as mock_provider:
        mock_provider.get_signing_key = AsyncMock(
            side_effect=HTTPException(
                status_code=401,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            ),
        )

        with pytest.raises(HTTPException) as exc_info:
            await verify_cognito_token("not.a.valid.jwt.at.all")

        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_kid_not_matching_any_jwks_key_raises_401(
    rsa_key: RSAPrivateKey,
) -> None:
    """#17: Token with kid not matching any JWKS key raises 401."""
    token = _make_token(rsa_key, "unknown-kid-xyz")

    with patch("app.core.auth._jwks_provider") as mock_provider:
        mock_provider.get_signing_key = AsyncMock(
            side_effect=HTTPException(
                status_code=401,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            ),
        )

        with pytest.raises(HTTPException) as exc_info:
            await verify_cognito_token(token)

        assert exc_info.value.status_code == 401
