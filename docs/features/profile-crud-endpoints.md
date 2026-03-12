# Profile CRUD Endpoints

> Lets users view and update their profile information, and permanently delete their account with GDPR-compliant cascading erasure across all systems.

**Status**: Released
**Added in**: Phase 1.5 (P1.5-02)
**Platforms**: Backend
**GitHub Issue**: #84

---

## Overview

Three REST endpoints form the complete profile lifecycle for an authenticated Ember user. `GET /api/v1/profile` returns all profile fields needed by the mobile settings screen, including the `subscription_expires_at` field not present in the auth registration response. `PUT /api/v1/profile` supports partial updates — only the fields the caller explicitly includes are written; omitted fields are preserved unchanged.

`DELETE /api/v1/profile/account` is the GDPR Article 17 ("right to erasure") implementation. It permanently removes every record associated with the user: the profile row itself (which cascades via `ON DELETE CASCADE` through characters, conversations, messages, body measurements, and user activity), plus all Mem0 memories, all S3 files, and the Cognito identity. An explicit confirmation string in the request body prevents accidental deletion by automated tools or misclicks.

This feature does not handle email or password changes (those flow through Cognito directly), subscription management, FCM token updates, or the `onboarding_completed` flag (managed by P01-09).

---

## Architecture

### How It Works (Data Flow)

#### GET /api/v1/profile

1. Client sends `GET /api/v1/profile` with `Authorization: Bearer <jwt>`.
2. The `get_current_user` dependency validates the JWT and fetches the `Profile` row from PostgreSQL.
3. The route handler calls `ProfileService.get_profile(user)`, which maps the ORM object to `ProfileResponse` via `model_validate`.
4. The response is returned with status 200.

#### PUT /api/v1/profile

1. Client sends `PUT /api/v1/profile` with a JSON body containing only the fields to change.
2. `get_current_user` resolves the authenticated `Profile`.
3. Pydantic validates the request body. Fields fail fast on invalid timezone, name too long, unsupported language, or avatar URL not starting with `https://`.
4. `ProfileService.update_profile()` inspects `body.model_fields_set` to determine which fields were actually sent.
5. Only fields present in `model_fields_set` are written to the ORM object. `avatar_url` is a special case: if it is in `model_fields_set` with value `None`, the avatar is cleared; if it is absent from `model_fields_set` entirely, the existing value is preserved (see sentinel pattern below).
6. The session is committed, the ORM object is refreshed, and the full `ProfileResponse` is returned with status 200.

#### DELETE /api/v1/profile/account

1. Client sends `DELETE /api/v1/profile/account` with `{"confirmation": "DELETE MY ACCOUNT"}`.
2. `get_current_user` resolves the authenticated `Profile`.
3. The route handler validates the confirmation string exactly (case-sensitive). A mismatch returns 400 immediately before the service is called.
4. **Phase 1 — gather external cleanup data**: The service queries all `Character` rows for the user (including inactive) to collect `mem0_agent_id` values. The user's `mem0_user_id`, `id`, and `email` are noted.
5. **Phase 2 — delete from the database (point of no return)**: `db.delete(user)` is called. Due to `ON DELETE CASCADE` foreign keys, this single delete cascades to all characters, conversations, messages, body measurements, user activity rows, and partner links. The session is committed. The user can no longer authenticate after this point (JWT verification fails because the Profile row is gone).
6. **Phase 3 — external cleanup (best-effort)**: All cleanup tasks run in parallel via `asyncio.gather(*coros, return_exceptions=True)`:
   - One Mem0 `delete_all(user_id, agent_id)` call per character agent ID.
   - One Mem0 `delete_all(user_id)` call for global memories (no agent ID).
   - S3 batch deletion under `photos/{user_id}/` and `audio/{user_id}/` prefixes.
   - Cognito `admin_delete_user(UserPoolId, Username=email)`.
7. Failures in Phase 3 are logged at ERROR level with the `user_id` for manual remediation. If some but not all tasks fail, 204 is returned. If all tasks fail, 503 is raised.

