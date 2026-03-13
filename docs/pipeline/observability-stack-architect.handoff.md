# Architect Handoff: Observability Stack

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

A comprehensive observability layer for the Ember backend covering four areas: (1) structured logging via structlog replacing the existing hand-rolled JSON formatter, (2) request ID middleware that generates/propagates `X-Request-ID` through all log entries via contextvars, (3) Sentry error tracking integration with PII scrubbing, and (4) timing instrumentation for all external API calls (Mem0, Claude, S3, Cognito JWKS) plus an enhanced health check with dependency probing.

## Key Decisions

- **structlog over plain stdlib logging**: The current `logging.Formatter` string-interpolation JSON format is fragile (does not escape special characters, cannot handle structured fields). structlog produces proper JSON via dict serialization and supports `contextvars` for automatic request ID propagation. All existing `logging.getLogger("ember")` call sites continue to work without modification via stdlib integration.
- **`contextvars` over thread-local storage**: FastAPI runs on asyncio where multiple requests interleave on one thread. `contextvars` (PEP 567) provides per-task context isolation, preventing request ID cross-contamination between concurrent requests.
- **Request ID as outermost middleware**: Must be outermost so that all responses (including CORS preflight and 429 rate limit responses) get the `X-Request-ID` header, and all log entries (including from rate limit and CORS middleware) include the request ID.
- **Sentry with `send_default_pii=False` and `before_send` scrubber**: Per docs/standards/common.md Section 8, no PII in logs or error reports. Default Sentry PII collection would capture request bodies (potentially containing message content).
- **Timing as async context manager, not decorator**: Service methods often handle external call results inline (e.g., iterating Claude streaming response). A context manager wraps only the external call for accurate timing and composes with existing `async with` patterns.
- **Health check dependencies are informational, not authoritative**: ECS health checks must not fail when upstream dependencies are down (would cause cascading restarts). Dependency status is exposed via `check_dependencies=true` query param for dashboards, not for orchestration.
- **`check_dependencies` query param instead of always probing**: ECS probes `/api/v1/health` every 30 seconds. Always probing would generate unnecessary load on Mem0 and Claude APIs.

## Spec Location

`shared/feature-specs/observability-stack.md`

## Assumptions Made

- The existing `backend/app/core/logging.py` can be fully rewritten (no external consumers depend on its current interface beyond calling `setup_logging()`).
- The `backend/tests/infra/test_logging.py` tests will be rewritten to match the new structlog implementation.
- structlog `>=24.1.0` provides a stable `contextvars` API.
- sentry-sdk `>=2.0.0` with `[fastapi]` extra provides `FastApiIntegration` with native async support.
- The `backend/tests/utils/` directory does not exist yet and must be created with `__init__.py`.

## Dependencies

- Requires: P01-01 (project-setup -- FastAPI scaffold, `main.py`, `config.py`, `core/logging.py`)
- Blocks: backend-dev (implementation)

## File Manifest

```
Backend:
  MODIFY  backend/app/core/logging.py          (full rewrite: structlog)
  CREATE  backend/app/core/sentry.py
  CREATE  backend/app/middleware/request_id.py
  CREATE  backend/app/utils/timing.py
  CREATE  backend/app/services/health_service.py
  MODIFY  backend/app/routes/health.py
  MODIFY  backend/app/schemas/health.py
  MODIFY  backend/app/config.py
  MODIFY  backend/app/main.py
  MODIFY  backend/app/services/chat_service.py
  MODIFY  backend/app/services/memory_service.py
  MODIFY  backend/app/services/media_service.py
  MODIFY  backend/app/core/auth.py
  MODIFY  backend/requirements.txt
  MODIFY  backend/tests/infra/test_logging.py
  MODIFY  backend/tests/infra/test_health.py
  CREATE  backend/tests/middleware/test_request_id.py
  CREATE  backend/tests/infra/test_sentry.py
  CREATE  backend/tests/utils/__init__.py
  CREATE  backend/tests/utils/test_timing.py

Shared:
  CREATE  shared/feature-specs/observability-stack.md
  CREATE  docs/pipeline/observability-stack-architect.handoff.md
```

## Notes for Developers

- Use `structlog.stdlib.ProcessorFormatter` for stdlib integration -- all existing `logging.getLogger("ember")` calls emit structured output with zero code changes.
- Clear `structlog.contextvars` after `call_next(request)` in the request ID middleware to prevent leakage between requests.
- The timing context manager for Claude streaming should wrap the entire `async with client.messages.stream()` block, not just the initial connection, to capture total streaming duration.
- Pin `structlog>=24.1.0,<25.0.0` and `sentry-sdk[fastapi]>=2.0.0,<3.0.0` in requirements.txt.
- Register RequestIDMiddleware as the last `add_middleware` call in `main.py` (Starlette applies in reverse order, making it outermost).
- The `tests/utils/` directory needs `__init__.py` created.

## Next Steps

backend-dev should read the spec and implement. backend-tester follows after implementation.
