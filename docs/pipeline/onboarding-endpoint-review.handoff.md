# Reviewer Handoff: Onboarding Endpoint

**Date**: 2026-02-24
**Agent**: reviewer
**Status**: APPROVED

## Review Summary

| Category | Passed | Warnings | Issues |
|----------|--------|----------|--------|
| Architecture | 7 | 0 | 0 |
| Code Quality | 5 | 0 | 0 |
| Testing | 4 | 0 | 0 |
| Security | 4 | 0 | 0 |
| **Total** | **20** | **0** | **0** |

## Checklist Results

### Architecture

- [x] **user_id from JWT only** -- PASS. Route handler (`backend/app/routes/onboarding.py`, line 24) uses `profile: Profile = Depends(get_current_user)`. The `OnboardingRequest` schema has no `user_id` field. Grep for `user_id.*body|body.*user_id` in routes returned zero matches.
- [x] **Global memory scope (no agent_id in Mem0 seeding)** -- PASS. `_seed_memories()` (`backend/app/services/onboarding_service.py`, lines 215-218) passes only `user_id=mem0_user_id` to `client.add()`. No `agent_id` parameter. Grep for `agent_id` in the service file returned only a comment on line 206 documenting the design decision.
- [x] **Retry-safe ordering (Haiku -> Mem0 -> DB flag)** -- PASS. `complete_onboarding()` (`backend/app/services/onboarding_service.py`, lines 89-123) executes: step 1 idempotency guard, step 2 Haiku call (line 100), step 3 Mem0 seed (lines 103-106), step 4 profile update (lines 109-115), step 5 DB commit (line 118). If Haiku or Mem0 fail, the 503 exception is raised before `onboarding_completed` is set or committed.
- [x] **409 for already-completed onboarding** -- PASS. Lines 90-94 of `onboarding_service.py` check `profile.onboarding_completed` and raise `HTTPException(409, detail="Onboarding already completed")`.
- [x] **Deterministic fallback when Haiku fails** -- PASS. `_parse_haiku_response()` (lines 156-187) catches `json.JSONDecodeError` and unexpected formats, logging warnings and delegating to `_fallback_memories()` (lines 189-197) which uses the `_FALLBACK_TEMPLATES` dict.
- [x] **All Mem0 calls wrapped in asyncio.to_thread()** -- PASS. `_seed_memories()` (line 215) wraps the synchronous `client.add()` call in `asyncio.to_thread()`.
- [x] **Claude Haiku used (not Sonnet)** -- PASS. `_convert_answers_to_memories()` (line 139) uses `model=settings.claude_haiku_model`, which resolves to `"claude-haiku-4-5"` per `backend/app/config.py` line 56.

### Code Quality

- [x] **No hardcoded secrets, API keys, or credentials** -- PASS. API keys are read from `settings.anthropic_api_key` and `settings.mem0_api_key` (sourced from environment variables or AWS Secrets Manager). Grep for hardcoded secret patterns returned zero matches across all `backend/app/` files.
- [x] **Error messages are user-friendly** -- PASS. Error details are: `"Onboarding already completed"` (409), `"AI service temporarily unavailable"` (503). No raw exception messages or stack traces exposed. Pydantic 422 errors use FastAPI's standard formatting.
- [x] **All API errors handled explicitly** -- PASS. The service handles: already-completed (409), Haiku API failure (503), unparseable Haiku response (fallback + continue), Mem0 failure (503). The `except HTTPException: raise` clause (line 147-148) correctly re-raises HTTP exceptions (e.g., rate limit 429) without wrapping them in 503.
- [x] **No TODO/FIXME in production code** -- PASS. Grep for `TODO|FIXME` in all three production files returned zero matches.
- [x] **async def on all routes** -- PASS. The single route handler `complete_onboarding` (`backend/app/routes/onboarding.py`, line 22) uses `async def`. Grep for synchronous `^def ` in `backend/app/routes/` returned zero matches across all route files.

### Testing

