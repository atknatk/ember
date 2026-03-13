# Architect Handoff: Activity Tracking Middleware

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

A FastAPI middleware that updates the `user_activity` table on every authenticated request. It sets `last_active_at` on all authenticated requests and additionally sets `last_chat_at` when the request is `POST /characters/:id/messages`. The update runs as a background task (zero latency impact) using a PostgreSQL upsert (`ON CONFLICT DO UPDATE`).

## Key Decisions

- **Background task, not inline await**: The activity update runs after the response is sent via Starlette's `BackgroundTask`, adding zero latency to API responses. A database failure in the background task does not affect the user's request.
- **Separate database session**: The background task creates its own `AsyncSessionLocal()` session because the request-scoped session is closed by the time the background task runs.
- **Reuse existing JWT parsing**: Imports `_extract_sub_from_jwt` from `request_id.py` rather than duplicating the lightweight JWT payload extraction logic.
- **Upsert pattern**: Uses `INSERT ... ON CONFLICT (user_id) DO UPDATE` for atomic insert-or-update behavior, avoiding race conditions under concurrent requests.
- **No throttling**: At current scale (max 60 reads/min per user due to rate limiting), the per-request upsert load is negligible. Throttling can be added later if monitoring shows it is needed.
- **Innermost middleware**: Registered before rate limiting middleware so it only fires for requests that pass rate limiting. Rate-limited (429) requests do not trigger activity updates.

## Spec Location

`shared/feature-specs/activity-tracking-middleware.md`

## Assumptions Made

- The `user_activity` table and `UserActivity` SQLAlchemy model already exist and match the schema in `docs/04-veri-api.md`.
- The `backend/app/middleware/` and `backend/tests/middleware/` directories already exist (created by P1.5-01 rate-limiting-middleware).
- The `_extract_sub_from_jwt` function in `request_id.py` is stable and can be imported by the activity tracking middleware.

## Dependencies

- Requires: P01-06 (chat-streaming), P01-03 (cognito-auth-middleware), P01-02 (database-schema)
- Blocks: backend-dev (implements), backend-tester (tests)

## Next Steps

backend-dev should read the spec and implement. backend-tester follows after implementation is complete.
