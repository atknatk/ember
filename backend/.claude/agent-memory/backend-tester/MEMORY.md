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
- Backend-dev writes initial tests using classes (TestFeatureName); tester should also use classes to match style
- Commit format: `test({feature}): description [agent:backend-tester] [platform:backend]`

## zoneinfo Behavior (Python 3.12)
- `ZoneInfo('utc')` is VALID -- lowercase 'utc' accepted; do not test it as invalid
- `ZoneInfo('')` raises `ValueError` (not `ZoneInfoNotFoundError` or `KeyError`), so the profile schema validator's except clause does NOT catch empty string -- Pydantic still raises 422 but with a different message than "Invalid IANA timezone"

## --cov flag format
- Use `--cov=app` (package name) not `--cov=app/routes/profile` (file path) to get coverage data; file paths cause "module-not-imported" warnings and no data

## Known Crashing Endpoints (avoid in integration tests)
- `POST /api/v1/auth/login` and other auth routes hit Cognito via `asyncio.to_thread` -- crash with `anyio.EndOfStream` in ASGITransport when credentials are empty (test env). Use direct service/RateLimiter unit tests for coverage of these paths instead.

## structlog / stdlib Logging in Tests
- `structlog.testing.capture_logs()` only captures structlog-native logger calls (`structlog.get_logger()`), NOT stdlib `logging.getLogger("ember")` calls
- For middleware/services that use `logging.getLogger("ember")`, use a custom `_RecordHandler` attached directly to that logger
- Pattern: `handler = _RecordHandler(); logger.addHandler(handler)` -- see `tests/utils/test_timing.py` for the fixture pattern
- The middleware `RequestIDMiddleware` uses stdlib `logging.getLogger("ember")`, so capture with a stdlib handler

## Health Service Probe Mocking
- `MemoryClient` and `AsyncAnthropic` are imported locally inside `_probe_mem0` / `_probe_claude` methods -- cannot patch at `app.services.health_service.MemoryClient`
- Best approach: patch `app.services.health_service.asyncio.wait_for` to raise/sleep/return as needed
- This avoids RuntimeWarning for unawaited coroutines too (wait_for mock replaces the whole await)

## Middleware Dispatch Direct Testing
- To test specific status code log levels in `RequestIDMiddleware`, instantiate middleware directly and call `dispatch(request, mock_call_next)` -- avoids the complexity of FastAPI route patching
- Build minimal Starlette Request: `Request({"type": "http", "method": "GET", "path": "/", "query_string": b"", "headers": []})`
- `StarletteResponse(status_code=500)` from `starlette.responses` works as mock response

## Circuit Breaker Test Patterns
- Reset singleton between tests: conftest.py autouse fixture sets `app.core.circuit_breaker._breaker = None`
- Save and restore original `cb_module._breaker` in each test that injects a custom instance (`original = cb_module._breaker; cb_module._breaker = ...; try/finally`)
- To test `CircuitOpenError` from `call_with_breaker` (race path), use `patch.object(breaker, "call_with_breaker", side_effect=CircuitOpenError(...))`
- TTL boundary: at exactly TTL, entry is valid (condition is `elapsed > ttl`); at TTL+epsilon, expired
- `drain_retry_queue` failures must NOT open the circuit even with `failure_threshold=1` -- drain uses `logger.warning`, not `record_failure()`
