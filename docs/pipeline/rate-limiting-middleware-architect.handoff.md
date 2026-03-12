# Architect Handoff: Rate Limiting Middleware

**Date**: 2026-03-12
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

Per-user rate limiting middleware for the Ember backend using an in-memory token bucket algorithm. Requests are keyed by JWT `sub` claim (authenticated users) or client IP (unauthenticated requests). Three rate limit groups provide differentiated limits: chat endpoints (10 req/min), write endpoints (20 req/min), and read endpoints (60 req/min). The health endpoint is exempt. Exceeding the limit returns HTTP 429 with `Retry-After` header.

## Key Decisions

- **In-memory token bucket over Redis**: Single ECS task in Phase 1.5 makes Redis unnecessary overhead. The `RateLimiter` class interface is designed for future Redis swap without middleware changes.
- **Three groups (chat/write/read) over per-endpoint limits**: Maps to the cost profile of Ember operations. Chat triggers expensive LLM calls (stricter), reads are cheap DB queries (relaxed). Avoids maintenance burden of per-endpoint config.
- **Lightweight JWT parsing (base64 decode) over full JWKS verification**: Middleware cannot use `Depends()`. Full verification would duplicate `get_current_user` work. The `sub` claim is only needed for keying, not authentication.
- **Fail-open on middleware errors**: Rate limiting is defense-in-depth. A crash in the rate limiter must not take down the API. Auth/authz enforcement happens in route handlers.
- **`BaseHTTPMiddleware` over pure ASGI**: Simpler to implement and test. Performance difference is negligible for this use case.
- **Health endpoint exempt by path, not by auth absence**: Login/register should still be rate-limited by IP. Path exemption is explicit.
- **Token bucket over fixed/sliding window**: No boundary-burst problem, memory-efficient, naturally handles bursty traffic.
- **New `middleware/` directory in `app/`**: Middleware is a distinct concern from `core/` (which holds singletons and utilities). Establishes pattern for future middleware (e.g., request logging, correlation IDs).

## Spec Location

`shared/feature-specs/rate-limiting-middleware.md`

## Assumptions Made

- Ember runs a single ECS task (or very few) in Phase 1.5, making in-memory rate limiting acceptable.
- The JWT `sub` claim is always a UUID matching `profiles.id` (established by P01-03 auth middleware).
- `BaseHTTPMiddleware` from Starlette is available via FastAPI (it is -- FastAPI depends on Starlette).
- The `backend/app/middleware/` directory does not exist yet and must be created.

## Dependencies

- Requires: P01-03 (cognito-auth-middleware) -- JWT format and `sub` claim
- Requires: P01-01 (project-setup) -- FastAPI scaffold, config.py, main.py
- Blocks: None directly, but all subsequent features benefit from rate limiting being in place

## File Manifest

```
Backend:
  CREATE  backend/app/core/rate_limit.py
  CREATE  backend/app/middleware/__init__.py
  CREATE  backend/app/middleware/rate_limit.py
  MODIFY  backend/app/config.py
  MODIFY  backend/app/main.py
  CREATE  backend/tests/middleware/__init__.py
  CREATE  backend/tests/middleware/test_rate_limit.py
  CREATE  backend/tests/middleware/test_rate_limit_middleware.py

Shared:
  CREATE  shared/feature-specs/rate-limiting-middleware.md
  CREATE  docs/pipeline/rate-limiting-middleware-architect.handoff.md
```

## Notes for Developers

- Create `backend/app/middleware/` and `backend/tests/middleware/` directories with `__init__.py` files.
- Use `time.monotonic()` for all timing (consistent with `core/auth.py`).
- `extract_user_key` must never raise -- catch all exceptions and fall back to IP-based keying.
- Register the middleware in `main.py` AFTER the CORS `add_middleware` call (Starlette applies middleware in reverse order).
- Compile the chat path regex at module level, not inside `classify_request`.
- `Retry-After` header value must be `math.ceil()` of the float seconds (integer).
- Config fields: `rate_limit_chat=10`, `rate_limit_write=20`, `rate_limit_read=60` with env var overrides.

## Next Steps

backend-dev should read the spec and implement. backend-tester follows after implementation.
