# Observability Stack

> Adds structured logging (structlog), per-request correlation IDs, Sentry error tracking, external API call timing, and dependency-aware health checks to the Ember backend.

**Status**: Released
**Added in**: Phase 1.5 (P1.5-03)
**Platforms**: Backend
**GitHub Issue**: #85

---

## Overview

Prior to this feature the Ember backend produced log output via a hand-rolled `logging.Formatter` that built JSON strings through string interpolation. That approach silently broke whenever a log message contained JSON special characters, produced no structured fields (key-value pairs were concatenated into strings), and gave no way to correlate all log entries produced by a single request. Without request correlation, tracing a production issue across a high-concurrency server required manually matching timestamps across hundreds of interleaved log lines.

This feature replaces that fragile formatter with `structlog`, which serializes Python dicts to JSON natively. Every log entry automatically carries the fields needed for CloudWatch log insights — `timestamp`, `level`, `logger`, `event`, and any context variables bound to the current async task. A new `RequestIDMiddleware` runs as the outermost layer of the ASGI stack and seeds that per-task context with a `request_id` UUID on every incoming request. Authenticated requests also carry `user_id` extracted from the JWT so that all log lines for a request reference the acting user without any change to route handlers or services.

The feature also adds three capabilities that were absent entirely: Sentry SDK integration for error tracking and alerting on unhandled exceptions; a reusable `log_external_call` async context manager that emits a `duration_ms` / `success` log entry around every call to Mem0, Claude, S3, and Cognito JWKS; and an enhanced `GET /api/v1/health` endpoint that can optionally probe all three upstream dependencies in parallel and report whether each one is `"ok"`, `"degraded"`, or `"unavailable"`.

---

## Architecture

### How It Works (Data Flow)

1. An HTTP request enters the ASGI stack. `RequestIDMiddleware` is the outermost middleware (registered last in `main.py` so that Starlette applies it first).
2. The middleware reads the `X-Request-ID` request header. If it is present and 1–128 alphanumeric-plus-hyphen characters, that value is used; otherwise a UUID v4 is generated.
3. `structlog.contextvars.bind_contextvars(request_id=...)` stores the ID in the current asyncio task context. If the request carries a `Bearer` token, `_extract_sub_from_jwt` decodes the payload without signature verification and also binds `user_id`.
4. `sentry_sdk.set_tag("request_id", ...)` associates the ID with any Sentry events that arise from this request.
5. The middleware logs `request_started` with the HTTP method and path, then calls `await call_next(request)`.
6. Inside route handlers and services, calls to Mem0, Claude, S3, and Cognito JWKS are wrapped in `async with log_external_call(service, operation)`. This records `time.monotonic()` before and after the call and emits an `external_call` log entry with `service`, `operation`, `duration_ms`, and `success` fields. On exception it logs `success=False` with the error type and re-raises.
7. structlog's `merge_contextvars` processor automatically includes `request_id` and `user_id` in every log entry, regardless of which module emits it.
8. After `call_next` returns, the middleware logs `request_completed` (or `request_failed` on an unhandled exception) with `status_code` and `duration_ms`, appends `X-Request-ID` to the response headers, then clears the structlog contextvars to prevent leakage into subsequent requests on the same task.
9. In production (`debug=False`) all log entries are JSON lines on stdout, ingested by CloudWatch. In development (`debug=True`) the `ConsoleRenderer` produces colored, human-readable output.

### Middleware Stack Ordering

Starlette applies middleware in reverse of `add_middleware` registration order (last registered = outermost at request time). The registration sequence in `main.py` is:

```
app.add_middleware(RateLimitMiddleware, ...)   # innermost
app.add_middleware(CORSMiddleware, ...)
app.add_middleware(RequestIDMiddleware)        # outermost (registered last)
```

Runtime request flow: `RequestIDMiddleware → CORSMiddleware → RateLimitMiddleware → route`

This ordering ensures that `X-Request-ID` is present on all responses including CORS preflights and 429 rate-limit responses, and that all log entries from the rate limiter already have `request_id` bound.

### structlog Pipeline

`setup_logging()` in `backend/app/core/logging.py` configures two pipelines that share the same processor chain:

**Shared processors** (applied to every entry):
- `merge_contextvars` — pulls `request_id`, `user_id`, and any other bound values into the entry
- `add_log_level` — adds `level` field
- `add_logger_name` — adds `logger` field
- `TimeStamper(fmt="iso")` — adds `timestamp` in ISO 8601
- `StackInfoRenderer`, `format_exc_info`, `UnicodeDecoder`

