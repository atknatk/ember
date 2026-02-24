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

## Completed Reviews
- P01-05 character-crud (backend layer): APPROVED 2026-02-23, 0 issues found
- P01-06 chat-streaming (backend layer): APPROVED 2026-02-24, 0 issues found, 130 tests at 100% coverage
- P01-08 memory-endpoints (backend layer): APPROVED 2026-02-24, 0 issues found, 110 tests at 100% coverage
