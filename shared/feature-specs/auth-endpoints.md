# Feature Spec: P01-04 -- Auth Endpoints

**Feature ID**: P01-04
**Phase**: 1
**Layer**: backend
**GitHub Issue**: #6
**Date**: 2026-02-23
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature implements three public authentication endpoints for the Ember backend:

1. **POST /api/v1/auth/register** -- Creates a new user in AWS Cognito, creates a `profiles` row in the database, initializes a Mem0 user, creates a default "General Friend" character with the `companion` template, creates the corresponding auto-conversation for that character, and returns tokens plus user data.

2. **POST /api/v1/auth/login** -- Authenticates an existing user against AWS Cognito using `USER_PASSWORD_AUTH` flow, looks up the profile in the database, and returns tokens plus user data.

3. **POST /api/v1/auth/refresh** -- Exchanges a Cognito refresh token for a new access (ID) token.

All three endpoints are **public** (no JWT required). The register and login endpoints return the Cognito ID token (which Ember uses as its access token), a refresh token, and the user profile. The refresh endpoint returns only a new ID token.

### Why It Exists

Without these endpoints, no user can create an account, sign in, or refresh their session. This is the entry point for every user in the Ember application. The register flow is particularly important because it bootstraps the user's entire environment: database profile, Mem0 memory space, and the default character that every user starts with.

### Dependencies

- **Requires**: P01-01 (project-setup -- FastAPI scaffold, config, health endpoint)
- **Requires**: P01-02 (database-schema -- Profile, Character, Conversation models)
- **Requires**: P01-03 (cognito-auth-middleware -- `verify_cognito_token`, `get_current_user`)
- **Blocks**: All subsequent features that require an authenticated user

### What This Feature Does NOT Do

- It does not implement email verification flows. Cognito handles verification emails if configured.
- It does not implement forgot-password or reset-password. Those are Phase 2 features.
- It does not implement social login (Google, Apple). Those are Phase 4 features.
- It does not generate dynamic system prompts via Claude. The default companion character uses a hardcoded template prompt. Dynamic prompt generation (via Claude Haiku) is a separate feature for custom characters.
- It does not create onboarding memories in Mem0. Onboarding is a separate feature that runs after the first login.

---

## 2. Data Models

### No New Tables

This feature does not create or modify any database tables. It writes to three existing tables defined in P01-02 (documented in `docs/04-veri-api.md`):

- **profiles** -- A new row is inserted during registration with the Cognito `sub` as the primary key.
- **characters** -- A new row is inserted for the default "General Friend" character with `template="companion"` and `is_default=true`.
- **conversations** -- A new row is inserted for the auto-conversation linked to the default character.

### Key Column References

| Table | Column | Usage in This Feature |
|-------|--------|----------------------|
| `profiles.id` | UUID PK | Set to the Cognito `sub` UUID returned by `sign_up` |
| `profiles.email` | TEXT UNIQUE | Set from the registration request body |
| `profiles.name` | TEXT | Set from the registration request body |
| `profiles.mem0_user_id` | TEXT UNIQUE | Set to `"user_{cognito_sub}"` during registration |
| `characters.user_id` | UUID FK | Points to the new profile |
| `characters.template` | TEXT | Set to `"companion"` for the default character |
| `characters.mem0_agent_id` | TEXT UNIQUE | Set to `"companion_{cognito_sub}"` |
| `characters.is_default` | BOOLEAN | Set to `true` for the default character |
| `characters.system_prompt` | TEXT | Set to the hardcoded companion template prompt |
| `conversations.character_id` | UUID FK UNIQUE | Points to the default character |
| `conversations.user_id` | UUID FK | Points to the new profile |

### Mem0 Operations

During registration, a Mem0 user is initialized. No memories are added at this stage -- that happens during onboarding and conversations.

- **Mem0 user_id**: `"user_{cognito_sub}"` -- this is stored in `profiles.mem0_user_id`.
- **Mem0 agent_id** for the default character: `"companion_{cognito_sub}"` -- this follows the `{template}_{user_id}` pattern from `docs/05-ai-bellek.md`.

The actual Mem0 "user creation" is implicit. Mem0 creates user records lazily on the first `add()` or `search()` call. The registration flow does NOT need to make an explicit Mem0 API call to create the user. The `mem0_user_id` stored in the profile is simply the identifier that will be passed to all future Mem0 calls.

---

## 3. API Endpoints

All endpoints are under the `/api/v1` prefix. All three are **public** (no `Authorization` header required).

---

### POST /api/v1/auth/register

Creates a new user account.