### Sentinel Pattern for `avatar_url`

The `avatar_url` field in `ProfileUpdateRequest` is typed `str | None` with a default of `None`. Because `None` is both the default value and a valid intent (clearing the avatar), the implementation uses Pydantic's `model_fields_set` attribute to differentiate:

- `"avatar_url"` is **absent** from `model_fields_set`: field was not sent by the caller — do not modify the existing value.
- `"avatar_url"` is **present** in `model_fields_set` with value `None`: caller explicitly sent `null` — clear the avatar.
- `"avatar_url"` is **present** in `model_fields_set` with a string: caller sent a new URL — update to the new value.

The three non-nullable fields (`name`, `timezone`, `preferred_language`) use simpler semantics: `None` means "not provided, do not change", so they are only written if both present in `model_fields_set` and non-`None`.

### Database Tables Involved

| Table | Operation | Notes |
|-------|-----------|-------|
| `profiles` | SELECT (via `get_current_user`), UPDATE, DELETE | The DELETE cascades to all tables below |
| `characters` | SELECT (gather `mem0_agent_id` before delete), CASCADE DELETE | `ON DELETE CASCADE` from `profiles.id` |
| `conversations` | CASCADE DELETE | `ON DELETE CASCADE` from `characters.id` |
| `messages` | CASCADE DELETE | `ON DELETE CASCADE` from `conversations.id` |
| `body_measurements` | CASCADE DELETE | `ON DELETE CASCADE` from `profiles.id` |
| `user_activity` | CASCADE DELETE | `ON DELETE CASCADE` from `profiles.id` |
| `partners` | CASCADE DELETE (user_id_1) / SET NULL (user_id_2) | Mixed FK behavior |

No new tables or columns were introduced by this feature. All columns used by GET and PUT already existed on the `profiles` table.

### External Service Cleanup Order and Error Handling

The database deletion is the authoritative action. External cleanup is designed as eventual consistency:

- If DB deletion succeeds but external cleanup partially fails: 204 is returned; failures are logged at ERROR for manual retry.
- If DB deletion succeeds but ALL external cleanup fails: 503 is returned.
- There is no rollback path for failed external cleanup — the user's DB data is already gone. A future background job can retry using the logged `user_id`.

Cognito deletion uses `admin_delete_user` (not `delete_user`) because the user's access token is invalid after the DB row is gone. The admin variant requires only the `cognito_user_pool_id` config value and the user's email.

---

## API Reference

See [`docs/04-veri-api.md`](../04-veri-api.md) for the full API contract.

### `GET /api/v1/profile`

**Auth**: Bearer JWT required
**Rate limit group**: `read` (60 req/min)

**Request**: No body, no query parameters.

**Response 200**:

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

**Error Responses**:

| Status | When |
|--------|------|
| 401 | Missing or invalid JWT |

---

### `PUT /api/v1/profile`

**Auth**: Bearer JWT required
**Content-Type**: `application/json`
**Rate limit group**: `write` (20 req/min)

**Request Body (all fields optional)**:

```json
{
  "name": "Alex",
  "timezone": "Europe/Istanbul",
  "avatar_url": "https://s3.amazonaws.com/photos/user_id/avatar.jpg",
  "preferred_language": "tr"
}
```

**Field Validation**:

| Field | Constraints |
|-------|-------------|
| `name` | 1–100 characters after trimming whitespace; must be non-empty after trim |
| `timezone` | Valid IANA timezone, validated via Python stdlib `zoneinfo.ZoneInfo` |
| `avatar_url` | Max 2048 characters; must start with `https://` if non-null; send `null` to clear |
| `preferred_language` | One of: `en`, `tr` (case-sensitive) |

**Response 200**: Full updated profile (same shape as GET response).

**Error Responses**:

| Status | When |
|--------|------|
| 401 | Missing or invalid JWT |
| 422 | Validation error on any field (invalid timezone, empty name, name > 100 chars, unsupported language, avatar URL not `https://`, avatar URL > 2048 chars) |

---

