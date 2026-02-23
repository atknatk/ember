# Backend Tester Memory

## Project Structure
- Backend root: `backend/`
- Tests: `backend/tests/`
- conftest.py sets `DEBUG=true` and test `DATABASE_URL` via `os.environ.setdefault()` before any app imports
- venv: `backend/.venv/`
- Run tests: `backend/.venv/bin/python -m pytest backend/tests/ -v`

## Key Patterns
- Use `_env_file=None` when constructing `Settings()` in config tests to avoid reading `.env`
- Even with `_env_file=None`, pydantic-settings still reads from `os.environ` -- must save/restore env vars for secret default tests
- For exception handler tests, use `ASGITransport(raise_app_exceptions=False)` to prevent Starlette middleware from propagating errors
- For lifespan tests, use `unittest.mock.patch` on `app.main.setup_logging` and `app.main.engine` (with AsyncMock for dispose)
- TimestampMixin columns accessible via `TimestampMixin.__dict__["field_name"].column`
- Engine pool config: `engine.pool.size()` for pool_size, `engine.pool._pre_ping` for pre_ping
- Session factory config: `AsyncSessionLocal.kw` dict for expire_on_commit/autoflush, `.class_` for session class

## Coverage Notes
- `app/config.py` AWS Secrets Manager path (lines ~24, 80-82) intentionally uncovered -- requires real AWS
- `app/dependencies.py` get_db yield body (lines ~20-21) uncovered -- requires real DB connection
- Testing standards doc: `docs/standards/testing.md`
- Coverage target: >=80% lines, >=70% branches

## Style
- Test functions: `async def test_{what}_{condition}_{expected}`
- No test classes used in this project (flat functions with pytest.mark.asyncio)
- Commit format: `test({feature}): description [agent:backend-tester] [platform:backend]`
