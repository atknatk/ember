# Feature Spec: P01-03 -- Cognito Auth Middleware

**Feature ID**: P01-03
**Phase**: 1
**Layer**: backend
**GitHub Issue**: #5
**Date**: 2026-02-23
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature replaces the `get_current_user` stub in `backend/app/dependencies.py` (which currently returns HTTP 501) with a fully functional AWS Cognito JWT authentication middleware. It verifies RS256-signed JWT tokens against the Cognito JWKS endpoint, extracts the `user_id` from the `sub` claim, looks up the corresponding `Profile` row in the database, and returns the authenticated user object. It provides JWKS key caching with a 10-minute TTL to avoid fetching keys on every request, and returns appropriate 401 errors for expired, malformed, or invalid tokens.

### Why It Exists

Every protected endpoint in Ember depends on `Depends(get_current_user)` to identify the calling user. Without this middleware, no endpoint can authenticate requests, enforce data isolation (user can only access their own data), or extract the `user_id` from the JWT. This is the security foundation for the entire API.

### Dependencies

- **Requires**: P01-01 (project-setup -- FastAPI scaffold, config, dependencies stub, httpx, python-jose in requirements.txt)
- **Requires**: P01-02 (database-schema -- `Profile` model with `id` as Cognito sub UUID)
- **Blocks**: P01-04 (character CRUD), P01-05 (basic messaging), and all subsequent features that use `Depends(get_current_user)`

### What This Feature Does NOT Do

- It does not implement user registration or login endpoints. Those are a separate feature (Cognito handles registration/login; the backend receives tokens).
- It does not implement token refresh logic. Refresh tokens are handled by the mobile clients via the Cognito SDK.
- It does not implement authorization (role-based access control). Authorization checks (e.g., "does this character belong to this user?") are implemented in individual route features.
- It does not add any new database tables or columns. It reads from the existing `profiles` table.

---

## 2. Data Models

### No New Tables

This feature does not create or modify any database tables. It reads from the existing `profiles` table (defined in P01-02, documented in `docs/04-veri-api.md`).

### Key Table Reference

The `profiles` table has `id` as a UUID primary key, where the value is the AWS Cognito `sub` claim. The auth middleware extracts `sub` from the JWT and uses it to look up the profile:

```
profiles.id = JWT claims["sub"]   (UUID format)
```

---

## 3. API Changes

### No New Endpoints

This feature does not introduce any new API endpoints. It modifies the behavior of the `get_current_user` dependency that existing and future endpoints inject via `Depends(get_current_user)`.

### Auth Dependency Behavior Change

**Before (P01-01 stub)**:
```
Depends(get_current_user) -> always raises HTTP 501 Not Implemented
```

**After (this feature)**:
```
Depends(get_current_user) -> verifies JWT, returns Profile ORM object
```

### Error Responses Produced by the Middleware

All 401 responses include the `WWW-Authenticate: Bearer` header as required by RFC 6750.

| Scenario | Status | Response Body |
|----------|--------|---------------|
| No `Authorization` header | 401 | `{"detail": "Not authenticated"}` |
| `Authorization` header without `Bearer` prefix | 401 | `{"detail": "Not authenticated"}` |
| Token is malformed (cannot parse header) | 401 | `{"detail": "Invalid or expired token"}` |
| Token signature is invalid | 401 | `{"detail": "Invalid or expired token"}` |
| Token `kid` does not match any JWKS key | 401 | `{"detail": "Invalid or expired token"}` |
| Token has expired (`exp` claim in the past) | 401 | `{"detail": "Invalid or expired token"}` |
| Token `aud` (audience) does not match `COGNITO_APP_CLIENT_ID` | 401 | `{"detail": "Invalid or expired token"}` |
| Token `iss` (issuer) does not match Cognito user pool URL | 401 | `{"detail": "Invalid or expired token"}` |
| Token `token_use` claim is not `"id"` | 401 | `{"detail": "Invalid or expired token"}` |
| Token is valid but `sub` does not match any `profiles.id` | 401 | `{"detail": "User not found"}` |

The generic "Invalid or expired token" message is intentionally vague for all token-level failures. This prevents information leakage about the specific reason for rejection. The "User not found" message is a separate case because the token itself is valid but the user has no profile in the database (e.g., registration incomplete, account deleted).

