# Feature Spec: P02-03 -- FCM Push Service

**Feature ID**: P02-03
**Phase**: 2
**Layer**: backend
**GitHub Issue**: #15
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature adds two capabilities to the Ember backend:

1. **FCM Token Registration Endpoint** -- A `PUT /api/v1/notifications/token` endpoint that allows mobile clients to register or update their Firebase Cloud Messaging device token. When a user installs the app, grants notification permission, or when the FCM SDK refreshes the token, the client calls this endpoint to persist the token to the `profiles.fcm_token` column.

2. **High-Level Notification Service** -- A `NotificationService` class that wraps the existing low-level `send_push_notification()` function (from `notification_sender.py`) with user lookup, token validation, dead token cleanup, and structured logging. This service is the single entry point for any backend code that needs to send a push notification to a user by `user_id`, without needing to manually look up the FCM token or handle invalid token cleanup.

### Why It Exists

- Mobile clients currently have no way to register their FCM token with the backend. The `profiles.fcm_token` column exists but has no endpoint to set it. Without this endpoint, the notification scheduler (P02-02) cannot send push notifications because no tokens are stored.
- The notification scheduler currently handles token lookup and invalid-token cleanup inline. As more notification sources are added (chat mentions, partner activity, system alerts), each would need to duplicate this logic. A centralized `NotificationService` provides a reusable abstraction.

### Dependencies

- **Requires**: P01-02 (database-schema) -- `profiles` table with `fcm_token` column
- **Requires**: P01-03 (cognito-auth-middleware) -- JWT authentication for the endpoint
- **Requires**: P02-02 (notification-scheduler) -- provides `notification_sender.py` with `send_push_notification()` and `SendResult`

### What This Feature Does NOT Do

- It does not implement notification preferences (`PUT /notifications/preferences`). That is a separate feature.
- It does not modify the notification scheduler logic. The scheduler continues to call `send_push_notification()` directly (a future refactor may route it through `NotificationService`, but that is out of scope).
- It does not implement APNs (Apple Push Notification service) directly -- FCM handles delivery to both iOS and Android.
- It does not add a notification history table or delivery tracking beyond logging.

---

## 2. Data Models

### No New Tables

All required tables already exist per `docs/04-veri-api.md`:
- `profiles` -- has `fcm_token` column (TEXT, nullable)

### No Schema Changes

No `ALTER TABLE` statements are needed. The `profiles.fcm_token` column already exists and is used by the notification scheduler.

### No New Indexes

No new indexes are needed. The token registration endpoint updates a single row by primary key (`profiles.id`). The `NotificationService` also looks up profiles by primary key.

### Columns Written

| Table | Column | Operation | Endpoint/Service |
|-------|--------|-----------|------------------|
| `profiles` | `fcm_token` | UPDATE (set or clear) | `PUT /notifications/token` |
| `profiles` | `fcm_token` | UPDATE (set to NULL) | `NotificationService.send()` on invalid token |

### Columns Read

| Table | Column | Purpose |
|-------|--------|---------|
| `profiles` | `id`, `fcm_token` | Look up user's token in `NotificationService.send()` |

### No Mem0 Operations

This feature does not interact with Mem0.

---

## 3. API Endpoints

### PUT /api/v1/notifications/token

Register or update the authenticated user's FCM device token. This endpoint follows the contract defined in `docs/04-veri-api.md` (section "Bildirimler").

```
PUT /api/v1/notifications/token
Auth: Bearer JWT required
Rate Limit Group: write

Request Headers:
  Content-Type: application/json
  Authorization: Bearer <cognito_jwt>

Request Body:
{
  "fcm_token": "string"    // required, 1-4096 characters, the FCM registration token
}

Response 200:
{
  "status": "ok"
}

Response 400:
{
  "detail": "fcm_token must be between 1 and 4096 characters"
}

Response 401:
{
  "detail": "Not authenticated"
}

Response 422:
{
  "detail": [...]           // Pydantic validation errors
}
```