**Output renderer** (final processor):
- Production: `JSONRenderer()` — JSON lines to stdout
- Development: `ConsoleRenderer()` — colored human-readable output

The stdlib integration is achieved via `ProcessorFormatter`, which applies the same shared processors to all stdlib `logging.getLogger()` calls. No existing call site in the codebase needed to change.

### SSE Streaming Considerations

For SSE endpoints (chat streaming), `RequestIDMiddleware.dispatch` wraps the entire stream lifecycle. `call_next` does not return until the SSE stream closes. The `request_completed` log entry and `clear_contextvars()` call therefore happen after the last SSE chunk is sent, which is correct: the `request_id` remains bound and visible in all log entries throughout the stream.

For `log_external_call` around Claude streaming, the context manager wraps the entire `async with client.messages.stream()` block including iteration, so `duration_ms` captures total streaming duration rather than just the initial connection latency.

### Sentry Integration

`init_sentry()` in `backend/app/core/sentry.py` is called during `lifespan()` startup. If `SENTRY_DSN` is empty (the default), Sentry is not initialized and the function returns silently. This keeps Sentry entirely optional — the app runs normally without it.

When a DSN is configured, the SDK is initialized with `send_default_pii=False` to comply with the no-PII-in-logs policy, and a `before_send` hook (`_scrub_event`) strips the `Authorization` header from all Sentry event request data before transmission. `FastApiIntegration` automatically captures unhandled exceptions as Sentry issues and names transactions by endpoint path.

### Dependency Health Probing

`HealthService.check_dependencies()` runs three probes in parallel via `asyncio.gather(return_exceptions=True)`. Each probe is independently wrapped in try/except with `asyncio.wait_for` to enforce a configurable timeout (default 3 s). Response time is compared against a second threshold (default 1 s) to distinguish "ok" from "degraded":

| Probe result | Status |
|---|---|
| Responds within 1 s | `"ok"` |
| Responds between 1 s and 3 s | `"degraded"` |
| Times out or throws | `"unavailable"` |

The probes are:
- **database**: `SELECT 1` via the async SQLAlchemy session
- **mem0**: `MemoryClient.search("health_check", user_id="health_probe", limit=1)` via `asyncio.to_thread`
- **claude**: `AsyncAnthropic.messages.create(max_tokens=1, messages=[{"role": "user", "content": "hi"}])`

A failed probe returns `"unavailable"` for that dependency without affecting the others. The HTTP status code is always 200 — dependency failures do not cause ECS health probes to fail, which would trigger unnecessary task replacement during upstream outages.

### No Database Schema Changes

This feature does not create or modify any database tables. All observability state is transient.

---

## API Reference

See [`docs/04-veri-api.md`](../04-veri-api.md) for the full API contract.

### `GET /api/v1/health`

**Auth**: Not required
**Query parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `check_dependencies` | boolean | `false` | When `true`, probes database, Mem0, and Claude before responding |

**Response (without `check_dependencies`)** — fast path used by ECS probes:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "dependencies": null
}
```

**Response (with `check_dependencies=true`)** — used by dashboards and manual debugging:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "dependencies": {
    "database": "ok",
    "mem0": "degraded",
    "claude": "ok"
  }
}
```

The top-level `status` is always `"ok"` as long as the backend process is running. Dependency values are `"ok"`, `"degraded"`, or `"unavailable"`.

**Important**: The `dependencies` field was `null` in the previous health response schema and remains `null` by default, preserving backward compatibility with ECS health probes that only inspect `status`.

### `X-Request-ID` Response Header

Every response from every endpoint now includes an `X-Request-ID` header. The value is either echoed from the client's `X-Request-ID` request header (if valid format) or a newly generated UUID v4.

**Validation rule**: Client-supplied request IDs must match `^[a-zA-Z0-9\-]{1,128}$`. Invalid values are ignored and a new UUID is generated.

---

## Configuration

Six new fields were added to `backend/app/config.py`:

