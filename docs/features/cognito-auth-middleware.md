# Cognito Auth Middleware

> Authenticates every protected API request by verifying AWS Cognito RS256 JWT tokens against cached JWKS keys and resolving the caller's database profile.

**Status**: Released
**Added in**: Phase 1 (P01-03)
**Platforms**: Backend
**GitHub Issue**: #5

---

## Overview

Cognito Auth Middleware replaces the placeholder `get_current_user` stub (which returned HTTP 501) with a fully functional JWT authentication dependency. Every protected endpoint in Ember injects `Depends(get_current_user)` to identify the calling user. This middleware is the security foundation for the entire API -- without it, no endpoint can authenticate requests, enforce data isolation, or extract the `user_id` from the token.

The middleware verifies RS256-signed Cognito ID tokens by fetching the JSON Web Key Set (JWKS) from the Cognito well-known endpoint, caching those keys in memory with a 10-minute TTL, and using them to validate the token's signature, expiry, audience, issuer, and `token_use` claims. On successful verification, it extracts the `sub` claim (a UUID), looks up the corresponding `Profile` row in the database, and returns the ORM object. If any step fails, a 401 response is returned with an intentionally vague error message to prevent information leakage.

This feature does not implement user registration, login, token refresh, or authorization (role-based access control). Registration and login are handled by AWS Cognito directly. Token refresh is handled by the mobile clients via the Cognito SDK. Authorization checks (e.g., "does this character belong to this user?") are implemented in individual route features.

---

## Architecture

### Authentication Flow

The end-to-end flow for every authenticated request:

1. The client sends an HTTP request with the header `Authorization: Bearer <jwt_token>`.
2. FastAPI's `HTTPBearer` security scheme extracts the token string. If the header is missing or malformed, FastAPI returns 401 automatically with `{"detail": "Not authenticated"}`.
3. `verify_cognito_token(token)` is called with the raw JWT string.
4. The `CognitoJWKSProvider` singleton fetches JWKS keys from Cognito (or returns cached keys if the cache is fresh).
5. The token header is decoded (unverified) to extract the `kid` (Key ID).
6. The matching public key is found in the JWKS response by `kid`.
7. `jose.jwt.decode()` verifies the RS256 signature, checks `exp` (expiry), `aud` (audience matches `COGNITO_APP_CLIENT_ID`), and `iss` (issuer matches the Cognito user pool URL).
8. The `token_use` claim is validated as `"id"` (Ember uses ID tokens, not access tokens).
9. The `sub` claim is extracted and validated as a UUID.
10. A database query looks up `SELECT * FROM profiles WHERE id = {sub}`.
11. If a profile is found, it is returned as the `Profile` ORM object. If not, a 401 "User not found" error is raised.

```
Authorization: Bearer <jwt>
         |
         v
  HTTPBearer extracts token
         |
         v
  verify_cognito_token(token)
     |
     +--> CognitoJWKSProvider.get_signing_key(token)
     |        +--> get_jwks() with 10-min TTL cache
     |        +--> Force refresh on kid miss (key rotation)
     |        +--> Stale cache fallback on endpoint unreachable
     |
     +--> jose.jwt.decode(token, key, RS256, audience, issuer)
     +--> Validate token_use == "id"
     +--> Validate sub is a UUID
         |
         v
  DB lookup: SELECT * FROM profiles WHERE id = {sub}
         |
         +--> Found: return Profile
         +--> Not found: raise 401 "User not found"
```

### JWKS Caching Strategy

The JWKS cache is an in-memory dict stored on the `CognitoJWKSProvider` singleton. This is intentionally simple because the JWKS response is small (typically 2 keys, under 1 KB) and each ECS task process handles its own requests.

**Cache lifecycle**:

- **First request**: Cache is empty. JWKS is fetched from Cognito. Cache is populated. Timestamp is recorded using `time.monotonic()`.
- **Subsequent requests (within 10 minutes)**: Cache is fresh. Cached keys are returned immediately without an HTTP call.
- **After 10 minutes**: Cache is stale. JWKS is re-fetched. Cache is updated.
- **Key rotation (kid not found)**: A force refresh is triggered. If the `kid` is found in the new keys, verification proceeds. If still not found, the token is rejected. Only one refresh attempt per `get_signing_key` call prevents infinite loops.
- **Endpoint unreachable (with stale cache)**: Stale cached keys are used and a warning is logged. JWKS keys change approximately every 30 days, so stale keys are almost certainly still valid.
- **Endpoint unreachable (no cache)**: All authenticated requests fail with 401 "Authentication service unavailable".

