"""AWS Cognito JWT authentication — JWKS fetching, caching, and token verification.

Provides CognitoJWKSProvider for fetching and caching Cognito JWKS keys with
a 10-minute TTL, and verify_cognito_token for RS256 JWT validation including
signature, expiry, audience, issuer, and token_use claims.

The module-level singleton _jwks_provider shares the JWKS cache across all
requests in the same process.
"""

from __future__ import annotations

import logging
import time
import uuid

import httpx
from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.config import settings
from app.utils.timing import log_external_call

logger = logging.getLogger("ember")


class CognitoJWKSProvider:
    """Fetches and caches JWKS keys from the AWS Cognito well-known endpoint.

    Attributes:
        _jwks_cache: The cached JWKS response (the full JSON with ``keys`` array).
        _cache_timestamp: ``time.monotonic()`` when the cache was last populated.
        _cache_ttl: Cache time-to-live in seconds (default 600 = 10 minutes).
    """

    def __init__(
        self,
        *,
        region: str,
        user_pool_id: str,
        cache_ttl: float = 600.0,
    ) -> None:
        self._region = region
        self._user_pool_id = user_pool_id
        self._cache_ttl = cache_ttl
        self._jwks_cache: dict[str, object] | None = None
        self._cache_timestamp: float = 0.0
        self._jwks_url = (
            f"https://cognito-idp.{region}.amazonaws.com/"
            f"{user_pool_id}/.well-known/jwks.json"
        )
        self._issuer_url = (
            f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        )

    @property
    def issuer_url(self) -> str:
        """Return the expected JWT issuer URL for this Cognito user pool."""
        return self._issuer_url

    def _cache_is_fresh(self) -> bool:
        """Return True if the JWKS cache exists and has not expired."""
        if self._jwks_cache is None:
            return False
        return (time.monotonic() - self._cache_timestamp) < self._cache_ttl

    async def get_jwks(self, *, force_refresh: bool = False) -> dict[str, object]:
        """Fetch JWKS from Cognito, using cache when available.

        Args:
            force_refresh: If True, bypass cache and fetch fresh keys.

        Returns:
            The JWKS JSON response containing the ``keys`` array.

        Raises:
            HTTPException: 401 if JWKS endpoint is unreachable and no cache exists.
        """
        if not force_refresh and self._cache_is_fresh():
            return self._jwks_cache  # type: ignore[return-value]

        try:
            async with log_external_call("cognito", "jwks_fetch"):
                async with httpx.AsyncClient() as client:
                    resp = await client.get(self._jwks_url, timeout=5)
                    resp.raise_for_status()
                    jwks: dict[str, object] = resp.json()
            self._jwks_cache = jwks
            self._cache_timestamp = time.monotonic()
            return jwks
        except (httpx.HTTPError, httpx.TimeoutException):
            if self._jwks_cache is not None:
                logger.warning(
                    "JWKS endpoint unreachable, using stale cache "
                    "(age=%.0fs, url=%s)",
                    time.monotonic() - self._cache_timestamp,
                    self._jwks_url,
                )
                return self._jwks_cache
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication service unavailable",
                headers={"WWW-Authenticate": "Bearer"},
            )

    async def get_signing_key(self, token: str) -> dict[str, object]:
        """Extract the kid from the token header and find the matching JWK.

        If the kid is not found in cached keys, forces a JWKS refresh (once)
        to handle key rotation gracefully.

        Args:
            token: The raw JWT string.

        Returns:
            The JWK dict matching the token's kid.

        Raises:
            HTTPException: 401 if kid is not found in JWKS even after refresh.
        """
        try:
            header = jwt.get_unverified_header(token)
        except JWTError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        kid = header.get("kid")
        if kid is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # First attempt: search cached keys
        jwks = await self.get_jwks()
        key = self._find_key(jwks, kid)
        if key is not None:
            return key

        # Second attempt: force refresh (key rotation scenario)
        jwks = await self.get_jwks(force_refresh=True)
        key = self._find_key(jwks, kid)
        if key is not None:
            return key

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    @staticmethod
    def _find_key(
        jwks: dict[str, object],
        kid: str,
    ) -> dict[str, object] | None:
        """Find a JWK by kid in the JWKS response."""
        keys = jwks.get("keys", [])
        if not isinstance(keys, list):
            return None
        for k in keys:
            if isinstance(k, dict) and k.get("kid") == kid:
                return k
        return None


# Module-level singleton — shares JWKS cache across all requests in the process
_jwks_provider = CognitoJWKSProvider(
    region=settings.aws_region,
    user_pool_id=settings.cognito_user_pool_id,
)


async def verify_cognito_token(token: str) -> dict[str, object]:
    """Verify a Cognito JWT and return its claims.

    Validates the token's RS256 signature against the JWKS, checks
    audience matches COGNITO_APP_CLIENT_ID, issuer matches the Cognito
    user pool URL, and token_use is "id".

    Args:
        token: The raw JWT string (without ``Bearer`` prefix).

    Returns:
        The decoded JWT claims dict containing sub, email, iss, aud, exp,
        token_use and other Cognito ID token claims.

    Raises:
        HTTPException: 401 if the token is invalid, expired, or has
            wrong audience/issuer/token_use.
    """
    key = await _jwks_provider.get_signing_key(token)

    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.cognito_app_client_id,
            issuer=_jwks_provider.issuer_url,
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # Validate token_use — Ember uses ID tokens, not access tokens
    if claims.get("token_use") != "id":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate sub is a valid UUID
    sub = claims.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        uuid.UUID(str(sub))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    result: dict[str, object] = claims
    return result


def get_jwks_provider() -> CognitoJWKSProvider:
    """Return the module-level JWKS provider singleton.

    Useful for testing — allows tests to access and reset the provider.
    """
    return _jwks_provider