```
Auth: None (public endpoint)
Content-Type: application/json
```

**Request Body:**

```json
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "name": "Alex"
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `email` | string | yes | Valid email format, max 320 chars |
| `password` | string | yes | Min 8 chars (Cognito enforces its own policy on top) |
| `name` | string | yes | Min 1 char, max 100 chars, whitespace-trimmed |

**Response 201 Created:**

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

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 400 | Email already registered in Cognito | `{"detail": "An account with this email already exists"}` |
| 400 | Password does not meet Cognito policy | `{"detail": "Password does not meet requirements"}` |
| 422 | Pydantic validation failure (missing fields, invalid email format) | Standard FastAPI 422 response |
| 503 | Cognito service unavailable | `{"detail": "Authentication service unavailable"}` |

---

### POST /api/v1/auth/login

Authenticates an existing user.

```
Auth: None (public endpoint)
Content-Type: application/json
```

**Request Body:**

```json
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `email` | string | yes | Valid email format |
| `password` | string | yes | Non-empty |

**Response 200 OK:**

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

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 401 | Wrong email or password | `{"detail": "Invalid email or password"}` |
| 401 | User not confirmed in Cognito | `{"detail": "User is not confirmed"}` |
| 401 | Profile not found in database (orphaned Cognito user) | `{"detail": "Invalid email or password"}` |
| 422 | Pydantic validation failure | Standard FastAPI 422 response |
| 503 | Cognito service unavailable | `{"detail": "Authentication service unavailable"}` |

**Security note**: The "Invalid email or password" message is intentionally generic for both wrong-email and wrong-password cases. This prevents email enumeration attacks. The "Profile not found" case also uses the same generic message.

---

### POST /api/v1/auth/refresh

Refreshes an expired access token.

```
Auth: None (public endpoint)
Content-Type: application/json
```

**Request Body:**