### `DELETE /api/v1/profile/account`

**Auth**: Bearer JWT required
**Content-Type**: `application/json`
**Rate limit group**: `write` (20 req/min)

**Request Body**:

```json
{
  "confirmation": "DELETE MY ACCOUNT"
}
```

The `confirmation` value must be exactly `"DELETE MY ACCOUNT"` (case-sensitive). Any other value returns 400 before the service is invoked.

**Response 204**: No content. Account and all associated data have been permanently deleted.

**Error Responses**:

| Status | When |
|--------|------|
| 400 | Confirmation string does not match exactly |
| 401 | Missing or invalid JWT |
| 422 | Request body missing or `confirmation` field is empty string |
| 503 | DB deletion succeeded but ALL external cleanup operations (Mem0, S3, Cognito) failed |

**Important**: The 503 response means the database deletion has already been committed. The user's data is gone from the application perspective, but Mem0 memories, S3 files, or the Cognito identity may not have been cleaned up. The user should contact support for manual remediation.

---

## GDPR Deletion Flow

The account deletion endpoint implements GDPR Article 17 right to erasure. The full data inventory for a deleted user:

| System | Data Removed | Mechanism |
|--------|-------------|-----------|
| PostgreSQL | Profile, characters, conversations, messages, body measurements, user activity, partner links | `ON DELETE CASCADE` from Profile row delete |
| Mem0 | All memories per character (`agent_id` scoped) + all global memories (`user_id` scoped) | `MemoryClient.delete_all()` called per agent and once globally |
| AWS S3 | All objects under `photos/{user_id}/` and `audio/{user_id}/` | `list_objects_v2` + `delete_objects` batch (up to 1000 keys per batch) |
| AWS Cognito | User identity | `admin_delete_user(UserPoolId, Username=email)` |

The database deletion is committed before external cleanup begins. This design means the user is immediately locked out (JWT verification fails with no Profile row) even if external cleanup takes time or partially fails.

---

## Configuration

No new configuration values are required. This feature uses existing settings:

| Config Field | Used For |
|-------------|----------|
| `mem0_api_key` | Authenticating with Mem0 SDK during account deletion |
| `s3_bucket_name` | Identifying the S3 bucket for file deletion |
| `aws_region` | boto3 client initialization for S3 and Cognito |
| `cognito_user_pool_id` | `admin_delete_user` call during account deletion |

---

## Testing

### Coverage Summary

| Module | Lines | Covered | Coverage |
|--------|-------|---------|----------|
| `app/routes/profile.py` | 23 | 23 | 100% |
| `app/schemas/profile.py` | 74 | 74 | 100% |
| `app/services/profile_service.py` | 89 | 88 | 99% |

Line 147 of `profile_service.py` (`return {"total": 0, "failed": 0}` inside `_cleanup_external_services`) is unreachable dead code — S3 and Cognito tasks are always appended before the guard, so `tasks` can never be empty at that point. Behavior is correct; the guard is a defensive check that cannot fire.

Total profile tests: 172 (33 from backend-dev, 139 from backend-tester).

### Running Tests

```bash
cd backend && python -m pytest tests/routes/test_profile.py tests/services/test_profile.py tests/schemas/test_profile.py tests/routes/test_profile_extended.py tests/services/test_profile_extended.py -v
```

Full backend suite:

```bash
cd backend && python -m pytest tests/ -v
```

### Test File Index

| File | Tests | What Is Covered |
|------|-------|-----------------|
| `tests/routes/test_profile.py` | 19 | Route-level happy paths and auth failures |
| `tests/services/test_profile.py` | 14 | Service unit tests for core update and delete logic |
| `tests/schemas/test_profile.py` | 58 | Pydantic validation: all field constraints, sentinel behavior, ORM compatibility |
| `tests/routes/test_profile_extended.py` | 31 | Extended route edge cases: response shape, 503 propagation, confirmation case sensitivity |
| `tests/services/test_profile_extended.py` | 53 | Service internals: deletion order of operations, S3 pagination, Mem0 task building, Cognito args |