| Environment Variable | Config Field | Type | Default | Description |
|---------------------|-------------|------|---------|-------------|
| `SENTRY_DSN` | `sentry_dsn` | `str` | `""` | Sentry DSN. Empty string disables Sentry entirely. |
| `SENTRY_ENVIRONMENT` | `sentry_environment` | `str` | `"development"` | Sentry environment tag (`development`, `staging`, `production`). |
| `SENTRY_TRACES_SAMPLE_RATE` | `sentry_traces_sample_rate` | `float` | `0.1` | Fraction of transactions to trace for performance monitoring (0.0–1.0). |
| `HEALTH_CHECK_TIMEOUT` | `health_check_timeout` | `float` | `3.0` | Per-probe timeout in seconds. |
| `HEALTH_CHECK_DEGRADED_THRESHOLD` | `health_check_degraded_threshold` | `float` | `1.0` | Response time in seconds above which a dependency is reported as `"degraded"`. |
| `LOG_REQUEST_BODY` | `log_request_body` | `bool` | `False` | Whether to log request bodies. Always `False` in production; useful for local debugging only. |

---

## Backend Implementation

### Module Layout

| File | Role |
|------|------|
| `backend/app/core/logging.py` | `setup_logging()` — structlog configuration with stdlib integration |
| `backend/app/core/sentry.py` | `init_sentry()`, `_scrub_event()` — Sentry initialization and PII scrubbing |
| `backend/app/middleware/request_id.py` | `RequestIDMiddleware`, `_extract_sub_from_jwt()` |
| `backend/app/utils/timing.py` | `log_external_call(service, operation)` async context manager |
| `backend/app/services/health_service.py` | `HealthService.check_dependencies()` and per-dependency probe methods |
| `backend/app/routes/health.py` | Health route handler with `check_dependencies` query param |
| `backend/app/schemas/health.py` | `DependencyStatus`, updated `HealthResponse` with optional `dependencies` field |

### New Dependencies

Two packages added to `backend/requirements.txt`:

```
structlog>=24.1.0,<25.0.0
sentry-sdk[fastapi]>=2.0.0,<3.0.0
```

### External Call Instrumentation Sites

The `log_external_call` context manager was applied at the following call sites:

| Service | Operation | File |
|---------|-----------|------|
| `claude` | `stream` | `app/services/chat_service.py` |
| `claude` | `create` | `app/services/chat_service.py` |
| `mem0` | `search` | `app/services/chat_service.py` |
| `mem0` | `add` | `app/services/chat_service.py` |
| `mem0` | `get_all` | `app/services/memory_service.py` |
| `mem0` | `delete` | `app/services/memory_service.py` |
| `cognito` | `jwks_fetch` | `app/core/auth.py` |
| `s3` | `generate_presigned_url` | `app/services/media_service.py` |

### Log Entry Examples

Production JSON log (all entries include `request_id` automatically):

```json
{"timestamp":"2026-03-13T14:30:00.123Z","level":"info","logger":"ember","request_id":"550e8400-e29b-41d4-a716-446655440000","user_id":"usr_abc123","event":"external_call","service":"mem0","operation":"search","duration_ms":145,"success":true}
```

Development console log:

```
2026-03-13 14:30:00 [info     ] external_call    duration_ms=145 operation=search request_id=550e8400... service=mem0 success=True user_id=usr_abc123
```

### Fail-Open Guarantees

All observability components are fail-open:
- **Sentry init failure**: logs a warning, app starts normally.
- **Request ID middleware error**: falls back to a new UUID, never blocks a request.
- **Timing context manager**: always re-raises exceptions from the wrapped call; a failure in the logging itself does not swallow the original exception.
- **Health check probe failure**: returns `"unavailable"` for that dependency only; other probes continue unaffected.

---

## Testing

### Coverage Summary

| Module | Line Coverage |
|--------|--------------|
| `app/core/logging.py` | 100% |
| `app/core/sentry.py` | 100% |
| `app/middleware/request_id.py` | 97% |
| `app/utils/timing.py` | 100% |
| `app/services/health_service.py` | 94% |
| `app/routes/health.py` | 100% |
| **Overall** | **97%** |

### Test Files

| File | Tests | What Is Covered |
|------|-------|-----------------|
| `tests/infra/test_logging.py` | 9 | structlog JSON/console output, context variable propagation, logger level suppression, exception formatting |
| `tests/infra/test_sentry.py` | 6 | `init_sentry` enable/disable, `_scrub_event` Authorization header removal, init failure handling |
| `tests/utils/test_timing.py` | 5 | Success/failure paths of `log_external_call`, exception re-raise, log field correctness |
| `tests/middleware/test_request_id.py` | 23 | UUID generation, client ID echo, invalid ID rejection, log correlation, user ID binding, context clearing, 429 header presence |
| `tests/infra/test_health.py` | 23 | Fast path vs. dependency probe path, `"ok"`/`"degraded"`/`"unavailable"` status mapping, parallel execution, HTTP 200 on all-unavailable state |
| **Total** | **66** | |