- [x] **Coverage >= 80%** -- PASS. Per the backend-test handoff, all three source files are at 100% line coverage and 100% branch coverage: `routes/onboarding.py` (12/12 stmts), `schemas/onboarding.py` (35/35 stmts, 6/6 branches), `services/onboarding_service.py` (71/71 stmts, 10/10 branches). 131 total onboarding tests, 0 failures.
- [x] **Mocks/fakes used for Claude and Mem0** -- PASS. All tests mock `app.services.onboarding_service.AsyncAnthropic` (Claude) and `app.services.onboarding_service.MemoryClient` (Mem0) at the module level. No real API calls in any test. Mem0 failure tests patch `asyncio.to_thread` with side_effect exceptions.
- [x] **All critical happy paths tested** -- PASS. Test R1/S3 cover the full happy path (7 answers -> Haiku -> Mem0 -> DB commit -> 200). Test R13/S4 cover the fallback path. Test R11/S7 cover profile name update. All 14 spec scenarios (R1-R14) and 14 service scenarios (S1-S14) are implemented.
- [x] **At least one error case tested per endpoint** -- PASS. Error cases covered: 409 already completed (R2/S1), 422 missing keys (R3), 422 duplicate keys (R4), 422 invalid key (R5), 422 empty answer (R6), 422 over-length (R7), 401 no auth (R8), 503 Haiku failure (R9/S10), 503 Mem0 failure (R10/S11), 422 whitespace-only (R14). Extended tests add ConnectionError, TimeoutError, and HTTPException re-raise cases.

### Security

- [x] **No credentials in code** -- PASS. Grep for `api_key\s*=\s*['\"]`, `secret\s*=\s*['\"]`, `password\s*=\s*['\"]`, and `token\s*=\s*['\"]` all returned zero matches in `backend/app/`.
- [x] **No user_id in request body** -- PASS. `OnboardingRequest` schema contains only `answers: list[OnboardingAnswer]`. No `user_id` field. The user identity comes exclusively from `Depends(get_current_user)`.
- [x] **SQL injection prevention** -- PASS. No raw SQL in the onboarding code. The only DB operation is `await self.db.commit()` (SQLAlchemy ORM). Profile attribute updates use ORM attribute assignment (`profile.onboarding_completed = True`, `profile.name = preferred_name`).
- [x] **No internal IDs exposed** -- PASS. Error responses contain only human-readable messages ("Onboarding already completed", "AI service temporarily unavailable"). No database IDs, stack traces, or system paths in any error response.

## Files Reviewed

**Backend**:
- `backend/app/routes/onboarding.py` (41 lines) -- PASS. Clean route handler, delegates all logic to service, uses `async def`, correct dependency injection pattern.
- `backend/app/services/onboarding_service.py` (229 lines) -- PASS. Clean separation of concerns with 5 methods, retry-safe operation ordering, proper error handling with `except HTTPException: raise` before generic catch, logging via `logging.getLogger("ember")`.
- `backend/app/schemas/onboarding.py` (84 lines) -- PASS. Proper Pydantic v2 patterns: `Field(...)` with constraints, `@field_validator` with `@classmethod`, `@model_validator(mode="after")`, `VALID_QUESTION_KEYS` as `frozenset`.
- `backend/app/main.py` (line 20, 60) -- PASS. Onboarding router correctly imported and registered at `prefix="/api/v1/onboarding"` with `tags=["onboarding"]`.
- `backend/tests/test_onboarding_routes.py` (16 tests) -- PASS.
- `backend/tests/test_onboarding_service.py` (18 tests) -- PASS.
- `backend/tests/test_onboarding_schemas.py` (15 tests) -- PASS.
- `backend/tests/test_onboarding_routes_extended.py` (18 tests) -- PASS.
- `backend/tests/test_onboarding_service_extended.py` (33 tests) -- PASS.
- `backend/tests/test_onboarding_schemas_extended.py` (31 tests) -- PASS.

## Issues Resolved During Review

- None (first-pass clean).

## Warnings (Not Blocking)

- None.

## Notes

- The `_parse_haiku_response` method correctly strips both `\`\`\`json` and bare `\`\`\`` markdown code block delimiters using regex before JSON parsing.
- The `_fallback_memories` static method gracefully handles missing keys (returns fewer memories) and empty answers (skips them), though in normal flow all 7 keys are always present due to Pydantic validation.
- The backend-tester identified and covered line 148 (`except HTTPException: raise`) which was not exercised by the original test suite. This is a correctness-critical code path that ensures HTTP exceptions (e.g., 429 rate limit from the Anthropic SDK) are not incorrectly wrapped as 503.
- Total test count: 131 onboarding tests (49 original + 82 extended), all passing, 100% line and branch coverage.
