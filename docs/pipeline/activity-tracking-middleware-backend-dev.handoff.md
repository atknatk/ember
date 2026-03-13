# Backend Dev Handoff: Activity Tracking Middleware

**Date**: 2026-03-13
**Agent**: backend-dev
**Status**: COMPLETE

## Implemented Files
- `backend/app/middleware/activity_tracking.py` -- ActivityTrackingMiddleware (1 middleware class)
- `backend/app/services/activity_service.py` -- update_user_activity function (1 service function)
- `backend/app/main.py` -- registered ActivityTrackingMiddleware as innermost middleware
- `docs/standards/backend.md` -- added activity_tracking.py and activity_service.py to project structure
- `backend/tests/middleware/test_activity_tracking.py` -- 14 tests (regex, middleware unit, integration)
- `backend/tests/services/test_activity_service.py` -- 8 tests (upsert behavior, error handling)

## Endpoints Implemented
- No new endpoints. This is a middleware that runs as a side effect on all authenticated requests.

## Middleware Behavior
- Updates `user_activity.last_active_at` on every authenticated request (background task)
- Updates `user_activity.last_chat_at` additionally on `POST /api/v1/characters/{id}/messages`
- Uses PostgreSQL `INSERT ... ON CONFLICT (user_id) DO UPDATE` upsert
- Runs as Starlette BackgroundTask (zero latency impact on response)
- Fail-open: all errors caught and logged at warning level
- Registered as innermost middleware (after rate limiting in request flow)

## Test Results
- pytest: 22 passed, 0 failed
- ruff: clean (all 4 source+test files)
- doc-code sync: 75 passed, 0 failed
- No hardcoded secrets

## Known Issues / Deviations from Spec
- None

## Notes for Backend Tester
- Mock `app.middleware.activity_tracking.update_user_activity` for middleware unit tests
- Mock `app.services.activity_service.AsyncSessionLocal` for service unit tests
- Construct test JWTs using base64-encoding approach (see `_make_jwt` helper in test file)
- The middleware chains background tasks defensively if `response.background` is already set
- To verify upsert SQL correctness, inspect `session_mock.execute.call_args[0][0].text`
- The `_CHAT_PATH_RE` regex is tested separately for path matching correctness