**Why stale cache over hard failure**: Rejecting all requests during a transient network issue would cause a complete service outage. Serving stale keys for a few minutes is far less risky because key rotation happens approximately every 30 days.

**TTL details**:
- Default: 600 seconds (10 minutes)
- Time source: `time.monotonic()` (immune to system clock adjustments)
- HTTP timeout: 5 seconds per JWKS fetch to prevent hanging

### Why ID Tokens (not Access Tokens)

Cognito issues two token types. Ember validates `token_use == "id"` because:

- The ID token `sub` claim is the user's UUID, which maps directly to `profiles.id`.
- The ID token contains the user's email and other attributes, useful for profile operations.
- Access tokens are used for OAuth2 resource server authorization patterns, which Ember does not need (the backend is both the auth and resource server).

### Database Tables Involved

| Table | Operation | Notes |
|-------|-----------|-------|
| `profiles` | SELECT | Lookup by `id = JWT sub claim`. Read-only -- no writes. |

No new tables are created or modified by this feature. It reads from the existing `profiles` table defined in P01-02.

---

## Error Responses

All error responses from the auth middleware follow the standard Ember error format `{"detail": "..."}`.

All 401 responses include the `WWW-Authenticate: Bearer` header as required by RFC 6750.

| Scenario | Status | Response Body |
|----------|--------|---------------|
| No `Authorization` header | 401 | `{"detail": "Not authenticated"}` |
| `Authorization` header without `Bearer` prefix | 401 | `{"detail": "Not authenticated"}` |
| Token is malformed (cannot parse header) | 401 | `{"detail": "Invalid or expired token"}` |
| Token signature is invalid | 401 | `{"detail": "Invalid or expired token"}` |
| Token `kid` does not match any JWKS key | 401 | `{"detail": "Invalid or expired token"}` |
| Token has expired (`exp` claim in the past) | 401 | `{"detail": "Invalid or expired token"}` |
| Token `aud` does not match `COGNITO_APP_CLIENT_ID` | 401 | `{"detail": "Invalid or expired token"}` |
| Token `iss` does not match Cognito user pool URL | 401 | `{"detail": "Invalid or expired token"}` |
| Token `token_use` claim is not `"id"` | 401 | `{"detail": "Invalid or expired token"}` |
| Token `sub` claim missing or not a UUID | 401 | `{"detail": "Invalid or expired token"}` |
| Valid token but `sub` does not match any `profiles.id` | 401 | `{"detail": "User not found"}` |
| JWKS endpoint unreachable and no cache exists | 401 | `{"detail": "Authentication service unavailable"}` |

The generic "Invalid or expired token" message is intentionally used for all token-level failures. This prevents information leakage about the specific reason for rejection. "User not found" is a distinct case because the token itself is valid but the user has no profile in the database (e.g., registration incomplete or account deleted).

---

## Configuration

No new configuration variables were introduced by this feature. The required settings already exist from P01-01:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `COGNITO_USER_POOL_ID` | str | `""` | AWS Cognito user pool ID |
| `COGNITO_APP_CLIENT_ID` | str | `""` | AWS Cognito app client ID |
| `AWS_REGION` | str | `us-east-1` | AWS region for Cognito endpoint URL |

Two URLs are derived at runtime from these settings (they are not stored as separate configuration):

- **JWKS URL**: `https://cognito-idp.{AWS_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}/.well-known/jwks.json`
- **Issuer URL**: `https://cognito-idp.{AWS_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}`

---

## Usage in Routes

Any route that requires authentication injects the `get_current_user` dependency via FastAPI's `Depends()`:

```python
from fastapi import APIRouter, Depends
from app.dependencies import get_current_user
from app.models.profile import Profile

router = APIRouter()

@router.get("/api/v1/example")
async def example_endpoint(
    current_user: Profile = Depends(get_current_user),
):
    # current_user is the authenticated Profile ORM object
    # current_user.id is the UUID matching the JWT sub claim
    return {"user_id": str(current_user.id)}
```

