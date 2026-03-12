# Feature Spec: P1.5-02 -- Profile CRUD Endpoints

**Feature ID**: P1.5-02
**Phase**: 1.5
**Layer**: backend
**GitHub Issue**: #84
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature adds three REST endpoints for user profile management:

1. **GET /api/v1/profile** -- Returns the authenticated user's profile data.
2. **PUT /api/v1/profile** -- Updates mutable profile fields (name, timezone, avatar_url, preferred_language).
3. **DELETE /api/v1/profile/account** -- GDPR-compliant full account deletion. Removes the user's profile, all characters, conversations, messages, Mem0 memories, and S3 files. Requires explicit confirmation in the request body.

### Why It Exists

Users need to view and update their profile information (displayed in settings screens) and must have the right to delete all their data per GDPR Article 17 ("right to erasure"). The profile read/update endpoints are foundational for the mobile settings screen. Account deletion is a compliance requirement and a user trust signal.

### Dependencies

- **Requires**: P01-04 (auth-endpoints -- `get_current_user` dependency, Profile model)
- **Requires**: P01-01 (project-setup -- FastAPI scaffold, config.py)
- **Uses at runtime**: P01-02 (database-schema -- all 7 tables exist for cascade deletion)

### What This Feature Does NOT Do

- It does not handle email or password changes (those go through Cognito directly).
- It does not handle subscription management (separate billing feature).
- It does not handle FCM token updates (separate notification feature).
- It does not handle onboarding_completed flag updates (handled by P01-09 onboarding endpoint).

---

## 2. Data Models

### No New Tables

This feature does not create or alter any database tables.

### No New Columns

All required columns already exist on the `profiles` table (see `docs/04-veri-api.md`).

### Existing Columns Read

| Table | Column | Usage |
|-------|--------|-------|
| `profiles.*` | All columns | Returned by GET, updated by PUT, deleted by DELETE |
| `characters.mem0_agent_id` | Text | Collected for Mem0 memory deletion during account delete |
| `characters.user_id` | UUID FK | Filter characters for the user being deleted |

### Existing Cascade Behavior

The Profile model already has `cascade="all, delete-orphan"` on characters and conversations relationships. Foreign keys on `characters.user_id`, `conversations.user_id`, and `messages.user_id` all have `ondelete="CASCADE"`. Deleting the Profile row cascades to all related DB rows automatically.

### No New Indexes

Existing indexes are sufficient:
- `profiles.id` (PK) for GET/PUT lookups.
- `idx_characters_user_active` for listing characters during account deletion.

### No Mem0 Schema Changes

Account deletion uses existing Mem0 SDK methods (`delete_all` with `user_id` and `agent_id` filters). No new memory categories are introduced.

---

## 3. API Endpoints

All endpoints are under the `/api/v1` prefix. All three endpoints require `Authorization: Bearer <jwt>`.

---

### GET /api/v1/profile

Returns the current user's profile.

```
Auth: Bearer JWT required
Rate limit group: read
```

**Request**: No body, no query parameters.

**Response 200:**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "name": "Alex",
  "timezone": "America/New_York",
  "avatar_url": "https://s3.amazonaws.com/...",
  "preferred_language": "en",
  "onboarding_completed": true,
  "subscription_tier": "free",
  "subscription_expires_at": null,
  "created_at": "2026-02-23T14:30:00Z"
}
```

**Response 401:**

```json
{
  "detail": "Invalid or expired token"
}
```

**Notes**: The response reuses the existing `UserResponse` schema from `app/schemas/auth.py` with the addition of `subscription_expires_at`. See Section 4 for the schema extension.

---

### PUT /api/v1/profile

Updates mutable profile fields. Only provided fields are updated; omitted fields remain unchanged.

```
Auth: Bearer JWT required
Content-Type: application/json
Rate limit group: write
```

**Request Body (all fields optional):**

```json
{
  "name": "Alex",
  "timezone": "Europe/Istanbul",
  "avatar_url": "https://s3.amazonaws.com/photos/user_id/avatar.jpg",
  "preferred_language": "tr"
}
```

**Field Validation:**

| Field | Type | Constraints |
|-------|------|-------------|
| `name` | string, optional | 1-100 chars after trimming whitespace; must not be empty after trim |
| `timezone` | string, optional | Must be a valid IANA timezone (validated via `zoneinfo.ZoneInfo`) |
| `avatar_url` | string or null, optional | Max 2048 chars; must start with `https://` if non-null |
| `preferred_language` | string, optional | Must be one of: `en`, `tr` (extendable list) |

