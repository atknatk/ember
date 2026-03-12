# Backend Dev Handoff: Observability Stack

**Date**: 2026-03-13
**Agent**: backend-dev
**Status**: COMPLETE

## Implemented Files

### Created
- `backend/app/core/sentry.py` — Sentry SDK initialization with PII scrubbing
- `backend/app/middleware/request_id.py` — X-Request-ID middleware with structlog contextvars
- `backend/app/utils/timing.py` — Async context manager for timing external API calls
- `backend/app/services/health_service.py` — Dependency probing service (DB, Mem0, Claude)
- `backend/tests/infra/test_sentry.py` — 6 Sentry integration tests
- `backend/tests/middleware/test_request_id.py` — 7 request ID middleware tests
- `backend/tests/utils/__init__.py` — Test package init
- `backend/tests/utils/test_timing.py` — 5 timing utility tests

### Modified
- `backend/app/core/logging.py` — Full rewrite: structlog with ProcessorFormatter, contextvars, JSON/Console rendering
- `backend/app/config.py` — Added 6 new config fields (sentry_dsn, sentry_environment, sentry_traces_sample_rate, health_check_timeout, health_check_degraded_threshold, log_request_body)
- `backend/app/schemas/health.py` — Added DependencyStatus model, optional dependencies field on HealthResponse
- `backend/app/routes/health.py` — Added check_dependencies query parameter, db dependency
- `backend/app/main.py` — Registered RequestIDMiddleware (outermost), call init_sentry() in lifespan
- `backend/app/services/chat_service.py` — Wrapped Claude stream, Claude create, Mem0 search, Mem0 add with log_external_call
- `backend/app/services/memory_service.py` — Wrapped Mem0 get_all, delete, delete_all with log_external_call
- `backend/app/services/media_service.py` — Wrapped S3 generate_presigned_url with log_external_call
- `backend/app/core/auth.py` — Wrapped Cognito JWKS fetch with log_external_call
- `backend/requirements.txt` — Added structlog>=24.1.0,<25.0.0 and sentry-sdk[fastapi]>=2.0.0,<3.0.0
- `backend/tests/infra/test_logging.py` — Full rewrite: 9 tests for structlog configuration
- `backend/tests/infra/test_health.py` — Extended: 9 tests including dependency check scenarios
- `backend/tests/infra/test_schemas.py` — Updated health response serialization test for new dependencies field

## Endpoints Implemented
- `GET /api/v1/health` — Enhanced with optional `check_dependencies=true` query parameter
- All endpoints now return `X-Request-ID` response header

## Test Results
- pytest (excluding pre-existing infra failures): 1254 passed, 0 new failures
- New observability tests: 36 passed
- ruff check app/: clean (0 errors)

## Known Issues / Deviations from Spec
- None. All spec requirements implemented as designed.
- Pre-existing test failures in `tests/infra/test_config.py` (wrong path resolution for `.env.example`, `requirements.txt`, `pyproject.toml`) and `tests/infra/test_docker.py` (missing Docker files) are unrelated to this feature.

## Notes for Backend Tester

### Mocking Requirements
- **structlog**: Use `structlog.testing.capture_logs()` for structlog-native loggers, or add a custom `logging.Handler` to the `"ember"` stdlib logger for stdlib-based log capture.
- **Sentry**: Mock `sentry_sdk.init` and `sentry_sdk.set_tag` with `unittest.mock.patch`. Also mock `app.core.sentry.settings` to control DSN.
- **Timing**: The `log_external_call` context manager uses `time.monotonic()` internally. For deterministic tests, mock `time.monotonic` via `unittest.mock.patch("app.utils.timing.time.monotonic")`.
- **Health check probes**: Mock `HealthService._probe_database`, `_probe_mem0`, `_probe_claude` as `AsyncMock` returning status strings.

### Key Behaviors to Verify
- Request ID middleware clears `structlog.contextvars` between requests (no leakage)
- Sentry is completely optional (empty DSN = no initialization)
- `_scrub_event` removes both `Authorization` and `authorization` header casing
- Health check always returns HTTP 200 even when all dependencies are unavailable
- Timing context manager never swallows exceptions from wrapped calls
- structlog `foreign_pre_chain` ensures stdlib logger extra fields (service, operation, duration_ms) appear in JSON output

### Edge Cases
- Request ID validation: accepts 1-128 chars alphanumeric+hyphens, rejects anything else
- SSE streaming: request ID middleware's `dispatch` wraps the entire stream lifecycle; context cleanup happens after stream ends
- The `check_dependencies=false` (default) path does NOT execute any DB query, making it safe for ECS probes
