# Feature Spec: P1.5-03 -- Observability Stack

**Feature ID**: P1.5-03
**Phase**: 1.5
**Layer**: backend
**GitHub Issue**: #85
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature replaces the existing `logging.Formatter`-based structured logging in `backend/app/core/logging.py` with `structlog`, adds a request ID middleware that injects an `X-Request-ID` header into every request/response and propagates it through all log entries, integrates Sentry for error tracking, adds timing instrumentation for all external API calls (Mem0, Claude, S3, Cognito JWKS), and extends the health check endpoint to report dependency status metrics.

### Why It Exists

The current logging setup (`app/core/logging.py`) produces a hand-rolled JSON format using `logging.Formatter` string interpolation. This is fragile: it does not handle structured fields (key-value pairs), does not escape JSON special characters in messages, and makes it difficult to correlate log entries across a single request. Per `docs/standards/common.md` Section 8: "In production: structured logging (JSON) to CloudWatch." The current implementation technically emits JSON but lacks the reliability and flexibility needed for production observability.

Without request ID correlation, debugging production issues requires manually matching log timestamps across hundreds of concurrent requests. Without Sentry, unhandled exceptions are only visible in CloudWatch logs -- there is no alerting, no issue tracking, and no stack trace grouping. Without timing instrumentation, the performance targets in `docs/standards/common.md` Section 9 (e.g., "Memory search (Mem0) < 800ms", "API p99 latency < 5000ms") cannot be monitored.

### Dependencies

- **Requires**: P01-01 (project-setup -- FastAPI scaffold, `main.py`, `config.py`, `core/logging.py`)
- **Extends**: The existing `core/logging.py` module (full rewrite, not incremental modification)
- **Extends**: The existing `middleware/` directory (new `request_id.py` middleware)
- **Extends**: The existing `routes/health.py` (enhanced health check response)

### What This Feature Does NOT Do

- It does not add APM (Application Performance Monitoring) dashboards. Timing metrics are logged as structured fields; dashboard creation is a future operational task.
- It does not add distributed tracing (OpenTelemetry). Request ID correlation within a single service is sufficient for Phase 1.5 with a single ECS task.
- It does not add custom Sentry integrations for SQLAlchemy or ASGI beyond the default FastAPI integration. The default `sentry_sdk.init()` with `FastApiIntegration` is sufficient.
- It does not add log-based alerting rules. CloudWatch alarms and Sentry alert rules are infrastructure configuration, not application code.
- It does not change the rate limiting middleware or any route handler business logic.

---

## 2. Data Models

### No New Tables

This feature does not create or alter any database tables. Observability state is transient (logs, request IDs, Sentry events).

### No New Columns

No database changes required.

### No Mem0 Operations

This feature does not interact with Mem0 directly. It instruments existing Mem0 calls with timing, but does not add new Mem0 operations.

---

## 3. API Changes

### Modified Endpoint: `GET /api/v1/health`

The existing health check endpoint is extended to include dependency status information.

```
GET /api/v1/health
Auth: Not required
Request headers: None
Request body: None

Response 200:
{
  "status": "ok",
  "version": "1.0.0",
  "dependencies": {
    "database": "ok" | "degraded" | "unavailable",
    "mem0": "ok" | "degraded" | "unavailable",
    "claude": "ok" | "degraded" | "unavailable"
  }
}

Notes:
  - The existing HealthResponse schema is extended with an optional `dependencies` field.
  - The top-level `status` remains "ok" as long as the backend process is running.
    Dependency failures do not change the top-level status, because ECS health checks
    must continue to pass even if an upstream dependency is down. The `dependencies`
    field is informational for dashboards and debugging.
  - Each dependency check has a 3-second timeout. If it times out, the status is "unavailable".
  - A `check_dependencies` query parameter controls whether dependency checks run:
    `GET /api/v1/health` returns only status+version (fast, for ECS probes).
    `GET /api/v1/health?check_dependencies=true` additionally probes dependencies.
  - This endpoint must still respond within 5 seconds total, as required by
    the existing docstring in `routes/health.py`.
```

### New Response Header on ALL Endpoints

Every response includes the `X-Request-ID` header:

