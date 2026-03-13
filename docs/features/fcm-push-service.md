# FCM Push Service

> Enables mobile clients to register their Firebase Cloud Messaging device token with the backend, and provides a centralized notification service for any backend code that needs to push a notification to a user.

**Status**: Released
**Added in**: Phase 2 (P02-03)
**Platforms**: Backend
**GitHub Issue**: #15

---

## Overview

This feature adds two complementary pieces to the Ember notification stack: an FCM token registration API and a higher-level notification delivery service.

Before this feature, the `profiles.fcm_token` column existed in the database but had no endpoint to populate it. Mobile clients had no way to register their device token, meaning the notification scheduler (P02-02) could not deliver pushes to any user. The `PUT /api/v1/notifications/token` and `DELETE /api/v1/notifications/token` endpoints close that gap: clients call PUT after receiving a token from the FCM SDK, and DELETE when the user disables notifications or logs out.

The `NotificationService` class solves a different problem. As more backend features need to send one-off notifications (partner activity, system alerts, goal follow-ups), each would otherwise duplicate the same pattern: look up the user's FCM token from the `profiles` table, call `send_push_notification()`, and clean up dead tokens. `NotificationService.send()` centralizes that logic into a single reusable method. It does not replace the notification scheduler's existing inline batch logic — the scheduler processes users in bulk and has its own token cleanup path that does not benefit from per-user round trips.

This feature introduces no new database tables or columns. All required infrastructure (`profiles.fcm_token`, Firebase Admin SDK initialization, `send_push_notification()` from `notification_sender.py`) was already in place from P01-02 and P02-02.

---

## Architecture

### How It Works (Data Flow)

**Token Registration (PUT)**:

1. The mobile client receives an FCM registration token from the Firebase SDK (on app install, notification permission grant, or SDK-triggered token refresh).
2. The client calls `PUT /api/v1/notifications/token` with `Authorization: Bearer {jwt}` and `{"fcm_token": "<token>"}`.
3. Pydantic validates `fcm_token` is a non-empty string of at most 4096 characters; returns 422 if not.
4. `get_current_user()` extracts `user_id` from the JWT.
5. A SQL `UPDATE profiles SET fcm_token = $token WHERE id = $user_id` is executed and committed.
6. The endpoint returns `{"status": "ok"}`.

**Token Removal (DELETE)**:

1. The client calls `DELETE /api/v1/notifications/token` with `Authorization: Bearer {jwt}`.
2. `get_current_user()` extracts `user_id` from the JWT.
3. A SQL `UPDATE profiles SET fcm_token = NULL WHERE id = $user_id` is executed and committed.
4. The endpoint returns 204 with no body.

**Sending a Notification via NotificationService**:

1. A backend caller (e.g., a future partner-activity feature) instantiates `NotificationService(db)` and calls `await service.send(user_id, title, body, data)`.
2. The service queries `SELECT fcm_token FROM profiles WHERE id = $user_id`.
3. If `fcm_token` is `None`, the service returns `SendResult.INVALID_TOKEN` immediately without calling Firebase.
4. If a token is found, `send_push_notification(fcm_token, title, body, data or {})` is called.
5. If the result is `SendResult.INVALID_TOKEN`, the service calls `_clear_token(user_id)` which sets `profiles.fcm_token = NULL` and commits. Any DB error during cleanup is caught and logged at ERROR level — it does not propagate.
6. The `SendResult` string is returned to the caller.

### Design Decisions

**PUT instead of POST**: The endpoint follows the `docs/04-veri-api.md` contract. The operation is idempotent — each user has exactly one active FCM token, and repeated calls with the same token have the same effect. This aligns with PUT semantics. (The GitHub issue description said POST; the API contract doc takes precedence per `docs/standards/common.md`.)

**Separate DELETE endpoint**: An explicit DELETE endpoint cleanly maps to the "disable notifications" and "logout" user intents. Overloading PUT with a null value would be ambiguous.

**NotificationService returns SendResult, not exceptions**: Notification failures should never break the calling flow. Returning a `SendResult` enum lets callers inspect the outcome without try/except boilerplate. The three possible values are `"sent"`, `"invalid_token"`, and `"transient_error"`.

**Dead token cleanup on INVALID_TOKEN only**: A `TRANSIENT_ERROR` result (e.g., a temporary FCM outage) does not clear the token. Only `INVALID_TOKEN` (where Firebase confirms the token is no longer valid) triggers cleanup. This prevents losing valid tokens due to transient network failures.