**Response 200:**

Returns the full updated profile (same shape as GET /api/v1/profile response).

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "name": "Alex",
  "timezone": "Europe/Istanbul",
  "avatar_url": "https://s3.amazonaws.com/...",
  "preferred_language": "tr",
  "onboarding_completed": true,
  "subscription_tier": "free",
  "subscription_expires_at": null,
  "created_at": "2026-02-23T14:30:00Z"
}
```

**Response 422:**

```json
{
  "detail": [
    {
      "loc": ["body", "timezone"],
      "msg": "Invalid IANA timezone",
      "type": "value_error"
    }
  ]
}
```

**Notes**: Partial updates -- the request body uses `Optional` fields with `None` as default, and only non-`None` fields are applied to the model. Setting `avatar_url` to explicit `null` in JSON clears the avatar.

---

### DELETE /api/v1/profile/account

GDPR-compliant full account deletion. Permanently removes all user data across all systems.

```
Auth: Bearer JWT required
Content-Type: application/json
Rate limit group: write
```

**Request Body:**

```json
{
  "confirmation": "DELETE MY ACCOUNT"
}
```

The `confirmation` field must be exactly the string `"DELETE MY ACCOUNT"` (case-sensitive). This prevents accidental deletions.

**Response 204:** No content.

**Response 400:**

```json
{
  "detail": "Confirmation text must be exactly 'DELETE MY ACCOUNT'"
}
```

**Response 401:**

```json
{
  "detail": "Invalid or expired token"
}
```

**Response 503:**

```json
{
  "detail": "Account deletion partially failed. Please contact support."
}
```

**Notes**: The 503 response is returned when external service cleanup (Mem0, S3, Cognito) fails after the DB deletion has already committed. The DB deletion is the point of no return. See Section 4 for the detailed deletion sequence.

---

## 4. Backend Logic

### 4.1 GET /api/v1/profile -- Service Method

```
ProfileService.get_profile(user: Profile) -> ProfileResponse
```

**Responsibilities:**
- Accepts the Profile ORM object from `get_current_user` dependency.
- Maps to response schema and returns.

**Notes**: This is trivial -- the `get_current_user` dependency already performs the DB lookup. The route handler simply maps the Profile to the response schema.

---

### 4.2 PUT /api/v1/profile -- Service Method

```
ProfileService.update_profile(
    db: AsyncSession,
    user: Profile,
    name: str | None,
    timezone: str | None,
    avatar_url: str | None | UNSET,
    preferred_language: str | None,
) -> ProfileResponse
```

**Responsibilities:**
1. Apply each non-None field to the Profile ORM object.
2. For `avatar_url`: distinguish between "field not provided" (do nothing) and "field explicitly set to null" (clear the avatar). Use a sentinel pattern or Pydantic's `model_fields_set` to differentiate.
3. Commit the transaction.
4. Refresh the Profile and return the updated data.

**Sentinel pattern for nullable fields:**

The `ProfileUpdateRequest` schema uses `Optional[str]` with a default of `UNSET` (a sentinel object) for `avatar_url`. The service checks:
- If `avatar_url is UNSET`: do not change the field.
- If `avatar_url is None`: set to `None` (clear avatar).
- If `avatar_url is str`: set to the new value.

For `name`, `timezone`, and `preferred_language` which are non-nullable in the DB, `None` means "do not change" (standard partial update).

**Error conditions:**
- Validation errors (timezone, language) are caught by Pydantic before reaching the service (422).

---

### 4.3 DELETE /api/v1/profile/account -- Service Method

```
ProfileService.delete_account(
    db: AsyncSession,
    user: Profile,
) -> None
```

**Responsibilities (in order):**

**Phase 1 -- Gather data needed for external cleanup:**
1. Query all characters for this user (including inactive) to collect `mem0_agent_id` values.
2. Note the user's `mem0_user_id` for global memory deletion.
3. Note the user's `id` for S3 prefix deletion and Cognito deletion.
4. Note the user's `email` for Cognito user deletion.

**Phase 2 -- Delete DB rows (point of no return):**
5. Delete the Profile row. Due to `ON DELETE CASCADE`, this cascades to:
   - All `characters` rows for this user
   - All `conversations` rows for this user
   - All `messages` rows for this user
   - All `body_measurements` rows for this user
   - The `user_activity` row for this user
   - All `partners` rows where `user_id_1` matches (CASCADE) or `user_id_2` matches (SET NULL)
6. Commit the transaction.

**Phase 3 -- External service cleanup (best-effort, logged errors do not fail the request):**
7. Delete Mem0 memories:
   - For each `mem0_agent_id`: `mem0.delete_all(user_id=mem0_user_id, agent_id=agent_id)` via `asyncio.to_thread()`.
   - Delete global memories: `mem0.delete_all(user_id=mem0_user_id)` via `asyncio.to_thread()`.
   - All Mem0 deletions run in parallel with `asyncio.gather(*tasks, return_exceptions=True)`.
8. Delete S3 files:
   - List and delete all objects under `photos/{user_id}/` and `audio/{user_id}/` prefixes.
   - Use boto3 `list_objects_v2` + `delete_objects` (batch delete up to 1000 keys per call).
   - Wrapped in `asyncio.to_thread()`.
9. Delete Cognito user:
   - `admin_delete_user(UserPoolId=..., Username=email)` via `asyncio.to_thread()`.

**Error handling for Phase 3:**
- Each external cleanup step is wrapped in try/except. Failures are logged at ERROR level with the user_id for manual remediation.
- If ALL external cleanups fail, raise HTTPException(503) with the message "Account deletion partially failed. Please contact support."
- If some succeed and some fail, still return 204 (the DB deletion is the authoritative action) but log the failures prominently.
- Rationale: the DB row is gone, so the user can no longer access anything. External cleanup is eventual consistency; a background job or manual process can retry later.

**Why this order matters:**
- DB deletion first ensures the user is immediately locked out. Even if Mem0/S3/Cognito cleanup fails, the user cannot access the API (JWT verification fails because the Profile row is gone).
- External cleanup after DB ensures we don't leave the user in a state where their DB data exists but their Cognito account is deleted (which would be irrecoverable without support intervention).

**Mem0 operations:**
- `agent_id` pattern: `{template}_{user_id}` per `docs/05-ai-bellek.md`.
- Global memories are deleted with `user_id` only (no `agent_id`).
- Character memories are deleted with both `user_id` and `agent_id`.

**No new config values needed.** All required config fields already exist:
- `mem0_api_key` for Mem0 SDK
- `s3_bucket_name` and `aws_region` for S3
- `cognito_user_pool_id` for Cognito admin operations

---

### 4.4 Schema Definitions

#### ProfileResponse

Extends the existing `UserResponse` from `app/schemas/auth.py` with `subscription_expires_at`. Rather than modifying the auth schema (which is used by register/login responses), create a new `ProfileResponse` that includes all profile fields.

```
ProfileResponse:
  id: str
  email: str
  name: str
  timezone: str
  avatar_url: str | None
  preferred_language: str
  onboarding_completed: bool
  subscription_tier: str
  subscription_expires_at: datetime | None
  created_at: datetime
