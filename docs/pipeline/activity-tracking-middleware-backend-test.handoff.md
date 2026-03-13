# Backend Test Handoff: Activity Tracking Middleware

**Date**: 2026-03-13
**Agent**: backend-tester
**Status**: COMPLETE

## Test Files Written

- `backend/tests/middleware/test_activity_tracking_additional.py` — 39 tests
- `backend/tests/services/test_activity_service_additional.py` — 17 tests

## Coverage Results (target modules only)

| Module | Lines | Covered | % |
|--------|-------|---------|---|
| `app/middleware/activity_tracking.py` | 32 | 32 | **100%** |
| `app/services/activity_service.py` | 17 | 17 | **100%** |

Both modules exceed the 80% line coverage target.

## Test Run Results

- Passed: 78 (14 backend-dev middleware + 8 backend-dev service + 39 additional middleware + 17 additional service)
- Failed: 0
- Skipped: 0

## What the Additional Tests Cover

### `test_activity_tracking_additional.py` (39 tests)

**Chat URL regex edge cases** (`TestChatPathRegexEdgeCases`, 16 tests):
- Positive matches: standard UUID, short alphanumeric ID, numeric-only ID, very long ID, underscore in ID, mixed-case ID
- Negative matches: trailing slash, empty character segment, slash inside ID, wrong prefix, query string appended, memories endpoint, stream subpath, root `/messages`, partial prefix that attempts to bypass `^` anchor
- Documents that the regex is path-only (method check lives in dispatch, not the regex)

**JWT format edge cases** (`TestJWTFormatEdgeCases`, 7 tests):
- Missing `sub` claim, non-string `sub` (integer), empty string `sub`, null `sub` — all rejected
- JWT with many extra Cognito claims still extracts `sub` correctly
- 2-part token (missing signature segment) rejected
- 4-part token (extra segment) rejected

**Authorization header variants** (`TestAuthorizationHeaderVariants`, 4 tests):
- `Token <jwt>` scheme rejected
- `Basic <credentials>` rejected
- `Bearer ` (no token) rejected
- Empty Authorization header rejected

**HTTP method vs chat detection** (`TestHTTPMethodChatDetection`, 4 tests):
- GET, PUT, PATCH, DELETE to `/messages` path all produce `is_chat_request=False`
- Only POST triggers `is_chat_request=True` (covered by existing tests)

**Background task chaining variants** (`TestBackgroundTaskChaining`, 3 tests):
- Existing `BackgroundTasks` (plural) instance is preserved alongside activity task
- Existing task executes before activity task (ordering guarantee)
- No existing task results in a single `BackgroundTask` (not a `BackgroundTasks` wrapper)

**Middleware response passthrough** (`TestMiddlewareResponsePassthrough`, 3 tests):
- 4xx status codes are preserved unmodified
- 5xx responses still schedule the activity task (authenticated request regardless of route error)
- If `_extract_sub_from_jwt` raises unexpectedly, middleware is fail-open and response is returned with no background task

**Concurrent dispatch** (`TestConcurrentMiddlewareDispatches`, 1 test):
- 5 concurrent `dispatch()` calls each independently schedule their own activity task

### `test_activity_service_additional.py` (17 tests)

**SQL parameter details** (`TestSQLParameterDetails`, 4 tests):
- `now` parameter is a `datetime` object (not a string) for both chat and non-chat paths
- `now` is timezone-aware (UTC)
- Both `user_id` and `now` keys are present in execute params for both paths

**SQL structure — non-chat path** (`TestSQLStructureNonChat`, 2 tests):
- `last_chat_at` is absent from the INSERT VALUES clause
- `last_chat_at` is absent from the entire SQL statement (zero occurrences)

**SQL structure — chat path** (`TestSQLStructureChat`, 4 tests):
- `last_chat_at` appears in INSERT VALUES clause
- `last_chat_at` appears in ON CONFLICT SET clause
- `notifications_sent_today` default included in chat SQL
- `notifications_sent_today` default included in non-chat SQL

**Error handling edge cases** (`TestErrorHandlingEdgeCases`, 4 tests):
- Commit failure on non-chat path is caught and logged
- Commit failure on chat path is caught and logged
- Session `__aexit__` failure is caught and logged
- Warning log message includes the `user_id` for operator visibility

**Concurrent upserts** (`TestConcurrentUpserts`, 2 tests):
- 3 concurrent calls each create their own independent DB session (not shared)
- Mixed success/failure in concurrent calls: failures don't affect successful siblings

**User ID edge cases** (`TestUserIDEdgeCases`, 2 tests):
- 512-character `user_id` accepted without error
- Standard UUID format `user_id` passed through unchanged

## Issues Found During Testing

None. The implementation matches the spec exactly:
- Fail-open in both middleware and service layer
- Correct SQL branching on `is_chat_request`
- Correct `sub` validation (rejects non-string, empty, null, missing)
- Correct background task chaining when existing task is present
- Concurrent calls are fully independent (each opens its own session)

## Notes for Reviewer

- The `test_four_part_token_does_not_trigger_update` test confirms that `_extract_sub_from_jwt` enforces the JWT 3-part structure. The implementation's `len(parts) != 3` check correctly handles this.
- The `test_chains_when_existing_task_is_background_tasks_instance` test exercises the `BackgroundTasks` (plural) chaining path in the middleware. The implementation uses `tasks.tasks.append()` which appends a single `BackgroundTask` to the existing task list; this works when the existing background is a `BackgroundTasks` instance with a `.tasks` attribute.
- The ordering test (`test_existing_task_executes_before_activity_task`) confirms the spec requirement that route-level background tasks execute before the activity tracking task.
- `test_5xx_response_still_schedules_activity_update` is intentional: a 500 from a route handler is still an authenticated request, so tracking the activity is correct behaviour per the spec.
