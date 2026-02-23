# Backend Dev Handoff: Cognito Auth Middleware

**Date**: 2026-02-23
**Agent**: backend-dev
**Status**: COMPLETE
**Feature ID**: P01-03
**GitHub Issue**: #5

## Implemented Files

### Created
- `backend/app/core/auth.py` -- CognitoJWKSProvider class (JWKS fetching, 10-min TTL cache, force refresh on kid miss, stale cache fallback) and verify_cognito_token function (RS256 verification, audience/issuer/token_use validation)
- `backend/tests/test_auth.py` -- 17 unit tests covering JWKS provider caching, TTL, force refresh, stale cache, and token verification scenarios
- `backend/tests/test_auth_dependency.py` -- 7 integration tests covering get_current_user dependency via FastAPI test client

### Modified
- `backend/app/dependencies.py` -- Replaced `get_current_user` stub (HTTP 501) with real Cognito JWT authentication: HTTPBearer token extraction, verify_cognito_token call, Profile DB lookup by sub claim UUID
- `backend/tests/test_dependencies.py` -- Updated tests to reflect new get_current_user signature (no longer raises 501; now validates it is a coroutine with credentials and db parameters)

## Endpoints Implemented

No new endpoints. This feature modifies the `get_current_user` dependency injected into all protected endpoints via `Depends(get_current_user)`.

**Before**: `Depends(get_current_user)` always raised HTTP 501 Not Implemented.
**After**: `Depends(get_current_user)` verifies the Cognito JWT and returns the authenticated `Profile` ORM object.

## Architecture

### Authentication Flow
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
    +--> Extract sub claim (UUID)
    |
    v
DB lookup: SELECT * FROM profiles WHERE id = {sub}
    |
    +--> Found: return Profile
    +--> Not found: raise 401 "User not found"
```

### JWKS Caching
- 10-minute TTL using `time.monotonic()`
- Force refresh on kid miss (handles Cognito key rotation)
- Stale cache preferred over hard failure when endpoint unreachable
- Module-level singleton shares cache across all requests

## Test Results
- pytest: 394 passed, 0 failed
- ruff: clean (app/ and all new/modified test files)
- mypy: clean (app/core/auth.py, app/dependencies.py)
- hardcoded secrets check: clean

## Test Command
```bash
backend/.venv/bin/python -m pytest backend/tests/test_auth.py backend/tests/test_auth_dependency.py -v
```

## Known Issues / Deviations from Spec
- None. Implementation follows the spec exactly.

## Notes for Backend Tester

### Mock Setup
- **JWKS Provider**: Patch `app.core.auth._jwks_provider` to control JWKS key responses. The provider has `get_signing_key` (returns JWK dict) and `issuer_url` (string property).
- **Settings**: Patch `app.core.auth.settings` to set `cognito_app_client_id`.
- **httpx**: For JWKS provider unit tests, patch `app.core.auth.httpx.AsyncClient` to mock HTTP responses.
- **Database**: Override `get_db` dependency to inject mock AsyncSession.

### RSA Key Generation
```python
from cryptography.hazmat.primitives.asymmetric import rsa
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
```
Convert to JWK for mock JWKS, convert to PEM for signing test tokens with python-jose.

### Token Creation
Use `jose.jwt.encode()` with the private key PEM and `headers={"kid": kid}`. Set claims: sub (UUID), aud (client_id), iss (issuer_url), token_use ("id"), exp, iat.

### Key Scenarios to Verify
1. Valid token + existing profile returns Profile object
2. Expired token returns 401 "Invalid or expired token"
3. Wrong signature returns 401
4. Wrong audience returns 401
5. Wrong issuer returns 401
6. token_use="access" returns 401
7. Valid token + no profile returns 401 "User not found"
8. No Authorization header returns 401 "Not authenticated"
9. JWKS cache TTL honored (10 min)
10. Force refresh on kid miss
11. Stale cache used when endpoint unreachable
12. Health endpoint remains public (no auth required)
