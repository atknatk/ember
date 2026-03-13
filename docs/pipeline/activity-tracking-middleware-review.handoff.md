# Reviewer Handoff: Activity Tracking Middleware

**Date**: 2026-03-13
**Agent**: reviewer
**Status**: APPROVED

## Review Summary

| Category | Passed | Warnings | Issues |
|----------|--------|----------|--------|
| Architecture | 7 | 0 | 0 |
| Backend | 8 | 1 | 0 |
| Testing | 6 | 0 | 0 |
| Security | 4 | 0 | 0 |
| **Total** | **25** | **1** | **0** |

## Files Reviewed

**Backend**:
- `backend/app/middleware/activity_tracking.py` -- PASS (94% coverage)
- `backend/app/services/activity_service.py` -- PASS (100% coverage)
- `backend/app/main.py` -- PASS (middleware registration order correct)
- `backend/tests/middleware/test_activity_tracking.py` -- PASS (14 tests)
- `backend/tests/services/test_activity_service.py` -- PASS (8 tests)

## Checklist Results

### Architecture Compliance
- [x] Background task pattern: `BackgroundTask` from starlette, response returned before upsert executes
- [x] Fail-open: both middleware dispatch and service function catch all exceptions, log at warning
- [x] Upsert SQL correct: `INSERT ... ON CONFLICT (user_id) DO UPDATE` with conditional `last_chat_at`
- [x] Chat detection regex: `^/api/v1/characters/[^/]+/messages$` + `method == "POST"`, compiled at module level
- [x] Innermost middleware: registered first in `main.py`, runs after rate limiting in request flow
- [x] All handlers async: middleware `dispatch` is `async def`, service function is `async def`
- [x] JWT-based user identification: imports `_extract_sub_from_jwt` from `request_id.py`

### Backend Code Quality
- [x] No hardcoded secrets
- [x] No OFFSET pagination
- [x] No user_id from request body -- extracted from JWT sub claim
- [x] Parameterized SQL via `text()` with named parameters (`:user_id`, `:now`)
- [x] Separate `AsyncSessionLocal()` session for background task (request session closed by then)
- [x] Background task chaining: defensively handles existing `response.background`
- [x] Logging via `logging.getLogger("ember")` -- no `print()` statements
- [x] Type annotations on all functions

### Testing
- [x] 22 tests, all passing
- [x] 96% combined coverage (94% middleware, 100% service) -- exceeds 80% minimum
- [x] Regex edge cases tested (match, no-match for characters list, nested path, memories)
- [x] Unauthenticated and malformed JWT cases tested
- [x] Background task execution verified (not just scheduling)
- [x] Error handling tested: DB error caught and logged, session creation failure caught

### Security
- [x] No hardcoded secrets (grep confirmed)
- [x] No user_id accepted from request body
- [x] SQL parameterized (no string concatenation)
- [x] No internal IDs or stack traces exposed in error messages

## Issues Resolved During Review
- None (first-pass clean)

## Warnings (Not Blocking)
- The spec's developer notes suggested using `sqlalchemy.dialects.postgresql.insert` with `on_conflict_do_update()`, but the implementation uses raw `text()` SQL with named parameters. Both approaches are parameterized and correct. The `text()` approach is clear and readable for this simple upsert case. This is a style difference, not a correctness issue.