---

## 4. Backend Logic

### Authentication Flow

```
Client sends: Authorization: Bearer <jwt_token>
                 |
                 v
    HTTPBearer extracts token string
                 |
                 v
    verify_cognito_token(token)
        |
        +--> get_jwks() — fetch keys from Cognito (cached 10 min)
        |        |
        |        +--> Cache HIT: return cached keys
        |        +--> Cache MISS or EXPIRED: fetch from
        |             https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/jwks.json
        |
        +--> jwt.get_unverified_header(token) — extract kid
        |
        +--> Find matching key in JWKS by kid
        |        |
        |        +--> NOT FOUND: try JWKS refresh (key rotation scenario), then fail if still not found
        |
        +--> jwt.decode(token, key, algorithms=["RS256"], audience=client_id, issuer=issuer_url)
        |
        +--> Validate token_use == "id"
        |
        +--> Extract sub claim (UUID)
                 |
                 v
    DB lookup: SELECT * FROM profiles WHERE id = {sub}
                 |
                 +--> Found: return Profile object
                 +--> Not found: raise 401 "User not found"
```

### Module: `backend/app/core/auth.py`

This module contains the JWKS fetching, caching, and token verification logic. It is placed in `core/` rather than `utils/` because authentication is an application-wide concern (not a stateless helper). The `docs/standards/backend.md` Section 1 shows `utils/cognito.py` as a reference, but the actual project structure (from P01-01) already has `core/` for application-wide concerns like logging.

**Class: `CognitoJWKSProvider`**

Responsibilities:
- Fetch JWKS keys from the Cognito well-known endpoint
- Cache keys in memory with a 10-minute TTL
- Handle key rotation: if a token's `kid` is not found in the cached keys, force a refresh (once per request) before failing
- Construct the Cognito issuer URL from `aws_region` and `cognito_user_pool_id`

State:
- `_jwks_cache: dict | None` -- the cached JWKS response (the full JSON with `keys` array)
- `_cache_timestamp: float` -- `time.monotonic()` when the cache was last populated
- `_cache_ttl: float` -- 600.0 seconds (10 minutes)

Methods:

```
async def get_jwks(self, *, force_refresh: bool = False) -> dict
    """Fetch JWKS from Cognito, using cache when available.

    Args:
        force_refresh: If True, bypass cache and fetch fresh keys.

    Returns:
        The JWKS JSON response containing the 'keys' array.

    Raises:
        HTTPException 401: If JWKS endpoint is unreachable after retries.
    """
```

The `get_jwks` method:
1. If `force_refresh` is False and cache is populated and cache age < 600 seconds, return cached keys.
2. Otherwise, make an async HTTP GET to the JWKS URL using httpx.
3. Set `timeout=5` on the httpx request to prevent hanging.
4. On success, update `_jwks_cache` and `_cache_timestamp`.
5. On failure (network error, non-200 status), if there is a stale cache, return it with a warning log. If there is no cache at all, raise 401 with detail "Authentication service unavailable".

```
async def get_signing_key(self, token: str) -> dict
    """Extract the kid from the token header and find the matching JWK.

    Args:
        token: The raw JWT string.

    Returns:
        The JWK dict matching the token's kid.

    Raises:
        HTTPException 401: If kid is not found in JWKS (even after refresh).
    """
```

The `get_signing_key` method:
1. Decode the token header (unverified) to get the `kid`.
2. Search the cached JWKS keys for a matching `kid`.
3. If not found, call `get_jwks(force_refresh=True)` and search again. This handles Cognito key rotation gracefully.
4. If still not found after refresh, raise 401.

**Function: `verify_cognito_token`**

```
async def verify_cognito_token(token: str) -> dict
    """Verify a Cognito JWT and return its claims.

    Args:
        token: The raw JWT string (without 'Bearer ' prefix).

    Returns:
        The decoded JWT claims dict, containing at minimum: sub, email, iss, aud, exp, token_use.

    Raises:
        HTTPException 401: If the token is invalid, expired, or has wrong audience/issuer.
    """
```

