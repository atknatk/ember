# Rate Limiting Middleware

> Enforces per-user request quotas on all API endpoints using an in-memory token bucket algorithm, preventing any single user from overwhelming the backend with expensive LLM calls or excessive read operations.

**Status**: Released
**Added in**: Phase 1.5 (P1.5-01)
**Platforms**: Backend
**GitHub Issue**: #83

---

## Overview

Rate limiting middleware is a cross-cutting concern that intercepts every HTTP request before it reaches a route handler. It limits the number of requests a given user (or unauthenticated IP) can make per minute, differentiated by the cost profile of the operation. Chat endpoints, which trigger Claude API calls and Mem0 memory searches, are held to the strictest limit (10 req/min). Standard write operations are limited to 20 req/min. Read-only operations, which are cheap database queries frequently used during message history scrolling, are allowed up to 60 req/min.

The feature was introduced as Phase 1.5 (security hardening between P01 and P02) because the chat streaming endpoint, once deployed, exposes an expensive LLM operation to the public internet. Without rate limiting, a single user with a runaway mobile client or a malicious actor could trigger hundreds of Claude API calls per minute, incurring unbounded cost and degrading the experience for other users.

The implementation deliberately uses in-memory state rather than an external store. Ember runs a single ECS Fargate task in Phase 1.5, so there is no cross-instance state to synchronize. The `RateLimiter` class is designed with a clean interface so that a Redis-backed replacement can be swapped in without changing the middleware or configuration layers.

---

## Architecture

### How It Works (Data Flow)

For every incoming HTTP request:

1. The ASGI request enters the middleware stack. CORS middleware is outermost; `RateLimitMiddleware` sits inside CORS, so CORS headers are applied to all responses including 429s.
2. `RateLimitMiddleware.dispatch()` calls `RateLimiter.classify_request(method, path)` to determine which rate limit group applies.
3. If the path is exempt (currently only `GET /api/v1/health`), the request passes through without any rate limiting or header injection.
4. `extract_user_key(request)` extracts the rate limit key: the JWT `sub` claim for authenticated requests, or `ip:{client_host}` for unauthenticated requests.
5. `RateLimiter.check(key, group)` looks up (or creates) the `TokenBucket` for the `"{key}:{group}"` pair, calls `bucket.consume()`, and returns `(allowed, headers_dict)`.
6. If allowed, the request proceeds to the route handler. The rate limit headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`) are appended to the response before it is returned.
7. If not allowed, the middleware immediately returns an HTTP 429 `JSONResponse` with `{"detail": "Rate limit exceeded"}` and a `Retry-After` header. The route handler is never called.
8. If any exception is thrown inside the middleware (unexpected error), the request is allowed through (fail-open) and the exception is logged. This ensures a bug in the rate limiter cannot take down the entire API.

### Token Bucket Algorithm

Each `(user_id_or_ip, group)` pair has its own `TokenBucket`. The bucket state is:

```
tokens: float       — current available tokens (starts at max_tokens)
last_refill: float  — time.monotonic() of last refill calculation
max_tokens: int     — maximum tokens (equals the per-minute limit)
refill_rate: float  — tokens added per second (max_tokens / 60)
```

On each request, `consume()` runs this logic:

```
elapsed = now - last_refill
tokens = min(max_tokens, tokens + elapsed * refill_rate)
last_refill = now

if tokens >= 1.0:
    tokens -= 1.0
    return allowed=True, retry_after=0.0
else:
    retry_after = ceil((1.0 - tokens) / refill_rate)
    return allowed=False, retry_after=retry_after
