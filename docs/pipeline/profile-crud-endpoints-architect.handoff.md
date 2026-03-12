# Architect Handoff: Profile CRUD Endpoints

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

Three REST endpoints for user profile management: GET (read profile), PUT (update name/timezone/avatar_url/preferred_language), and DELETE (GDPR-compliant full account deletion with cascade across DB, Mem0, S3, and Cognito). The delete endpoint requires explicit confirmation text in the request body to prevent accidental deletions.

## Spec Location

`shared/feature-specs/profile-crud-endpoints.md`

## Layer

backend

## Key Decisions

- **DB cascade for deletion**: The existing `ON DELETE CASCADE` foreign keys on characters, conversations, messages, body_measurements, user_activity, and partners already handle all DB cleanup when the Profile row is deleted. No custom SQL needed.
- **DB first, external cleanup second**: DB deletion is the point of no return. Mem0/S3/Cognito cleanup happens after the commit as best-effort. This ensures the user is immediately locked out even if external cleanup fails partially.
- **Best-effort external cleanup**: If some but not all external services fail during deletion, return 204 and log errors. Only return 503 if ALL external cleanups fail.
- **Confirmation string**: `"DELETE MY ACCOUNT"` as a case-sensitive confirmation to prevent accidental deletions via automated tools or misclicks.
- **Sentinel pattern for avatar_url**: Use Pydantic's `model_fields_set` to distinguish between "field not sent" (preserve current value) and "field sent as null" (clear the avatar). Other non-nullable fields use simple `None` = "do not change" semantics.
- **New ProfileResponse schema**: Rather than modifying the existing `UserResponse` in auth schemas (which is stable), create a new `ProfileResponse` that includes `subscription_expires_at` for the profile endpoints.
- **IANA timezone validation**: Use `zoneinfo.ZoneInfo` (stdlib in Python 3.9+) for timezone validation rather than adding a dependency like pytz.
- **Supported languages**: `en` and `tr` only for now. The list is a Pydantic validator, easily extendable.
- **No new config values**: All required secrets (mem0_api_key, s3_bucket_name, cognito_user_pool_id) already exist in config.py.
- **Parallel Mem0 cleanup**: All Mem0 delete_all calls (one per character agent_id + one global) run in parallel via asyncio.gather with return_exceptions=True.

## File Manifest

```
Backend:
  CREATE  backend/app/routes/profile.py
  CREATE  backend/app/services/profile_service.py
  CREATE  backend/app/schemas/profile.py
  MODIFY  backend/app/main.py
  CREATE  backend/tests/routes/test_profile_routes.py
  CREATE  backend/tests/services/test_profile_service.py

Shared:
  CREATE  shared/feature-specs/profile-crud-endpoints.md
  CREATE  docs/pipeline/profile-crud-endpoints-architect.handoff.md
```

## Assumptions Made

- The existing `ON DELETE CASCADE` on all FK references to `profiles.id` is correct and will cascade through characters -> conversations -> messages.
- S3 files for a user are stored under `photos/{user_id}/` and `audio/{user_id}/` prefixes (per `docs/09-dagitim.md` and the media-upload spec P01-10).
- Cognito user deletion uses `admin_delete_user` with the user's email as the Username (same as registration).
- The Mem0 SDK's `delete_all(user_id=..., agent_id=...)` method correctly scopes deletion to that agent. The `delete_all(user_id=...)` call (no agent_id) deletes global memories only.

## Dependencies

- Requires: P01-04 (auth-endpoints), P01-01 (project-setup), P01-02 (database-schema)
- Blocks: backend-dev (implements the endpoints)

## Notes for Developers

1. **Do not modify `app/schemas/auth.py`**. Create a new `ProfileResponse` in `app/schemas/profile.py` instead. The auth schemas are used by register/login and should remain stable.
2. **Cognito deletion**: Use `admin_delete_user`, not `delete_user`. The admin variant does not require the user's access token (which will be invalid after DB deletion). The admin call requires the `cognito_user_pool_id` config value.
3. **S3 batch deletion**: `delete_objects` accepts up to 1000 keys per call. For most users this is sufficient in a single batch, but implement a loop for safety.
4. **Testing external services**: All Mem0, S3, and Cognito calls must be mocked in tests. Use `unittest.mock.patch` or `unittest.mock.AsyncMock` as appropriate.
5. **Rate limit groups**: GET /profile falls under "read" (60/min), PUT /profile and DELETE /profile/account fall under "write" (20/min). No changes to the rate limiter are needed -- the existing `classify_request` method handles this automatically based on HTTP method.

## Next Steps

backend-dev should read the spec and implement.