The `verify_cognito_token` function:
1. Get the signing key from the JWKS provider.
2. Call `jose.jwt.decode()` with:
   - `algorithms=["RS256"]`
   - `audience=settings.cognito_app_client_id`
   - `issuer=f"https://cognito-idp.{settings.aws_region}.amazonaws.com/{settings.cognito_user_pool_id}"`
3. Validate that `claims["token_use"] == "id"`. Cognito issues both `id` and `access` tokens; Ember uses the ID token which contains the user's email and other attributes.
4. On any `JWTError`, `JWTClaimsError`, `ExpiredSignatureError`, or `StopIteration`, raise HTTP 401 with detail "Invalid or expired token" and `WWW-Authenticate: Bearer` header.
5. Return the claims dict on success.

### JWKS Provider Singleton

The `CognitoJWKSProvider` is instantiated as a module-level singleton in `core/auth.py`:

```python
_jwks_provider = CognitoJWKSProvider(settings=settings)
```

This ensures the JWKS cache is shared across all requests in the same process. The `verify_cognito_token` function uses this singleton.

### Module: `backend/app/dependencies.py` (Modified)

The existing `get_current_user` stub is replaced with the real implementation.

**Function: `get_current_user`**

```
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    db: AsyncSession = Depends(get_db),
) -> Profile
    """Authenticate the request and return the current user's Profile.

    Extracts the Bearer token from the Authorization header, verifies it
    against Cognito JWKS, and looks up the corresponding profile in the database.

    Args:
        credentials: The Bearer token extracted by FastAPI's HTTPBearer.
        db: The async database session.

    Returns:
        The authenticated user's Profile ORM object.

    Raises:
        HTTPException 401: If the token is missing, invalid, expired, or the user is not found.
    """
```

Implementation steps:
1. `HTTPBearer()` extracts the token from the `Authorization: Bearer <token>` header. If the header is missing or malformed, FastAPI automatically returns 401 with `{"detail": "Not authenticated"}`.
2. Call `verify_cognito_token(credentials.credentials)` to validate the token and get claims.
3. Extract `cognito_sub = claims["sub"]` as a UUID.
4. Query the database: `SELECT * FROM profiles WHERE id = {cognito_sub}`.
5. If no profile is found, raise HTTP 401 with detail "User not found".
6. Return the `Profile` ORM object.

The `get_db` dependency remains unchanged from P01-01.

### Why `core/auth.py` and not `utils/cognito.py`

The `docs/standards/backend.md` Section 1 reference structure shows `utils/cognito.py`. However, the actual P01-01 implementation established `core/` for application-wide concerns (logging is in `core/logging.py`). Authentication is an application-wide concern, not a stateless utility function. Placing it in `core/` follows the established pattern and keeps `utils/` for truly stateless helpers (like cursor encoding).

That said, `utils/cognito.py` as shown in the standards is also acceptable. The developer should use `core/auth.py` to be consistent with the existing `core/logging.py` pattern established in P01-01. If the developer strongly prefers the standards reference, `utils/cognito.py` is also acceptable -- the key requirement is that the implementation is correct, not the exact file path.

### Configuration

The `Settings` class in `backend/app/config.py` already has the required fields:
- `cognito_user_pool_id: str = ""` (line 51)
- `cognito_app_client_id: str = ""` (line 52)
- `aws_region: str = "us-east-1"` (line 43)

No changes to `config.py` are needed.

### Derived Constants

The JWKS URL is derived at runtime:
```
https://cognito-idp.{settings.aws_region}.amazonaws.com/{settings.cognito_user_pool_id}/.well-known/jwks.json
```

The issuer URL is derived at runtime:
```
https://cognito-idp.{settings.aws_region}.amazonaws.com/{settings.cognito_user_pool_id}
```

These are NOT stored in `config.py` as separate settings. They are computed from `aws_region` and `cognito_user_pool_id`.

---

## 5. JWKS Caching Strategy

### Cache Design

The JWKS cache is an in-memory dict stored on the `CognitoJWKSProvider` singleton. This is intentionally simple.

**Why not Redis or external cache**: The JWKS response is small (typically 2 keys, under 1 KB). In-memory caching is sufficient because:
- Each ECS task process handles its own requests and needs its own cached copy.
- The JWKS endpoint is highly available (AWS-managed).
- The worst case on cache miss is one additional HTTP call per 10 minutes per process.