```

`time.monotonic()` is used for all timing (consistent with `core/auth.py`). `Retry-After` is always at least 1 second (using `max(1, math.ceil(retry_after))`).

This approach avoids the "boundary burst" problem of fixed windows, is memory-efficient (one small struct per active user-group pair), and handles bursty traffic gracefully — users can use their full quota immediately then wait for gradual refill.

### Rate Limit Groups

| Group | Matched By | Limit | Rationale |
|-------|-----------|-------|-----------|
| `chat` | `POST` to `^/api/v1/characters/[^/]+/messages(/stream)?$` | 10 req/min | Each request triggers Claude API call + Mem0 search — most expensive operation |
| `write` | `POST`, `PUT`, `DELETE`, `PATCH` (not matching chat) | 20 req/min | Standard write operations (character CRUD, onboarding, auth, etc.) |
| `read` | `GET` (not exempt) | 60 req/min | Read-only DB queries; relaxed for frequent pagination scrolling |
| exempt | `GET /api/v1/health` | unlimited | ECS/ALB health checks must never be throttled |

The classification logic in `RateLimiter.classify_request()` checks in this order: exempt path → chat regex → write methods → read method → default to `write`. Unknown HTTP methods (OPTIONS, HEAD) fall through to the final `return "write"` default.

### User Identification

`extract_user_key()` identifies users without performing full JWT verification:

1. Check for `Authorization: Bearer <token>` header.
2. If present, split the token by `.` — a valid JWT has exactly 3 parts.
3. Base64url-decode the payload (second part), adding `=` padding as needed.
4. Parse as JSON and extract the `sub` string field.
5. If the `sub` is a non-empty string, return it as the rate limit key.
6. On any failure at any step, return `ip:{request.client.host}`.

The function catches all exceptions and always returns a string. Full JWKS signature verification is intentionally skipped: the middleware only needs the `sub` claim for bucket keying, not for authentication. The actual auth check happens later in `get_current_user()`.

### Stale Bucket Cleanup

The `_buckets` dict would grow unbounded as new users connect. Every `check()` call triggers `_maybe_cleanup()`, which runs `_cleanup_stale_buckets()` if more than 300 seconds (5 minutes) have elapsed since the last cleanup. A bucket is considered stale when `tokens >= max_tokens` — it has fully refilled and is no longer active. Stale buckets are removed from the dict. This runs synchronously inside `check()` because dict iteration is fast and cleanup is infrequent.

### Module Layout

| File | Purpose |
|------|---------|
| `backend/app/core/rate_limit.py` | `TokenBucket`, `RateLimiter`, `extract_user_key`, `_ip_key` |
| `backend/app/middleware/__init__.py` | Package init |
| `backend/app/middleware/rate_limit.py` | `RateLimitMiddleware` (Starlette `BaseHTTPMiddleware`) |

The middleware is registered in `backend/app/main.py` `create_app()`:

```python
rate_limiter = RateLimiter(
    group_limits={
        "chat": settings.rate_limit_chat,
        "write": settings.rate_limit_write,
        "read": settings.rate_limit_read,
    },
    exempt_paths={"/api/v1/health"},
)
app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)
```

The `rate_limiter` instance is also stored on `app.state.rate_limiter` to allow test fixtures to reset bucket state between tests.

**Middleware ordering note**: FastAPI/Starlette applies middleware in reverse registration order (last `add_middleware` call = outermost). The rate limit middleware is registered before CORS (so CORS wraps it), ensuring `Access-Control-Allow-Origin` is present on 429 responses. This is intentionally opposite to the naive reading of the spec, which said "register AFTER CORS" — the actual registration order achieves the same runtime behavior.

### No Database or Mem0 Involvement

This feature stores no data in PostgreSQL and performs no Mem0 operations. All rate limiting state is held in the `_buckets` dict of the `RateLimiter` instance for the lifetime of the process.

---

## API Reference

Rate limiting is middleware behavior, not an endpoint. There are no new endpoints. All existing endpoints are affected.

### Response Headers Added to All Non-Exempt Responses

Every response from a non-exempt endpoint includes these headers:

| Header | Type | Description |
|--------|------|-------------|
| `X-RateLimit-Limit` | integer | Maximum requests allowed per minute for this group |
| `X-RateLimit-Remaining` | integer | Remaining requests in the current window |
| `X-RateLimit-Reset` | integer | Unix timestamp when the bucket will be fully refilled |

### 429 Response

When a user exceeds their group's limit:

```
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 4
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1741872345
Access-Control-Allow-Origin: *