### Running Tests

Observability tests only:

```bash
cd /path/to/ember/backend && python -m pytest tests/infra/test_logging.py tests/infra/test_sentry.py tests/utils/test_timing.py tests/middleware/test_request_id.py tests/infra/test_health.py -v
```

Full backend suite:

```bash
cd /path/to/ember/backend && python -m pytest tests/ -v
```

### Intentionally Uncovered Lines

- `request_id.py` lines 101–102: The `sentry_sdk.set_tag` call is always guarded by a silent `try/except`. It only does anything when Sentry is initialized, which requires a real DSN. Sentry initialization is covered separately in `test_sentry.py`.
- `health_service.py` lines 95–96, 125–126: The inner `_do_probe()` coroutine bodies that construct real `MemoryClient` and `AsyncAnthropic` instances require live API credentials and are excluded from unit tests by design.

---

## Known Limitations

- **No distributed tracing**: Request ID correlation is scoped to a single Ember process. Cross-service trace propagation (e.g., from the Ember backend into Mem0 or Claude API call graphs) requires OpenTelemetry and is not implemented. The `request_id` tag on Sentry events is the only cross-system correlation mechanism.
- **In-process context only**: `structlog.contextvars` binds to the current asyncio task. Background tasks spawned with `asyncio.create_task()` or `BackgroundTasks` do not inherit the parent context unless the calling code explicitly propagates it.
- **Sentry profiles_sample_rate not configurable**: The `profiles_sample_rate=0.1` value is hardcoded in `init_sentry()` and is not exposed as a config field. To change it, modify `backend/app/core/sentry.py` directly.
- **Mem0 health probe creates a real API client per call**: `_probe_mem0` constructs a fresh `MemoryClient` on each `check_dependencies=true` request. This is acceptable for infrequent monitoring use but would be wasteful if health probes ran frequently.
- **Query parameters are never logged**: The middleware intentionally omits query strings from `request_started` and `request_completed` log entries to avoid inadvertently logging tokens or sensitive parameters. This makes debugging query-parameter-dependent behavior slightly harder.

---

## Extending This Feature

**Adding a new external call site**: Wrap any new external API call in `async with log_external_call("service_name", "operation_name"):` imported from `app.utils.timing`. No other changes are needed — the context manager emits the `external_call` log entry automatically, and `request_id` is included via contextvars.

**Adding a new dependency probe to the health check**: Add a `_probe_{name}` async method to `HealthService` following the pattern of `_probe_database`. Add it to the `asyncio.gather` call in `check_dependencies`, update the `DependencyStatus` Pydantic model in `app/schemas/health.py`, and add corresponding test cases to `tests/infra/test_health.py`.

**Switching the output format**: The renderer is the final processor in the shared chain. To switch from JSON lines to a different format (e.g., logfmt), replace `structlog.processors.JSONRenderer()` with the desired renderer in `setup_logging()` in `app/core/logging.py`. The structlog processor chain before the renderer does not need to change.

**Enriching log context**: To add a new field to all log entries within a request (e.g., `character_id`), call `structlog.contextvars.bind_contextvars(character_id=...)` anywhere during the request lifecycle. The field will appear in all subsequent log entries for that request automatically. Clear it explicitly if it should not persist for the whole request.

**Enabling Sentry in a new environment**: Set `SENTRY_DSN` to the project DSN from the Sentry dashboard and `SENTRY_ENVIRONMENT` to the environment name (e.g., `staging`). No code changes are required.

---

## Related Documentation

- [Database Schema and API Endpoints](../04-veri-api.md)
- [Security and Performance Standards](../08-guvenlik-performans.md) — Section 8 (no-PII logging policy) and Section 9 (performance targets that timing metrics monitor)
- [Deployment Architecture](../09-dagitim.md) — CloudWatch log ingestion, ECS health check configuration
- [Rate Limiting Middleware](./rate-limiting-middleware.md) — P1.5-01; sits inside `RequestIDMiddleware` in the middleware stack
- [Chat Streaming](./chat-streaming.md) — P01-06; the primary beneficiary of `log_external_call` instrumentation on Claude and Mem0