```json
{
  "refresh_token": "eyJjdHkiOiJ..."
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `refresh_token` | string | yes | Non-empty |

**Response 200 OK:**

```json
{
  "token": "eyJraWQiOiJ..."
}
```

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 401 | Refresh token is invalid or expired | `{"detail": "Invalid or expired refresh token"}` |
| 422 | Pydantic validation failure | Standard FastAPI 422 response |
| 503 | Cognito service unavailable | `{"detail": "Authentication service unavailable"}` |

**Note**: The refresh endpoint does NOT return `refresh_token` in the response. Cognito's `REFRESH_TOKEN_AUTH` flow returns a new ID token and access token but does NOT issue a new refresh token. The client retains its existing refresh token (valid for 30 days per `docs/08-guvenlik-performans.md`).

---

## 4. Backend Logic

### Registration Flow (Step-by-Step)

```
Client sends: POST /api/v1/auth/register
    { email, password, name }
         |
         v
    1. Validate request body (Pydantic)
         |
         v
    2. Call Cognito sign_up(email, password)
         |
         +--> UsernameExistsException → 400 "An account with this email already exists"
         +--> InvalidPasswordException → 400 "Password does not meet requirements"
         +--> ClientError (other) → 503 "Authentication service unavailable"
         |
         v
    3. Call Cognito admin_confirm_sign_up(username=email)
         |   (Auto-confirm the user so they can log in immediately.
         |    In production, this may be replaced by email verification
         |    via a Cognito pre-sign-up Lambda trigger.)
         |
         v
    4. Call Cognito initiate_auth(USER_PASSWORD_AUTH, email, password)
         |   Returns: IdToken, RefreshToken, AccessToken
         |   (We use IdToken as Ember's "access token")
         |
         v
    5. Decode the IdToken to extract the Cognito `sub` (UUID)
         |   Use jose.jwt.get_unverified_claims() — we trust this token
         |   because we just obtained it directly from Cognito.
         |
         v
    6. Build mem0_user_id = f"user_{sub}"
       Build mem0_agent_id = f"companion_{sub}"
         |
         v
    7. Create Profile row:
         id = sub (UUID)
         email = request.email
         name = request.name
         mem0_user_id = mem0_user_id
         timezone = "UTC" (default)
         preferred_language = "en" (default)
         onboarding_completed = false
         subscription_tier = "free"
         |
         v
    8. Create default Character row:
         id = uuid4()
         user_id = sub
         name = "Ember"
         template = "companion"
         description = null
         system_prompt = DEFAULT_COMPANION_PROMPT (hardcoded constant)
         mem0_agent_id = mem0_agent_id
         avatar_style = "default"
         is_default = true
         is_active = true
         |
         v
    9. Create Conversation row:
         id = uuid4()
         user_id = sub
         character_id = character.id
         last_message_at = null
         |
         v
   10. Commit all DB writes in a single transaction
         |
         v
   11. Return 201 { token: IdToken, refresh_token: RefreshToken, user: UserResponse }
```

**Important**: Steps 7-9 are all part of a single database transaction. If any step fails, the entire transaction rolls back. However, the Cognito user (steps 2-3) has already been created. The service must handle this partial-failure scenario:

- If DB insertion fails after Cognito signup, the Cognito user exists but has no profile. On the next login attempt, the backend will not find a profile and return 401 "Invalid email or password". The user can try registering again, which will get a "email already exists" error from Cognito. To handle this gracefully, the register flow should check if a Cognito user already exists but has no profile, and if so, proceed from step 4 (authenticate and create the profile). This is a known edge case.
- **Recommended approach**: Catch the `UsernameExistsException` in step 2. When caught, attempt to authenticate (step 4). If authentication succeeds and no profile exists in the DB, proceed with steps 5-10 to create the profile and character. If authentication fails (wrong password), return 400 "An account with this email already exists". This makes registration idempotent for the case where Cognito signup succeeded but DB creation failed.

### Login Flow (Step-by-Step)

```
Client sends: POST /api/v1/auth/login
    { email, password }
         |
         v
    1. Validate request body (Pydantic)
         |
         v
    2. Call Cognito initiate_auth(USER_PASSWORD_AUTH, email, password)
         |
         +--> NotAuthorizedException → 401 "Invalid email or password"
         +--> UserNotConfirmedException → 401 "User is not confirmed"
         +--> ClientError (other) → 503 "Authentication service unavailable"
         |
         v
    3. Extract IdToken, RefreshToken from Cognito response
         |
         v
    4. Decode the IdToken to extract the Cognito `sub` (UUID)
         |
         v
    5. Look up Profile by id = sub
         |
         +--> Not found → 401 "Invalid email or password"
         |       (Generic message to prevent information leakage)
         |
         v
    6. Return 200 { token: IdToken, refresh_token: RefreshToken, user: UserResponse }
```

### Refresh Flow (Step-by-Step)

```
Client sends: POST /api/v1/auth/refresh
    { refresh_token }
         |
         v
    1. Validate request body (Pydantic)
         |
         v
    2. Call Cognito initiate_auth(REFRESH_TOKEN_AUTH, refresh_token)
         |
         +--> NotAuthorizedException → 401 "Invalid or expired refresh token"
         +--> ClientError (other) → 503 "Authentication service unavailable"
         |
         v
    3. Extract new IdToken from Cognito response
         |
         v
    4. Return 200 { token: IdToken }
```

### Service Layer Design

#### AuthService Class

The `AuthService` class in `backend/app/services/auth_service.py` encapsulates all authentication business logic. Route handlers delegate to this service; they do not contain business logic themselves.

```
class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._cognito_client = None  # Lazy-initialized boto3 client

    @property
    def cognito(self) -> CognitoIdentityProviderClient:
        """Lazy-initialize the boto3 Cognito client."""
        if self._cognito_client is None:
            self._cognito_client = boto3.client(
                "cognito-idp",
                region_name=settings.aws_region,
            )
        return self._cognito_client

    async def register(self, email: str, password: str, name: str) -> AuthResponse:
        """Register a new user: Cognito signup + DB profile + default character."""

    async def login(self, email: str, password: str) -> AuthResponse:
        """Authenticate user via Cognito and return tokens + profile."""

    async def refresh(self, refresh_token: str) -> RefreshResponse:
        """Refresh an access token via Cognito."""
```

**Why boto3 sync client in async service**: The `boto3` Cognito IDP client is synchronous. Since all Cognito API calls are I/O-bound (network calls to AWS), they must be wrapped with `asyncio.to_thread()` to avoid blocking the event loop:

```python
result = await asyncio.to_thread(
    self.cognito.sign_up,
    ClientId=settings.cognito_app_client_id,
    Username=email,
    Password=password,
    UserAttributes=[{"Name": "email", "Value": email}],
)
```

All three Cognito calls (`sign_up`, `admin_confirm_sign_up`, `initiate_auth`) must use `asyncio.to_thread()`.

#### Default Companion System Prompt

The default companion character's system prompt is a constant defined in the auth service module (or a separate constants file). It is NOT generated dynamically via Claude. Dynamic generation is for custom characters in a future feature.

```
DEFAULT_COMPANION_PROMPT = (
    "You are {user_name}'s personal AI companion. "
    "You are a holistic life friend -- covering fitness, nutrition, work, stress, and relationships. "
    "You are warm, honest, and genuine but never overly positive. "
    "You remember everything about the user and get to know them better over time. "
    "Use what you know naturally -- never say 'I remember that...' -- just know it. "
    "Keep messages concise. Ask questions when needed, don't monologue."
)
```

The `{user_name}` placeholder is replaced with the user's `name` at character creation time.

#### Cognito API Details

The following Cognito Identity Provider API calls are used:

**sign_up** (registration step 2):
```python
cognito.sign_up(
    ClientId=settings.cognito_app_client_id,
    Username=email,        # Cognito username = email
    Password=password,
    UserAttributes=[
        {"Name": "email", "Value": email},
        {"Name": "name", "Value": name},
    ],
)
```

**admin_confirm_sign_up** (registration step 3):
```python
cognito.admin_confirm_sign_up(
    UserPoolId=settings.cognito_user_pool_id,
    Username=email,
)
```

This requires the backend's IAM role to have `cognito-idp:AdminConfirmSignUp` permission. This is acceptable because:
- The backend runs on ECS Fargate with an IAM task role.
- Auto-confirming during development simplifies the flow. In production, a Cognito pre-sign-up Lambda trigger can replace this.

**initiate_auth** (login and registration step 4):
```python
cognito.initiate_auth(
    ClientId=settings.cognito_app_client_id,
    AuthFlow="USER_PASSWORD_AUTH",
    AuthParameters={
        "USERNAME": email,
        "PASSWORD": password,
    },
)
```

Returns `AuthenticationResult` containing `IdToken`, `AccessToken`, `RefreshToken`, `ExpiresIn`.

**initiate_auth** (refresh):
```python
cognito.initiate_auth(
    ClientId=settings.cognito_app_client_id,
    AuthFlow="REFRESH_TOKEN_AUTH",
    AuthParameters={
        "REFRESH_TOKEN": refresh_token,
    },
)
```

Returns `AuthenticationResult` containing `IdToken`, `AccessToken`, `ExpiresIn` (no new `RefreshToken`).

**Important**: `USER_PASSWORD_AUTH` must be enabled in the Cognito User Pool App Client configuration. This is an infrastructure concern, not a code concern, but the developer should document this requirement.

### Error Handling

All Cognito exceptions from `botocore.exceptions.ClientError` are caught and mapped to appropriate HTTP responses. The service MUST NOT expose raw AWS error messages to the client.

| Cognito Exception Code | HTTP Status | Response Detail |
|------------------------|-------------|-----------------|
| `UsernameExistsException` | 400 | "An account with this email already exists" |
| `InvalidPasswordException` | 400 | "Password does not meet requirements" |
| `InvalidParameterException` | 400 | "Invalid request parameters" |
| `NotAuthorizedException` | 401 | "Invalid email or password" (login) or "Invalid or expired refresh token" (refresh) |
| `UserNotConfirmedException` | 401 | "User is not confirmed" |
| `UserNotFoundException` | 401 | "Invalid email or password" |
| `TooManyRequestsException` | 429 | "Too many requests, please try again later" |
| Any other `ClientError` | 503 | "Authentication service unavailable" |

The error handling pattern:

```python
try:
    result = await asyncio.to_thread(self.cognito.sign_up, ...)
except self.cognito.exceptions.UsernameExistsException:
    raise HTTPException(status_code=400, detail="An account with this email already exists")
except ClientError as e:
    code = e.response["Error"]["Code"]
    # Map code to HTTP status and detail
    ...
```

Note: `boto3` client exceptions are accessed via `client.exceptions.ExceptionName`, but `botocore.exceptions.ClientError` is the base class. The service should catch `ClientError` as the fallback after catching specific named exceptions.

---

## 5. Pydantic Schemas

All schemas use Pydantic v2 patterns from `docs/standards/backend.md` Section 4.

### Request Schemas

```
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower().strip()
```

```
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower().strip()
```

```
class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)
```

### Response Schemas

```
class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str                        # UUID as string
    email: str
    name: str
    onboarding_completed: bool
    subscription_tier: str
    preferred_language: str
    timezone: str
    avatar_url: str | None
    created_at: datetime
