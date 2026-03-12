# Backend Dev Handoff: Rate Limiting Middleware

**Date**: 2026-03-13
**Agent**: backend-dev
**Status**: COMPLETE

## Implemented Files

- `backend/app/core/rate_limit.py` -- TokenBucket, RateLimiter, extract_user_key (core logic)
- `backend/app/middleware/__init__.py` -- package init
- `backend/app/middleware/rate_limit.py` -- RateLimitMiddleware (ASGI middleware)
- `backend/app/config.py` -- MODIFIED: added rate_limit_chat, rate_limit_write, rate_limit_read fields
- `backend/app/main.py` -- MODIFIED: registered RateLimitMiddleware, stored rate_limiter on app.state
- `backend/tests/conftest.py` -- MODIFIED: added autouse fixture to reset rate limiter between tests
- `backend/tests/middleware/__init__.py` -- package init
- `backend/tests/middleware/test_rate_limit.py` -- 26 unit tests
- `backend/tests/middleware/test_rate_limit_middleware.py` -- 8 integration tests

## Endpoints Implemented

No new endpoints. The middleware applies to all existing endpoints:

- All `POST /api/v1/characters/*/messages` and `/messages/stream` -- "chat" group, 10 req/min
- All other POST, PUT, DELETE, PATCH -- "write" group, 20 req/min
- All GET (except health) -- "read" group, 60 req/min
- `GET /api/v1/health` -- exempt (never rate limited)

Rate-limited responses return HTTP 429 with `{"detail": "Rate limit exceeded"}` and `Retry-After` header.

All responses (including successful ones) include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` headers.

## Test Results

- pytest: 1339 passed, 0 failed (full suite excluding 3 pre-existing infra failures: test_config.py, test_docker.py, test_migration.py)
- pytest middleware tests: 34 passed, 0 failed
- ruff: clean (all modified files)
- mypy: clean (all new files)
- No hardcoded secrets found

## Test Command

```bash
cd backend && python -m pytest tests/middleware/ -v
```

## Known Issues / Deviations from Spec

- **Middleware ordering**: The spec says "register AFTER CORS middleware". In practice, Starlette applies middleware in reverse registration order (last added = outermost). To ensure CORS headers appear on 429 responses, the rate limit middleware is registered BEFORE CORS (so CORS wraps it as the outer layer). The end result matches the spec's intent: CORS headers are present on all responses including 429s.
- **app.state.rate_limiter**: The rate limiter instance is stored on `app.state` to allow test fixtures to reset bucket state between tests. This is not in the spec but is necessary for test isolation.
- **autouse fixture in conftest.py**: An autouse `_reset_rate_limiter` fixture was added to the shared conftest to clear rate limiter buckets before each test. Without this, existing tests that make many requests would be rate-limited and fail.

## Notes for Backend Tester

- Mock `time.monotonic()` via `unittest.mock.patch("app.core.rate_limit.time.monotonic")` for all time-dependent tests. Without mocking, token bucket refill happens in real time and tests become timing-sensitive.
- The `extract_user_key` function does lightweight JWT parsing (base64 decode only). For tests, construct minimal JWTs by base64url-encoding a JSON payload with a `sub` field -- no signing needed.
- The middleware is fail-open: if `extract_user_key` or `classify_request` throws an unexpected error, the request passes through. Consider testing this edge case.
- Rate limiter buckets are keyed by `"{user_id}:{group}"` -- use unique user IDs per test to avoid cross-test interference (the autouse fixture resets buckets, but unique IDs are still a good practice).
- The `_cleanup_stale_buckets` method removes buckets at `max_tokens` capacity. When testing cleanup, patch `time.monotonic()` in the `RateLimiter.__init__` context too, so `_last_cleanup` has a consistent value.
- CORS test (test 26): Send an `Origin` header in the request to trigger CORS middleware to add `Access-Control-Allow-Origin` to the response.