**Behavior**:
- Extracts `user_id` from the JWT (never from request body).
- Validates that `fcm_token` is a non-empty string of at most 4096 characters.
- Updates `profiles.fcm_token` for the authenticated user.
- If `fcm_token` is the same value already stored, the update is still executed (idempotent, no 409).
- Returns `{"status": "ok"}` on success.

**Why PUT instead of POST**: The operation is idempotent -- calling it multiple times with the same token has the same effect. `docs/04-veri-api.md` specifies `PUT`. Each user has exactly one FCM token at a time (the latest device); this is a replace operation, not a create.

### DELETE /api/v1/notifications/token

Unregister the authenticated user's FCM token. Used when the user disables notifications or logs out.

```
DELETE /api/v1/notifications/token
Auth: Bearer JWT required
Rate Limit Group: write

Request Headers:
  Authorization: Bearer <cognito_jwt>

Response 204: (no body)

Response 401:
{
  "detail": "Not authenticated"
}
```

**Behavior**:
- Sets `profiles.fcm_token = NULL` for the authenticated user.
- Returns 204 regardless of whether a token was previously stored (idempotent).

---

## 4. Backend Logic

### Route: `backend/app/routes/notifications.py`

A new router module with two endpoints.

#### `PUT /notifications/token`

1. Validate request body via `FcmTokenRequest` Pydantic model.
2. Extract `user_id` from JWT via `Depends(get_current_user)`.
3. Update `profiles.fcm_token` via a SQL UPDATE statement.
4. Return `{"status": "ok"}`.

No service class needed for this simple CRUD operation. The route handler directly executes the database update.

#### `DELETE /notifications/token`

1. Extract `user_id` from JWT via `Depends(get_current_user)`.
2. Set `profiles.fcm_token = NULL` via SQL UPDATE.
3. Return 204.

### Service: `backend/app/services/notification_service.py`

A higher-level service that provides `send_notification(user_id, title, body, data)` for use by any backend code that needs to push a notification to a user.

#### Class: `NotificationService`

```
class NotificationService:
    def __init__(self, db: AsyncSession) -> None
```

#### Method: `send`

```
async def send(
    self,
    user_id: uuid.UUID,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> str
```

Responsibilities:

1. Look up the user's `fcm_token` from the `profiles` table by `user_id`.
2. If `fcm_token` is `None`, return `SendResult.INVALID_TOKEN` (no token registered -- nothing to send).
3. Call `send_push_notification(fcm_token, title, body, data or {})` from `notification_sender.py`.
4. If the result is `SendResult.INVALID_TOKEN`:
   - Set `profiles.fcm_token = NULL` for the user.
   - Commit the change.
   - Log at INFO level: "Cleared invalid FCM token for user_id={user_id}".
5. If the result is `SendResult.SENT`:
   - Log at DEBUG level: "Notification sent to user_id={user_id}".
6. Return the `SendResult` string.

**Return value**: One of `SendResult.SENT`, `SendResult.INVALID_TOKEN`, or `SendResult.TRANSIENT_ERROR`.