```

```
class AuthResponse(BaseModel):
    token: str                     # Cognito ID token
    refresh_token: str             # Cognito refresh token
    user: UserResponse
```

```
class RefreshResponse(BaseModel):
    token: str                     # New Cognito ID token
```

### Notes

- `EmailStr` requires the `email-validator` package. It must be added to `requirements.txt`.
- The `UserResponse.id` field is `str` (not `UUID`) because all IDs in Ember API responses are UUID strings per `docs/standards/common.md` Section 5.
- `from_attributes=True` allows constructing `UserResponse` directly from the `Profile` ORM object.
- The `created_at` field serializes as ISO 8601 UTC automatically via Pydantic v2.

---

## 6. Test Requirements

### Route Tests (`backend/tests/test_auth_routes.py`)

These tests use the FastAPI test client. Cognito calls are mocked at the service level.

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Register with valid email/password/name | 201, response contains `token`, `refresh_token`, and `user` with correct fields |
| 2 | Register with email that already exists in Cognito | 400, detail = "An account with this email already exists" |
| 3 | Register with password that fails Cognito policy | 400, detail = "Password does not meet requirements" |
| 4 | Register with missing email field | 422 (Pydantic validation) |
| 5 | Register with missing name field | 422 (Pydantic validation) |
| 6 | Register with invalid email format | 422 (Pydantic validation) |
| 7 | Register with password shorter than 8 chars | 422 (Pydantic validation) |
| 8 | Register with name that is only whitespace | 422 (after strip, name is empty, fails min_length=1) |
| 9 | Login with valid credentials | 200, response contains `token`, `refresh_token`, and `user` |
| 10 | Login with wrong password | 401, detail = "Invalid email or password" |
| 11 | Login with non-existent email | 401, detail = "Invalid email or password" |
| 12 | Login when Cognito returns UserNotConfirmedException | 401, detail = "User is not confirmed" |
| 13 | Login with valid Cognito auth but no profile in DB | 401, detail = "Invalid email or password" |
| 14 | Refresh with valid refresh token | 200, response contains `token` |
| 15 | Refresh with invalid/expired refresh token | 401, detail = "Invalid or expired refresh token" |
| 16 | Refresh with missing refresh_token field | 422 (Pydantic validation) |
| 17 | Register when Cognito is unavailable | 503, detail = "Authentication service unavailable" |

### Service Tests (`backend/tests/test_auth_service.py`)

These tests unit-test the `AuthService` class directly. Both Cognito (boto3) and the database session are mocked.

| # | Scenario | Expected |
|---|----------|----------|
| 18 | `register()` calls Cognito sign_up, admin_confirm_sign_up, initiate_auth in order | Three Cognito calls made in the correct sequence |
| 19 | `register()` creates Profile, Character (is_default=true, template=companion), and Conversation | All three rows added to the session; session.commit() called once |
| 20 | `register()` sets mem0_user_id to `"user_{sub}"` and mem0_agent_id to `"companion_{sub}"` | Profile and Character have correct Mem0 identifiers |
| 21 | `register()` sets character name to "Ember" and system_prompt to the companion template with user's name substituted | Character fields match expected values |
| 22 | `login()` calls Cognito initiate_auth then queries Profile by sub | Cognito called once; DB queried once |
| 23 | `login()` returns None/raises when no profile found in DB | Appropriate error raised |
| 24 | `refresh()` calls Cognito initiate_auth with REFRESH_TOKEN_AUTH | Cognito called with correct AuthFlow |
| 25 | All Cognito calls use `asyncio.to_thread` | Verify calls are wrapped (or mock correctly handles async) |

### Schema Tests (`backend/tests/test_auth_schemas.py`)

| # | Scenario | Expected |
|---|----------|----------|
| 26 | `RegisterRequest` strips whitespace from name | Leading/trailing spaces removed |
| 27 | `RegisterRequest` lowercases email | Uppercase letters converted to lowercase |
| 28 | `RegisterRequest` rejects name that is only spaces (after strip) | ValidationError |
| 29 | `LoginRequest` lowercases email | Uppercase letters converted to lowercase |
| 30 | `UserResponse.model_validate` from Profile ORM object | All fields correctly mapped |

### How to Mock Cognito

Use `unittest.mock.patch` to mock the boto3 Cognito client. The service lazily initializes the client, so patching can target the service instance's `_cognito_client` attribute or the `boto3.client` factory.

Recommended approach:

```python
from unittest.mock import MagicMock, patch, AsyncMock

