# Architect Handoff: FCM Push Service

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

A backend feature adding an FCM token registration endpoint (`PUT /api/v1/notifications/token` and `DELETE /api/v1/notifications/token`) and a higher-level `NotificationService` class that wraps the existing `send_push_notification()` with user lookup, dead token cleanup, and structured logging. The service provides a single `send(user_id, title, body, data)` method for any backend code that needs to push a notification to a user.

## Key Decisions

- **PUT instead of POST** for token registration -- follows `docs/04-veri-api.md` spec. The operation is idempotent (replacing the stored token), which aligns with PUT semantics. The issue description said POST, but the API contract doc takes precedence.
- **Separate DELETE endpoint** for token removal -- gives mobile clients a clean API for logout/notification-disable flows, rather than overloading PUT with null values.
- **NotificationService returns SendResult enum, not exceptions** -- callers can decide how to handle failures without try/except boilerplate. Notification failures should never break the calling flow.
- **NotificationService does not replace notification_scheduler's direct usage** -- the scheduler has its own batch processing pattern with inline token lookup. Refactoring it is not worth the risk for this feature. Future one-off notification senders will use NotificationService.
- **4096 character limit on fcm_token** -- generous headroom above typical 150-200 char tokens, prevents abuse.
- **No new config values** -- Firebase credentials and all dependencies are already configured from P02-02.
- **No new DB columns or tables** -- `profiles.fcm_token` already exists.

## Spec Location

`shared/feature-specs/fcm-push-service.md`

## Assumptions Made

- `profiles.fcm_token` column is already nullable TEXT, no schema migration needed.
- `notification_sender.py` with `send_push_notification()` and `SendResult` class already exists and is stable from P02-02.
- Firebase Admin SDK is already initialized in the application lifespan from P02-02.
- The existing `conftest.py` test fixtures provide database sessions and authenticated clients.

## Dependencies

- Requires: P02-02 (notification-scheduler) -- provides `notification_sender.py`
- Requires: P01-02 (database-schema) -- `profiles` table
- Requires: P01-03 (cognito-auth-middleware) -- JWT auth

## File Manifest

```
Backend:
  CREATE  backend/app/routes/notifications.py
  CREATE  backend/app/schemas/notifications.py
  CREATE  backend/app/services/notification_service.py
  MODIFY  backend/app/main.py
  CREATE  backend/tests/routes/test_notifications_routes.py
  CREATE  backend/tests/services/test_notification_service.py
```

## Notes for Developers

- The route file should follow the same patterns as `backend/app/routes/profile.py` -- use `Depends(get_current_user)` and `Depends(get_db)`.
- The `NotificationService` takes an `AsyncSession` in its constructor, matching the pattern used by `ProfileService`.
- Do NOT modify `notification_sender.py` or `notification_scheduler.py`. Build on top of them.
- The `PUT /notifications/token` endpoint belongs to the `write` rate limit group.
- Register the router in `main.py` with prefix `/api/v1` (not `/api/v1/notifications`) because the router paths already include `/notifications/token`.

## Next Steps

backend-dev should read the spec and implement. No iOS or Android implementation needed (backend-only layer).
