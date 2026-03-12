# Reviewer Handoff: Profile CRUD Endpoints

**Date**: 2026-03-13
**Agent**: reviewer
**Status**: APPROVED

## Review Summary

| Category | Passed | Warnings | Issues |
|----------|--------|----------|--------|
| Architecture | 5 | 0 | 0 |
| Backend | 8 | 2 | 0 |
| Testing | 6 | 0 | 0 |
| Security | 4 | 0 | 0 |
| **Total** | **23** | **2** | **0** |

## Grep Checks (All Clean)

| Check | Result |
|-------|--------|
| `OFFSET` in app code | None found |
| `user_id` from request body in routes | None found |
| Hardcoded `api_key=` or `secret=` | None found |
| Synchronous `def` in routes | None found |
| `/conversations` path in routes | None found |
| `TODO`/`FIXME`/`HACK` | None found |
| `print()` in production code | None found |

## Checklist Results

### Architecture Compliance
- [x] **No `/conversations` path segment** -- PASS
- [x] **Mem0 agent_id format** -- PASS (uses `mem0_agent_id` from Character model, follows `{template}_{user_id}` convention)
- [x] **No secrets in code** -- PASS (all config from `settings`)
- [x] **Spec adherence** -- PASS (all 3 endpoints implemented: GET, PUT, DELETE)
- [x] **Router registration** -- PASS (`prefix="/api/v1"`, tags=`["profile"]` in main.py)

### Backend Code Quality
- [x] **All route handlers are async** -- PASS (all 3 use `async def`)
- [x] **Parallel operations** -- PASS (`asyncio.gather(*coros, return_exceptions=True)` for external cleanup)
- [x] **JWT extraction** -- PASS (all routes use `Depends(get_current_user)`)
- [x] **Proper error responses** -- PASS (400 for bad confirmation, 422 for validation, 503 for all-external-fail)
- [x] **Input validation** -- PASS (Pydantic validators for name, timezone, avatar_url, preferred_language)
- [x] **No rate limit re-implementation** -- PASS (middleware handles it)
- [x] **Business logic in service layer** -- PASS (routes delegate to ProfileService)
- [x] **Logging, no print()** -- PASS (uses `logging.getLogger("ember")`)

### Testing
- [x] **Coverage >= 80%** -- PASS (99-100% across all 3 modules)
- [x] **Edge cases covered** -- PASS (auth failure, validation errors, empty body, partial external failure, all-fail 503)
- [x] **External services mocked** -- PASS (Mem0 MemoryClient, boto3 S3, boto3 Cognito all mocked)
- [x] **Ownership tested** -- PASS (unauthed_client tests verify 401/403)
- [x] **Schema validation tested** -- PASS (58 schema tests for boundary lengths, sentinel pattern, IANA timezone, URL constraints)
- [x] **Deletion order tested** -- PASS (TestDeleteAccountOrderOfOperations verifies DB delete before external cleanup)

### Security
- [x] **No credentials in code** -- PASS
- [x] **No user_id in request body** -- PASS (always from JWT via `get_current_user`)
- [x] **SQL injection prevention** -- PASS (SQLAlchemy parameterized queries only)
- [x] **No internal IDs exposed** -- PASS (error messages are user-friendly, no stack traces)

## Files Reviewed

**Backend**:
- `backend/app/routes/profile.py` -- PASS
- `backend/app/services/profile_service.py` -- PASS
- `backend/app/schemas/profile.py` -- PASS
- `backend/app/main.py` (modification) -- PASS
- `backend/tests/routes/test_profile.py` -- PASS (19 tests)
- `backend/tests/routes/test_profile_extended.py` -- PASS (31 tests)
- `backend/tests/services/test_profile.py` -- PASS (14 tests)
- `backend/tests/services/test_profile_extended.py` -- PASS (53 tests)
- `backend/tests/schemas/test_profile.py` -- PASS (58 tests)

## Issues Resolved During Review
- None (first-pass clean)

## Warnings (Not Blocking)

1. **`ProfileService.__new__` in GET route** (`routes/profile.py`, line 26): The GET handler uses `ProfileService.__new__(ProfileService)` to avoid passing a db session since `get_profile()` is synchronous and does not need `self.db`. This works correctly but is an unconventional pattern. Consider refactoring `get_profile()` to a standalone function or making it a `@staticmethod` in a future cleanup pass.

2. **Dead code guard** (`services/profile_service.py`, line 146-147): The `if not tasks: return {"total": 0, "failed": 0}` guard in `_cleanup_external_services` is unreachable because S3 and Cognito tasks are always appended before this check. Defensive but dead. Documented by the tester. Minor -- no functional impact.

3. **Empty string timezone error message** (documented by tester): Empty string timezone raises Python's raw `ValueError` instead of the custom "Invalid IANA timezone" message because the except clause catches `ZoneInfoNotFoundError` and `KeyError` but not `ValueError`. The 422 response is still returned correctly -- only the error message text differs. Non-blocking.
