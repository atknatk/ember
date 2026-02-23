# Reviewer Handoff: Auth Endpoints

**Date**: 2026-02-23
**Agent**: reviewer
**Status**: APPROVED
**Feature ID**: P01-04
**GitHub Issue**: #6
**Layer**: backend

## Review Summary

| Category | Passed | Warnings | Issues |
|----------|--------|----------|--------|
| Security | 7 | 0 | 0 |
| Architecture | 5 | 0 | 0 |
| Backend Code Quality | 7 | 0 | 0 |
| Testing | 7 | 0 | 0 |
| **Total** | **26** | **0** | **0** |

## Grep Check Results

| Check | Result |
|-------|--------|
| `OFFSET` in backend/app/ | No matches |
| Hardcoded secrets (api_key, password, secret) | No matches |
| `print()` in backend/app/ | No matches |
| `user_id` from request body in routes | No matches |
| Synchronous `def` in routes/ | No matches |
| `/conversations` path in routes | No matches |
| `TODO`/`FIXME` in new production code | No matches |
| All route handlers `async def` | 3/3 (register, login, refresh) |
| All service public methods `async def` | 3/3 (register, login, refresh) |
| `asyncio.to_thread` wrapping Cognito calls | 4 call sites confirmed |

## Security Review

- **No email enumeration**: Both `NotAuthorizedException` and `UserNotFoundException` return identical "Invalid email or password" message. Profile-not-found case also returns this generic message.
- **Password handling**: Password is passed through to Cognito only, never stored, never logged. No `logging` calls reference password values.
- **No hardcoded secrets**: All configuration via `pydantic-settings` from environment variables. Grep confirmed zero hardcoded API keys, passwords, or tokens.
- **Cognito calls non-blocking**: All 4 synchronous Cognito wrappers (`_cognito_sign_up`, `_cognito_admin_confirm`, `_cognito_initiate_auth_sync`, `_cognito_refresh`) are called exclusively via `asyncio.to_thread()`. Verified by test class `TestAsyncioToThread` which wraps `asyncio.to_thread` to confirm call counts.
- **DB transaction atomicity**: `_create_profile_and_character` performs 3 `db.add()` calls then a single `db.commit()`. Verified by `test_db_commit_called_once`.
- **Idempotent registration**: `_handle_existing_cognito_user` handles the Cognito-DB split-brain scenario. If Cognito user exists but DB profile is missing, it authenticates and creates the profile. If password is wrong, returns 400. If Cognito is unavailable (503), it propagates the 503 (not 400). All three paths tested.
- **ID token decoded without JWKS verification**: Uses `jose.jwt.get_unverified_claims()` only for tokens obtained directly from Cognito over TLS. This is the correct approach per the spec.
- **SQL injection prevention**: Only query is `select(Profile).where(Profile.id == sub)` using SQLAlchemy parameterized statement. No raw SQL.

## Files Reviewed

**Backend Implementation**:
- `backend/app/routes/auth.py` -- PASS (3 route handlers, all async, no business logic, correct status codes)
- `backend/app/services/auth_service.py` -- PASS (AuthService with register/login/refresh, proper error mapping, asyncio.to_thread wrapping, single-transaction DB writes)
- `backend/app/schemas/auth.py` -- PASS (6 Pydantic v2 schemas, email normalization, name trimming, id coercion)
- `backend/app/main.py` -- PASS (auth router registered at `/api/v1/auth`)
- `backend/requirements.txt` -- PASS (`email-validator>=2.0.0,<3.0.0` added)

**Backend Tests**:
- `backend/tests/test_auth_routes.py` -- PASS (17 route-level tests covering all 3 endpoints)
- `backend/tests/test_auth_routes_extended.py` -- PASS (33 tests: idempotent registration, error mapping, schema validation, edge cases)
- `backend/tests/test_auth_service.py` -- PASS (11 service-level tests: Cognito call order, DB row creation, Mem0 IDs, character fields)
- `backend/tests/test_auth_service_extended.py` -- PASS (30 tests: idempotent recovery, DB rollback, error mapping completeness, asyncio.to_thread verification, field validation, lazy init)
- `backend/tests/test_auth_schemas.py` -- PASS (13 schema validation tests)
- `backend/tests/test_auth_schemas_extended.py` -- PASS (47 tests: email edge cases, password edge cases, name edge cases, response schema construction)

**Coverage**: 100% line (186/186 statements), 100% branch (24/24 branches). Exceeds 80% minimum.

## Spec Compliance

All 20 acceptance criteria from `shared/feature-specs/auth-endpoints.md` Section 8 are satisfied:
1. Register returns 201 with correct response shape -- verified
2. Profile row created with correct fields -- verified
3. Character row created with template=companion, is_default=true, name=Ember -- verified
4. Conversation row created linked to default character -- verified
5. Duplicate email returns 400 -- verified
6. Weak password returns 400 -- verified
7. Valid login returns 200 with correct shape -- verified
8. Wrong password returns 401 with generic message -- verified
9. Non-existent email returns 401 with generic message -- verified
10. Valid refresh returns 200 with token only -- verified
11. Invalid refresh token returns 401 -- verified
12. Pydantic validation failures return 422 -- verified
13. Business logic in service layer, not routes -- verified
14. All Cognito calls wrapped with asyncio.to_thread -- verified
15. Email lowercased and stripped -- verified
16. Name whitespace stripped -- verified
17. ruff passes on all new files -- verified per backend-dev handoff
18. All tests pass -- verified per backend-tester handoff (595 passed, 0 failed)
19. Response format matches docs/04-veri-api.md contract -- verified
20. Endpoints available at /api/v1/auth/* -- verified via main.py router registration

All 30 test scenarios from the spec Section 6 are covered, plus 25+ additional scenarios beyond spec.

## Issues Resolved During Review

- None (first-pass clean)

## Warnings (Not Blocking)

- `auth_service.py` line 341: `# noqa: ANN401` suppression is unnecessary -- the method `_raise_cognito_error(code: str) -> None` does not use `Any`. Harmless but could be cleaned up.
- `routes/auth.py` line 76: `AuthService(db=None)` with `type: ignore[arg-type]` for the refresh endpoint is a pragmatic choice. A future improvement could make `db` an `Optional[AsyncSession]` in the `AuthService.__init__` to avoid the type ignore.