### Mocking Strategy

All external services are mocked in tests — no real Mem0, S3, or Cognito calls are made:

- **Mem0**: Mock `app.services.profile_service.MemoryClient`. Verify `delete_all` called with correct `user_id` and `agent_id` parameters.
- **S3**: Mock `app.services.profile_service.boto3`. Verify `list_objects_v2` and `delete_objects` called with correct bucket and prefix.
- **Cognito**: Mock `app.services.profile_service.boto3`. Verify `admin_delete_user` called with correct `UserPoolId` and `Username=email`.

---

## Known Limitations

- **No rollback for failed external cleanup**: If Mem0, S3, or Cognito cleanup fails after the DB commit, there is no automated retry. Failures are logged at ERROR level with the `user_id`; manual remediation is required. A future background job could process these failures.
- **S3 deletion batch limit**: The `_delete_s3_prefix` static method batches up to 1000 keys per `delete_objects` call and paginates via `list_objects_v2`. For users with extremely large media libraries this works correctly, but it is synchronous inside `asyncio.to_thread` and may be slow for very large deletions.
- **Supported languages are hardcoded**: `preferred_language` accepts only `"en"` or `"tr"`. The list is a `frozenset` constant in `app/schemas/profile.py` (`SUPPORTED_LANGUAGES`). Adding a new language requires a code change and deployment.
- **Empty string timezone behavior**: Python's `zoneinfo.ZoneInfo("")` raises `ValueError` (not `ZoneInfoNotFoundError`), which is not caught by the validator's `except (ZoneInfoNotFoundError, KeyError)` clause. The result is a 422 with a Pydantic-generated error message rather than the custom "Invalid IANA timezone" message. Behavior is correct (422 is returned) but the error message format differs from the spec for this edge case.
- **`'utc'` (lowercase) is accepted**: Python's `zoneinfo` accepts `'utc'` as a valid timezone. This is consistent with Python stdlib behavior but differs from strict IANA zone name casing.
- **Implementation deviation — dead code in `_cleanup_external_services`**: The guard `if not tasks: return {"total": 0, "failed": 0}` at line 147 of `profile_service.py` can never be reached because S3 and Cognito tasks are unconditionally appended before it. This is harmless defensive code.

---

## Extending This Feature

**Adding a new updatable profile field**: Add the field to `ProfileUpdateRequest` in `app/schemas/profile.py` with `Optional[T] = None`. Add the corresponding update logic in `ProfileService.update_profile()` following the existing pattern (check `model_fields_set`, apply if present). If the field is nullable in the DB (like `avatar_url`), use the `model_fields_set` sentinel pattern instead of the simpler `None`-means-skip pattern.

**Adding a new supported language**: Add the language code to `SUPPORTED_LANGUAGES` in `app/schemas/profile.py`. No other changes are needed — the validator error message is dynamically generated from the set.

**Adding retry logic for failed external cleanup**: Introduce a background task queue (e.g., a `failed_cleanups` table) in `delete_account()`. After the DB commit, record the cleanup targets in the queue before running Phase 3. A periodic background job can then retry the queue entries. This avoids the current manual remediation requirement.

**Adding more data to the GET response**: `ProfileResponse` in `app/schemas/profile.py` is a standalone Pydantic model distinct from `UserResponse` in `app/schemas/auth.py`. Add new fields to `ProfileResponse` without touching the auth schemas.

---

## Related Documentation

- [Database Schema and API Endpoints](../04-veri-api.md)
- [AI Memory System](../05-ai-bellek.md) — `agent_id` format and memory categories
- [Security and Performance](../08-guvenlik-performans.md)
- [Deployment Architecture](../09-dagitim.md) — S3 prefix conventions and Cognito user pool
- [Auth Endpoints](./auth-endpoints.md) — P01-04, which defines `get_current_user` and the Profile model
- [Rate Limiting Middleware](./rate-limiting-middleware.md) — P1.5-01, which classifies GET /profile as `read` and PUT/DELETE as `write`