```

#### ProfileUpdateRequest

```
ProfileUpdateRequest:
  name: str | None = None          # 1-100 chars, trimmed
  timezone: str | None = None      # valid IANA timezone
  avatar_url: str | None | UNSET   # https:// URL or null to clear
  preferred_language: str | None = None  # "en" or "tr"
```

For the sentinel pattern on `avatar_url`, use Pydantic's `model_fields_set` attribute. If `"avatar_url"` is in `body.model_fields_set`, the user explicitly provided it (could be null or a string). If not in `model_fields_set`, the user did not send the field and it should not be updated.

#### AccountDeleteRequest

```
AccountDeleteRequest:
  confirmation: str   # must equal "DELETE MY ACCOUNT"
```

---

### 4.5 Route Handler Structure

The profile router handles three routes:

```
GET  /profile         -> profile_service.get_profile(user)
PUT  /profile         -> profile_service.update_profile(db, user, body)
DELETE /profile/account -> profile_service.delete_account(db, user)
```

The router is registered in `main.py` with `prefix="/api/v1"`.

---

## 5. iOS Screens and Components

Not applicable -- this is a backend-only feature (layer: backend).

---

## 6. Android Screens and Components

Not applicable -- this is a backend-only feature (layer: backend).

---

## 7. Test Plan

### Backend Route Tests (`test_profile_routes.py`)

#### GET /api/v1/profile
1. **Happy path**: Authenticated user gets their profile. Assert 200 with all expected fields.
2. **Auth failure**: No token returns 401.
3. **Auth failure**: Invalid token returns 401.

#### PUT /api/v1/profile
4. **Happy path**: Update name only. Assert 200, name changed, other fields unchanged.
5. **Happy path**: Update timezone to valid IANA timezone. Assert 200.
6. **Happy path**: Update preferred_language to "tr". Assert 200.
7. **Happy path**: Update avatar_url to a valid https URL. Assert 200.
8. **Happy path**: Clear avatar_url by sending null. Assert 200, avatar_url is null.
9. **Happy path**: Update multiple fields at once. Assert 200, all changed.
10. **Empty body**: Send `{}`. Assert 200, nothing changed.
11. **Validation error**: Invalid timezone string. Assert 422.
12. **Validation error**: Empty name after trim. Assert 422.
13. **Validation error**: Name too long (>100 chars). Assert 422.
14. **Validation error**: Invalid preferred_language. Assert 422.
15. **Validation error**: avatar_url not starting with https://. Assert 422.
16. **Auth failure**: No token returns 401.

#### DELETE /api/v1/profile/account
17. **Happy path**: Correct confirmation string. Assert 204. Verify profile is gone from DB.
18. **Wrong confirmation**: Send wrong string. Assert 400.
19. **Missing confirmation**: Send empty body. Assert 422.
20. **Auth failure**: No token returns 401.
21. **Cascade verification**: After deletion, verify characters, conversations, and messages for the user are gone.

### Backend Service Tests (`test_profile_service.py`)

#### ProfileService.update_profile
22. **Partial update**: Only name provided, other fields untouched.
23. **Avatar clear**: avatar_url explicitly set to None clears the field.
24. **Avatar not provided**: avatar_url not in request, existing value preserved.
25. **All fields update**: All four fields provided.

#### ProfileService.delete_account
26. **Full deletion flow**: Mock Mem0, S3, and Cognito. Verify all external calls made with correct parameters.
27. **Mem0 failure**: Mem0 delete_all raises exception. Verify 204 still returned but error logged.
28. **S3 failure**: S3 list/delete raises exception. Verify 204 still returned but error logged.
29. **Cognito failure**: admin_delete_user raises exception. Verify 204 still returned but error logged.
30. **All external failures**: All three services fail. Verify 503 returned.
31. **Multiple characters**: User has 3 characters. Verify Mem0 delete_all called for each agent_id plus global.
32. **No characters**: User has no characters (edge case). Verify only global Mem0 deletion attempted.

### Mocking Strategy

- **Mem0**: Mock `MemoryClient` class. Verify `delete_all` called with correct `user_id` and `agent_id` parameters.
- **S3**: Mock `boto3.client("s3")`. Verify `list_objects_v2` and `delete_objects` called with correct bucket and prefix.
- **Cognito**: Mock `boto3.client("cognito-idp")`. Verify `admin_delete_user` called with correct UserPoolId and Username.
- **DB**: Use the existing async test session pattern from other test files.

---

## 8. Acceptance Criteria

1. Given an authenticated user, when they call `GET /api/v1/profile`, then they receive a 200 response with all their profile fields including `subscription_expires_at`.
2. Given an unauthenticated request, when calling any profile endpoint, then a 401 is returned.
3. Given an authenticated user, when they call `PUT /api/v1/profile` with `{"name": "New Name"}`, then only the name is updated and all other fields remain unchanged.
4. Given an authenticated user, when they call `PUT /api/v1/profile` with `{"timezone": "Invalid/Zone"}`, then a 422 is returned.
5. Given an authenticated user, when they call `PUT /api/v1/profile` with `{"avatar_url": null}`, then the avatar_url is cleared to null.
6. Given an authenticated user, when they call `PUT /api/v1/profile` with an empty body `{}`, then a 200 is returned with the profile unchanged.
7. Given an authenticated user, when they call `DELETE /api/v1/profile/account` with `{"confirmation": "DELETE MY ACCOUNT"}`, then a 204 is returned and their profile, characters, conversations, and messages are deleted from the database.
8. Given an authenticated user, when they call `DELETE /api/v1/profile/account` with incorrect confirmation text, then a 400 is returned and no data is deleted.
9. Given a successful account deletion, when external cleanup (Mem0, S3) partially fails, then 204 is still returned and failures are logged at ERROR level.
10. Given a successful account deletion, when ALL external cleanup operations fail, then 503 is returned.
11. Given a user with multiple characters, when account deletion occurs, then Mem0 `delete_all` is called once per character (with its `agent_id`) plus once for global memories.
12. Given a successful account deletion, then the Cognito user is deleted via `admin_delete_user`.

---

## 9. File Manifest

```
Backend:
  CREATE  backend/app/routes/profile.py
  CREATE  backend/app/services/profile_service.py
  CREATE  backend/app/schemas/profile.py
  MODIFY  backend/app/main.py                        (register profile router)
  CREATE  backend/tests/routes/test_profile_routes.py
  CREATE  backend/tests/services/test_profile_service.py