**NotificationService does not replace notification_scheduler's direct usage**: The scheduler performs batch processing — it fetches all users with tokens in batches of 100 and calls `send_push_notification()` inline with inline cleanup. Routing each user through `NotificationService.send()` would add per-user DB round trips to what is a batch operation. Future one-off notification senders will use `NotificationService`; a future refactor of the scheduler is out of scope.

### Database Tables Involved

| Table | Operation | Notes |
|-------|-----------|-------|
| `profiles` | UPDATE | `PUT /token`: sets `fcm_token`; `DELETE /token`: sets `fcm_token = NULL` |
| `profiles` | SELECT | `NotificationService.send()`: reads `fcm_token` by `user_id` |
| `profiles` | UPDATE | `NotificationService._clear_token()`: sets `fcm_token = NULL` on invalid token |

---

## API Reference

See [`docs/04-veri-api.md`](../04-veri-api.md) for the full API contract. OpenAPI spec: `shared/api-contracts/paths/notifications.yaml`.

### `PUT /api/v1/notifications/token`

Register or update the authenticated user's FCM device token.

**Auth**: Bearer JWT required
**Rate Limit Group**: write
**Content-Type**: `application/json`

**Request Body**:
```json
{
  "fcm_token": "dO3K7x..."
}
```

**Validation**: `fcm_token` must be a non-empty string (min_length=1) of at most 4096 characters. FCM tokens are typically 150-200 characters; the generous limit provides headroom for future Google token format changes.

**Response 200**:
```json
{
  "status": "ok"
}
```

**Error Responses**:

| Status | When |
|--------|------|
| 401 | Missing or invalid JWT |
| 422 | `fcm_token` is empty, missing, or longer than 4096 characters |

**Idempotency**: Calling this endpoint multiple times with the same token produces the same result. No 409 is returned for duplicate tokens.

---

### `DELETE /api/v1/notifications/token`

Unregister the authenticated user's FCM token. Typically called on logout or when the user disables notifications.

**Auth**: Bearer JWT required
**Rate Limit Group**: write

**Response**: 204 No Content (empty body)

**Error Responses**:

| Status | When |
|--------|------|
| 401 | Missing or invalid JWT |

**Idempotency**: Returns 204 regardless of whether a token was previously stored.

---

## NotificationService API

`backend/app/services/notification_service.py`

### Constructor

```python
NotificationService(db: AsyncSession) -> None
```

Accepts an `AsyncSession` injected from the calling route's `Depends(get_db)`.

### `send()`

```python
async def send(
    self,
    user_id: uuid.UUID,
    title: str,
    body: str,
    data: dict[str, str] | None = None,
) -> str
```

Sends a push notification to a user by `user_id`. Handles token lookup, FCM delivery, and dead token cleanup automatically.

**Returns**: One of `SendResult.SENT` (`"sent"`), `SendResult.INVALID_TOKEN` (`"invalid_token"`), or `SendResult.TRANSIENT_ERROR` (`"transient_error"`).

**Never raises**: FCM failures and database errors during cleanup are caught internally. Callers do not need try/except.

**`data` parameter**: Pass `None` (default) or a `dict[str, str]` for client-side deep-linking data. `None` is converted to `{}` before being forwarded to `send_push_notification()`. The caller's dict is not mutated.

**Example usage**:
```python
service = NotificationService(db)
result = await service.send(
    user_id=user.id,
    title="New message",
    body="Emma sent you a message.",
    data={"character_id": str(character.id), "type": "message"},
)
if result == SendResult.SENT:
    # success
```

---

## Configuration

No new configuration values are required. All dependencies are already in place from prior features:

| Dependency | Source | Notes |
|-----------|--------|-------|
| Firebase Admin SDK | P02-02 (notification-scheduler) | `initialize_firebase()` called at app startup in `main.py` lifespan |
| `send_push_notification()` and `SendResult` | `backend/app/services/notification_sender.py` | Used as-is, not modified |
| `profiles.fcm_token` column | P01-02 (database-schema) | Nullable TEXT, no migration needed |
| AWS Cognito JWT auth | P01-03 (cognito-auth-middleware) | `Depends(get_current_user)` |
| Rate limiting | P1.5-01 (rate-limiting-middleware) | `write` group applies to both endpoints |

The notifications router is registered in `backend/app/main.py`:

```python
from app.routes import notifications
app.include_router(notifications.router, prefix="/api/v1", tags=["notifications"])
```

Note: the prefix is `/api/v1`, not `/api/v1/notifications`, because the router paths already include `/notifications/token`.

---