The health endpoint (`GET /api/v1/health`) does not use `Depends(get_current_user)` and remains public.

---

## Files

| File | Role |
|------|------|
| `backend/app/core/auth.py` | `CognitoJWKSProvider` class, `verify_cognito_token` function, module-level singleton |
| `backend/app/dependencies.py` | `get_current_user` dependency (modified from 501 stub to real implementation) |
| `backend/app/config.py` | Settings (unchanged -- already had required Cognito settings) |

### `backend/app/core/auth.py`

This module is placed in `core/` (not `utils/`) because authentication is an application-wide concern, consistent with the existing `core/logging.py` pattern from P01-01.

**`CognitoJWKSProvider`** -- manages JWKS fetching and caching:
- `get_jwks(force_refresh=False)` -- fetches JWKS with cache-first strategy
- `get_signing_key(token)` -- extracts `kid` from token header and finds the matching JWK
- `_find_key(jwks, kid)` -- static method to search the JWKS keys array
- `_cache_is_fresh()` -- checks if cache exists and is within TTL
- `issuer_url` -- property returning the expected JWT issuer URL

**`verify_cognito_token(token)`** -- verifies a JWT and returns its claims dict. Validates signature, expiry, audience, issuer, `token_use`, and `sub` format.

**`get_jwks_provider()`** -- returns the module-level singleton (useful for testing).

**`_jwks_provider`** -- module-level singleton instantiated with `settings.aws_region` and `settings.cognito_user_pool_id`.

### `backend/app/dependencies.py`

The `get_current_user` function:
1. Accepts `credentials` from `HTTPBearer()` and `db` from `get_db()` via `Depends()`.
2. Calls `verify_cognito_token(credentials.credentials)`.
3. Converts `claims["sub"]` to `uuid.UUID`.
4. Queries `profiles` for a matching row.
5. Returns the `Profile` ORM object or raises 401 "User not found".

The `get_db` dependency is unchanged from P01-01.

---

## Testing

### Coverage Summary

| Module | Line Coverage | Branch Coverage |
|--------|---------------|-----------------|
| `app/core/auth.py` | 100% | 100% |
| `app/dependencies.py` | 92% | 100% |
| **Combined** | **98%** | **100%** |

The only uncovered lines (26-27 of `dependencies.py`) are the `get_db()` body, which is a database session dependency unrelated to the auth feature.

### Test Files

| Test File | Count | What It Covers |
|-----------|-------|----------------|
| `tests/test_auth.py` | 17 | JWKS provider caching, TTL, force refresh, stale cache, token verification (valid, expired, wrong signature, wrong audience, wrong issuer, wrong token_use, malformed) |
| `tests/test_auth_extended.py` | 40 | `_find_key` edge cases, TTL boundary conditions (599s/600s), multiple key rotation, concurrent JWKS refresh, timeout handling, `get_signing_key` edge cases, sub claim validation, WWW-Authenticate header verification, error message exactness, provider URL construction, singleton accessor |
| `tests/test_auth_dependency.py` | 7 | `get_current_user` with valid token + profile, valid token + no profile, missing auth header, non-Bearer auth, invalid token |
| `tests/test_auth_dependency_extended.py` | 10 | DB session error handling, HTTPBearer edge cases (empty bearer, whitespace, malformed), WWW-Authenticate on "User not found", multiple sequential requests, health endpoint with invalid bearer |
| `tests/test_dependencies.py` | 3 | Dependency introspection (coroutine check, parameter types) |

**Total**: 77 auth-specific tests passing, 0 failures.

### Test Approach

Tests generate a real RSA key pair (2048-bit) at test-module scope using the `cryptography` library. A mock JWKS response is constructed from the public key. Test JWTs are signed with the private key using `python-jose`. The httpx client is mocked to return the JWKS JSON. This approach:

- Does not require network access or real Cognito endpoints.
- Tests the full verification pipeline (JWKS fetch, key extraction, signature verification, claim validation).
- Allows creating tokens with various invalid states (expired, wrong audience, wrong key, etc.).