| Header | Type | Description |
|--------|------|-------------|
| `X-Request-ID` | string (UUID v4) | Unique identifier for this request. If the client sends an `X-Request-ID` header, the server echoes it back. Otherwise, the server generates one. |

### No New Endpoints

No new API endpoints are introduced beyond the health check modification.

---

## 4. Backend Logic

### 4.1 Structured Logging with structlog

**Module: `backend/app/core/logging.py` (full rewrite)**

The existing `setup_logging` function is replaced with a structlog-based configuration. The module configures structlog to use its standard library integration, so that all existing `logging.getLogger("ember")` calls throughout the codebase continue to work without modification. Third-party libraries that use stdlib logging (uvicorn, SQLAlchemy, httpx) also emit structured JSON in production.

**`setup_logging(log_level: str, debug: bool) -> None`**

Configures the logging pipeline:

1. **structlog processors** (applied to every log entry):
   - `structlog.contextvars.merge_contextvars` -- merges context variables (request_id, user_id) into every log entry
   - `structlog.stdlib.add_log_level` -- adds the `level` field
   - `structlog.stdlib.add_logger_name` -- adds the `logger` field
   - `structlog.processors.TimeStamper(fmt="iso")` -- adds `timestamp` in ISO 8601 format
   - `structlog.processors.StackInfoRenderer()` -- renders stack info if present
   - `structlog.processors.format_exc_info` -- formats exception info
   - `structlog.processors.UnicodeDecoder()` -- ensures all strings are unicode

2. **Output renderer** (final processor):
   - Production (`debug=False`): `structlog.processors.JSONRenderer()` -- JSON lines to stdout
   - Development (`debug=True`): `structlog.dev.ConsoleRenderer()` -- colored, human-readable output

3. **stdlib integration**:
   - Configure structlog to wrap stdlib's `logging` module via `structlog.stdlib.ProcessorFormatter`
   - All existing `logger = logging.getLogger("ember")` calls emit structured logs without code changes
   - Third-party library loggers (uvicorn, sqlalchemy) also pass through the structlog pipeline

4. **Log level suppression** (same as current implementation):
   - `uvicorn.access`: WARNING
   - `sqlalchemy.engine`: DEBUG in debug mode, WARNING otherwise

**Structured log output example (production)**:

```json
{"timestamp":"2026-03-13T14:30:00.123Z","level":"info","logger":"ember","request_id":"550e8400-e29b-41d4-a716-446655440000","user_id":"usr_abc123","event":"Mem0 search completed","duration_ms":145,"agent_id":"luna_usr_abc123"}
```

**Structured log output example (development)**:

```
2026-03-13 14:30:00 [info     ] Mem0 search completed          duration_ms=145 request_id=550e8400... user_id=usr_abc123
```

### 4.2 Request ID Middleware

**Module: `backend/app/middleware/request_id.py`**

**Class: `RequestIDMiddleware`**