Shared:
  CREATE  shared/feature-specs/profile-crud-endpoints.md   (this file)
  CREATE  docs/pipeline/profile-crud-endpoints-architect.handoff.md
```

### File Details

**backend/app/routes/profile.py**
- Defines `router = APIRouter()` with three route handlers.
- Depends on `get_current_user` and `get_db`.
- Delegates all logic to `ProfileService`.

**backend/app/services/profile_service.py**
- `ProfileService` class with `get_profile()`, `update_profile()`, `delete_account()`.
- Uses `MemoryClient` from mem0, `boto3` for S3 and Cognito.
- All boto3 and Mem0 calls wrapped in `asyncio.to_thread()`.

**backend/app/schemas/profile.py**
- `ProfileResponse` (full profile for GET/PUT responses).
- `ProfileUpdateRequest` (partial update body for PUT).
- `AccountDeleteRequest` (confirmation body for DELETE).

**backend/app/main.py**
- Add import: `from app.routes import profile`
- Add router: `app.include_router(profile.router, prefix="/api/v1", tags=["profile"])`

**backend/tests/routes/test_profile_routes.py**
- Route-level tests for all three endpoints (test cases 1-21 from Section 7).

**backend/tests/services/test_profile_service.py**
- Service-level unit tests (test cases 22-32 from Section 7).