mock_cognito = MagicMock()
mock_cognito.sign_up.return_value = {"UserSub": "test-uuid-123"}
mock_cognito.admin_confirm_sign_up.return_value = {}
mock_cognito.initiate_auth.return_value = {
    "AuthenticationResult": {
        "IdToken": "fake-id-token",
        "RefreshToken": "fake-refresh-token",
        "AccessToken": "fake-access-token",
        "ExpiresIn": 3600,
    }
}

# Patch boto3.client to return mock_cognito
with patch("boto3.client", return_value=mock_cognito):
    service = AuthService(db=mock_db)
    result = await service.register(email="test@ember.ai", password="Pass1234!", name="Test")
```

For testing Cognito exceptions:

```python
from botocore.exceptions import ClientError

mock_cognito.sign_up.side_effect = ClientError(
    {"Error": {"Code": "UsernameExistsException", "Message": "User already exists"}},
    "SignUp"
)
```

### How to Mock the Database

Use an `AsyncMock` for the `AsyncSession`. The register flow calls `db.add()`, `db.commit()`, and `db.refresh()`. The login flow calls `db.execute()` with a `select()` statement.

For route-level tests, override the `get_db` dependency to yield a mock session. For service-level tests, pass a mock session directly to `AuthService(db=mock_db)`.

### Code Quality Checks

```bash
ruff check backend/app/routes/auth.py backend/app/services/auth_service.py backend/app/schemas/auth.py
mypy backend/app/routes/auth.py backend/app/services/auth_service.py backend/app/schemas/auth.py
pytest backend/tests/test_auth_routes.py backend/tests/test_auth_service.py backend/tests/test_auth_schemas.py -v
```

---

## 7. File Manifest

Every file to be created or modified, grouped by purpose.

### Route Handler

```
Backend:
  CREATE  backend/app/routes/auth.py
