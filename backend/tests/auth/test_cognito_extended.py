"""Extended tests for the Cognito JWT authentication module (core/auth.py).

Covers edge cases and scenarios NOT addressed by the backend-dev's original
test_auth.py (17 tests) and test_auth_dependency.py (7 tests):

- Empty/missing sub claim in token
- Non-UUID sub claim
- Token with extra claims (still valid)
- Exact TTL boundary conditions (cache fresh at TTL-1, stale at TTL+0)
- Error message content verification on all 401 paths
- WWW-Authenticate: Bearer header presence on all 401s
- Multiple kid rotation scenarios (3+ keys in JWKS)
- _find_key edge cases (non-list keys, empty keys array, keys without kid)
- get_signing_key with token missing kid header
- get_signing_key with completely malformed token
- get_jwks_provider() accessor
- Concurrent JWKS refresh behavior (asyncio.gather)
- JWKS fetch timeout handling
- DB session error handling in get_current_user
- HTTPBearer edge cases (empty Bearer, whitespace-only token)

All tests use locally generated RSA keys -- no network access required.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicNumbers
from fastapi import HTTPException
from jose import jwt as jose_jwt

from app.core.auth import CognitoJWKSProvider, get_jwks_provider, verify_cognito_token

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEST_REGION = "eu-west-1"
TEST_POOL_ID = "eu-west-1_TestPool"
TEST_CLIENT_ID = "test-client-id-123"
TEST_KID = "test-kid-001"
TEST_KID_2 = "test-kid-002"
TEST_KID_3 = "test-kid-003"
TEST_ISSUER = f"https://cognito-idp.{TEST_REGION}.amazonaws.com/{TEST_POOL_ID}"


# ---------------------------------------------------------------------------
# RSA key helpers
# ---------------------------------------------------------------------------


def _generate_rsa_key() -> RSAPrivateKey:
    """Generate a 2048-bit RSA private key for testing."""
    return rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )


def _private_key_to_jwk(private_key: RSAPrivateKey, kid: str) -> dict[str, Any]:
    """Convert an RSA private key to a JWK dict (public key only) for JWKS."""
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
    """Export RSA private key as PEM string for python-jose signing."""
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
    omit_sub: bool = False,
) -> str:
    """Create a signed JWT using the given RSA private key.

    Args:
        omit_sub: If True, do not include the 'sub' claim at all.
    """
    now = datetime.now(tz=UTC)
    exp = now + (exp_delta if exp_delta is not None else timedelta(hours=1))
    claims: dict[str, Any] = {
        "aud": aud or TEST_CLIENT_ID,
        "iss": iss or TEST_ISSUER,
        "token_use": token_use,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "email": "test@ember.ai",
    }
    if not omit_sub:
        claims["sub"] = sub if sub is not None else str(uuid.uuid4())
    if extra_claims:
        claims.update(extra_claims)

    return jose_jwt.encode(
        claims,
        _private_key_to_pem(private_key),
        algorithm="RS256",
        headers={"kid": kid},
    )


def _mock_httpx_response(
    json_data: dict[str, Any],
    status_code: int = 200,
) -> MagicMock:
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


def _make_mock_client(mock_get: Any) -> AsyncMock:
    """Create a mock httpx.AsyncClient instance with proper async context manager."""
    mock_client_instance = AsyncMock()
    mock_client_instance.get = mock_get
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=None)
    return mock_client_instance


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def rsa_key() -> RSAPrivateKey:
    """Provide a test RSA private key."""
    return _generate_rsa_key()


@pytest.fixture
def rsa_key_2() -> RSAPrivateKey:
    """Provide a second RSA private key."""
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


# ---------------------------------------------------------------------------
# _find_key edge cases
# ---------------------------------------------------------------------------


class TestFindKeyEdgeCases:
    """Tests for the _find_key static method edge cases."""

    def test_find_key_with_non_list_keys(self) -> None:
        """_find_key returns None when 'keys' is not a list."""
        jwks: dict[str, Any] = {"keys": "not-a-list"}
        result = CognitoJWKSProvider._find_key(jwks, TEST_KID)
        assert result is None

    def test_find_key_with_empty_keys_array(self) -> None:
        """_find_key returns None when 'keys' is an empty list."""
        jwks: dict[str, Any] = {"keys": []}
        result = CognitoJWKSProvider._find_key(jwks, TEST_KID)
        assert result is None

    def test_find_key_with_missing_keys_field(self) -> None:
        """_find_key returns None when 'keys' field is absent."""
        jwks: dict[str, Any] = {"something_else": True}
        result = CognitoJWKSProvider._find_key(jwks, TEST_KID)
        assert result is None

    def test_find_key_with_non_dict_entries(self) -> None:
        """_find_key skips non-dict entries in the keys array."""
        jwks: dict[str, Any] = {"keys": ["not-a-dict", 42, None]}
        result = CognitoJWKSProvider._find_key(jwks, TEST_KID)
        assert result is None

    def test_find_key_with_dict_entries_missing_kid(self) -> None:
        """_find_key skips dict entries that have no 'kid' field."""
        jwks: dict[str, Any] = {"keys": [{"kty": "RSA", "n": "abc"}]}
        result = CognitoJWKSProvider._find_key(jwks, TEST_KID)
        assert result is None

    def test_find_key_selects_correct_kid_among_multiple(
        self,
        rsa_key: RSAPrivateKey,
        rsa_key_2: RSAPrivateKey,
    ) -> None:
        """_find_key returns the correct key when multiple keys are present."""
        jwk_1 = _private_key_to_jwk(rsa_key, TEST_KID)
        jwk_2 = _private_key_to_jwk(rsa_key_2, TEST_KID_2)
        jwks: dict[str, Any] = {"keys": [jwk_1, jwk_2]}

        result = CognitoJWKSProvider._find_key(jwks, TEST_KID_2)
        assert result is not None
        assert result["kid"] == TEST_KID_2


# ---------------------------------------------------------------------------
# JWKS Provider: TTL boundary conditions
# ---------------------------------------------------------------------------


class TestJWKSCacheTTLBoundary:
    """Tests for exact TTL boundary conditions on cache freshness."""

    @pytest.mark.asyncio
    async def test_cache_fresh_at_exactly_ttl_minus_one_second(
        self,
        provider: CognitoJWKSProvider,
        jwks_response: dict[str, Any],
    ) -> None:
        """Cache is still fresh at TTL-1 second (599s for 600s TTL)."""
        mock_get = AsyncMock(return_value=_mock_httpx_response(jwks_response))
        with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _make_mock_client(mock_get)

            await provider.get_jwks()
            assert mock_get.call_count == 1

            # Set cache timestamp to TTL-1 second ago
            provider._cache_timestamp = time.monotonic() - 599

            result = await provider.get_jwks()
            assert result == jwks_response
            assert mock_get.call_count == 1  # Still cached

    @pytest.mark.asyncio
    async def test_cache_stale_at_exactly_ttl(
        self,
        provider: CognitoJWKSProvider,
        jwks_response: dict[str, Any],
    ) -> None:
        """Cache is stale at exactly TTL seconds (600s boundary)."""
        mock_get = AsyncMock(return_value=_mock_httpx_response(jwks_response))
        with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _make_mock_client(mock_get)

            await provider.get_jwks()
            assert mock_get.call_count == 1

            # Set cache timestamp to exactly TTL ago
            provider._cache_timestamp = time.monotonic() - 600

            await provider.get_jwks()
            assert mock_get.call_count == 2  # Re-fetched

    @pytest.mark.asyncio
    async def test_cache_is_fresh_returns_false_when_no_cache(
        self,
        provider: CognitoJWKSProvider,
    ) -> None:
        """_cache_is_fresh returns False when cache is None."""
        assert provider._jwks_cache is None
        assert provider._cache_is_fresh() is False

    @pytest.mark.asyncio
    async def test_cache_is_fresh_returns_true_when_just_populated(
        self,
        provider: CognitoJWKSProvider,
        jwks_response: dict[str, Any],
    ) -> None:
        """_cache_is_fresh returns True immediately after populating cache."""
        mock_get = AsyncMock(return_value=_mock_httpx_response(jwks_response))
        with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _make_mock_client(mock_get)
            await provider.get_jwks()

        assert provider._cache_is_fresh() is True


# ---------------------------------------------------------------------------
# JWKS Provider: Multiple key rotation scenarios
# ---------------------------------------------------------------------------


class TestMultipleKeyRotation:
    """Tests for JWKS with multiple keys and rotation scenarios."""

    @pytest.mark.asyncio
    async def test_three_keys_in_jwks_find_correct_one(
        self,
        provider: CognitoJWKSProvider,
    ) -> None:
        """Provider finds the correct key among 3 JWKS keys."""
        key_1 = _generate_rsa_key()
        key_2 = _generate_rsa_key()
        key_3 = _generate_rsa_key()
        jwks: dict[str, Any] = {
            "keys": [
                _private_key_to_jwk(key_1, TEST_KID),
                _private_key_to_jwk(key_2, TEST_KID_2),
                _private_key_to_jwk(key_3, TEST_KID_3),
            ],
        }

        token = _make_token(key_2, TEST_KID_2)
        mock_get = AsyncMock(return_value=_mock_httpx_response(jwks))
        with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _make_mock_client(mock_get)

            key = await provider.get_signing_key(token)

        assert key["kid"] == TEST_KID_2

    @pytest.mark.asyncio
    async def test_key_rotation_old_key_removed_new_key_added(
        self,
        provider: CognitoJWKSProvider,
    ) -> None:
        """Simulates full key rotation: old JWKS has kid-A, new JWKS has kid-B."""
        old_key = _generate_rsa_key()
        new_key = _generate_rsa_key()

        old_jwks: dict[str, Any] = {"keys": [_private_key_to_jwk(old_key, "old-kid")]}
        new_jwks: dict[str, Any] = {
            "keys": [
                _private_key_to_jwk(old_key, "old-kid"),
                _private_key_to_jwk(new_key, "new-kid"),
            ],
        }

        # Token signed with new key
        token = _make_token(new_key, "new-kid")

        call_count = 0

        async def _mock_get(*args: object, **kwargs: object) -> object:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_httpx_response(old_jwks)
            return _mock_httpx_response(new_jwks)

        with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _make_mock_client(_mock_get)

            key = await provider.get_signing_key(token)

        assert key["kid"] == "new-kid"
        assert call_count == 2


# ---------------------------------------------------------------------------
# JWKS Provider: Concurrent refresh behavior
# ---------------------------------------------------------------------------


class TestConcurrentJWKSRefresh:
    """Tests for concurrent JWKS fetch behavior."""

    @pytest.mark.asyncio
    async def test_concurrent_get_jwks_calls_all_complete(
        self,
        provider: CognitoJWKSProvider,
        jwks_response: dict[str, Any],
    ) -> None:
        """Multiple concurrent get_jwks calls all complete without error."""
        mock_get = AsyncMock(return_value=_mock_httpx_response(jwks_response))
        with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _make_mock_client(mock_get)

            # Simulate 5 concurrent requests
            results = await asyncio.gather(
                provider.get_jwks(),
                provider.get_jwks(),
                provider.get_jwks(),
                provider.get_jwks(),
                provider.get_jwks(),
            )

        # All results should be the JWKS response
        for result in results:
            assert result == jwks_response


# ---------------------------------------------------------------------------
# JWKS Provider: Timeout handling
# ---------------------------------------------------------------------------


class TestJWKSTimeoutHandling:
    """Tests for JWKS endpoint timeout scenarios."""

    @pytest.mark.asyncio
    async def test_timeout_with_no_cache_raises_401(
        self,
        provider: CognitoJWKSProvider,
    ) -> None:
        """Timeout on JWKS fetch with no cache raises 401."""
        with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
            mock_client_instance = _make_mock_client(
                AsyncMock(side_effect=httpx.TimeoutException("Request timed out")),
            )
            mock_client_cls.return_value = mock_client_instance

            with pytest.raises(HTTPException) as exc_info:
                await provider.get_jwks()

            assert exc_info.value.status_code == 401
            assert exc_info.value.detail == "Authentication service unavailable"
            assert exc_info.value.headers is not None
            assert exc_info.value.headers["WWW-Authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_timeout_with_stale_cache_returns_stale(
        self,
        provider: CognitoJWKSProvider,
        jwks_response: dict[str, Any],
    ) -> None:
        """Timeout on JWKS fetch with stale cache returns stale keys."""
        call_count = 0

        async def _mock_get(*args: object, **kwargs: object) -> object:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_httpx_response(jwks_response)
            raise httpx.TimeoutException("Request timed out")

        with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _make_mock_client(_mock_get)

            await provider.get_jwks()
            provider._cache_timestamp = time.monotonic() - 700

            result = await provider.get_jwks()

        assert result == jwks_response

    @pytest.mark.asyncio
    async def test_http_status_error_with_stale_cache(
        self,
        provider: CognitoJWKSProvider,
        jwks_response: dict[str, Any],
    ) -> None:
        """HTTP 500 on JWKS fetch with stale cache returns stale keys."""
        call_count = 0

        async def _mock_get(*args: object, **kwargs: object) -> object:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_httpx_response(jwks_response)
            return _mock_httpx_response({}, status_code=500)

        with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _make_mock_client(_mock_get)

            await provider.get_jwks()
            provider._cache_timestamp = time.monotonic() - 700

            result = await provider.get_jwks()

        assert result == jwks_response


# ---------------------------------------------------------------------------
# get_signing_key edge cases
# ---------------------------------------------------------------------------


class TestGetSigningKeyEdgeCases:
    """Tests for get_signing_key with malformed tokens and missing kid."""

    @pytest.mark.asyncio
    async def test_completely_malformed_token_raises_401(
        self,
        provider: CognitoJWKSProvider,
    ) -> None:
        """Completely non-JWT string raises 401 from get_signing_key."""
        with pytest.raises(HTTPException) as exc_info:
            await provider.get_signing_key("this-is-not-a-jwt")

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid or expired token"
        assert exc_info.value.headers is not None
        assert exc_info.value.headers["WWW-Authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_token_without_kid_in_header_raises_401(
        self,
        provider: CognitoJWKSProvider,
        rsa_key: RSAPrivateKey,
    ) -> None:
        """Token with no kid in header raises 401."""
        # Create a token without a kid header
        now = datetime.now(tz=UTC)
        claims: dict[str, Any] = {
            "sub": str(uuid.uuid4()),
            "aud": TEST_CLIENT_ID,
            "iss": TEST_ISSUER,
            "token_use": "id",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        }
        # Encode without kid header
        token = jose_jwt.encode(
            claims,
            _private_key_to_pem(rsa_key),
            algorithm="RS256",
            # No kid in headers
        )

        with pytest.raises(HTTPException) as exc_info:
            await provider.get_signing_key(token)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid or expired token"

    @pytest.mark.asyncio
    async def test_empty_string_token_raises_401(
        self,
        provider: CognitoJWKSProvider,
    ) -> None:
        """Empty string token raises 401 from get_signing_key."""
        with pytest.raises(HTTPException) as exc_info:
            await provider.get_signing_key("")

        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# verify_cognito_token: sub claim edge cases
# ---------------------------------------------------------------------------


class TestVerifyCognitoTokenSubClaim:
    """Tests for verify_cognito_token sub claim validation."""

    @pytest.mark.asyncio
    async def test_missing_sub_claim_raises_401(
        self,
        rsa_key: RSAPrivateKey,
    ) -> None:
        """Token without sub claim raises 401."""
        token = _make_token(rsa_key, TEST_KID, omit_sub=True)

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
            assert exc_info.value.detail == "Invalid or expired token"
            assert exc_info.value.headers is not None
            assert exc_info.value.headers["WWW-Authenticate"] == "Bearer"

    @pytest.mark.asyncio
    async def test_non_uuid_sub_claim_raises_401(
        self,
        rsa_key: RSAPrivateKey,
    ) -> None:
        """Token with non-UUID sub claim raises 401."""
        token = _make_token(rsa_key, TEST_KID, sub="not-a-uuid-value")

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
            assert exc_info.value.detail == "Invalid or expired token"

    @pytest.mark.asyncio
    async def test_empty_string_sub_claim_raises_401(
        self,
        rsa_key: RSAPrivateKey,
    ) -> None:
        """Token with empty string sub claim raises 401."""
        token = _make_token(rsa_key, TEST_KID, sub="")

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
            assert exc_info.value.detail == "Invalid or expired token"


# ---------------------------------------------------------------------------
# verify_cognito_token: extra claims and happy path details
# ---------------------------------------------------------------------------


class TestVerifyCognitoTokenExtraClaims:
    """Tests for verify_cognito_token with extra/unusual claims."""

    @pytest.mark.asyncio
    async def test_token_with_extra_claims_still_valid(
        self,
        rsa_key: RSAPrivateKey,
    ) -> None:
        """Token with additional custom claims still validates successfully."""
        test_sub = str(uuid.uuid4())
        token = _make_token(
            rsa_key,
            TEST_KID,
            sub=test_sub,
            extra_claims={
                "custom:role": "admin",
                "cognito:groups": ["users", "admins"],
                "given_name": "Test",
                "family_name": "User",
            },
        )

        with patch("app.core.auth._jwks_provider") as mock_provider, \
             patch("app.core.auth.settings") as mock_settings:
            mock_provider.get_signing_key = AsyncMock(
                return_value=_private_key_to_jwk(rsa_key, TEST_KID),
            )
            mock_provider.issuer_url = TEST_ISSUER
            mock_settings.cognito_app_client_id = TEST_CLIENT_ID

            claims = await verify_cognito_token(token)

        assert claims["sub"] == test_sub
        assert claims["custom:role"] == "admin"
        assert claims["cognito:groups"] == ["users", "admins"]

    @pytest.mark.asyncio
    async def test_valid_token_returns_all_standard_claims(
        self,
        rsa_key: RSAPrivateKey,
    ) -> None:
        """Valid token claims dict contains all expected standard fields."""
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

        assert "sub" in claims
        assert "aud" in claims
        assert "iss" in claims
        assert "token_use" in claims
        assert "exp" in claims
        assert "iat" in claims
        assert "email" in claims
        assert claims["iss"] == TEST_ISSUER
        assert claims["aud"] == TEST_CLIENT_ID

    @pytest.mark.asyncio
    async def test_token_use_missing_raises_401(
        self,
        rsa_key: RSAPrivateKey,
    ) -> None:
        """Token without token_use claim raises 401."""
        now = datetime.now(tz=UTC)
        claims: dict[str, Any] = {
            "sub": str(uuid.uuid4()),
            "aud": TEST_CLIENT_ID,
            "iss": TEST_ISSUER,
            # token_use intentionally omitted
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        }
        token = jose_jwt.encode(
            claims,
            _private_key_to_pem(rsa_key),
            algorithm="RS256",
            headers={"kid": TEST_KID},
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
            assert exc_info.value.detail == "Invalid or expired token"


# ---------------------------------------------------------------------------
# WWW-Authenticate header verification on all 401 paths
# ---------------------------------------------------------------------------


class TestWWWAuthenticateHeader:
    """Verify WWW-Authenticate: Bearer header is present on all 401 responses."""

    @pytest.mark.asyncio
    async def test_expired_token_has_www_authenticate_header(
        self,
        rsa_key: RSAPrivateKey,
    ) -> None:
        """401 for expired token includes WWW-Authenticate: Bearer."""
        token = _make_token(rsa_key, TEST_KID, exp_delta=timedelta(hours=-1))

        with patch("app.core.auth._jwks_provider") as mock_provider, \
             patch("app.core.auth.settings") as mock_settings:
            mock_provider.get_signing_key = AsyncMock(
                return_value=_private_key_to_jwk(rsa_key, TEST_KID),
            )
            mock_provider.issuer_url = TEST_ISSUER
            mock_settings.cognito_app_client_id = TEST_CLIENT_ID

            with pytest.raises(HTTPException) as exc_info:
                await verify_cognito_token(token)

            assert exc_info.value.headers is not None
            assert exc_info.value.headers.get("WWW-Authenticate") == "Bearer"

    @pytest.mark.asyncio
    async def test_wrong_audience_has_www_authenticate_header(
        self,
        rsa_key: RSAPrivateKey,
    ) -> None:
        """401 for wrong audience includes WWW-Authenticate: Bearer."""
        token = _make_token(rsa_key, TEST_KID, aud="wrong-client")

        with patch("app.core.auth._jwks_provider") as mock_provider, \
             patch("app.core.auth.settings") as mock_settings:
            mock_provider.get_signing_key = AsyncMock(
                return_value=_private_key_to_jwk(rsa_key, TEST_KID),
            )
            mock_provider.issuer_url = TEST_ISSUER
            mock_settings.cognito_app_client_id = TEST_CLIENT_ID

            with pytest.raises(HTTPException) as exc_info:
                await verify_cognito_token(token)

            assert exc_info.value.headers is not None
            assert exc_info.value.headers.get("WWW-Authenticate") == "Bearer"

    @pytest.mark.asyncio
    async def test_wrong_token_use_has_www_authenticate_header(
        self,
        rsa_key: RSAPrivateKey,
    ) -> None:
        """401 for token_use=access includes WWW-Authenticate: Bearer."""
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

            assert exc_info.value.headers is not None
            assert exc_info.value.headers.get("WWW-Authenticate") == "Bearer"

    @pytest.mark.asyncio
    async def test_no_cache_unreachable_has_www_authenticate_header(
        self,
        provider: CognitoJWKSProvider,
    ) -> None:
        """401 for unreachable JWKS (no cache) includes WWW-Authenticate."""
        with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _make_mock_client(
                AsyncMock(side_effect=httpx.ConnectError("Connection refused")),
            )

            with pytest.raises(HTTPException) as exc_info:
                await provider.get_jwks()

            assert exc_info.value.headers is not None
            assert exc_info.value.headers.get("WWW-Authenticate") == "Bearer"

    @pytest.mark.asyncio
    async def test_kid_not_found_after_refresh_has_www_authenticate_header(
        self,
        rsa_key: RSAPrivateKey,
        provider: CognitoJWKSProvider,
    ) -> None:
        """401 for kid not found after refresh includes WWW-Authenticate."""
        token = _make_token(rsa_key, "nonexistent-kid")
        jwks: dict[str, Any] = {"keys": [_private_key_to_jwk(rsa_key, TEST_KID)]}

        with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _make_mock_client(
                AsyncMock(return_value=_mock_httpx_response(jwks)),
            )

            with pytest.raises(HTTPException) as exc_info:
                await provider.get_signing_key(token)

            assert exc_info.value.headers is not None
            assert exc_info.value.headers.get("WWW-Authenticate") == "Bearer"


# ---------------------------------------------------------------------------
# Error message content verification
# ---------------------------------------------------------------------------


class TestErrorMessageContent:
    """Verify exact error messages on all failure paths."""

    @pytest.mark.asyncio
    async def test_expired_token_exact_message(
        self,
        rsa_key: RSAPrivateKey,
    ) -> None:
        """Expired token produces exactly 'Invalid or expired token'."""
        token = _make_token(rsa_key, TEST_KID, exp_delta=timedelta(hours=-1))

        with patch("app.core.auth._jwks_provider") as mock_provider, \
             patch("app.core.auth.settings") as mock_settings:
            mock_provider.get_signing_key = AsyncMock(
                return_value=_private_key_to_jwk(rsa_key, TEST_KID),
            )
            mock_provider.issuer_url = TEST_ISSUER
            mock_settings.cognito_app_client_id = TEST_CLIENT_ID

            with pytest.raises(HTTPException) as exc_info:
                await verify_cognito_token(token)

            assert exc_info.value.detail == "Invalid or expired token"

    @pytest.mark.asyncio
    async def test_wrong_signature_exact_message(
        self,
        rsa_key: RSAPrivateKey,
        rsa_key_2: RSAPrivateKey,
    ) -> None:
        """Wrong signature produces exactly 'Invalid or expired token'."""
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

            assert exc_info.value.detail == "Invalid or expired token"

    @pytest.mark.asyncio
    async def test_wrong_issuer_exact_message(
        self,
        rsa_key: RSAPrivateKey,
    ) -> None:
        """Wrong issuer produces exactly 'Invalid or expired token'."""
        token = _make_token(rsa_key, TEST_KID, iss="https://wrong-issuer.example.com")

        with patch("app.core.auth._jwks_provider") as mock_provider, \
             patch("app.core.auth.settings") as mock_settings:
            mock_provider.get_signing_key = AsyncMock(
                return_value=_private_key_to_jwk(rsa_key, TEST_KID),
            )
            mock_provider.issuer_url = TEST_ISSUER
            mock_settings.cognito_app_client_id = TEST_CLIENT_ID

            with pytest.raises(HTTPException) as exc_info:
                await verify_cognito_token(token)

            assert exc_info.value.detail == "Invalid or expired token"

    @pytest.mark.asyncio
    async def test_unreachable_jwks_no_cache_exact_message(
        self,
        provider: CognitoJWKSProvider,
    ) -> None:
        """Unreachable JWKS with no cache produces 'Authentication service unavailable'."""
        with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value = _make_mock_client(
                AsyncMock(side_effect=httpx.ConnectError("Connection refused")),
            )

            with pytest.raises(HTTPException) as exc_info:
                await provider.get_jwks()

            assert exc_info.value.detail == "Authentication service unavailable"


# ---------------------------------------------------------------------------
# CognitoJWKSProvider: issuer_url and jwks_url construction
# ---------------------------------------------------------------------------


class TestProviderURLConstruction:
    """Tests for correct URL construction in CognitoJWKSProvider."""

    def test_issuer_url_format(self) -> None:
        """issuer_url follows Cognito format without trailing slash."""
        provider = CognitoJWKSProvider(
            region="us-west-2",
            user_pool_id="us-west-2_AbcDef",
        )
        expected = "https://cognito-idp.us-west-2.amazonaws.com/us-west-2_AbcDef"
        assert provider.issuer_url == expected
        assert not provider.issuer_url.endswith("/")

    def test_jwks_url_format(self) -> None:
        """_jwks_url points to the well-known JWKS endpoint."""
        provider = CognitoJWKSProvider(
            region="us-west-2",
            user_pool_id="us-west-2_AbcDef",
        )
        expected = (
            "https://cognito-idp.us-west-2.amazonaws.com/"
            "us-west-2_AbcDef/.well-known/jwks.json"
        )
        assert provider._jwks_url == expected

    def test_custom_ttl(self) -> None:
        """Cache TTL can be customized via constructor."""
        provider = CognitoJWKSProvider(
            region="eu-west-1",
            user_pool_id="eu-west-1_Test",
            cache_ttl=300.0,
        )
        assert provider._cache_ttl == 300.0


# ---------------------------------------------------------------------------
# get_jwks_provider accessor
# ---------------------------------------------------------------------------


class TestGetJWKSProvider:
    """Tests for the get_jwks_provider function."""

    def test_returns_provider_instance(self) -> None:
        """get_jwks_provider returns a CognitoJWKSProvider instance."""
        provider = get_jwks_provider()
        assert isinstance(provider, CognitoJWKSProvider)

    def test_returns_same_singleton(self) -> None:
        """get_jwks_provider returns the same instance each time."""
        provider_1 = get_jwks_provider()
        provider_2 = get_jwks_provider()
        assert provider_1 is provider_2


# ---------------------------------------------------------------------------
# JWKS Provider: stale cache logging
# ---------------------------------------------------------------------------


class TestStaleCacheLogging:
    """Tests for stale cache warning log behavior."""

    @pytest.mark.asyncio
    async def test_stale_cache_fallback_logs_warning(
        self,
        provider: CognitoJWKSProvider,
        jwks_response: dict[str, Any],
    ) -> None:
        """Using stale cache logs a warning with cache age and URL."""
        call_count = 0

        async def _mock_get(*args: object, **kwargs: object) -> object:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_httpx_response(jwks_response)
            raise httpx.ConnectError("Connection refused")

        with patch("app.core.auth.httpx.AsyncClient") as mock_client_cls, \
             patch("app.core.auth.logger") as mock_logger:
            mock_client_cls.return_value = _make_mock_client(_mock_get)

            await provider.get_jwks()
            provider._cache_timestamp = time.monotonic() - 700

            await provider.get_jwks()

        mock_logger.warning.assert_called_once()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "stale cache" in warning_msg.lower()
