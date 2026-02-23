# Backend Test Handoff: Auth Endpoints

**Date**: 2026-02-23
**Agent**: backend-tester
**Status**: COMPLETE
**Feature ID**: P01-04
**GitHub Issue**: #6

## Test Files Written
- `backend/tests/test_auth_routes_extended.py` -- 33 tests (idempotent registration, Cognito error mapping, response schema validation, email normalization, password edge cases, name edge cases, request body edge cases)
- `backend/tests/test_auth_service_extended.py` -- 30 tests (idempotent registration, DB transaction rollback, Cognito error mapping completeness, non-401 re-raise, login Cognito 503, asyncio.to_thread verification, DB row field validation, DEFAULT_COMPANION_PROMPT, _extract_sub, lazy init, login DB query)
- `backend/tests/test_auth_schemas_extended.py` -- 47 tests (email edge cases, password edge cases, name edge cases, RefreshRequest, UserResponse extended, AuthResponse, RefreshResponse)

## Pre-existing Test Files (from backend-dev)
- `backend/tests/test_auth_routes.py` -- 17 tests
- `backend/tests/test_auth_service.py` -- 11 tests
- `backend/tests/test_auth_schemas.py` -- 13 tests

## Coverage Results
- Lines: 100% (target: >= 80%) -- 186/186 statements covered
- Branches: 100% (target: >= 70%) -- 24/24 branches covered
- All previously uncovered lines (217, 338, 349, 354 in auth_service.py) now covered

## Test Run Results
- Total auth tests: 151 (41 original + 110 new)
- Full suite: 595 passed (151 auth + 444 pre-existing)
- Failed: 0
- Skipped: 0

## Test Command
```bash
backend/.venv/bin/python -m pytest backend/tests/ -v --tb=short --ignore=backend/tests/test_migration.py
```

## Spec Scenario Coverage (30 scenarios from spec)

All 30 scenarios from `shared/feature-specs/auth-endpoints.md` Section 6 are covered:

| Spec # | Scenario | Covered By |
|--------|----------|-----------|
| 1 | Register success (201) | test_auth_routes.py + extended |
| 2 | Register email exists (400) | test_auth_routes.py + extended idempotent tests |
| 3 | Register bad password (400) | test_auth_routes.py |
| 4 | Register missing email (422) | test_auth_routes.py |
| 5 | Register missing name (422) | test_auth_routes.py |
| 6 | Register invalid email (422) | test_auth_routes.py + extended email edge cases |
| 7 | Register short password (422) | test_auth_routes.py + extended password edge cases |
| 8 | Register whitespace name (422) | test_auth_routes.py + extended name edge cases |
| 9 | Login success (200) | test_auth_routes.py |
| 10 | Login wrong password (401) | test_auth_routes.py |
| 11 | Login non-existent email (401) | test_auth_routes.py |
| 12 | Login UserNotConfirmed (401) | test_auth_routes.py |
| 13 | Login no profile in DB (401) | test_auth_routes.py |
| 14 | Refresh success (200) | test_auth_routes.py + extended |
| 15 | Refresh invalid token (401) | test_auth_routes.py + extended |
| 16 | Refresh missing field (422) | test_auth_routes.py + extended |
| 17 | Register Cognito unavailable (503) | test_auth_routes.py + extended |
| 18 | Register Cognito call order | test_auth_service.py |
| 19 | Register creates 3 DB rows | test_auth_service.py + extended |
| 20 | Register mem0 IDs | test_auth_service.py + extended |
| 21 | Register character name/prompt | test_auth_service.py + extended |
| 22 | Login Cognito + DB query | test_auth_service.py + extended |
| 23 | Login no profile raises | test_auth_service.py |
| 24 | Refresh calls Cognito correctly | test_auth_service.py + extended |
| 25 | asyncio.to_thread wrapping | test_auth_service_extended.py |
| 26 | Strip name whitespace | test_auth_schemas.py + extended |
| 27 | Lowercase email | test_auth_schemas.py + extended |
| 28 | Whitespace-only name rejected | test_auth_schemas.py + extended |
| 29 | Login email lowercase | test_auth_schemas.py + extended |
| 30 | UserResponse from ORM | test_auth_schemas.py + extended |

## Additional Scenarios Tested (beyond spec)

- Idempotent registration: Cognito user exists + DB profile missing (recovery path)
- Idempotent registration: Cognito user exists + DB profile exists (skip creation)
- Idempotent registration: wrong password during recovery returns 400
- Non-401 exception during idempotent recovery propagates (503, not converted to 400)
- DB commit failure propagates error
- InvalidParameterException maps to 400
- TooManyRequestsException maps to 429
- Login Cognito unavailable maps to 503
- Refresh UserNotFoundException maps to 401
- Refresh Cognito unavailable maps to 503
- asyncio.to_thread used for all 3 flows (register/login/refresh)
- Character/Conversation field-level validation
- UUID generation for Character and Conversation IDs
- db.commit called exactly once during registration
- db.refresh called on Profile after commit
- Login does not modify DB (no add/commit/refresh)
- Cognito client lazy initialization and reuse
- DEFAULT_COMPANION_PROMPT content validation
- _extract_sub with different UUID values
- Response schema field presence and types (all fields)
- RefreshResponse excludes refresh_token
- Email normalization with plus addressing, dots, mixed case
- Password boundary values (7 vs 8 chars, empty, very long, unicode, spaces)
- Name boundary values (1 char, 100 chars, 101 chars, tabs, newlines, unicode, special chars)
- Request body edge cases (empty body, null fields, extra fields, wrong content type)
- RefreshRequest validation (empty, missing, long token)
- UserResponse id coercion from UUID and string
- AuthResponse and RefreshResponse serialization

## Issues Found During Testing
- None. All implementation code matches the spec. Coverage was already 98% from the backend-dev's tests; the extended tests brought it to 100% by covering the remaining 4 uncovered lines and all 24 branches.

## Notes for Reviewer
- The `_handle_existing_cognito_user` method has a re-raise path (line 338) for non-401 HTTP exceptions during idempotent recovery. This is now tested by `TestHandleExistingCognitoUserNon401`.
- All Cognito error codes from the spec's error mapping table are tested at both route and service level.
- The asyncio.to_thread wrapping is verified using `wraps=asyncio.to_thread` to ensure calls actually go through the thread executor.
