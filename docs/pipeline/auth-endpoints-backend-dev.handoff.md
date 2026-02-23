# Backend Dev Handoff: Auth Endpoints

**Date**: 2026-02-23
**Agent**: backend-dev
**Status**: COMPLETE
**Feature ID**: P01-04
**GitHub Issue**: #6

## Implemented Files

### Created
- `backend/app/schemas/auth.py` -- 6 schemas (RegisterRequest, LoginRequest, RefreshRequest, UserResponse, AuthResponse, RefreshResponse)
- `backend/app/services/auth_service.py` -- AuthService class with 3 public methods (register, login, refresh) + DEFAULT_COMPANION_PROMPT constant
- `backend/app/routes/auth.py` -- 3 route handlers (POST /register, POST /login, POST /refresh)
- `backend/tests/test_auth_routes.py` -- 17 route-level integration tests
- `backend/tests/test_auth_service.py` -- 11 service-level unit tests
- `backend/tests/test_auth_schemas.py` -- 13 schema validation tests

### Modified
- `backend/app/main.py` -- Added auth router registration at `/api/v1/auth`
- `backend/requirements.txt` -- Added `email-validator>=2.0.0,<3.0.0`

## Endpoints Implemented

| Method | Path | Status Code | Description |
|--------|------|-------------|-------------|
| POST | `/api/v1/auth/register` | 201 | Cognito signup + DB profile + default character + auto-conversation |
| POST | `/api/v1/auth/login` | 200 | Cognito USER_PASSWORD_AUTH + profile lookup |
| POST | `/api/v1/auth/refresh` | 200 | Cognito REFRESH_TOKEN_AUTH, returns new ID token |

All three endpoints are public (no JWT required).

## Test Results

```
pytest: 485 passed (41 new auth tests + 444 pre-existing), 0 failed
ruff: clean (all new/modified files)
No hardcoded secrets found
```

## Test Command

```bash
backend/.venv/bin/python -m pytest backend/tests/test_auth_routes.py backend/tests/test_auth_service.py backend/tests/test_auth_schemas.py -v
```

## Known Issues / Deviations from Spec

- None. All 20 acceptance criteria from the spec are covered by the implementation and tests.

## Notes for Backend Tester

### Mocking Strategy

- **Cognito client**: Mock `app.services.auth_service.boto3.client` with a `MagicMock` (NOT `AsyncMock`). The boto3 calls are synchronous and run via `asyncio.to_thread()`. Using `AsyncMock` causes "coroutine not subscriptable" errors.
- **JWT decode**: Mock `app.services.auth_service.jwt.get_unverified_claims` to return `{"sub": "test-uuid"}`.
- **Database**: Override `get_db` dependency to yield a configured `AsyncMock` session. Key mock setup:
  - `mock_db.execute` returns a `MagicMock` with `.scalar_one_or_none()` configured
  - `mock_db.add` should be a `MagicMock` (sync call)
  - `mock_db.commit` and `mock_db.refresh` should be `AsyncMock`
- **Cognito errors**: Use `botocore.exceptions.ClientError` with the appropriate error code in the `Error.Code` field.

### Key Code Paths to Test Thoroughly

- **Register idempotent recovery**: When Cognito returns `UsernameExistsException`, the service attempts authentication. If auth succeeds and no profile exists, it creates the missing DB rows. If auth fails (wrong password), it returns 400.
- **UserResponse.id coercion**: The `UserResponse` schema has a `field_validator("id", mode="before")` to convert `uuid.UUID` to `str`. Verify this works with real Profile ORM objects.
- **Email normalization**: Both `RegisterRequest` and `LoginRequest` lowercase and strip email before passing to Cognito.
- **Name trimming**: `RegisterRequest` strips whitespace from name. A name that becomes empty after trimming fails validation.

### Cognito Error Code Mapping

| Error Code | Register | Login | Refresh |
|-----------|----------|-------|---------|
| UsernameExistsException | 400 (or idempotent recovery) | N/A | N/A |
| InvalidPasswordException | 400 | N/A | N/A |
| NotAuthorizedException | N/A | 401 | 401 |
| UserNotConfirmedException | N/A | 401 | N/A |
| UserNotFoundException | N/A | 401 | 401 |
| TooManyRequestsException | 429 | N/A | N/A |
| Other ClientError | 503 | 503 | 503 |