**Cache lifecycle**:

```
Process starts
    |
    v
First authenticated request arrives
    |
    +--> Cache is empty → fetch JWKS → populate cache → set timestamp
    |
    v
Subsequent requests (within 10 min)
    |
    +--> Cache is populated and fresh → return cached keys
    |
    v
After 10 minutes
    |
    +--> Cache is stale → fetch JWKS → update cache → set new timestamp
    |
    v
Key rotation scenario (kid not found)
    |
    +--> Force refresh → fetch JWKS → update cache
    |    +--> kid found in new keys → proceed
    |    +--> kid still not found → reject token (401)
    |
    v
JWKS endpoint unreachable
    |
    +--> Stale cache exists → use stale cache + log warning
    +--> No cache exists → reject all requests (401 "Authentication service unavailable")
```

### TTL Details

- **Default TTL**: 600 seconds (10 minutes)
- **Time source**: `time.monotonic()` (immune to system clock changes)
- **Staleness policy**: Stale cache is preferred over a hard failure when the JWKS endpoint is temporarily unreachable. The stale keys are still valid for signature verification.
- **Force refresh**: Triggered when a token's `kid` is not found in the current cache. This handles key rotation without waiting for TTL expiry. Limited to one refresh attempt per `get_signing_key` call to prevent infinite loops.

---

## 6. Test Requirements

### What Must Be Tested

This is a security-critical feature. The test suite must cover all token validation paths, JWKS caching behavior, and dependency injection integration.

#### JWKS Provider Tests (`tests/test_auth.py`)

| # | Scenario | Expected |
|---|----------|----------|
| 1 | `get_jwks` fetches from Cognito URL on first call | httpx mock receives one GET request to the JWKS URL |
| 2 | `get_jwks` returns cached keys on second call within TTL | httpx mock receives exactly one GET request total (cache hit) |
| 3 | `get_jwks` re-fetches after TTL expiry | httpx mock receives two GET requests (initial + refresh after TTL) |
| 4 | `get_jwks(force_refresh=True)` bypasses cache | httpx mock receives a new GET request even when cache is fresh |
| 5 | `get_jwks` returns stale cache when endpoint is unreachable | Returns previously cached keys; logs a warning |
| 6 | `get_jwks` raises 401 when endpoint is unreachable and no cache exists | HTTPException with status 401 and detail "Authentication service unavailable" |
| 7 | `get_signing_key` returns the correct key matching the token's `kid` | Returned key dict has the expected `kid` value |
| 8 | `get_signing_key` triggers force refresh when `kid` is not in cache | After refresh, returns the newly available key |
| 9 | `get_signing_key` raises 401 when `kid` is not found even after refresh | HTTPException with status 401 |

#### Token Verification Tests (`tests/test_auth.py` continued)

These tests use a locally generated RSA key pair to create test JWTs and a mock JWKS response. They do NOT call real Cognito endpoints.

| # | Scenario | Expected |
|---|----------|----------|
| 10 | Valid token with correct signature, audience, issuer, and `token_use=id` | Returns claims dict with `sub` field |
| 11 | Token with expired `exp` claim | Raises HTTPException 401 with detail "Invalid or expired token" |
| 12 | Token signed with a different RSA key (wrong signature) | Raises HTTPException 401 |
| 13 | Token with wrong `aud` (different client ID) | Raises HTTPException 401 |
| 14 | Token with wrong `iss` (different issuer URL) | Raises HTTPException 401 |
| 15 | Token with `token_use=access` instead of `id` | Raises HTTPException 401 |
| 16 | Completely malformed token string (not a JWT) | Raises HTTPException 401 |
| 17 | Token with `kid` that does not match any JWKS key | Raises HTTPException 401 (after attempting JWKS refresh) |

#### Dependency Integration Tests (`tests/test_auth_dependency.py`)

These tests use the FastAPI test client with dependency overrides for the database session.

