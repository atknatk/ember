# Reviewer Agent Memory

## Project Structure
- Backend implementation: `backend/app/routes/`, `backend/app/services/`, `backend/app/schemas/`
- Tests: `backend/tests/test_*.py` (base + `_extended.py` files from backend-tester)
- Feature specs: `shared/feature-specs/{feature}.md`
- Pipeline handoffs: `docs/pipeline/{feature}-*.handoff.md`
- Config: `backend/app/config.py`, `backend/app/main.py`

## Key Review Patterns
- Auth model uses `Profile` (not `User`) -- `backend/app/models/profile.py`
- Auth dependency is `get_current_user` returning `Profile` from `app.dependencies`
- Route prefix set in `main.py`, routes use relative paths (`""`, `"/{character_id}"`)
- Backend-tester adds additional tests in the SAME test files (appended as extra classes)
- Tests use `os.environ.setdefault("DEBUG", "true")` at top to bypass AWS Secrets Manager

## Grep Checks to Always Run
1. `OFFSET` in `backend/app/` (forbidden)
2. `api_key\s*=\s*['"]` and `secret\s*=\s*['"]` (no hardcoded secrets)
3. `print(` in `backend/app/` (use logging instead)
4. `user_id.*body|body.*user_id` in routes (never accept user_id from client)
5. `async def` in routes and services (all must be async)
6. `/conversations` in routes (forbidden path segment for mobile-facing endpoints)
7. `TODO|FIXME` in implementation files
8. f-string SQL patterns (SQL injection check)

## Chat Streaming Review Notes
- Validation-before-streaming: `validate_send_message()` runs BEFORE `StreamingResponse` is created; HTTPExceptions produce proper 4xx JSON errors
- Background tasks use `AsyncSessionLocal()` (own session), NOT request-scoped `db`
- Mem0 SDK is synchronous; all calls wrapped in `asyncio.to_thread()`
- SSE events use JSON `type` field (no SSE `event:` header)
- Message model uses `metadata_` (Python name) mapped to `metadata` (column name) via `mapped_column("metadata", JSONB)`
- `asyncio.gather(..., return_exceptions=True)` for Mem0 resilience

## Memory Endpoints Review Notes
- MemoryService creates fresh MemoryClient per call (no shared state) -- good pattern
- Two routers in one module: `global_router` (prefix `/api/v1`) and `character_router` (prefix `/api/v1/characters`)
- `memory_id` is `str`, not `uuid.UUID` (Mem0 IDs are opaque strings)
- Idempotent delete: checks `exc_str.lower()` for "not found" or "404"
- Backend-tester created SEPARATE `_extended.py` files this time (not appended to originals)
- 110 total tests at 100% coverage

## Onboarding Endpoint Review Notes
- Single endpoint: POST /api/v1/onboarding/complete (router prefix set in main.py)
- Global Mem0 scope: `user_id` only, NO `agent_id` -- onboarding facts visible to all characters
- Retry-safe ordering: Haiku (stateless) -> Mem0 (idempotent) -> DB flag update
- `except HTTPException: raise` before generic `except Exception` -- critical for preserving 429 etc.
- Claude SDK is natively async (AsyncAnthropic), Mem0 SDK is sync (wrapped in asyncio.to_thread)
- Fallback templates in `_FALLBACK_TEMPLATES` dict when Haiku returns unparseable output
- Pydantic validates max_length BEFORE field_validator strip() runs (documented in tests)
- Backend-tester created SEPARATE `_extended.py` files (consistent with memory-endpoints pattern)
- 131 total tests at 100% line + branch coverage

## Media Upload Review Notes
- Single endpoint: POST /api/v1/media/upload-url (no DB interaction)
- Module-level boto3 S3 client (`_s3_client`) reused across requests (unlike Mem0 which is per-call)
- `generate_presigned_url` wrapped in `asyncio.to_thread()` for safety (even though it's local HMAC signing)
- Presigned URL NOT logged (security: contains AWS credentials in query params) -- only user_id and s3_key logged
- `_sanitize_filename()` is a module-level function (not a method), tested with 27 edge cases
- Pydantic validator rejects path traversal (`..`, `/`, `\`, null bytes) at input level; service sanitizes further
- `ALLOWED_CONTENT_TYPES` uses `frozenset` for immutability
- `except (ClientError, Exception)` catches both specific and generic boto3 errors
- `raise HTTPException(...) from None` suppresses exception chaining in 503 response
- Backend-tester created SEPARATE `_extended.py` file (consistent pattern)
- 137 total tests at 100% line + branch coverage

## FCM Push Service Review Notes
- Two endpoints: PUT and DELETE /api/v1/notifications/token (router prefix in main.py)
- Routes do simple CRUD directly (no service layer needed for token registration)
- NotificationService wraps `send_push_notification` with user lookup + dead token cleanup
- `_clear_token` uses `except Exception` with `logger.exception()` -- errors don't propagate
- `SendResult` is a class with string constants (SENT, INVALID_TOKEN, TRANSIENT_ERROR), not an enum
- Backend-tester created SEPARATE `_extended.py` files (consistent pattern)
- 67 total tests at 100% coverage

## iOS Cognito Auth Review Notes
- Auth goes through backend REST endpoints (not Amplify SDK) -- correct per spec
- AuthService makes own URLSession calls to avoid circular dependency with APIClient
- AuthViewModel is the reactive bridge (AuthService is @unchecked Sendable, not @Observable)
- KeychainTokenStore uses Security framework with kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
- `@AppStorage("isAuthenticated")` fully replaced by AuthViewModel.isAuthenticated
- LoginPlaceholderView deleted, replaced by real LoginView + SignUpView
- MockAuthService and MockURLProtocol used for testing
- Force unwrap on URL literal `URL(string: "https://api.ember.ai")!` is acceptable (known-valid, after ?? fallback)
- 45 total tests across 3 test files

## iOS Grep Checks to Always Run
1. `ObservableObject|@Published|@StateObject` in `ios/Ember/` (forbidden)
2. `NavigationView` in `ios/Ember/` (forbidden)
3. `UserDefaults` in `ios/Ember/Core/Auth/` (forbidden -- use Keychain)
4. `api_key\s*=\s*['"]|secret\s*=\s*['"]` (no hardcoded secrets)
5. `Amplify|AWSCognito` in `ios/Ember/` (no Amplify imports in production code)
6. `print(` in `ios/Ember/` (use logging/os_log instead)
7. `\)!` for force unwraps -- verify each is on a known-valid literal

## Completed Reviews
- P01-05 character-crud (backend layer): APPROVED 2026-02-23, 0 issues found
- P01-06 chat-streaming (backend layer): APPROVED 2026-02-24, 0 issues found, 130 tests at 100% coverage
- P01-08 memory-endpoints (backend layer): APPROVED 2026-02-24, 0 issues found, 110 tests at 100% coverage
- P01-09 onboarding-endpoint (backend layer): APPROVED 2026-02-24, 0 issues found, 131 tests at 100% coverage
- P01-10 media-upload (backend layer): APPROVED 2026-02-24, 0 issues found, 137 tests at 100% coverage
- P02-03 fcm-push-service (backend layer): APPROVED 2026-03-13, 0 issues found, 67 tests at 100% coverage
- P03-03 ios-cognito-auth (ios layer): APPROVED 2026-03-13, 0 issues found, 45 tests, 2 warnings