## iOS Implementation

Not applicable. This is a backend-only feature. Mobile clients consume the endpoints via standard HTTP calls; no new iOS-specific code patterns were introduced.

---

## Android Implementation

Not applicable. This is a backend-only feature. Mobile clients consume the endpoints via standard HTTP calls; no new Android-specific code patterns were introduced.

---

## Testing

### Coverage Summary

| Module | Lines | Coverage |
|--------|-------|----------|
| `app/routes/notifications.py` | 18 | 100% |
| `app/schemas/notifications.py` | 6 | 100% |
| `app/services/notification_service.py` | 30 | 100% |

### Test Files

| File | Tests | Description |
|------|-------|-------------|
| `backend/tests/routes/test_notifications_routes.py` | 12 | Core route scenarios |
| `backend/tests/routes/test_notifications_routes_extended.py` | 25 | Boundary, schema, DB call, and auth edge cases |
| `backend/tests/services/test_notification_service.py` | 8 | Core service scenarios |
| `backend/tests/services/test_notification_service_extended.py` | 20 | Data payload, logging, `_clear_token` error handling |

### Mocking Guide

| Component | Mock target |
|-----------|-------------|
| `send_push_notification` | `app.services.notification_service.send_push_notification` |
| Database session | Dependency override via `get_db` in route tests; mock `AsyncSession` in service tests |
| JWT / current user | Dependency override via `get_current_user` |

The `scalar_one_or_none()` call on the `execute()` return value in `NotificationService.send()` must be configured on the mock to return the desired FCM token string (or `None`).

### Running Tests

```bash
cd backend && python -m pytest tests/routes/test_notifications_routes.py tests/routes/test_notifications_routes_extended.py tests/services/test_notification_service.py tests/services/test_notification_service_extended.py -v --tb=short
```

Full backend suite:

```bash
cd backend && python -m pytest tests/ -v
```

---

## Known Limitations

- **No notification preferences**: This feature only manages the presence or absence of an FCM token. User-level opt-outs (e.g., "disable morning check-ins") and the `PUT /notifications/preferences` endpoint are a separate future feature.
- **Whitespace-only FCM token accepted**: A token consisting entirely of whitespace characters (e.g., `"   "`) satisfies Pydantic's `min_length=1` validation and is stored without error. The spec does not require whitespace stripping, so this is intentional behavior — documented in the extended test suite.
- **NotificationService not used by notification_scheduler**: The notification scheduler (P02-02) continues to call `send_push_notification()` directly with its own inline batch token lookup. Routing the scheduler through `NotificationService` would change its batch query pattern. This refactor is deferred to a future phase.
- **Single token per user**: Each user has exactly one FCM token stored at a time — whichever device registered most recently. Multi-device push delivery is not supported.

---

## Extending This Feature

**To add notification preferences** (opt-out by type): Add a `notification_preferences` table with a `user_id` foreign key and per-type boolean columns. In the notification scheduler's `_process_notification()`, add a preference check before the Mem0/Haiku call. `NotificationService.send()` does not need to change — preference filtering is a scheduling concern, not a delivery concern.

**To use NotificationService from a new feature**: Instantiate it inside your route handler and pass the `db` session:
```python
service = NotificationService(db)
result = await service.send(user_id=user.id, title="...", body="...", data={...})
```
The service handles everything else. Check `result` against `SendResult` values if you need to act on delivery outcome.

**To add multi-device support**: Change `profiles.fcm_token` to a separate `fcm_tokens` table (one row per device per user). Update `NotificationService.send()` to query all tokens for the user and call `send_push_notification()` for each, collecting results. `_clear_token()` would then target a specific token row rather than the profile row.

**To route the notification scheduler through NotificationService**: Replace the scheduler's inline token lookup and `send_push_notification()` call inside `_process_notification()` with a `NotificationService(db).send()` call. Remove the scheduler's own `fcm_token` cleanup block. This is a safe refactor but requires care with the scheduler's batch `AsyncSessionLocal` usage pattern.

---

## Related Documentation

- [Database Schema and API Endpoints](../04-veri-api.md) — `profiles` table definition, notifications endpoint contract
- [Proactive Notification System Design](../06-bildirimler.md) — FCM architecture, notification types, trigger conditions
- [Notification Scheduler](./notification-scheduler.md) — P02-02, the background job that consumes FCM tokens and calls `send_push_notification()` directly
- [Activity Tracking Middleware](./activity-tracking-middleware.md) — P02-01, which populates `last_active_at` and `last_chat_at` used by the scheduler
