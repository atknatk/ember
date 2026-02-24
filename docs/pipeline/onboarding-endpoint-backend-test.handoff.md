# Backend Test Handoff: Onboarding Endpoint

**Date**: 2026-02-24
**Agent**: backend-tester
**Status**: COMPLETE

## Test Files Written

### Original (by backend-dev) -- 49 tests
- `backend/tests/test_onboarding_schemas.py` -- 15 tests
- `backend/tests/test_onboarding_service.py` -- 18 tests
- `backend/tests/test_onboarding_routes.py` -- 16 tests

### Extended (by backend-tester) -- 82 tests
- `backend/tests/test_onboarding_schemas_extended.py` -- 31 tests
- `backend/tests/test_onboarding_service_extended.py` -- 33 tests
- `backend/tests/test_onboarding_routes_extended.py` -- 18 tests

### Total: 131 onboarding tests

## Coverage Results
- Lines: 100% (target: >= 80%)
- Branches: 100% (target: >= 70%)
- All 3 source files at 100%:
  - `app/routes/onboarding.py` -- 100% (12/12 stmts, 0/0 branches)
  - `app/schemas/onboarding.py` -- 100% (35/35 stmts, 6/6 branches)
  - `app/services/onboarding_service.py` -- 100% (71/71 stmts, 10/10 branches)

## Test Run Results
- Passed: 131 (onboarding tests)
- Failed: 0
- Skipped: 0
- Full suite: 1193 passed, 0 failed

## Extended Tests Added (by backend-tester)

### Schema Edge Cases (31 tests)
- Unicode / accented / CJK characters in answers
- Boundary lengths (1 char, 500 chars, 498+whitespace, 499+whitespace overflow)
- Newline-only, tab-only, mixed-whitespace-only answers
- Internal newlines preserved
- Missing fields, null values, numeric values
- Special characters (quotes, brackets, ampersands)
- Empty answers list, single answer, null answers
- All keys with whitespace trimmed
- All answers at max length
- Mixed valid/invalid keys
- All same key (7 duplicates)
- VALID_QUESTION_KEYS constant verification (7 keys, frozenset, expected values)
- OnboardingResponse edge cases (0 memories, large number, false flag)

### Service Edge Cases (33 tests)
- Haiku response parsing: dict, numbers, mixed types, nested arrays, null, string
- Code block without json qualifier
- Valid JSON with leading whitespace
- More/fewer than 7 memories returned by Haiku
- Unicode in Haiku response
- Fallback with special characters, very long answers, all empty, missing keys
- Fallback templates cover all valid question keys
- Fallback preserves template key order
- Haiku called with max_tokens=512
- Haiku called with single user message
- **HTTPException re-raise (line 148)** -- previously uncovered, now tested
- Profile name is None -> gets updated
- Profile name case-insensitive: UPPER vs lower
- Profile name with whitespace trimmed before comparison
- DB commit NOT called on Haiku failure
- DB commit NOT called on Mem0 failure
- onboarding_completed remains False on Haiku failure
- Mem0 messages format verification (list of user-role dicts)
- Answer order invariance at service level
- Return type is OnboardingResponse
- Fallback memories seeded to Mem0 on non-JSON Haiku response
- AsyncAnthropic created with api_key
- MemoryClient created with api_key

### Route Edge Cases (18 tests)
- Response Content-Type is application/json
- Response has exactly expected keys and types
- Empty request body, null answers, non-list answers
- Unicode answers via HTTP
- Exactly 500-char answers via HTTP
- Haiku returns empty list -> fallback
- Haiku returns dict -> fallback
- Profile name None -> updated via route
- Profile name UPPER -> not updated (case-insensitive match)
- GET method not allowed (405)
- Special characters in all answers
- 409 response detail format
- 422 response has detail field
- 503 on ConnectionError
- 503 on TimeoutError
- Haiku markdown code block via route

## Issues Found During Testing
- Line 148 (`except HTTPException: raise`) was not covered by the original test suite. Added `test_httpexception_re_raised_not_wrapped` to verify that HTTPExceptions raised inside the Haiku call path are re-raised with their original status code (e.g., 429) rather than being caught by the generic Exception handler and wrapped as 503. This is a correctness-critical code path.

## Notes for Reviewer
- Pydantic validates `max_length=500` on the raw input string BEFORE `field_validator` runs `strip()`. This means an answer of 498 chars + 2 spaces (500 total) is accepted and stripped, but 499 chars + 2 spaces (501 total) is rejected before strip. The test `test_499_chars_plus_whitespace_rejected_by_max_length` documents this behavior.
- The `_make_client_fixture` factory pattern in routes_extended is available for future use but not currently used by the fixtures -- each fixture is explicit for clarity.
- All extended test files follow the same env setup pattern (`os.environ.setdefault`) and import ordering as the original test files.