| # | Scenario | Expected |
|---|----------|----------|
| 18 | Request with valid token and existing profile in DB | `get_current_user` returns the Profile object with correct `id` |
| 19 | Request with valid token but no matching profile in DB | Raises HTTPException 401 with detail "User not found" |
| 20 | Request with no `Authorization` header | Returns 401 with detail "Not authenticated" |
| 21 | Request with `Authorization: Basic ...` (not Bearer) | Returns 401 with detail "Not authenticated" |
| 22 | Request with `Authorization: Bearer <invalid_token>` | Returns 401 with detail "Invalid or expired token" |

#### Route-Level Integration Test (`tests/test_auth_dependency.py` continued)

| # | Scenario | Expected |
|---|----------|----------|
| 23 | `GET /api/v1/health` without auth header | Returns 200 (health is public) |
| 24 | A hypothetical protected endpoint with valid auth returns the correct user context | The route handler receives the authenticated Profile object |

### How to Mock JWKS

The test suite must generate a real RSA key pair at test-module scope and construct a JWKS response from it.

```
Test setup:
1. Generate RSA key pair (2048-bit) using the `cryptography` library (already installed as a dependency of python-jose[cryptography])
2. Construct a JWKS JSON with the public key, a known `kid`, and `alg: RS256`
3. Patch the httpx.AsyncClient.get to return this JWKS JSON
4. Sign test JWTs with the private key using python-jose

This approach:
- Does not require network access
- Tests the full verification pipeline (JWKS fetch -> key extraction -> signature verification -> claim validation)
- Allows creating tokens with various invalid states (expired, wrong audience, etc.)
```

### How to Mock the Database for Dependency Tests

Use the `conftest.py` pattern from P01-01:
- Override `get_db` to yield a test database session
- Insert a test `Profile` row with a known UUID (matching the `sub` in the test JWT)
- Verify that `get_current_user` returns this profile

### Code Quality Checks

```bash
ruff check backend/app/core/auth.py backend/app/dependencies.py
ruff check backend/tests/test_auth.py backend/tests/test_auth_dependency.py
mypy backend/app/core/auth.py backend/app/dependencies.py
pytest backend/tests/test_auth.py backend/tests/test_auth_dependency.py -v
```

---

## 7. File Manifest

Every file to be created or modified, grouped by purpose.

### Core Authentication Module

```
Backend:
  CREATE  backend/app/core/auth.py
```

This file contains `CognitoJWKSProvider`, `verify_cognito_token`, and the module-level singleton.

### Dependencies (Modified)

```
Backend:
  MODIFY  backend/app/dependencies.py
```

Replace the `get_current_user` stub with the real implementation that uses `HTTPBearer`, `verify_cognito_token`, and a database lookup on `profiles`.

### Tests

```
Backend:
  CREATE  backend/tests/test_auth.py
  CREATE  backend/tests/test_auth_dependency.py
```

`test_auth.py` tests the JWKS provider and token verification logic in isolation.
`test_auth_dependency.py` tests the `get_current_user` dependency with the FastAPI test client.

### Documentation (Pipeline)

```
Shared:
  CREATE  shared/feature-specs/cognito-auth-middleware.md         (this file)
  CREATE  docs/pipeline/cognito-auth-middleware-architect.handoff.md
```

### Summary

| Action | Count |
|--------|-------|
| CREATE | 4 |
| MODIFY | 1 |
| DELETE | 0 |
| **Total** | **5** |

### Files NOT Modified

- `backend/app/config.py` -- already has `cognito_user_pool_id`, `cognito_app_client_id`, and `aws_region`. No changes needed.
- `backend/app/main.py` -- no new routes to register. The auth middleware is injected via `Depends()`, not via middleware registration.
- `backend/requirements.txt` -- `python-jose[cryptography]` and `httpx` are already listed.
- `backend/.env.example` -- already has `COGNITO_USER_POOL_ID` and `COGNITO_APP_CLIENT_ID` entries.

---

## 8. Acceptance Criteria

1. Given the `get_current_user` dependency, when a client sends a request with a valid Cognito ID token in the `Authorization: Bearer` header and a matching profile exists in the `profiles` table, then the dependency returns the `Profile` ORM object with `id` equal to the token's `sub` claim.

2. Given the `get_current_user` dependency, when a client sends a request without an `Authorization` header, then the response is HTTP 401 with body `{"detail": "Not authenticated"}`.