```

Contains the three route functions (`register`, `login`, `refresh`). Each delegates to `AuthService`. No business logic in the route handlers.

### Service Layer

```
Backend:
  CREATE  backend/app/services/auth_service.py
```

Contains the `AuthService` class with `register()`, `login()`, and `refresh()` methods. Contains the `DEFAULT_COMPANION_PROMPT` constant.

### Pydantic Schemas

```
Backend:
  CREATE  backend/app/schemas/auth.py
```

Contains `RegisterRequest`, `LoginRequest`, `RefreshRequest`, `UserResponse`, `AuthResponse`, `RefreshResponse`.

### Application Wiring

```
Backend:
  MODIFY  backend/app/main.py
```

Add `from app.routes import auth` and register the auth router:
```python
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
```

### Dependencies

```
Backend:
  MODIFY  backend/requirements.txt
```

Add `email-validator>=2.0.0,<3.0.0` (required by Pydantic `EmailStr`).

### Tests

```
Backend:
  CREATE  backend/tests/test_auth_routes.py
  CREATE  backend/tests/test_auth_service.py
  CREATE  backend/tests/test_auth_schemas.py
```

### Documentation (Pipeline)

```
Shared:
  CREATE  shared/feature-specs/auth-endpoints.md          (this file)
  CREATE  docs/pipeline/auth-endpoints-architect.handoff.md