An ASGI middleware (using Starlette's `BaseHTTPMiddleware`) that:

1. Reads the incoming `X-Request-ID` header. If present and a valid format (1-128 characters, alphanumeric plus hyphens), uses it. Otherwise, generates a new UUID v4.
2. Stores the request ID in `structlog.contextvars` so that all log entries within the request lifecycle automatically include it.
3. Also binds `user_id` to the context if the request has a valid `Authorization: Bearer` header (using the same lightweight JWT parsing as `extract_user_key` from `core/rate_limit.py`).
4. Adds the `X-Request-ID` header to the response.
5. Clears the context variables after the response is sent (to prevent leaking between requests).

```
Constructor:
    __init__(self, app: ASGIApp) -> None

Method:
    async def dispatch(self, request: Request, call_next) -> Response
        1. Extract or generate request_id
        2. Bind request_id to structlog contextvars
        3. Optionally bind user_id from JWT sub claim (lightweight parse)
        4. Log request start: {"event": "request_started", "method": "POST", "path": "/api/v1/characters/.../messages"}
        5. Call next middleware/handler, measure elapsed time
        6. Log request end: {"event": "request_completed", "method": "POST", "path": "/api/v1/...", "status_code": 200, "duration_ms": 342}
        7. Add X-Request-ID to response headers
        8. Clear contextvars
```

**Request/response logging rules**:
- Log the HTTP method and path, but NEVER log query parameters (may contain tokens) or request/response bodies (may contain PII per `docs/standards/common.md` Section 8).
- Log `status_code` and `duration_ms` on response.
- Log at `info` level for successful requests (2xx, 3xx).
- Log at `warning` level for client errors (4xx).
- Log at `error` level for server errors (5xx).

**Registration in `main.py`**:

The request ID middleware is registered AFTER the rate limit middleware (so it wraps it -- request ID is generated before rate limiting runs, meaning even 429 responses get an `X-Request-ID` header).

Starlette middleware registration order (reverse of execution): the request ID middleware should be added last (after CORS and rate limit) so it is the outermost middleware in the request phase:

```
Registration order in main.py:
  1. app.add_middleware(RequestIDMiddleware)      # added last = outermost
  2. app.add_middleware(RateLimitMiddleware, ...)  # existing
  3. app.add_middleware(CORSMiddleware, ...)       # existing
```

Wait -- Starlette applies in reverse: last registered = outermost. So:

```
Request flow:  RequestIDMiddleware -> RateLimitMiddleware -> CORSMiddleware -> route
Response flow: route -> CORSMiddleware -> RateLimitMiddleware -> RequestIDMiddleware
```

But CORS should be outermost (to add CORS headers to 429 responses). The current code registers rate limit first, then CORS second (making CORS outermost). The request ID middleware must be outermost of all three. So the registration order becomes:

```python
# In create_app(), registration order:
# 1. Rate limit middleware (innermost)
app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)
# 2. CORS middleware
app.add_middleware(CORSMiddleware, ...)
# 3. Request ID middleware (outermost -- registered last)
app.add_middleware(RequestIDMiddleware)
```

This means the request flows: RequestID -> CORS -> RateLimit -> route. CORS headers are still applied to 429 responses because CORS wraps rate limiting. Request ID wraps everything so all responses (including CORS preflight and 429) get the `X-Request-ID` header.

### 4.3 Sentry Integration

**Module: `backend/app/core/sentry.py`**

**Function: `init_sentry() -> None`**

Initializes the Sentry SDK if a DSN is configured. Called from `lifespan()` in `main.py`, before `setup_logging()`.

```
Configuration:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,           # empty string = Sentry disabled
        environment=settings.sentry_environment,
        release=settings.app_version,
        traces_sample_rate=0.1,            # sample 10% of transactions for performance
        profiles_sample_rate=0.1,          # sample 10% of profiled transactions
        send_default_pii=False,            # NEVER send PII (per docs/standards/common.md Section 8)
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
        ],
        before_send=_scrub_event,          # scrub sensitive data before sending
    )
```

**Function: `_scrub_event(event, hint) -> event | None`**

A Sentry `before_send` hook that:
- Removes any `Authorization` header values from request data
- Removes any `X-Request-ID` values that might be in breadcrumbs (these are fine to keep, but the pattern is established for future scrubbing)
- Returns the event unchanged otherwise

**Why `send_default_pii=False`**: Per `docs/standards/common.md` Section 8: "Never log email addresses, names, phone numbers, or message content." Sentry's default PII collection includes user IPs and request bodies, which could contain message content.

**Sentry context enrichment**: The request ID middleware sets the Sentry scope's `request_id` tag so that Sentry events can be correlated with log entries:

```python
import sentry_sdk
sentry_sdk.set_tag("request_id", request_id)
```

### 4.4 External Call Timing

**Module: `backend/app/utils/timing.py`**

Provides a reusable async context manager and decorator for timing external API calls.

**Async context manager: `log_external_call(service: str, operation: str)`**

```
Usage:
    async with log_external_call("mem0", "search"):
        results = await mem0_client.search(...)

Behavior:
    1. Records time.monotonic() at entry
    2. Yields control to the caller
    3. On exit (success or exception), calculates duration_ms
    4. Logs a structured event:
       {"event": "external_call", "service": "mem0", "operation": "search", "duration_ms": 145, "success": true}
    5. On exception, logs:
       {"event": "external_call", "service": "mem0", "operation": "search", "duration_ms": 2003, "success": false, "error": "TimeoutError"}
       Then re-raises the exception (does not swallow it)
```

**Services to instrument** (existing call sites that must be wrapped):

| Service | Operation | File | Call Site |
|---------|-----------|------|-----------|
| `claude` | `stream` | `app/services/chat_service.py` | `client.messages.stream()` in `stream_response()` |
| `claude` | `create` | `app/services/chat_service.py` | `client.messages.create()` in `_extract_intent()` |
| `mem0` | `search` | `app/services/chat_service.py` | `client.search()` in `_search_memories()` |
| `mem0` | `add` | `app/services/chat_service.py` | `client.add()` in `_persist_exchange()` |
| `mem0` | `get_all` | `app/services/memory_service.py` | Memory listing operations |
| `mem0` | `delete` | `app/services/memory_service.py` | Memory deletion operations |
| `cognito` | `jwks_fetch` | `app/core/auth.py` | `httpx.AsyncClient.get()` in `get_jwks()` |
| `s3` | `generate_presigned_url` | `app/services/media_service.py` | S3 presigned URL generation |

The timing wrapper is applied at each call site by wrapping the external call in an `async with log_external_call(...)` block. This is a small, mechanical modification to each file.

**Important**: The timing wrapper must NOT log request/response payloads. Only service name, operation name, duration, and success/failure status. Per `docs/standards/common.md` Section 8: no PII in logs.

### 4.5 Enhanced Health Check

**Module: `backend/app/routes/health.py` (modified)**

**Module: `backend/app/services/health_service.py` (new)**

The health route handler gains an optional `check_dependencies` query parameter. When `true`, it calls `HealthService.check_dependencies()` which probes each upstream dependency with a short timeout.

**Class: `HealthService`**

```
Methods:
    async def check_dependencies() -> dict[str, str]
        Probes database, Mem0, and Claude in parallel using asyncio.gather().
        Each probe has a 3-second timeout (asyncio.wait_for).

        Database probe: Execute "SELECT 1" via the async session.
        Mem0 probe: Call mem0 client health check or a lightweight search.
        Claude probe: Send a minimal completion request (1 token max).

        Returns: {"database": "ok"|"degraded"|"unavailable", ...}

        Status mapping:
          - Response within 1 second: "ok"
          - Response between 1-3 seconds: "degraded"
          - Timeout or exception: "unavailable"
```

**Schema change: `backend/app/schemas/health.py`**

```
class DependencyStatus(BaseModel):
    database: str   # "ok" | "degraded" | "unavailable"
    mem0: str       # "ok" | "degraded" | "unavailable"
    claude: str     # "ok" | "degraded" | "unavailable"

class HealthResponse(BaseModel):
    status: str
    version: str
    dependencies: DependencyStatus | None = None
```

The `dependencies` field is `None` when `check_dependencies` is not requested (backward compatible with ECS health probes that only check for `status: "ok"`).

### 4.6 New Config Fields

Six new fields in `backend/app/config.py`:

| Field | Type | Default | Env Var | Description |
|-------|------|---------|---------|-------------|
| `sentry_dsn` | `str` | `""` | `SENTRY_DSN` | Sentry DSN. Empty string disables Sentry. |
| `sentry_environment` | `str` | `"development"` | `SENTRY_ENVIRONMENT` | Sentry environment tag (development, staging, production). |
| `sentry_traces_sample_rate` | `float` | `0.1` | `SENTRY_TRACES_SAMPLE_RATE` | Fraction of transactions to trace (0.0-1.0). |
| `health_check_timeout` | `float` | `3.0` | `HEALTH_CHECK_TIMEOUT` | Timeout in seconds for each dependency probe. |
| `health_check_degraded_threshold` | `float` | `1.0` | `HEALTH_CHECK_DEGRADED_THRESHOLD` | Response time threshold in seconds above which a dependency is "degraded". |
| `log_request_body` | `bool` | `False` | `LOG_REQUEST_BODY` | Whether to log request bodies (always False in production, useful for local debugging). |

### 4.7 Error Handling

- **Sentry init failure**: If `sentry_sdk.init()` fails (bad DSN, network error), log a warning and continue. Sentry is optional; its absence must not prevent the app from starting.
- **Request ID middleware errors**: Fail-open. If generating or parsing the request ID fails, generate a fallback UUID and continue. Never block a request due to request ID issues.
- **Timing wrapper errors**: The timing context manager must never swallow exceptions from the wrapped call. It logs the duration and re-raises. If the logging itself fails, the exception from the wrapped call is still re-raised.
- **Health check dependency probe errors**: Each probe is independently wrapped in try/except. A failed probe returns "unavailable" for that dependency but does not affect other probes.

### 4.8 Integration with Existing Global Exception Handler

The unhandled exception handler in `main.py` currently logs via `logger.exception()`. With structlog integration, this continues to work. The request ID will automatically be included in the log entry because the context variable is still bound when the exception handler runs.

Additionally, Sentry will automatically capture unhandled exceptions via the `FastApiIntegration`. The Sentry event will include the `request_id` tag set by the request ID middleware, enabling correlation between Sentry issues and CloudWatch log entries.

---

## 5. Test Requirements

### What Must Be Tested

#### structlog Configuration Tests (`tests/infra/test_logging.py` -- modified)

The existing logging tests must be updated to reflect the new structlog-based implementation.

| # | Scenario | Expected |
|---|----------|----------|
| 1 | `setup_logging(debug=True)` produces human-readable output | Log output uses `ConsoleRenderer` format (not JSON) |
| 2 | `setup_logging(debug=False)` produces JSON output | Log output is valid JSON with `timestamp`, `level`, `logger`, `event` fields |
| 3 | Context variables (request_id, user_id) appear in log output | After binding `request_id` via `structlog.contextvars.bind_contextvars`, the field appears in log output |
| 4 | `uvicorn.access` logger is suppressed to WARNING level | Verified via `logging.getLogger("uvicorn.access").level` |
| 5 | `sqlalchemy.engine` logger level depends on debug flag | DEBUG when debug=True, WARNING otherwise |
| 6 | Exception info is formatted in structured output | `logger.exception()` includes `exc_info` field in JSON |

#### Request ID Middleware Tests (`tests/middleware/test_request_id.py`)

| # | Scenario | Expected |
|---|----------|----------|
| 7 | Request without `X-Request-ID` header | Response has `X-Request-ID` header with a valid UUID v4 |
| 8 | Request with `X-Request-ID: custom-id-123` header | Response echoes `X-Request-ID: custom-id-123` |
| 9 | Request with excessively long `X-Request-ID` (>128 chars) | Server generates a new UUID, ignores the invalid input |
| 10 | Request ID appears in request log entries | Capture log output, verify `request_id` field matches response header |
| 11 | User ID from JWT appears in log entries | Send request with Bearer token containing `sub` claim, verify `user_id` in logs |
| 12 | Request without auth does not include user_id in logs | `user_id` field is absent from log entries |
| 13 | Request completion log includes `status_code` and `duration_ms` | Verify both fields are present and have correct types |
| 14 | 429 responses from rate limiter still get `X-Request-ID` header | Exhaust rate limit, verify 429 response has the header |
| 15 | Context variables are cleared between requests | Send two requests, verify second request has a different `request_id` |

#### Sentry Integration Tests (`tests/infra/test_sentry.py`)

| # | Scenario | Expected |
|---|----------|----------|
| 16 | `init_sentry()` with empty DSN does not call `sentry_sdk.init()` | Mock `sentry_sdk.init`, verify not called |
| 17 | `init_sentry()` with valid DSN calls `sentry_sdk.init()` with correct params | Verify `send_default_pii=False`, `environment` matches config |
| 18 | `_scrub_event` removes Authorization header from event | Pass event with request headers, verify Authorization is removed |
| 19 | `init_sentry()` failure logs warning and does not raise | Mock `sentry_sdk.init` to raise, verify warning logged, no exception |

#### External Call Timing Tests (`tests/utils/test_timing.py`)

| # | Scenario | Expected |
|---|----------|----------|
| 20 | Successful external call logs duration_ms and success=true | Capture log output, verify fields |
| 21 | Failed external call logs duration_ms and success=false with error type | Raise exception inside context manager, verify log fields, verify exception re-raised |
| 22 | Timing does not swallow exceptions | `ValueError` raised inside `async with log_external_call(...)` propagates to caller |
| 23 | Service and operation names appear in log output | Verify `service` and `operation` fields match arguments |

#### Enhanced Health Check Tests (`tests/infra/test_health.py` -- modified/extended)

| # | Scenario | Expected |
|---|----------|----------|
| 24 | `GET /api/v1/health` without query param | Returns `{"status": "ok", "version": "...", "dependencies": null}` |
| 25 | `GET /api/v1/health?check_dependencies=true` with all healthy deps | Returns dependencies with all "ok" |
| 26 | `GET /api/v1/health?check_dependencies=true` with DB down | `database` is "unavailable", others may be "ok" |
| 27 | `GET /api/v1/health?check_dependencies=true` with slow DB (>1s) | `database` is "degraded" |
| 28 | Health check still returns 200 even when dependencies are down | Status code is 200, `status` is "ok" |
| 29 | Health check response time is under 5 seconds | Even with all deps timing out (3s each), `asyncio.gather` runs them in parallel, total < 5s |

### How to Mock External Dependencies

- **structlog**: Use `structlog.testing.capture_logs()` context manager to capture log entries as dicts for assertion.
- **Sentry**: Mock `sentry_sdk.init` and `sentry_sdk.set_tag` with `unittest.mock.patch`.
- **Timing**: Mock `time.monotonic()` via `unittest.mock.patch("app.utils.timing.time.monotonic")` to control durations.
- **Health check probes**: Mock the database session (`AsyncSession`), `MemoryClient`, and `AsyncAnthropic` to simulate healthy, slow, and failed states.

### Code Quality Checks

```bash
ruff check backend/app/core/logging.py backend/app/core/sentry.py backend/app/middleware/request_id.py backend/app/utils/timing.py backend/app/services/health_service.py
mypy backend/app/core/logging.py backend/app/core/sentry.py backend/app/middleware/request_id.py backend/app/utils/timing.py backend/app/services/health_service.py
pytest backend/tests/infra/test_logging.py backend/tests/middleware/test_request_id.py backend/tests/infra/test_sentry.py backend/tests/utils/test_timing.py backend/tests/infra/test_health.py -v
```

---

## 6. File Manifest

Every file to be created or modified, grouped by purpose.

### Structured Logging

```
Backend:
  MODIFY  backend/app/core/logging.py       (full rewrite: structlog configuration)
```

### Request ID Middleware

```
Backend:
  CREATE  backend/app/middleware/request_id.py
```

### Sentry Integration

```
Backend:
  CREATE  backend/app/core/sentry.py
```

### External Call Timing

```
Backend:
  CREATE  backend/app/utils/timing.py
```

### Health Check Enhancement

```
Backend:
  MODIFY  backend/app/routes/health.py        (add check_dependencies query param)
  MODIFY  backend/app/schemas/health.py        (add DependencyStatus model)
  CREATE  backend/app/services/health_service.py
```

### Configuration

```
Backend:
  MODIFY  backend/app/config.py               (add sentry_dsn, sentry_environment, etc.)
```

### App Registration

```
Backend:
  MODIFY  backend/app/main.py                 (register RequestIDMiddleware, call init_sentry, update lifespan)
```

### External Call Instrumentation (timing wrappers)

```
Backend:
  MODIFY  backend/app/services/chat_service.py     (wrap Claude and Mem0 calls)
  MODIFY  backend/app/services/memory_service.py   (wrap Mem0 calls)
  MODIFY  backend/app/services/media_service.py    (wrap S3 calls)
  MODIFY  backend/app/core/auth.py                 (wrap JWKS fetch)
```

### Dependencies

```
Backend:
  MODIFY  backend/requirements.txt             (add structlog, sentry-sdk)
```

### Tests

```
Backend:
  MODIFY  backend/tests/infra/test_logging.py       (rewrite for structlog)
  MODIFY  backend/tests/infra/test_health.py        (add dependency check tests)
  CREATE  backend/tests/middleware/test_request_id.py
  CREATE  backend/tests/infra/test_sentry.py
  CREATE  backend/tests/utils/__init__.py
  CREATE  backend/tests/utils/test_timing.py
```

### Documentation (Pipeline)

```
Shared:
  CREATE  shared/feature-specs/observability-stack.md          (this file)
  CREATE  docs/pipeline/observability-stack-architect.handoff.md
```

### Summary

| Action | Count |
|--------|-------|
| CREATE | 8 |
| MODIFY | 10 |
| DELETE | 0 |
| **Total** | **18** |

### New Dependencies

Two new packages added to `requirements.txt`:

```
structlog>=24.1.0,<25.0.0
sentry-sdk[fastapi]>=2.0.0,<3.0.0
```

- `structlog`: Structured logging library. The `[fastapi]` extra is not needed; structlog integrates via stdlib logging, not via framework-specific adapters.
- `sentry-sdk[fastapi]`: Sentry error tracking with the FastAPI integration (`FastApiIntegration`). The `[fastapi]` extra pulls in Starlette/FastAPI-specific integrations for automatic request/response capture and transaction naming.

---

## 7. Acceptance Criteria

1. Given a request to any API endpoint, when the response is received, then the `X-Request-ID` header is present and contains a valid UUID v4 or the client-provided request ID.

2. Given a request with an `X-Request-ID: abc-123` header, when the response is received, then the response `X-Request-ID` header value is `abc-123`.

3. Given the backend running in production mode (`debug=False`), when a log entry is emitted, then it is valid JSON containing at minimum `timestamp`, `level`, `logger`, and `event` fields.

4. Given a request to `POST /api/v1/characters/:id/messages`, when the request is processed, then all log entries emitted during that request include the same `request_id` field value.

5. Given an authenticated request with a valid JWT, when log entries are emitted during the request, then they include a `user_id` field matching the JWT `sub` claim.

6. Given the backend configured with a valid `SENTRY_DSN`, when an unhandled exception occurs, then Sentry receives the error event with the `request_id` tag.

7. Given the backend configured with an empty `SENTRY_DSN` (default), when the app starts, then Sentry is not initialized and the app functions normally.

8. Given a call to Mem0 `search()` during message processing, when the call completes, then a structured log entry is emitted with `service=mem0`, `operation=search`, `duration_ms` (integer), and `success` (boolean) fields.

9. Given a call to Claude `messages.stream()` during message processing, when the streaming completes, then a structured log entry is emitted with `service=claude`, `operation=stream`, and `duration_ms` fields.

10. Given `GET /api/v1/health` without the `check_dependencies` query parameter, when called, then the response is `{"status": "ok", "version": "..."}` with `dependencies` being `null` (backward compatible with ECS health probes).

11. Given `GET /api/v1/health?check_dependencies=true` with all dependencies healthy, when called, then the response includes `dependencies` with `database`, `mem0`, and `claude` each set to `"ok"`.

12. Given `GET /api/v1/health?check_dependencies=true` with the database unreachable, when called, then the response status code is still 200 and `dependencies.database` is `"unavailable"`.

13. Given the backend source code, when `ruff check` is run on all new and modified files, then zero errors are reported.

14. Given the backend test suite, when `pytest` is run on all observability-related test files, then all tests pass with exit code 0.

15. Given a rate-limited request (429 response), when the response is inspected, then the `X-Request-ID` header is present.

16. Given the timing utility logging an external call failure, when the exception propagates, then the caller receives the original exception (the timing wrapper does not swallow it).

17. Given the Sentry `before_send` hook, when an error event contains an `Authorization` header, then the header value is removed before the event is sent to Sentry.

---

## 8. Design Decisions and Rationale

### Why structlog over plain stdlib logging

The current `logging.Formatter` approach builds JSON via string interpolation (`'{"time":"%(asctime)s",...}'`). This breaks if any log message contains quotes, braces, or other JSON special characters. structlog produces proper JSON by serializing Python dicts, handles structured fields natively (key=value pairs), and supports context variable binding (essential for request ID propagation). The stdlib integration ensures zero changes to existing `logging.getLogger("ember")` call sites across the codebase.

### Why request ID middleware over request-scoped dependency

FastAPI dependencies work well for route handlers, but middleware runs before dependencies are resolved. The request ID must be available from the very first log entry (before any route handler code runs), including rate limit middleware logs and CORS handling. Middleware is the only mechanism that provides this guarantee.

### Why `structlog.contextvars` over thread-local storage

FastAPI runs on asyncio, where multiple requests can be interleaved on the same thread. Thread-local storage would mix request IDs between concurrent requests. `contextvars` (PEP 567) is the correct mechanism for async Python -- each asyncio task has its own context, preventing cross-request contamination.

### Why Sentry with `send_default_pii=False`

Per `docs/standards/common.md` Section 8: "Never log email addresses, names, phone numbers, or message content." Sentry's default PII mode captures user IPs, cookies, and potentially request bodies. Disabling default PII and adding a `before_send` scrubber ensures compliance while still providing useful error tracking (stack traces, error types, request metadata).

### Why timing as a context manager over a decorator

Service methods that call external APIs often need to handle the result inline (e.g., iterating a streaming response from Claude). A decorator would wrap the entire method, including unrelated logic. A context manager wraps only the external call, producing accurate timing. It also composes naturally with `async with` syntax already used for Claude streaming.

### Why health check dependencies are informational, not authoritative

ECS health checks determine whether to replace a task. If the health check fails when a dependency is down, ECS would restart the Ember backend -- which cannot fix an upstream outage and would cause cascading failures. The top-level `status` always returns `"ok"` as long as the process is alive. Dependency status is exposed for dashboards and debugging, not for orchestration.

### Why the `check_dependencies` query parameter instead of always probing

The ECS health check probe hits `/api/v1/health` every 30 seconds. Probing dependencies on every health check would generate unnecessary load on Mem0 and Claude APIs. The `check_dependencies=true` parameter is used only by monitoring dashboards and manual debugging, not by the ECS probe.

---

## 9. Notes for Developers

### For backend-dev

- **structlog setup**: Use `structlog.stdlib.ProcessorFormatter` as the stdlib handler formatter. This makes `logging.getLogger("ember").info("message", extra={"key": "value"})` produce structured output. The `extra` dict fields are merged into the structured log entry.
- **contextvars clearing**: After `await call_next(request)` in the request ID middleware, call `structlog.contextvars.clear_contextvars()`. This is critical to prevent request ID leakage in long-lived connections or SSE streams.
- **SSE streaming considerations**: The request ID middleware's `dispatch` method wraps the entire request lifecycle. For SSE endpoints, the `call_next` does not return until the stream closes. The "request completed" log and context cleanup happen after the stream ends. This is correct behavior.
- **Sentry FastApiIntegration**: Import from `sentry_sdk.integrations.fastapi`. The integration automatically captures unhandled exceptions and creates transactions for each request.
- **`log_external_call` implementation**: Use `contextlib.asynccontextmanager`. Record `time.monotonic()` before and after yield. Use `structlog.get_logger()` to emit the timing log (it automatically picks up the request ID from contextvars).
- **Chat service timing**: For `client.messages.stream()`, the timing should wrap the entire `async with` block (including iteration), not just the initial connection. This captures the full streaming duration.
- **Requirements pinning**: Pin structlog to `>=24.1.0,<25.0.0` (stable contextvars API). Pin sentry-sdk to `>=2.0.0,<3.0.0` (v2 has the modern Python SDK with native async support).
- **Do not modify** the rate limiting middleware or core logic. The request ID middleware is a separate, additional middleware.
- **Existing test updates**: The existing `tests/infra/test_logging.py` tests the current `logging.Formatter`-based setup. These tests must be rewritten to test the structlog configuration instead.

### For backend-tester

- **structlog testing**: Use `structlog.testing.capture_logs()` to capture log entries as a list of dicts. Each dict has the fields from the structured log entry. This avoids parsing JSON strings.
- **Request ID middleware testing**: Use the FastAPI test client. Check both request and response headers. For log assertion, combine with `structlog.testing.capture_logs()`.
- **Sentry testing**: Mock `sentry_sdk.init` and assert it is called with the expected arguments. Do not actually connect to Sentry in tests.
- **Timing tests**: Create a simple async function that sleeps for a controlled duration, wrap it in `log_external_call`, and verify the logged `duration_ms` is within an acceptable range. Mock `time.monotonic()` for deterministic tests.
- **Health check probe mocking**: For the database probe, mock the `AsyncSession.execute` method. For Mem0 and Claude probes, mock the respective clients. Use `asyncio.sleep()` in mocks to simulate slow responses.