3. Given the `get_current_user` dependency, when a client sends a request with an expired JWT, then the response is HTTP 401 with body `{"detail": "Invalid or expired token"}` and the `WWW-Authenticate: Bearer` header is present.

4. Given the `get_current_user` dependency, when a client sends a request with a JWT signed by a different key (invalid signature), then the response is HTTP 401 with body `{"detail": "Invalid or expired token"}`.

5. Given the `get_current_user` dependency, when a client sends a request with a JWT that has a wrong `aud` (audience) claim (not matching `COGNITO_APP_CLIENT_ID`), then the response is HTTP 401.

6. Given the `get_current_user` dependency, when a client sends a request with a JWT that has a wrong `iss` (issuer) claim, then the response is HTTP 401.

7. Given the `get_current_user` dependency, when a client sends a request with a valid JWT but the `sub` does not match any `profiles.id`, then the response is HTTP 401 with body `{"detail": "User not found"}`.

8. Given the `get_current_user` dependency, when a client sends a request with a JWT that has `token_use=access` instead of `token_use=id`, then the response is HTTP 401.

9. Given the JWKS provider, when the first authenticated request arrives, then the provider fetches the JWKS from `https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/jwks.json` and caches the response.

10. Given the JWKS provider with a populated cache, when a second authenticated request arrives within 10 minutes, then the provider returns the cached JWKS without making another HTTP request.

11. Given the JWKS provider with a cache older than 10 minutes, when an authenticated request arrives, then the provider fetches fresh JWKS from Cognito and updates the cache.

12. Given the JWKS provider, when a token's `kid` is not found in the cached JWKS, then the provider forces a refresh and retries the lookup before failing.

13. Given the JWKS provider, when the Cognito JWKS endpoint is unreachable and stale cached keys exist, then the provider uses the stale cached keys and logs a warning.

14. Given the JWKS provider, when the Cognito JWKS endpoint is unreachable and no cached keys exist, then all authenticated requests fail with HTTP 401.

15. Given the `GET /api/v1/health` endpoint, when a client sends a request without any `Authorization` header, then the response is HTTP 200 (health endpoint remains public and unaffected by the auth middleware).

16. Given the backend source code, when a developer runs `ruff check backend/app/core/auth.py backend/app/dependencies.py`, then zero errors are reported.

17. Given the backend source code, when a developer runs `mypy backend/app/core/auth.py backend/app/dependencies.py`, then zero errors are reported.

18. Given the backend test suite, when a developer runs `pytest backend/tests/test_auth.py backend/tests/test_auth_dependency.py -v`, then all tests pass with exit code 0.

19. Given the `backend/app/dependencies.py` file after implementation, when a developer inspects it, then the old `NoReturn` stub raising 501 is completely removed and replaced with the real `get_current_user` that returns `Profile`.

20. Given the error response for any 401 from the auth middleware, when a developer inspects the response, then it follows the format `{"detail": "..."}` as specified in `docs/standards/common.md` Section 7.

---

## 9. Design Decisions and Rationale

### Why `CognitoJWKSProvider` is a class with instance state, not a module-level dict

The initial reference in `docs/standards/backend.md` Section 5 shows a simple `_jwks_cache: dict | None` module variable. This spec upgrades that to a class because:
1. The cache needs both the data and a timestamp for TTL enforcement.
2. The force-refresh logic (for key rotation) requires coordinated access to both fields.
3. A class is easier to test -- tests can create instances with custom settings and mock the HTTP client without patching module globals.
4. The singleton pattern (`_jwks_provider` at module level) still provides the same performance as a module-level variable.

### Why `token_use` is validated as `"id"` (not `"access"`)

Cognito issues two types of tokens: ID tokens and access tokens. The ID token contains the user's email, name, and other attributes from the user pool. The access token contains OAuth2 scopes. Ember uses the ID token because:
1. The `sub` claim in the ID token is the user's UUID, which maps to `profiles.id`.
2. The ID token contains the user's email, useful for profile auto-creation in future features.
3. The access token is typically used for resource server authorization, which Ember does not need (the backend is both the auth and resource server).

### Why the auth module is in `core/auth.py` instead of `utils/cognito.py`

