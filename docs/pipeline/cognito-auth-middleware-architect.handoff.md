# Architect Handoff: Cognito Auth Middleware

**Date**: 2026-02-23
**Agent**: architect
**Status**: COMPLETE
**Feature ID**: P01-03
**GitHub Issue**: #5
**Layer**: backend

---

## What Was Designed

AWS Cognito JWT authentication middleware for FastAPI that replaces the existing `get_current_user` stub (which returns HTTP 501) with real RS256 JWT verification. The middleware fetches JWKS keys from the Cognito well-known endpoint, caches them with a 10-minute TTL, verifies token signature/expiry/audience/issuer claims, validates `token_use=id`, extracts the `sub` claim as the user UUID, and looks up the corresponding `Profile` row in the database. It handles key rotation gracefully by force-refreshing JWKS when a `kid` is not found in the cache.

## Spec Location

`shared/feature-specs/cognito-auth-middleware.md`

## Key Decisions

- **`CognitoJWKSProvider` class instead of simple module-level dict**: The cache requires both data and a TTL timestamp, plus force-refresh logic for key rotation. A class encapsulates this cleanly and is easier to test than module-level globals. A module-level singleton provides identical runtime performance.
- **`token_use` validated as `"id"` (not `"access"`)**: Ember uses Cognito ID tokens because they contain the `sub` UUID mapping to `profiles.id` and user attributes (email, name). Access tokens are for OAuth2 resource server patterns that Ember does not use.
- **Auth module placed at `core/auth.py`** (not `utils/cognito.py`): Consistent with the existing `core/logging.py` pattern from P01-01. Authentication is an application-wide concern, not a stateless utility. The standards doc shows `utils/cognito.py` as a reference, but the implemented project structure favors `core/`.
- **Stale cache preferred over hard failure**: When the Cognito JWKS endpoint is unreachable, stale cached keys are used (with a warning log) rather than rejecting all requests. JWKS keys change approximately every 30 days; a few minutes of staleness is acceptable.
- **Force refresh on `kid` miss**: When a token's `kid` is not in the cached JWKS, one forced refresh is attempted before rejecting the token. This handles Cognito key rotation without waiting for TTL expiry.
- **`HTTPBearer` from `fastapi.security`**: Standard FastAPI pattern that handles header extraction, missing-header 401s, and OpenAPI documentation automatically.
- **No changes to `config.py`**: The required settings (`cognito_user_pool_id`, `cognito_app_client_id`, `aws_region`) already exist from P01-01.
- **Generic error messages for token failures**: All token-level failures return "Invalid or expired token" to prevent information leakage about the specific rejection reason. Only "User not found" is distinct (valid token, missing profile).

## Assumptions Made

- P01-01 is complete: `config.py` has `cognito_user_pool_id`, `cognito_app_client_id`, `aws_region` settings; `dependencies.py` has the `get_current_user` stub and `get_db`; `core/` directory exists with `logging.py`.
- P01-02 is complete: The `Profile` model exists with `id: Mapped[uuid.UUID]` as the PK (Cognito sub).
- `python-jose[cryptography]` and `httpx` are already in `requirements.txt` (verified -- they are).
- The mobile clients will send Cognito ID tokens (not access tokens) in the `Authorization: Bearer` header.
- The `profiles` table is pre-populated for authenticated users (profile creation happens during registration, which is a separate feature).

## Dependencies

- **Requires**: P01-01 (project-setup), P01-02 (database-schema)
- **Blocks**: P01-04 (character CRUD), P01-05 (basic messaging), and all subsequent features that use `Depends(get_current_user)`

## File Manifest

```
Backend:
  CREATE  backend/app/core/auth.py
  MODIFY  backend/app/dependencies.py
  CREATE  backend/tests/test_auth.py
  CREATE  backend/tests/test_auth_dependency.py

Shared:
  CREATE  shared/feature-specs/cognito-auth-middleware.md
  CREATE  docs/pipeline/cognito-auth-middleware-architect.handoff.md
```

## Notes for Developers

- **Read the full spec first**: `shared/feature-specs/cognito-auth-middleware.md` -- it contains the complete authentication flow, JWKS caching strategy, all error scenarios, and all 24 test scenarios.
- **Start with `core/auth.py`**: Implement `CognitoJWKSProvider` and `verify_cognito_token` first. Then modify `dependencies.py` to use them.
- **RSA key generation for tests**: Use `cryptography.hazmat.primitives.asymmetric.rsa.generate_private_key()` to create test keys. Build a mock JWKS from the public key. Sign test JWTs with the private key using `python-jose`.
- **UUID conversion**: The `sub` claim is a string. Convert with `uuid.UUID(claims["sub"])` before querying `profiles.id`.
- **Use `time.monotonic()`** for cache TTL, not `time.time()`.
- **`HTTPBearer` import**: `from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer`.
- **Preserve `get_db`**: Only replace `get_current_user` in `dependencies.py`. Do not touch `get_db`.
- **All 401 responses** must include the `WWW-Authenticate: Bearer` header (except the automatic ones from `HTTPBearer` which handle this themselves).

## Next Steps

backend-dev should read the spec at `shared/feature-specs/cognito-auth-middleware.md` and implement all 5 files (1 new module, 1 modification, 2 test files, plus verifying ruff/mypy pass). backend-tester should then verify all 20 acceptance criteria.