{"detail": "Rate limit exceeded"}
```

| Header | Description |
|--------|-------------|
| `Retry-After` | Seconds until the next request will be accepted. Always >= 1. Integer (ceiling of the float calculation). |

The response body uses the standard error envelope `{"detail": "..."}` as specified in `docs/standards/common.md` Section 7.

### Exempt Endpoint

`GET /api/v1/health` is fully exempt. It receives no rate limit headers and is never blocked.

---

## Configuration

Three environment variables control the per-group limits. They are read via the `Settings` class in `backend/app/config.py`:

| Environment Variable | Config Field | Default | Description |
|---------------------|-------------|---------|-------------|
| `RATE_LIMIT_CHAT` | `rate_limit_chat` | `10` | Max requests per minute for chat/streaming endpoints |
| `RATE_LIMIT_WRITE` | `rate_limit_write` | `20` | Max requests per minute for write endpoints |
| `RATE_LIMIT_READ` | `rate_limit_read` | `60` | Max requests per minute for read endpoints |

Defaults match `docs/08-guvenlik-performans.md`: chat is stricter (LLM cost), read is relaxed (cheap DB reads). Changes take effect on process restart without code changes.

---

## Testing

### Coverage Summary

| File | Tests | Line Coverage | Branch Coverage |
|------|-------|---------------|-----------------|
| `tests/middleware/test_rate_limit.py` | 25 (backend-dev) | — | — |
| `tests/middleware/test_rate_limit_middleware.py` | 9 (backend-dev) | — | — |
| `tests/middleware/test_rate_limit_additional.py` | 40 (backend-tester) | — | — |
| **Total** | **74** | **100%** | **100%** |

```
Name                           Stmts   Miss  Cover
--------------------------------------------------
app/core/rate_limit.py            96      0   100%
app/middleware/rate_limit.py      29      0   100%
--------------------------------------------------
TOTAL                            125      0   100%
```

### Running Tests

Rate limiting middleware tests only:

```bash
cd backend && python -m pytest tests/middleware/ -v
```

Full backend suite:

```bash
cd backend && python -m pytest tests/ -v
```

### Test Approach

**Unit tests** (`test_rate_limit.py`): Test `TokenBucket.consume()`, `RateLimiter.check()`, `RateLimiter.classify_request()`, and `extract_user_key()` directly. All time-dependent tests mock `app.core.rate_limit.time.monotonic` to avoid real-time waits and make token refill deterministic.

**Integration tests** (`test_rate_limit_middleware.py`): Use `httpx.AsyncClient` with ASGI transport against the full FastAPI app. Verify response headers, 429 body format, CORS header presence on 429 responses, and per-user bucket isolation.

**Additional tests** (`test_rate_limit_additional.py`): Cover boundary conditions (exactly 1.0 tokens, just below 1.0), edge cases in JWT parsing (wrong number of parts, invalid base64, non-string `sub` values), the fail-open path in `dispatch`, unknown HTTP methods, and stale bucket cleanup behavior.

**Test isolation**: An autouse `_reset_rate_limiter` fixture in `backend/tests/conftest.py` clears `app.state.rate_limiter._buckets` before each test, preventing cross-test interference from leftover bucket state.

---

## Known Limitations

- **In-memory state is not shared across ECS tasks**: If Ember scales to multiple ECS Fargate tasks, each task maintains its own `_buckets` dict. A user could exceed their nominal limit by a multiple of the task count. This is accepted for Phase 1.5 (single task). Future work: replace `RateLimiter` with a Redis-backed implementation using the same `check()` interface.
- **Rate limit state is lost on process restart**: Token buckets are in-memory only. After a deployment or crash, all buckets reset to full capacity. Accepted trade-off for simplicity.
- **No DDoS protection at the application layer**: IP-based rate limiting for unauthenticated requests is applied, but volumetric DDoS mitigation is the responsibility of AWS WAF and ALB, as described in `docs/09-dagitim.md`.
- **Health endpoint is never rate-limited regardless of caller**: Any client that knows the health endpoint path can poll it without limit. This is intentional (ECS health checks) but means it cannot be used to detect abuse.
- **Implementation deviation from spec**: The spec said to register the rate limit middleware "AFTER CORS" to ensure CORS headers appear on 429 responses. In practice, due to Starlette's reverse middleware ordering, the rate limit middleware is registered BEFORE CORS in `add_middleware` calls. The runtime behavior is identical to the spec's intent — CORS headers are present on all responses including 429s.
- **Comment inaccuracy in source**: Line 159 in `app/core/rate_limit.py` comments "e.g., PATCH" on the final `return "write"` fallback, but PATCH is actually caught by the explicit `method in ("POST", "PUT", "DELETE", "PATCH")` check on line 153. The final fallback is only reached by truly unknown methods like OPTIONS and HEAD. The behavior is correct; the comment is misleading.

---

## Extending This Feature

**Adding a new exempt path**: Pass additional paths in the `exempt_paths` set when constructing `RateLimiter` in `main.py`. No other changes required.

**Adding a new rate limit group**: Add the group name and limit to `group_limits` in `main.py`, add the classification logic to `RateLimiter.classify_request()`, and add the corresponding config field to `Settings` in `config.py`. The `check()` method handles unknown groups by defaulting to 20 req/min as a safe fallback.

**Switching to Redis**: Implement a new class with the same `check(key, group) -> tuple[bool, dict[str, str]]` and `classify_request(method, path) -> str | None` interface. Register it in `main.py` in place of the existing `RateLimiter`. The middleware, configuration, and test helpers (`_reset_rate_limiter` fixture) require no changes.

**Adjusting limits per environment**: Set `RATE_LIMIT_CHAT`, `RATE_LIMIT_WRITE`, or `RATE_LIMIT_READ` in the environment. For example, set `RATE_LIMIT_CHAT=5` in production to reduce Claude API spend, or set all three to a high number in local development to avoid hitting limits during manual testing.

**Adding per-user tier limits**: The current implementation uses uniform limits for all authenticated users. To support per-tier limits (e.g., free users get 10 chat req/min, premium users get 50), the middleware would need to look up the user's tier. This requires either a fast cache (Redis or in-memory LRU) keyed by user ID, or a lightweight DB query, since the middleware cannot use FastAPI `Depends()`. One approach: after `extract_user_key()` returns the `sub`, fetch the tier from an in-memory LRU cache populated lazily from PostgreSQL.

---

## Related Documentation

- [Database Schema and API Endpoints](../04-veri-api.md)
- [Security and Performance](../08-guvenlik-performans.md) — the 20 req/min target this feature implements
- [Deployment Architecture](../09-dagitim.md) — AWS WAF and ALB for infrastructure-layer DDoS protection
- [Cognito Auth Middleware](./cognito-auth-middleware.md) — P01-03, which established the JWT `sub` claim format used for bucket keying
- [Chat Streaming](./chat-streaming.md) — the chat endpoint that is most strictly rate-limited
