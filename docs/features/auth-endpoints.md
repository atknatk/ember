# Auth Endpoints

> Provides public registration, login, and token refresh endpoints backed by AWS Cognito, bootstrapping each new user with a database profile, a default companion character, and an auto-conversation.

**Status**: Released
**Added in**: Phase 1 (P01-04)
**Platforms**: Backend
**GitHub Issue**: #6

---

## Overview

Auth Endpoints is the entry point for every user in Ember. Without these three endpoints, no one can create an account, sign in, or maintain a session. The feature implements `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, and `POST /api/v1/auth/refresh` -- all public (no JWT required).

The registration flow is particularly significant because it does more than create a Cognito user. It bootstraps the user's entire environment in a single database transaction: a `profiles` row, a default "Ember" companion character (template `companion`, `is_default=true`), and the corresponding auto-conversation for that character. This means a newly registered user can immediately start chatting with their AI companion without any additional setup steps.

The login flow authenticates against Cognito using the `USER_PASSWORD_AUTH` flow, looks up the profile in the database, and returns tokens plus user data. The refresh flow exchanges a Cognito refresh token for a new ID token. All three endpoints delegate business logic to the `AuthService` class; route handlers contain no business logic themselves.

---

## Architecture

### Registration Flow (End-to-End)

1. Client sends `POST /api/v1/auth/register` with `{ email, password, name }`
2. Pydantic validates the request body (`RegisterRequest`). Email is lowercased and stripped. Name is whitespace-trimmed.
3. `AuthService.register()` calls `cognito.sign_up()` via `asyncio.to_thread()` to create the user in Cognito.
4. `AuthService` calls `cognito.admin_confirm_sign_up()` to auto-confirm the user (no email verification during MVP).
5. `AuthService` calls `cognito.initiate_auth()` with `USER_PASSWORD_AUTH` to obtain tokens (`IdToken`, `RefreshToken`, `AccessToken`).
6. The `IdToken` is decoded (without JWKS verification, since it was just obtained from Cognito) using `jose.jwt.get_unverified_claims()` to extract the `sub` claim (UUID).
7. A `Profile` row is created with `id = sub`, `mem0_user_id = "user_{sub}"`, `subscription_tier = "free"`, `onboarding_completed = false`.
8. A default `Character` row is created with `name = "Ember"`, `template = "companion"`, `is_default = true`, `mem0_agent_id = "companion_{sub}"`, and the `DEFAULT_COMPANION_PROMPT` with the user's name substituted.
9. A `Conversation` row is created linking the user and the default character.
10. All three DB rows are committed in a single transaction.
11. The response `201 Created` includes the `IdToken` (as `token`), the `RefreshToken`, and the full `UserResponse`.

### Idempotent Registration (Cognito-DB Split-Brain Recovery)

If Cognito signup succeeds but the database transaction fails (e.g., due to a transient DB error), the next registration attempt with the same email will receive a `UsernameExistsException` from Cognito. The service handles this gracefully:

1. Catches `UsernameExistsException` from `sign_up`.
2. Attempts to authenticate the user with the provided password via `initiate_auth`.
3. If authentication succeeds and no profile exists in the database, creates the missing Profile, Character, and Conversation rows.
4. If authentication succeeds and a profile already exists, returns the existing profile (true idempotency).
5. If authentication fails (wrong password), converts the 401 to a `400 "An account with this email already exists"`.

### Login Flow

1. Client sends `POST /api/v1/auth/login` with `{ email, password }`
2. `AuthService.login()` calls `cognito.initiate_auth()` with `USER_PASSWORD_AUTH`.
3. Extracts `IdToken` and `RefreshToken` from the Cognito response.
4. Decodes the `IdToken` to extract the `sub` claim.
5. Queries the `profiles` table for a row with `id = sub`.
6. If found, returns `200 OK` with tokens and user data.
7. If not found (orphaned Cognito user), returns `401 "Invalid email or password"` -- the generic message prevents information leakage.

### Refresh Flow

1. Client sends `POST /api/v1/auth/refresh` with `{ refresh_token }`
2. `AuthService.refresh()` calls `cognito.initiate_auth()` with `REFRESH_TOKEN_AUTH`.
3. Extracts the new `IdToken` from the Cognito response.
4. Returns `200 OK` with `{ token }`. No new refresh token is issued -- Cognito's `REFRESH_TOKEN_AUTH` flow reuses the existing refresh token (valid for 30 days).

### Async Handling of boto3

The `boto3` Cognito client is synchronous. All Cognito API calls are wrapped with `asyncio.to_thread()` to run in a thread pool worker, preventing the FastAPI async event loop from being blocked. This is a standard-library approach preferred over third-party async wrappers.

The Cognito client is lazily initialized on first use via a `@property` on `AuthService`. Subsequent calls within the same request reuse the same client instance.

### Mem0 Memory Integration

During registration, Mem0 identifiers are assigned but no Mem0 API calls are made:

- **`mem0_user_id`**: `"user_{cognito_sub}"` -- stored on the `profiles` row. Used for all future Mem0 calls involving this user.
- **`mem0_agent_id`**: `"companion_{cognito_sub}"` -- stored on the default character row. Follows the `{template}_{user_id}` pattern from the Ember memory architecture.
- Mem0 creates user records lazily on the first `add()` or `search()` call, so no explicit initialization is needed.

### Database Tables Involved

| Table | Operation | Notes |
|-------|-----------|-------|
| `profiles` | INSERT (register), SELECT (login) | Profile `id` is set to the Cognito `sub` UUID |
| `characters` | INSERT (register) | Default "Ember" character with `template="companion"`, `is_default=true` |
| `conversations` | INSERT (register) | Auto-conversation linked to the default character |

All three INSERT operations during registration are committed in a single transaction. If any row fails, the entire transaction rolls back (though the Cognito user will still exist -- see the idempotent recovery section above).

---

## API Reference

All three endpoints are under `/api/v1/auth` and are public (no `Authorization` header required). For the broader API contract, see [`docs/04-veri-api.md`](../04-veri-api.md).

### POST /api/v1/auth/register

**Auth**: None (public)
**Content-Type**: `application/json`
**Success Status**: `201 Created`

**Request Body**:

```json
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "name": "Alex"
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `email` | string | yes | Valid email format (Pydantic `EmailStr`), max 320 chars, lowercased and stripped |
| `password` | string | yes | Min 8 chars (Cognito enforces its own policy on top) |
| `name` | string | yes | Min 1 char, max 100 chars, whitespace-trimmed; empty-after-trim is rejected |