**Error handling**: The method does not raise exceptions for FCM failures. It catches them internally (via `send_push_notification`'s error handling) and returns the appropriate `SendResult`. Database errors during token cleanup are caught, logged, and do not propagate.

**Why a separate service instead of inlining**: Multiple future features will need to send notifications (partner activity, system alerts, goal followups). Centralizing token lookup and dead-token cleanup avoids duplicating this logic. The notification scheduler can optionally be refactored to use this service in the future, but that is out of scope for P02-03.

### Registration in `backend/app/main.py`

Add the notifications router:

```
from app.routes import notifications
...
app.include_router(notifications.router, prefix="/api/v1", tags=["notifications"])
```

Add `"notifications"` to `openapi_tags`:
```
{"name": "notifications", "description": "FCM token management and push notifications"}
```

### Pydantic Schemas: `backend/app/schemas/notifications.py`

```
class FcmTokenRequest(BaseModel):
    fcm_token: str = Field(..., min_length=1, max_length=4096)

class FcmTokenResponse(BaseModel):
    status: str
```

`FcmTokenRequest` validates:
- `fcm_token` is a non-empty string (min_length=1).
- `fcm_token` is at most 4096 characters (max_length=4096). FCM tokens are typically ~150-200 characters, but the spec allows generous headroom.

---

## 5. iOS Screens and Components

Not applicable. This is a backend-only feature.

---

## 6. Android Screens and Components

Not applicable. This is a backend-only feature.

---

## 7. Test Plan

### Backend Tests

#### Route Tests: `backend/tests/routes/test_notifications_routes.py`

| # | Scenario | Method | Path | Expected |
|---|----------|--------|------|----------|
| 1 | Register FCM token with valid JWT | PUT | `/api/v1/notifications/token` | 200, `{"status": "ok"}`, token stored in DB |
| 2 | Register FCM token without JWT | PUT | `/api/v1/notifications/token` | 401 |
| 3 | Register FCM token with empty string | PUT | `/api/v1/notifications/token` | 422 (Pydantic validation) |
| 4 | Register FCM token with string > 4096 chars | PUT | `/api/v1/notifications/token` | 422 (Pydantic validation) |
| 5 | Register FCM token with missing body field | PUT | `/api/v1/notifications/token` | 422 |
| 6 | Register FCM token twice (idempotent) | PUT | `/api/v1/notifications/token` | 200 both times, latest token stored |
| 7 | Register FCM token updates existing token | PUT | `/api/v1/notifications/token` | 200, DB has new token value |
| 8 | Delete FCM token with valid JWT | DELETE | `/api/v1/notifications/token` | 204, `fcm_token` is NULL in DB |
| 9 | Delete FCM token without JWT | DELETE | `/api/v1/notifications/token` | 401 |
| 10 | Delete FCM token when none exists | DELETE | `/api/v1/notifications/token` | 204 (idempotent) |

#### Service Tests: `backend/tests/services/test_notification_service.py`

| # | Scenario | Expected |
|---|----------|----------|
| 11 | `send()` with user who has valid FCM token | Calls `send_push_notification`, returns `SendResult.SENT` |
| 12 | `send()` with user who has no FCM token (NULL) | Returns `SendResult.INVALID_TOKEN`, does not call `send_push_notification` |
| 13 | `send()` when `send_push_notification` returns `INVALID_TOKEN` | Sets `fcm_token = NULL` in DB, returns `SendResult.INVALID_TOKEN` |
| 14 | `send()` when `send_push_notification` returns `TRANSIENT_ERROR` | Does NOT clear token, returns `SendResult.TRANSIENT_ERROR` |
| 15 | `send()` when `send_push_notification` returns `SENT` | Returns `SendResult.SENT`, token unchanged |
| 16 | `send()` with `data=None` | Passes empty dict `{}` to `send_push_notification` |
| 17 | `send()` with custom `data` dict | Passes the dict through to `send_push_notification` |

#### How to Mock

- **Firebase**: Mock `send_push_notification` from `notification_sender.py` at the import level. Return appropriate `SendResult` values.
- **Database**: Use the test database fixture from `conftest.py`. Insert a test `profiles` row with a known `fcm_token`.
- **JWT/Auth**: Use the existing `authenticated_client` fixture or mock `get_current_user`.

---

## 8. Acceptance Criteria

1. Given a mobile client with a valid JWT and an FCM token, when it calls `PUT /api/v1/notifications/token` with `{"fcm_token": "abc123"}`, then the response is 200 with `{"status": "ok"}` and the profile's `fcm_token` column is set to `"abc123"`.

2. Given a user whose FCM token has been registered, when the client calls `PUT /api/v1/notifications/token` with a new token value, then the profile's `fcm_token` is updated to the new value (replacing the old one).

3. Given a request to `PUT /api/v1/notifications/token` without an `Authorization` header, then the response is 401.

4. Given a request to `PUT /api/v1/notifications/token` with an empty `fcm_token` string, then the response is 422.

5. Given a request to `PUT /api/v1/notifications/token` with an `fcm_token` longer than 4096 characters, then the response is 422.

6. Given a user with a registered FCM token, when the client calls `DELETE /api/v1/notifications/token`, then the response is 204 and `profiles.fcm_token` is set to NULL.

7. Given a user with no FCM token stored, when the client calls `DELETE /api/v1/notifications/token`, then the response is 204 (idempotent, no error).

8. Given `NotificationService.send(user_id, title, body, data)` is called for a user with a valid FCM token, when `send_push_notification` succeeds, then `SendResult.SENT` is returned.

9. Given `NotificationService.send()` is called for a user with no FCM token, then `SendResult.INVALID_TOKEN` is returned without calling `send_push_notification`.

10. Given `NotificationService.send()` receives `SendResult.INVALID_TOKEN` from `send_push_notification`, then `profiles.fcm_token` is set to NULL for that user.

11. Given `NotificationService.send()` receives `SendResult.TRANSIENT_ERROR` from `send_push_notification`, then the FCM token is NOT cleared (the error is temporary).

12. Given the backend test suite, when `pytest backend/tests/routes/test_notifications_routes.py backend/tests/services/test_notification_service.py -v` is run, then all tests pass with exit code 0.

---

## 9. File Manifest

```
Backend:
  CREATE  backend/app/routes/notifications.py                    (PUT and DELETE /notifications/token)
  CREATE  backend/app/schemas/notifications.py                   (FcmTokenRequest, FcmTokenResponse)
  CREATE  backend/app/services/notification_service.py           (NotificationService.send)
  MODIFY  backend/app/main.py                                    (register notifications router, add openapi tag)
  CREATE  backend/tests/routes/test_notifications_routes.py
  CREATE  backend/tests/services/test_notification_service.py

Shared:
  CREATE  shared/feature-specs/fcm-push-service.md               (this file)
  CREATE  docs/pipeline/fcm-push-service-architect.handoff.md
```

### Summary

| Action | Count |
|--------|-------|
| CREATE | 6 |
| MODIFY | 1 |
| DELETE | 0 |
| **Total** | **7** |

### Files NOT Modified

- `backend/app/models/profile.py` -- already has `fcm_token` column. No schema changes.
- `backend/app/services/notification_sender.py` -- existing low-level FCM sender is used as-is. No modifications needed.
- `backend/app/services/notification_scheduler.py` -- the scheduler continues to call `send_push_notification` directly. Refactoring it to use `NotificationService` is out of scope.
- `backend/app/config.py` -- no new config values needed. Firebase credentials are already configured.
- `backend/requirements.txt` -- no new dependencies. `firebase-admin` is already installed.

---

## 10. Design Decisions and Rationale

### Why PUT instead of POST for token registration

`docs/04-veri-api.md` specifies `PUT /notifications/token`. The operation is idempotent: calling it multiple times with the same token has the same effect. Each user has exactly one active FCM token (the most recent device). This is a replace/upsert semantic, which aligns with PUT. The GitHub issue description says POST, but the API contract doc takes precedence per `docs/standards/common.md` section 5.

### Why a separate DELETE endpoint instead of PUT with null

Explicitly deleting the token (setting it to NULL) on logout or notification opt-out is a distinct user intent. A DELETE endpoint makes this semantically clear and avoids ambiguity about whether a PUT with a missing field means "clear" or "don't change." It also gives the mobile client a clean API for the "disable notifications" flow.

### Why 4096 character limit on fcm_token

FCM registration tokens are typically 150-200 characters, but the spec allows generous headroom. The 4096 limit prevents abuse (e.g., sending megabytes of data in the token field) while accommodating any future token format changes by Google.

### Why NotificationService returns SendResult instead of raising exceptions

The service is designed to be called from places where a notification failure should not break the calling flow (e.g., "send a notification after creating a character" should not fail the character creation). Returning a result enum lets callers decide how to handle each case without try/except boilerplate.

### Why NotificationService does not replace notification_scheduler's direct usage

The notification scheduler already has its own inline token lookup and cleanup logic, including batch processing across all users. Refactoring it to use `NotificationService.send()` (which does individual user lookups) would change its batch query pattern and add per-user DB round trips. This refactor is not worth the risk for P02-03. Future features that send one-off notifications (partner activity, system alerts) will use `NotificationService`.