See Section 4 for the rationale. The key points are: `core/` was established in P01-01 for application-wide concerns, authentication is an application-wide concern, and this is consistent with `core/logging.py`.

### Why stale cache is preferred over hard failure

When the Cognito JWKS endpoint is temporarily unreachable (network blip, AWS incident), rejecting all requests would cause a complete service outage. The JWKS keys change infrequently (only on key rotation, which Cognito does approximately every 30 days). Serving stale keys for a few minutes of unreachability is far less risky than rejecting all authenticated requests.

### Why force refresh on `kid` miss before failing

Cognito rotates signing keys periodically. When a new key is deployed, tokens signed with the new key will have a `kid` not present in the cached JWKS. Rather than rejecting these valid tokens, the middleware forces one JWKS refresh. If the `kid` is still not found after the fresh fetch, the token is genuinely invalid.

### Why `HTTPBearer` from `fastapi.security` instead of manual header parsing

`HTTPBearer` is a FastAPI-provided security scheme that:
1. Automatically extracts the token from `Authorization: Bearer <token>`.
2. Returns 401 with `{"detail": "Not authenticated"}` if the header is missing or malformed.
3. Adds the security scheme to the OpenAPI docs (Swagger UI "Authorize" button).
4. Is the standard pattern shown in `docs/standards/backend.md` Section 5.

---

## 10. Notes for Developers

### For backend-dev

- Start by creating `backend/app/core/auth.py` with the JWKS provider and verification function. Then modify `backend/app/dependencies.py` to import and use them.
- The `Profile` model from P01-02 uses `id: Mapped[uuid.UUID]` as the PK. The `sub` claim from Cognito is a UUID string. You need to convert it: `uuid.UUID(claims["sub"])` before querying.
- The `HTTPBearer` dependency from `fastapi.security` must be imported. When `auto_error=True` (default), it automatically returns 401 for missing/malformed Authorization headers.
- The httpx client for JWKS fetching should use `timeout=5` to prevent hanging on slow responses.
- Use `time.monotonic()` for cache TTL tracking, not `time.time()` or `datetime.now()`. Monotonic time is immune to system clock adjustments.
- When catching exceptions from `python-jose`, catch `jose.JWTError` as the base class. It covers `ExpiredSignatureError`, `JWTClaimsError`, and other JWT-specific errors.
- Import `jose.jwt` for `decode()` and `get_unverified_header()`. Do NOT import from `jose.jws` directly.
- The `issuer` URL format is `https://cognito-idp.{region}.amazonaws.com/{pool_id}` (no trailing slash).
- Do not create an `httpx.AsyncClient` on every JWKS fetch. Use a context-managed client within `get_jwks` or create one on the provider. Since JWKS fetches are infrequent (at most once per 10 minutes), creating a fresh client per fetch is acceptable and simpler than managing a persistent client lifecycle.
- The existing `get_db` dependency in `dependencies.py` must be preserved unchanged. Only `get_current_user` is replaced.
- Do not add `from __future__ import annotations` to files that need runtime type resolution for FastAPI dependency injection (FastAPI needs actual types at runtime for `Depends` to work). The existing `dependencies.py` already uses this import successfully with the stub, but verify it works with `HTTPBearer` and `Profile`.

### For backend-tester

- Generate RSA keys using `cryptography.hazmat.primitives.asymmetric.rsa.generate_private_key()`. Export the public key as JWK format for the mock JWKS response.
- Use `python-jose` to sign test tokens with the generated private key. Set `kid` in the header to match the mock JWKS.
- For the JWKS endpoint mock, use `unittest.mock.patch` on the httpx request. A `pytest.fixture` that patches `httpx.AsyncClient.get` or the provider's internal HTTP call is recommended.
- The `conftest.py` from P01-01 provides the basic test infrastructure. You may need to add fixtures for creating test `Profile` rows in the database.
- Test both the unit level (`core/auth.py` functions in isolation) and the integration level (FastAPI test client with real dependency injection).
- For TTL tests, mock `time.monotonic()` to simulate cache expiry without waiting 10 minutes.
- Verify that the `WWW-Authenticate: Bearer` header is present in all 401 responses from the auth middleware (not just from `HTTPBearer`).