**Response Body** (201):

```json
{
  "token": "eyJraWQiOiJ...",
  "refresh_token": "eyJjdHkiOiJ...",
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "name": "Alex",
    "onboarding_completed": false,
    "subscription_tier": "free",
    "preferred_language": "en",
    "timezone": "UTC",
    "avatar_url": null,
    "created_at": "2026-02-23T14:30:00Z"
  }
}
```

**Error Responses**:

| Status | Detail | When |
|--------|--------|------|
| 400 | `"An account with this email already exists"` | Email already registered in Cognito (and password does not match for idempotent recovery) |
| 400 | `"Password does not meet requirements"` | Password fails Cognito policy |
| 400 | `"Invalid request parameters"` | Cognito `InvalidParameterException` |
| 422 | Standard FastAPI validation error | Missing fields, invalid email format, password < 8 chars, empty name after trim |
| 429 | `"Too many requests, please try again later"` | Cognito rate limit exceeded |
| 503 | `"Authentication service unavailable"` | Cognito service error or unrecognized error |

### POST /api/v1/auth/login

**Auth**: None (public)
**Content-Type**: `application/json`
**Success Status**: `200 OK`

**Request Body**:

```json
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `email` | string | yes | Valid email format, lowercased and stripped |
| `password` | string | yes | Non-empty (min 1 char) |

**Response Body** (200): Same structure as the register response (`token`, `refresh_token`, `user`).

**Error Responses**:

| Status | Detail | When |
|--------|--------|------|
| 401 | `"Invalid email or password"` | Wrong email, wrong password, or valid Cognito user with no DB profile |
| 401 | `"User is not confirmed"` | User has not been confirmed in Cognito |
| 422 | Standard FastAPI validation error | Missing fields, invalid email format |
| 503 | `"Authentication service unavailable"` | Cognito service error |

The generic "Invalid email or password" message is used for multiple failure cases to prevent email enumeration attacks.

### POST /api/v1/auth/refresh

**Auth**: None (public)
**Content-Type**: `application/json`
**Success Status**: `200 OK`

**Request Body**:

```json
{
  "refresh_token": "eyJjdHkiOiJ..."
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `refresh_token` | string | yes | Non-empty (min 1 char) |

**Response Body** (200):

```json
{
  "token": "eyJraWQiOiJ..."
}
```

The response contains only a new ID token. No `refresh_token` is returned -- Cognito's `REFRESH_TOKEN_AUTH` flow does not issue a new refresh token. The client retains its existing refresh token (valid for 30 days).

**Error Responses**:

| Status | Detail | When |
|--------|--------|------|
| 401 | `"Invalid or expired refresh token"` | Token is invalid, expired, or revoked |
| 422 | Standard FastAPI validation error | Missing `refresh_token` field |
| 503 | `"Authentication service unavailable"` | Cognito service error |

---

## Pydantic Schemas

All schemas are in `backend/app/schemas/auth.py` and use Pydantic v2 patterns.

**Request schemas**:

- `RegisterRequest` -- validates `email` (EmailStr, lowercased), `password` (min 8 chars), `name` (1-100 chars, whitespace-trimmed, empty-after-trim rejected)
- `LoginRequest` -- validates `email` (EmailStr, lowercased), `password` (min 1 char)
- `RefreshRequest` -- validates `refresh_token` (min 1 char)

**Response schemas**:

- `UserResponse` -- maps from the `Profile` ORM object via `ConfigDict(from_attributes=True)`. The `id` field has a `field_validator("id", mode="before")` that coerces `uuid.UUID` to `str` for API output.
- `AuthResponse` -- contains `token` (str), `refresh_token` (str), `user` (UserResponse)
- `RefreshResponse` -- contains only `token` (str)

The `email-validator` package (added to `requirements.txt`) is required by Pydantic's `EmailStr` type.

---

## Configuration

No new configuration variables were introduced. The required settings already exist from P01-01:

| Variable | Type | Description |
|----------|------|-------------|
| `COGNITO_USER_POOL_ID` | str | AWS Cognito user pool ID |
| `COGNITO_APP_CLIENT_ID` | str | AWS Cognito app client ID |
| `AWS_REGION` | str | AWS region for Cognito |

**Infrastructure requirements** (not code concerns, but must be configured):

- The Cognito User Pool App Client must have `USER_PASSWORD_AUTH` enabled as an allowed auth flow.
- The ECS task IAM role must have `cognito-idp:AdminConfirmSignUp` permission (used during registration to auto-confirm users).

---

## Files

| File | Role |
|------|------|
| `backend/app/routes/auth.py` | Route handlers: `register`, `login`, `refresh`. Delegates to `AuthService`. |
| `backend/app/services/auth_service.py` | `AuthService` class with all business logic. Contains `DEFAULT_COMPANION_PROMPT`. |
| `backend/app/schemas/auth.py` | 6 Pydantic schemas: 3 request, 3 response. |
| `backend/app/main.py` | Modified to register auth router at `/api/v1/auth`. |
| `backend/requirements.txt` | Modified to add `email-validator>=2.0.0,<3.0.0`. |

### Service Layer

`AuthService` is instantiated per-request with the database session: `AuthService(db)`. The Cognito client is lazily initialized via the `cognito` property. Private helper methods handle specific concerns:

- `_cognito_sign_up`, `_cognito_admin_confirm`, `_cognito_initiate_auth_sync`, `_cognito_refresh` -- synchronous Cognito wrappers called via `asyncio.to_thread()`
- `_cognito_initiate_auth` -- async wrapper that calls `_cognito_initiate_auth_sync` and maps Cognito errors to HTTP exceptions
- `_create_profile_and_character` -- creates all three DB rows in one transaction
- `_handle_existing_cognito_user` -- idempotent recovery for the Cognito-DB split-brain case
- `_extract_sub` -- decodes the ID token without JWKS verification
- `_raise_cognito_error` -- maps Cognito error codes to HTTP exceptions

### Default Companion System Prompt

The default character's system prompt is a constant in `auth_service.py`:

```
You are {user_name}'s personal AI companion. You are a holistic life friend --
covering fitness, nutrition, work, stress, and relationships. You are warm,
honest, and genuine but never overly positive. You remember everything about
the user and get to know them better over time. Use what you know naturally --
never say 'I remember that...' -- just know it. Keep messages concise. Ask
questions when needed, don't monologue.
```

The `{user_name}` placeholder is substituted with the registering user's name via `str.format()` at character creation time. This prompt is not generated dynamically via Claude -- dynamic generation is for custom characters in a later phase.

---

## Testing

### Coverage Summary

| File | Tests | Line Coverage | Branch Coverage |
|------|-------|---------------|-----------------|
| `test_auth_routes.py` | 17 | -- | -- |
| `test_auth_routes_extended.py` | 33 | -- | -- |
| `test_auth_service.py` | 11 | -- | -- |
| `test_auth_service_extended.py` | 30 | -- | -- |
| `test_auth_schemas.py` | 13 | -- | -- |
| `test_auth_schemas_extended.py` | 47 | -- | -- |
| **Total** | **151** | **100%** (186/186 statements) | **100%** (24/24 branches) |

All 30 test scenarios from the feature spec are covered. An additional 80+ scenarios were added by the tester covering edge cases, boundary values, idempotent recovery paths, error code mappings, and response schema validation.

### Test Approach

- **Route tests**: Use the FastAPI test client (`httpx.AsyncClient`). Cognito is mocked at the service level via `unittest.mock.patch` on `boto3.client`. The `get_db` dependency is overridden to inject a mock `AsyncSession`.
- **Service tests**: Unit-test `AuthService` directly. Both Cognito (via a `MagicMock`) and the database session (via `AsyncMock`) are mocked. Cognito exceptions are simulated using `botocore.exceptions.ClientError` with appropriate error codes.
- **Schema tests**: Validate Pydantic request/response schemas directly -- email normalization, name trimming, boundary values, ORM-to-response mapping, UUID-to-string coercion.

### Running Tests

Auth tests only:

```bash
backend/.venv/bin/python -m pytest backend/tests/test_auth_routes.py backend/tests/test_auth_routes_extended.py backend/tests/test_auth_service.py backend/tests/test_auth_service_extended.py backend/tests/test_auth_schemas.py backend/tests/test_auth_schemas_extended.py -v
```

Full backend suite:

```bash
backend/.venv/bin/python -m pytest backend/tests/ -v --ignore=backend/tests/test_migration.py
```

Code quality:

```bash
ruff check backend/app/routes/auth.py backend/app/services/auth_service.py backend/app/schemas/auth.py
```

---

## Known Limitations

- **No email verification**: Users are auto-confirmed via `admin_confirm_sign_up` during registration. In production, this may be replaced by a Cognito pre-sign-up Lambda trigger or a proper email verification flow (planned for Phase 2).
- **No forgot-password or reset-password**: These are Phase 2 features, not implemented here.
- **No social login**: Google and Apple sign-in are Phase 4 features.
- **Cognito-DB partial failure**: If Cognito signup succeeds but the database transaction fails, the Cognito user exists without a profile. The idempotent recovery mechanism handles this on the next registration attempt with the same email and password. If the user tries a different password, they see "An account with this email already exists" and must use the original password.
- **No onboarding memories**: Registration does not create any Mem0 memories. Mem0 identifiers are assigned, but actual memory creation happens during the onboarding flow (a separate feature).
- **Refresh does not return a new refresh token**: This is Cognito's behavior, not a limitation of the implementation. Clients must retain their original refresh token (valid for 30 days).

---

## Design Decisions

### Why auto-confirm via `admin_confirm_sign_up`

During MVP, email verification adds friction without critical value. Auto-confirming allows immediate login after registration, which is the expected mobile app experience. The `admin_confirm_sign_up` call requires IAM permissions on the ECS task role. In production, this can be replaced by a Cognito pre-sign-up Lambda trigger.

### Why `USER_PASSWORD_AUTH` (not SRP)

The backend communicates with Cognito over HTTPS on AWS-internal networking. SRP (Secure Remote Password) is designed for client-side SDKs where the password must never leave the device. Since the password is sent to the backend over HTTPS and then forwarded to Cognito over HTTPS, `USER_PASSWORD_AUTH` is sufficient and simpler.

### Why a single transaction for Profile + Character + Conversation

The user expects to see the default character immediately after registration. If character or conversation creation failed independently, the user would see an empty app. A single transaction ensures atomicity.

### Why generic login error messages

Both "wrong email" and "wrong password" return `"Invalid email or password"`. This prevents email enumeration attacks where an attacker could discover which emails have accounts by observing different error messages.

### Why `asyncio.to_thread()` instead of `aioboto3`

`asyncio.to_thread()` is a standard-library solution that works with any synchronous code. `aioboto3` is a third-party wrapper with limited maintenance. The standard-library approach is more reliable and easier to understand.

### Why the default character is named "Ember"

The default companion character matches the app name to reinforce brand identity. Users can rename it later via character settings.

### Why `mem0_user_id` is `"user_{sub}"` (not just `"{sub}"`)

The `"user_"` prefix distinguishes Mem0 user identifiers from agent IDs and memory IDs, preventing potential collisions and making logs easier to read.

---

## Extending This Feature

To add a new auth endpoint (e.g., forgot-password), create a new method on `AuthService` in `backend/app/services/auth_service.py`, add request/response schemas in `backend/app/schemas/auth.py`, and add a route handler in `backend/app/routes/auth.py`. The router is already registered at `/api/v1/auth` in `main.py`, so the new route will be available automatically.

To replace auto-confirm with email verification, remove the `_cognito_admin_confirm` call from `AuthService.register()` and implement a `POST /api/v1/auth/confirm` endpoint that calls `cognito.confirm_sign_up()` with the verification code. Alternatively, configure a Cognito pre-sign-up Lambda trigger that auto-confirms users based on custom logic.

To add social login (Google, Apple), add new Cognito Identity Provider configurations and implement endpoints that handle the federated auth flow. The `AuthResponse` schema can be reused since the response format is the same.

To change the default character name or system prompt, modify the `DEFAULT_COMPANION_PROMPT` constant and the character creation logic in `_create_profile_and_character()` within `backend/app/services/auth_service.py`.

---

## Related Documentation

- [Cognito Auth Middleware](./cognito-auth-middleware.md) -- JWT verification used by protected endpoints (this feature creates tokens; the middleware verifies them)
- [Database Schema](./database-schema.md) -- the `profiles`, `characters`, and `conversations` tables written during registration
- [Project Setup](./project-setup.md) -- the FastAPI scaffold this feature builds on
- [Database Schema and API Endpoints](../04-veri-api.md) -- authoritative source for table definitions and API contracts
- [AI Memory System](../05-ai-bellek.md) -- Mem0 integration patterns and the `agent_id` format
- [Security and Performance](../08-guvenlik-performans.md) -- JWT strategy, token lifetimes, rate limiting