For dependency integration tests, the FastAPI test client is used with `get_db` overridden to inject a mock `AsyncSession`. A test `Profile` row with a known UUID (matching the `sub` in the test JWT) is used to verify the full dependency chain.

### Running Tests

Auth tests only:

```bash
cd backend && python -m pytest tests/test_auth.py tests/test_auth_extended.py tests/test_auth_dependency.py tests/test_auth_dependency_extended.py tests/test_dependencies.py -v
```

Full backend suite:

```bash
cd backend && python -m pytest tests/ -v --ignore=tests/test_migration.py
```

Code quality:

```bash
cd backend && ruff check app/core/auth.py app/dependencies.py
cd backend && mypy app/core/auth.py app/dependencies.py
```

---

## Known Limitations

- **No offline token validation**: The first authenticated request after process startup requires a network call to the Cognito JWKS endpoint. If the endpoint is unreachable and no cache exists, all authentication fails.
- **In-memory cache is per-process**: Each ECS Fargate task process maintains its own JWKS cache. There is no shared cache across processes. This is by design -- the JWKS payload is small and the worst case is one extra HTTP call per 10 minutes per process.
- **No token refresh logic**: The backend does not refresh tokens. Mobile clients are responsible for refreshing expired tokens via the Cognito SDK and resending the request.
- **No authorization**: This feature authenticates (who are you?) but does not authorize (what can you do?). Authorization checks are implemented in individual route features.
- **Profile must pre-exist**: A valid Cognito token for a user with no `profiles` row returns 401 "User not found". Profile creation happens during registration, which is a separate feature.

---

## Design Decisions

### `CognitoJWKSProvider` as a class (not a module-level dict)

The cache requires both data and a TTL timestamp, plus force-refresh logic for key rotation. A class encapsulates this cleanly and is easier to test (instances can be created with custom settings without patching module globals). The module-level singleton provides identical runtime performance to a module-level dict.

### Auth module at `core/auth.py` (not `utils/cognito.py`)

The `docs/standards/backend.md` reference shows `utils/cognito.py`, but the actual project structure from P01-01 established `core/` for application-wide concerns (`core/logging.py`). Authentication is an application-wide concern, not a stateless utility, so `core/auth.py` follows the established pattern.

### Generic error messages for token failures

All token-level failures return "Invalid or expired token" regardless of the specific cause. This prevents attackers from distinguishing between expired tokens, wrong signatures, and wrong audiences, reducing information leakage.

### `HTTPBearer` from `fastapi.security`

This is the standard FastAPI pattern. It automatically extracts the Bearer token, returns 401 for missing/malformed headers, and adds the security scheme to OpenAPI documentation (enabling the Swagger UI "Authorize" button).

---

## Extending This Feature

To add additional claims extraction (e.g., reading the user's email from the token), modify `verify_cognito_token` in `backend/app/core/auth.py` to extract the desired claim from the `claims` dict after verification. The claims dict contains all standard Cognito ID token claims (`sub`, `email`, `email_verified`, `name`, `cognito:username`, etc.).

To add a secondary authentication scheme (e.g., API keys), create a new dependency function alongside `get_current_user` in `backend/app/dependencies.py` and inject it via `Depends()` in the routes that accept it. Do not modify `get_current_user` -- it should remain Cognito-only.

To adjust the JWKS cache TTL, modify the `cache_ttl` parameter when instantiating `CognitoJWKSProvider` in `backend/app/core/auth.py`. The default is 600.0 seconds (10 minutes). A shorter TTL means more frequent JWKS fetches; a longer TTL means slower response to key rotation.

To support access tokens in addition to ID tokens, modify the `token_use` validation in `verify_cognito_token` to accept both `"id"` and `"access"`. Note that access tokens may have a different `aud` claim format.

---

## Related Documentation

- [Project Setup](./project-setup.md) -- the scaffold this feature builds on
- [Database Schema](./database-schema.md) -- the `profiles` table this feature reads from
- [Database Schema and API Endpoints](../04-veri-api.md) -- authoritative source for table definitions
- [Security and Performance](../08-guvenlik-performans.md) -- JWT strategy, rate limiting
- [Backend Standards](../standards/backend.md) -- coding conventions
