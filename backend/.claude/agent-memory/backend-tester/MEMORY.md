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

## OpenAPI / YAML Spec Test Patterns
- `load_yaml_specs()` returns path KEYS (14 in the current spec), not endpoint+method count (19)
- Scripts in `backend/scripts/` can be imported via `sys.path.insert(0, str(backend_dir))` in test files
- For `--cov` on scripts: use `--cov=scripts.validate_openapi` (dotted module path, not file path)
- `capsys` fixture captures `print()` output; useful for testing warning/error print paths in scripts
- `tmp_path` fixture (built-in pytest) creates a temp directory for tests that need to write YAML files
- For CLI `sys.exit()` tests: use `pytest.raises(SystemExit)` and check `.code`
- `get_path_params`, `extract_required_fields`, `resolve_ref` are all importable from `scripts.validate_openapi`
- `main()` CLI entry points are intentionally left uncovered -- subprocess testing adds fragility

## Activity Tracking Middleware Test Patterns
- Mock path for middleware unit tests: `app.middleware.activity_tracking.update_user_activity`
- Mock path for service unit tests: `app.services.activity_service.AsyncSessionLocal`
- `_mock_session_factory(session_mock)` helper creates a MagicMock ctx with `__aenter__`/`__aexit__` AsyncMock
- BackgroundTask chaining: when `response.background` is already a `BackgroundTasks` (plural) instance, the implementation appends via `tasks.tasks.append()` — test by asserting both the original task AND the activity task execute
- `caplog.at_level(logging.WARNING, logger="ember")` works directly for `logging.getLogger("ember")` calls in activity_service (no custom handler needed — caplog captures stdlib logging)
- `now` in service SQL params is a timezone-aware `datetime` object; verify with `isinstance(params["now"], datetime)` and `params["now"].tzinfo is not None`

## Content Moderation Test Patterns
- `ChatService._llm_router` is a `@property` — use `ChatService(db, llm_router=mock_router)` constructor param instead of `patch.object(service, "_llm_router")`
- Rolling window boundary tests: "exactly 24h ago" is unreliable because `datetime.now()` inside the function advances microseconds. Use 23h59m (clearly in-window) and 24h+1s (clearly expired) instead
- `MagicMock` datetime arithmetic returns truthy MagicMock — use real `UserModerationState` objects when testing datetime subtraction in `_update_abuse_state`
- `_record_violation_background` uses a custom `MockSession` class (not AsyncMock) to capture `db.add()` objects for `isinstance(obj, ModerationEvent)` checks
- `prompt_injection` and `length_exceeded` event types do NOT call `_update_abuse_state`; only `harmful_content` and `abuse_block` do
- Pydantic validates content length (max_length=4000) before the route handler — a 4001-char HTTP request returns 422, not 400. Service-layer 400 only reachable via direct calls.

## Notification Scheduler Test Patterns
- `evaluate_notification_triggers` is a pure function — test directly, no mocks needed
- Mock `app.services.notification_scheduler._search_mem0` for Mem0 tests (not the MemoryClient directly)
- Mock `app.services.notification_scheduler.get_llm_router` for Claude tests
- Mock `app.services.notification_sender.messaging.send` for FCM tests
- Mock `app.services.notification_scheduler.AsyncSessionLocal` for DB session tests
- `run_notification_cycle(now_utc=...)` and `reset_notifications_sent_today(now_utc=...)` accept optional override for deterministic time testing
- DST hazard: America/New_York is UTC-4 (not UTC-5) from mid-March onward due to DST — always verify UTC offset at the specific test date using `ZoneInfo` and `astimezone`
- `_search_mem0` direct body (lines 525-526) is always mocked via `asyncio.to_thread` in unit tests — unreachable without real Mem0 credentials; this is acceptable
- `firebase_admin.exceptions.InvalidArgumentError` (not `messaging.InvalidArgumentError`) is the correct import for the invalid-token error class
- APScheduler 4.x uses `stop()` not `shutdown()` for graceful teardown

## Circuit Breaker Test Patterns
- Reset singleton between tests: conftest.py autouse fixture sets `app.core.circuit_breaker._breaker = None`
- Save and restore original `cb_module._breaker` in each test that injects a custom instance (`original = cb_module._breaker; cb_module._breaker = ...; try/finally`)
- To test `CircuitOpenError` from `call_with_breaker` (race path), use `patch.object(breaker, "call_with_breaker", side_effect=CircuitOpenError(...))`
- TTL boundary: at exactly TTL, entry is valid (condition is `elapsed > ttl`); at TTL+epsilon, expired
- `drain_retry_queue` failures must NOT open the circuit even with `failure_threshold=1` -- drain uses `logger.warning`, not `record_failure()`