```

### Summary

| Action | Count |
|--------|-------|
| CREATE | 6 |
| MODIFY | 2 |
| DELETE | 0 |
| **Total** | **8** |

### Files NOT Modified

- `backend/app/config.py` -- Already has `cognito_user_pool_id`, `cognito_app_client_id`, `aws_region`. No changes needed.
- `backend/app/dependencies.py` -- The auth routes are public (no `get_current_user`). No changes needed.
- `backend/app/core/auth.py` -- The existing JWT verification is used only by `get_current_user` for protected endpoints. The auth routes do not call `verify_cognito_token` (they obtain tokens from Cognito directly, not verify them).
- `backend/app/models/` -- No model changes. Existing models from P01-02 are used as-is.
- `backend/app/schemas/__init__.py` -- If the developer follows the pattern from P01-01 where `health.py` is imported directly in the route, no change to `__init__.py` is needed. If the developer prefers re-exporting from `__init__.py`, that is also acceptable.
- `backend/.env.example` -- Already has `COGNITO_USER_POOL_ID` and `COGNITO_APP_CLIENT_ID`.

---

## 8. Acceptance Criteria

1. Given a valid email, password, and name, when a client sends `POST /api/v1/auth/register`, then the response is HTTP 201 with body containing `token` (non-empty string), `refresh_token` (non-empty string), and `user` object with `id`, `email`, `name`, `onboarding_completed` (false), `subscription_tier` ("free"), `preferred_language` ("en"), `timezone` ("UTC"), `avatar_url` (null), and `created_at` (ISO 8601 string).

2. Given a successful registration, when the database is inspected, then a `profiles` row exists with `id` equal to the Cognito `sub`, `email` equal to the request email (lowercased), `name` equal to the request name (trimmed), and `mem0_user_id` equal to `"user_{sub}"`.

3. Given a successful registration, when the database is inspected, then a `characters` row exists with `user_id` equal to the Cognito `sub`, `template` equal to `"companion"`, `is_default` equal to `true`, `name` equal to `"Ember"`, `mem0_agent_id` matching the pattern `"companion_{sub}"`, and `system_prompt` containing the companion template text with the user's name.

4. Given a successful registration, when the database is inspected, then a `conversations` row exists with `user_id` equal to the Cognito `sub`, `character_id` equal to the default character's `id`, and `last_message_at` equal to `null`.

5. Given an email that is already registered in Cognito, when a client sends `POST /api/v1/auth/register` with that email, then the response is HTTP 400 with detail "An account with this email already exists".

6. Given a password that does not meet Cognito's password policy, when a client sends `POST /api/v1/auth/register`, then the response is HTTP 400 with detail "Password does not meet requirements".

7. Given valid login credentials, when a client sends `POST /api/v1/auth/login`, then the response is HTTP 200 with body containing `token`, `refresh_token`, and `user` with the correct profile data.

8. Given an incorrect password, when a client sends `POST /api/v1/auth/login`, then the response is HTTP 401 with detail "Invalid email or password".

9. Given a non-existent email, when a client sends `POST /api/v1/auth/login`, then the response is HTTP 401 with detail "Invalid email or password".

10. Given a valid refresh token, when a client sends `POST /api/v1/auth/refresh`, then the response is HTTP 200 with body containing `token` (a new ID token) and no `refresh_token` field.

11. Given an expired or invalid refresh token, when a client sends `POST /api/v1/auth/refresh`, then the response is HTTP 401 with detail "Invalid or expired refresh token".

12. Given any auth endpoint, when the request body fails Pydantic validation (missing fields, invalid email format, password too short), then the response is HTTP 422 with standard FastAPI validation error format.

13. Given the register route handler, when a developer inspects the code, then all business logic is in `AuthService` and the route handler only calls service methods, validates input (Pydantic), and returns responses.

14. Given all Cognito API calls in `AuthService`, when a developer inspects the code, then every call is wrapped with `asyncio.to_thread()` to avoid blocking the async event loop.

15. Given the `email` field in both `RegisterRequest` and `LoginRequest`, when any email is submitted, then it is lowercased and stripped of whitespace before being sent to Cognito.

16. Given the `name` field in `RegisterRequest`, when a name with leading/trailing whitespace is submitted, then the whitespace is stripped before storage.

17. Given the backend source code, when a developer runs `ruff check` on all new files, then zero errors are reported.

18. Given the backend test suite, when a developer runs `pytest` on the new test files, then all tests pass with exit code 0.

19. Given the register and login response schemas, when a developer inspects the API output, then the response follows the format documented in `docs/04-veri-api.md` Section "Kimlik Dogrulama": `{ "token": "...", "refresh_token": "...", "user": { ... } }`.

20. Given the auth router registration in `main.py`, when the application starts, then the three auth endpoints are available at `/api/v1/auth/register`, `/api/v1/auth/login`, and `/api/v1/auth/refresh`.

---

## 9. Design Decisions and Rationale

### Why auto-confirm users via `admin_confirm_sign_up`

During early development and MVP, email verification adds friction without providing critical value. Auto-confirming allows immediate login after registration, which is the expected mobile app experience. In production, this can be replaced with either:
- A Cognito pre-sign-up Lambda trigger that auto-confirms.
- Removing auto-confirm and implementing an email verification flow in Phase 2.

The `admin_confirm_sign_up` call requires `AdminConfirmSignUp` IAM permissions on the ECS task role.

### Why Cognito `USER_PASSWORD_AUTH` flow (not `ALLOW_USER_SRP_AUTH`)

`USER_PASSWORD_AUTH` sends the password directly to Cognito over HTTPS. `ALLOW_USER_SRP_AUTH` uses the Secure Remote Password protocol which is more complex. Since the backend communicates with Cognito over a secure AWS-internal network and HTTPS, `USER_PASSWORD_AUTH` is sufficient and simpler to implement. SRP is typically used for client-side SDKs where the password must never leave the device.

### Why `asyncio.to_thread` for boto3 calls

The `boto3` library is synchronous. Calling it directly in an `async def` route handler would block the event loop, preventing other requests from being processed. `asyncio.to_thread()` runs the synchronous call in a thread pool worker, allowing the event loop to remain responsive. An alternative would be `aioboto3`, but it is a third-party wrapper with limited maintenance, while `asyncio.to_thread()` is a standard library solution that works with any sync code.

### Why the default character is named "Ember"

The default character is the "General Friend" with template `companion`. Its name matches the app name "Ember" to reinforce brand identity. Users can rename it later via character settings.

### Why `mem0_user_id` is `"user_{sub}"` and not just `"{sub}"`

Prefixing with `"user_"` distinguishes Mem0 user identifiers from other types of identifiers in the Mem0 system (agent IDs, memory IDs). This prevents potential collisions and makes logs easier to read.

### Why registration creates all three rows (Profile + Character + Conversation) in one transaction

The user expects to see the General Friend character immediately after registration. If the character or conversation creation fails independently, the user would see an empty app with no character to talk to. A single transaction ensures atomicity: either the entire setup succeeds or nothing is committed.

### Why login returns a generic "Invalid email or password" for both wrong email and wrong password

This prevents email enumeration attacks. If the error message distinguished between "email not found" and "wrong password", an attacker could use the register endpoint to verify which emails have accounts.

### Why refresh does not return a new refresh_token

This is a Cognito behavior, not a design choice. The `REFRESH_TOKEN_AUTH` flow returns a new ID token and access token but reuses the same refresh token (valid for 30 days per `docs/08-guvenlik-performans.md`).

---

## 10. Notes for Developers

### For backend-dev

- **Start with schemas** (`app/schemas/auth.py`), then the service (`app/services/auth_service.py`), then the route (`app/routes/auth.py`), then wire up in `main.py`. This order lets you test each layer incrementally.

- **EmailStr dependency**: Add `email-validator>=2.0.0,<3.0.0` to `requirements.txt`. Without it, Pydantic's `EmailStr` raises an import error at runtime.

- **boto3 exception handling**: Cognito exceptions are not standard Python exceptions. They are dynamically generated from the service model. Access them via `client.exceptions.UsernameExistsException` or catch the base `botocore.exceptions.ClientError` and check `e.response["Error"]["Code"]`. The recommended approach is to catch `ClientError` and dispatch on the error code string.

- **Decoding the ID token without verification**: After calling `initiate_auth`, the returned `IdToken` is trusted (it came directly from Cognito over TLS). Use `jose.jwt.get_unverified_claims(token)` to extract the `sub` claim without needing JWKS verification. This avoids a dependency on the JWKS cache for the registration flow.

- **UUID handling**: The Cognito `sub` is a UUID string like `"550e8400-e29b-41d4-a716-446655440000"`. Convert it with `uuid.UUID(sub)` before using it as the Profile `id`.

- **Transaction management**: The route handler gets a `db` session from `Depends(get_db)`. Pass this to `AuthService(db=db)`. The service calls `db.add()` for each new object (Profile, Character, Conversation) and then a single `db.commit()`. If the commit fails, SQLAlchemy automatically rolls back.

- **Router prefix**: Register the auth router with `prefix="/api/v1/auth"` in `main.py`. The route functions use relative paths: `@router.post("/register")`, `@router.post("/login")`, `@router.post("/refresh")`.

- **No auth dependency**: None of the three auth routes use `Depends(get_current_user)`. They are fully public. The router must NOT have a global dependency on `get_current_user`.

- **System prompt format**: The `DEFAULT_COMPANION_PROMPT` uses `{user_name}` as a placeholder. Use Python's `str.format(user_name=name)` to substitute the user's name at character creation time.

- **Import path for Profile**: `from app.models.profile import Profile` (the file is `profile.py`, not `user.py` -- the standards doc shows `user.py` but P01-02 implemented it as `profile.py`).

### For backend-tester

- **Mock boto3, not Cognito directly**: Patch `boto3.client` or patch the specific service instance's Cognito client. Do not make real calls to AWS.

- **Test the full route flow**: Use the FastAPI test client with mock Cognito. Override `get_db` to use a mock session (for route tests) or pass a mock session directly (for service tests).

- **Verify DB writes**: In service tests, verify that `db.add()` was called with the correct objects (check types and field values). Verify that `db.commit()` was called exactly once per successful registration.

- **Verify async wrapping**: Assert that Cognito calls go through `asyncio.to_thread`. You can mock `asyncio.to_thread` itself or verify that the mock Cognito client methods are called (which proves they were invoked, regardless of the async wrapper).

- **Test email normalization**: Register with `"Test@Example.COM"` and verify the stored email is `"test@example.com"`.

- **Test name trimming**: Register with `"  Alex  "` and verify the stored name is `"Alex"`.
