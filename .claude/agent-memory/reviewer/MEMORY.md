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
- Backend-tester adds `_extended.py` test files alongside backend-dev's base test files
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

## Completed Reviews
- P01-05 character-crud (backend layer): APPROVED 2026-02-23, 0 issues found
