# Feature Spec: P1.5-01 -- Rate Limiting Middleware

**Feature ID**: P1.5-01
**Phase**: 1.5
**Layer**: backend
**GitHub Issue**: #83
**Date**: 2026-03-12
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature adds per-user rate limiting to the Ember backend as a FastAPI middleware. It limits authenticated users to a configurable number of requests per minute, keyed by the JWT `sub` claim (user ID). Unauthenticated requests (e.g., health check, auth endpoints) are keyed by client IP address. The middleware returns HTTP 429 with a `Retry-After` header when a user exceeds their limit. Different endpoint groups have different limits: chat/streaming endpoints are more strictly limited than read-only endpoints.

The implementation uses an in-memory token bucket algorithm. Each user has a bucket that refills at a fixed rate. When a request arrives, the middleware checks if a token is available. If yes, the request proceeds. If no, the request is rejected with 429.

### Why It Exists

Per `docs/08-guvenlik-performans.md`: "Rate limiting: Kullanıcı basina dakikada maksimum 20 istek." Rate limiting prevents a single user from overwhelming the backend (expensive LLM calls, Mem0 operations, database queries) and protects the system from abuse, automated scraping, or runaway mobile client bugs. Without rate limiting, a single user could trigger hundreds of Claude API calls per minute, incurring cost and degrading the experience for other users.

### Dependencies

- **Requires**: P01-03 (cognito-auth-middleware -- JWT verification and `sub` claim extraction)
- **Requires**: P01-01 (project-setup -- FastAPI scaffold, `main.py` app factory, `config.py`)

### What This Feature Does NOT Do

- It does not use Redis or any external store. Phase 1.5 uses in-memory token buckets. This is appropriate for single-instance development and early ECS deployment. If Ember scales to multiple ECS tasks, a Redis-backed store can replace the in-memory store without changing the middleware interface (a future enhancement, not in scope).
- It does not implement IP-based rate limiting for DDoS protection. That is handled at the infrastructure layer (AWS WAF, ALB rate limiting) per `docs/09-dagitim.md`.
- It does not rate-limit the `GET /api/v1/health` endpoint. Health checks from ECS/ALB must never be throttled.
- It does not implement per-endpoint rate limiting granularity beyond the three groups defined below. Per-endpoint limits are a future enhancement.

---

## 2. Data Models

### No New Tables

This feature does not create or alter any database tables. Rate limiting state is stored in memory only.

### No New Columns

No database changes required.

### No Mem0 Operations

This feature does not interact with Mem0.

---

## 3. API Changes

### No New Endpoints

This feature does not introduce any new API endpoints. It adds a middleware that intercepts all requests before they reach route handlers.

### Modified Behavior on ALL Existing Endpoints

Every endpoint (except health) gains rate limiting behavior. When the limit is exceeded, the endpoint returns:

```
HTTP/1.1 429 Too Many Requests
Retry-After: {seconds_until_next_token}
Content-Type: application/json

{"detail": "Rate limit exceeded"}
```

### Response Headers Added to ALL Responses

Every response (including successful ones) includes rate limit information headers:

| Header | Type | Description |
|--------|------|-------------|
| `X-RateLimit-Limit` | int | Maximum requests allowed per window |
| `X-RateLimit-Remaining` | int | Remaining requests in current window |
| `X-RateLimit-Reset` | int | Unix timestamp when the bucket fully refills |
| `Retry-After` | int | Seconds until the next request will be accepted (only on 429 responses) |

### Exempt Endpoints

The following paths are exempt from rate limiting entirely:

- `GET /api/v1/health` -- ECS health checks must never be throttled

---

## 4. Backend Logic

### Rate Limit Groups

Three groups with different limits. Each group is identified by a combination of HTTP method and path prefix:

| Group | Paths | Limit | Rationale |
|-------|-------|-------|-----------|
| `chat` | `POST /api/v1/characters/*/messages` | 10 req/min | Each request triggers Claude API call + Mem0 search. Most expensive operation. |
| `write` | All other `POST`, `PUT`, `DELETE` endpoints | 20 req/min | Standard write operations (character CRUD, onboarding, etc.) |
| `read` | All `GET` endpoints (except health) | 60 req/min | Read-only operations are cheap (DB queries only). Relaxed limit for pagination scrolling. |

The default from `docs/08-guvenlik-performans.md` is 20 req/min. The chat group is stricter (10) because of LLM cost, and the read group is relaxed (60) because reads are inexpensive and users scroll through message history frequently.

### Token Bucket Algorithm

Each (user_id, group) pair has its own token bucket:

```
Bucket state:
  tokens: float        -- current token count (starts at max_tokens)
  last_refill: float   -- time.monotonic() of last refill calculation
  max_tokens: int      -- maximum tokens (equals the rate limit)
  refill_rate: float   -- tokens added per second (max_tokens / 60)

On each request:
  1. Calculate elapsed = now - last_refill
  2. Add elapsed * refill_rate tokens (capped at max_tokens)
  3. If tokens >= 1.0: consume 1 token, allow request
  4. If tokens < 1.0: reject with 429, set Retry-After = ceil((1.0 - tokens) / refill_rate)
```

This algorithm is smooth (no hard window boundaries), memory-efficient (one bucket per active user-group pair), and does not require synchronization (single-process GIL is sufficient).

### User Identification

The middleware extracts the user identity in this order:

1. If the `Authorization: Bearer <token>` header is present and parseable, decode the JWT header and payload (without full verification -- the auth dependency will verify later). Extract the `sub` claim as the rate limit key. This is a lightweight operation (base64 decode, no crypto) that avoids duplicating the full JWKS verification in the middleware.
2. If no `Authorization` header is present or the token is unparseable, use the client IP address from `request.client.host` as the rate limit key, prefixed with `ip:` to distinguish from user IDs.

**Why lightweight JWT parsing instead of full verification**: The rate limiting middleware runs before route handlers and before `Depends(get_current_user)`. Full JWT verification would duplicate work and add latency to every request. The middleware only needs the `sub` claim for keying; it does not need to verify the token is authentic. An attacker sending forged tokens with a real user's `sub` is a marginal concern: (a) they would still fail auth at the route handler, (b) the worst outcome is consuming the victim's rate limit bucket, which resets in 60 seconds.

**Why not use `get_current_user` in the middleware**: FastAPI middleware cannot use `Depends()`. The dependency injection system only works in route handlers. Middleware has access to the raw `Request` object only.

### Module: `backend/app/core/rate_limit.py`

This module contains the rate limiting logic. Placed in `core/` consistent with `core/auth.py` and `core/logging.py` -- application-wide cross-cutting concerns.

**Class: `TokenBucket`**

A simple data class representing a single user's bucket for one rate limit group.

```
Attributes:
    tokens: float
    last_refill: float
    max_tokens: int
    refill_rate: float  (tokens per second)

Methods:
    consume() -> tuple[bool, float]
        Refill tokens based on elapsed time, then attempt to consume one token.
        Returns (allowed: bool, retry_after_seconds: float).
        retry_after_seconds is 0.0 if allowed, otherwise the time until next token.
```

**Class: `RateLimiter`**

Manages all token buckets and provides the rate limiting decision.

```
Attributes:
    _buckets: dict[str, TokenBucket]
        Key format: "{user_id_or_ip}:{group}" e.g. "550e8400-...:{chat}" or "ip:192.168.1.1:read"
    _group_limits: dict[str, int]
        Maps group name to max requests per minute.
    _exempt_paths: set[str]
        Paths that bypass rate limiting entirely.
    _cleanup_interval: float
        How often to prune stale buckets (default: 300 seconds / 5 minutes).
    _last_cleanup: float
        time.monotonic() of last stale bucket cleanup.

Methods:
    check(key: str, group: str) -> tuple[bool, dict[str, str]]
        Check if the request is allowed. Returns (allowed, headers_dict).
        The headers_dict always contains X-RateLimit-Limit, X-RateLimit-Remaining,
        X-RateLimit-Reset. If not allowed, also contains Retry-After.

    classify_request(method: str, path: str) -> str | None
        Determine which rate limit group a request belongs to.
        Returns the group name ("chat", "write", "read") or None if exempt.

    _cleanup_stale_buckets() -> None
        Remove buckets that have been full (not used) for more than 5 minutes.
        Called periodically to prevent unbounded memory growth.
```

**Classification logic in `classify_request`**:

```
If path == "/api/v1/health": return None (exempt)
If method == "POST" and path matches /api/v1/characters/{uuid}/messages: return "chat"
If method in ("POST", "PUT", "DELETE"): return "write"
If method == "GET": return "read"
Otherwise: return "write" (default to most restrictive non-chat group)
```

The path matching for chat uses a simple regex: `^/api/v1/characters/[^/]+/messages$`. This avoids importing route definitions into the middleware.

**Function: `extract_user_key(request: Request) -> str`**

Extracts the rate limit key from the request:

```
1. Get Authorization header value
2. If starts with "Bearer ":
   a. Split token by "." (JWT has 3 parts)
   b. If 3 parts, base64url-decode the payload (second part)
   c. Parse as JSON, extract "sub" field
   d. If successful, return the sub value (UUID string)
3. If any step fails, return "ip:{request.client.host}"
```

This function intentionally catches all exceptions and falls back to IP-based keying. It must never raise or block.

**Stale Bucket Cleanup**:

Without cleanup, the `_buckets` dict would grow unbounded as new users make requests. Every `check()` call inspects `_last_cleanup`. If more than `_cleanup_interval` seconds have passed, buckets whose `tokens == max_tokens` (fully refilled = inactive) for more than 5 minutes are removed. This runs synchronously inside `check()` because it is fast (dict iteration) and infrequent (every 5 minutes).

### Module: `backend/app/middleware/rate_limit.py`

This module contains the ASGI middleware that integrates the `RateLimiter` into the FastAPI request lifecycle.

**Class: `RateLimitMiddleware`**

An ASGI middleware (using Starlette's `BaseHTTPMiddleware`) that:

1. Extracts the user key from the request.
2. Classifies the request into a rate limit group.
3. If exempt (group is None), passes through without rate limiting.
4. Calls `RateLimiter.check(key, group)`.
5. If allowed, calls the next handler and adds rate limit headers to the response.
6. If not allowed, returns a 429 JSONResponse with `Retry-After` header and rate limit headers.

```
Constructor:
    __init__(self, app: ASGIApp, rate_limiter: RateLimiter) -> None

Method:
    async def dispatch(self, request: Request, call_next) -> Response
```

### Registration in `main.py`

The middleware is registered in `create_app()` after CORS middleware (so CORS headers are applied even to 429 responses):

```python
from app.middleware.rate_limit import RateLimitMiddleware
from app.core.rate_limit import RateLimiter

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

**Middleware ordering**: FastAPI/Starlette applies middleware in reverse registration order. CORS is registered first (via `add_middleware`), then rate limiting. This means the request flows: CORS -> RateLimitMiddleware -> route handler. The response flows: route handler -> RateLimitMiddleware -> CORS. This ensures CORS headers are present on 429 responses (required for browser-based API testing tools like Swagger UI).

### New Config Fields

Three new fields in `backend/app/config.py`:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `rate_limit_chat` | `int` | `10` | Max requests per minute for chat/streaming endpoints |
| `rate_limit_write` | `int` | `20` | Max requests per minute for write endpoints |
| `rate_limit_read` | `int` | `60` | Max requests per minute for read endpoints |

These are configurable via environment variables (`RATE_LIMIT_CHAT`, `RATE_LIMIT_WRITE`, `RATE_LIMIT_READ`), allowing per-environment tuning without code changes.

### Error Handling

- The middleware catches all exceptions from `extract_user_key` and `classify_request` internally. If anything unexpected happens, the request is allowed through (fail-open). Rate limiting is a defense-in-depth measure, not a security boundary. A crash in the rate limiter must not take down the API.
- The 429 response uses the standard error format: `{"detail": "Rate limit exceeded"}` per `docs/standards/common.md` Section 7.

---

## 5. Test Requirements

### What Must Be Tested

#### Token Bucket Unit Tests (`tests/middleware/test_rate_limit.py`)

| # | Scenario | Expected |
|---|----------|----------|
| 1 | First request within limit | `consume()` returns `(True, 0.0)`, bucket has `max_tokens - 1` tokens |
| 2 | Requests up to limit within 1 minute | All return `(True, 0.0)` |
| 3 | Request exceeding limit (bucket empty) | Returns `(False, retry_after > 0)` |
| 4 | Request after waiting for refill | Bucket refills, returns `(True, 0.0)` |
| 5 | Bucket does not exceed max_tokens after long idle | Tokens capped at `max_tokens` |

#### RateLimiter Unit Tests (`tests/middleware/test_rate_limit.py` continued)

| # | Scenario | Expected |
|---|----------|----------|
| 6 | `classify_request("GET", "/api/v1/health")` | Returns `None` (exempt) |
| 7 | `classify_request("POST", "/api/v1/characters/{uuid}/messages")` | Returns `"chat"` |
| 8 | `classify_request("POST", "/api/v1/characters")` | Returns `"write"` |
| 9 | `classify_request("GET", "/api/v1/characters")` | Returns `"read"` |
| 10 | `classify_request("PUT", "/api/v1/characters/{uuid}")` | Returns `"write"` |
| 11 | `classify_request("DELETE", "/api/v1/characters/{uuid}")` | Returns `"write"` |
| 12 | `classify_request("POST", "/api/v1/auth/register")` | Returns `"write"` |
| 13 | `classify_request("POST", "/api/v1/onboarding/complete")` | Returns `"write"` |
| 14 | `check()` with different users produces independent buckets | User A exhausts limit, User B is still allowed |
| 15 | `check()` with same user but different groups produces independent buckets | User exhausts "chat" limit but "read" is still allowed |
| 16 | Stale bucket cleanup removes inactive buckets | After 5+ minutes idle, bucket is removed from `_buckets` |

#### extract_user_key Unit Tests (`tests/middleware/test_rate_limit.py` continued)

| # | Scenario | Expected |
|---|----------|----------|
| 17 | Request with valid Bearer JWT containing `sub` claim | Returns the `sub` UUID string |
| 18 | Request with no Authorization header | Returns `"ip:{client_ip}"` |
| 19 | Request with malformed Bearer token (not a JWT) | Returns `"ip:{client_ip}"` |
| 20 | Request with `Authorization: Basic ...` | Returns `"ip:{client_ip}"` |

#### Middleware Integration Tests (`tests/middleware/test_rate_limit_middleware.py`)

Using the FastAPI test client with the middleware registered:

| # | Scenario | Expected |
|---|----------|----------|
| 21 | Single request to any endpoint | Response includes `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` headers |
| 22 | Request to health endpoint with exhausted IP bucket | Returns 200, not 429 (exempt) |
| 23 | Requests exceeding chat limit (11th request within 1 minute) | 11th request returns 429 with `Retry-After` header and `{"detail": "Rate limit exceeded"}` body |
| 24 | Requests exceeding read limit (61st GET within 1 minute) | 61st GET returns 429 |
| 25 | 429 response has correct `Content-Type: application/json` | Verified |
| 26 | 429 response includes CORS headers | `Access-Control-Allow-Origin` present (CORS middleware applied) |
| 27 | Different users have independent rate limits | User A exhausted, User B succeeds |
| 28 | `Retry-After` header value is a positive integer | Verified on 429 response |
| 29 | After waiting `Retry-After` seconds, request succeeds | Mock time.monotonic() to advance time |

### How to Mock Time

For tests that verify token bucket refill behavior, mock `time.monotonic()` to simulate time progression without waiting. Use `unittest.mock.patch("app.core.rate_limit.time.monotonic")`.

### How to Create Test Requests with JWT

For `extract_user_key` tests, construct a minimal JWT by base64url-encoding a JSON payload with a `sub` field. No signing is needed because `extract_user_key` does not verify signatures.

### Code Quality Checks

```bash
ruff check backend/app/core/rate_limit.py backend/app/middleware/rate_limit.py
mypy backend/app/core/rate_limit.py backend/app/middleware/rate_limit.py
pytest backend/tests/middleware/ -v
```

---

## 6. File Manifest

Every file to be created or modified, grouped by purpose.

### Core Rate Limiting Logic

```
Backend:
  CREATE  backend/app/core/rate_limit.py
```

Contains `TokenBucket`, `RateLimiter`, and `extract_user_key`.

### Middleware

```
Backend:
  CREATE  backend/app/middleware/__init__.py
  CREATE  backend/app/middleware/rate_limit.py
```

Contains `RateLimitMiddleware` class.

### Configuration

```
Backend:
  MODIFY  backend/app/config.py
```

Add three new fields: `rate_limit_chat`, `rate_limit_write`, `rate_limit_read`.

### App Registration

```
Backend:
  MODIFY  backend/app/main.py
```

Import and register `RateLimitMiddleware` with configured `RateLimiter`.

### Tests

```
Backend:
  CREATE  backend/tests/middleware/__init__.py
  CREATE  backend/tests/middleware/test_rate_limit.py
  CREATE  backend/tests/middleware/test_rate_limit_middleware.py
```

### Documentation (Pipeline)

```
Shared:
  CREATE  shared/feature-specs/rate-limiting-middleware.md         (this file)
  CREATE  docs/pipeline/rate-limiting-middleware-architect.handoff.md
```

### Summary

| Action | Count |
|--------|-------|
| CREATE | 7 |
| MODIFY | 2 |
| DELETE | 0 |
| **Total** | **9** |

### Files NOT Modified

- `backend/requirements.txt` -- no new dependencies. The implementation uses only stdlib (`time`, `math`, `re`, `base64`, `json`) and Starlette's `BaseHTTPMiddleware` (included with FastAPI).
- `backend/app/dependencies.py` -- the middleware does not use FastAPI dependency injection.
- `backend/app/routes/` -- no route files are modified. Rate limiting is applied globally via middleware.
- `backend/.env.example` -- the new config fields have sensible defaults. Adding them to `.env.example` is optional (developer discretion) and not a required deliverable.

---

## 7. Acceptance Criteria

1. Given a user who has made fewer than 10 requests per minute to `POST /api/v1/characters/:id/messages`, when they send another request, then the request is processed normally and the response includes `X-RateLimit-Remaining` header showing the remaining quota.

2. Given a user who has made exactly 10 requests within the last minute to `POST /api/v1/characters/:id/messages`, when they send an 11th request, then the response is HTTP 429 with body `{"detail": "Rate limit exceeded"}` and a `Retry-After` header containing a positive integer.

3. Given a user who has been rate-limited (received 429), when they wait for the number of seconds specified in the `Retry-After` header and retry, then the request succeeds.

4. Given a user who has exhausted their chat rate limit (10/min), when they send a `GET /api/v1/characters` request, then it succeeds because read endpoints have a separate, higher limit (60/min).

5. Given a user who has made 60 GET requests within the last minute, when they send a 61st GET request, then the response is HTTP 429.

6. Given a user who has made 20 POST requests to non-chat endpoints within the last minute, when they send a 21st POST request, then the response is HTTP 429.

7. Given the ECS health check making requests to `GET /api/v1/health`, when the health check runs at any frequency, then it always receives HTTP 200 and is never rate-limited.

8. Given two different authenticated users, when User A exhausts their rate limit, then User B's requests are unaffected and continue to succeed.

9. Given an unauthenticated request (no Authorization header) to a public endpoint like `POST /api/v1/auth/login`, when the client exceeds the write rate limit, then the request is rate-limited by IP address and returns 429.

10. Given any successful API response (non-429), when a developer inspects the response headers, then `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers are present.

11. Given the 429 response, when a developer inspects it, then it follows the error format `{"detail": "..."}` as specified in `docs/standards/common.md` Section 7.

12. Given the backend configuration, when a developer sets `RATE_LIMIT_CHAT=5` in the environment, then the chat endpoint limit changes to 5 requests per minute without code changes.

13. Given the backend source code, when a developer runs `ruff check backend/app/core/rate_limit.py backend/app/middleware/rate_limit.py`, then zero errors are reported.

14. Given the backend test suite, when a developer runs `pytest backend/tests/middleware/ -v`, then all tests pass with exit code 0.

15. Given the rate limiter running for an extended period with many unique users, when stale buckets accumulate, then the cleanup mechanism removes them and memory usage does not grow unbounded.

---

## 8. Design Decisions and Rationale

### Why in-memory token bucket instead of Redis

Redis would be the correct choice for a horizontally scaled multi-instance deployment. However, Ember is in Phase 1.5 with a single ECS task. Adding Redis introduces infrastructure complexity (ElastiCache provisioning, connection management, failure modes) for a problem that does not yet exist. The in-memory approach is simpler, has zero additional latency (no network hop), and requires no new dependencies. When Ember scales to multiple ECS tasks, the `RateLimiter` class can be replaced with a Redis-backed implementation that exposes the same `check()` interface. The middleware and config remain unchanged.

### Why token bucket instead of fixed window or sliding window

- **Fixed window** has the "boundary burst" problem: a user can send 20 requests at second 59 and 20 more at second 61, effectively getting 40 requests in 2 seconds.
- **Sliding window** is accurate but requires storing individual request timestamps per user (memory-intensive).
- **Token bucket** provides smooth rate limiting, is memory-efficient (one small struct per user-group pair), and naturally handles bursty traffic (users can burst up to their limit, then must wait for refill).

### Why three groups instead of per-endpoint limits

Per-endpoint limits would require maintaining a mapping of every endpoint to its limit, which would need updating every time a new endpoint is added. Three groups cover the cost profile of all Ember endpoints: chat (expensive LLM calls), write (moderate DB writes), and read (cheap DB reads). This provides meaningful protection without maintenance burden.

### Why lightweight JWT parsing instead of full verification in middleware

Full JWT verification (JWKS fetch, RS256 signature check) would duplicate the work done in `get_current_user`. The middleware only needs the `sub` claim for rate limit keying, not for authentication. Lightweight parsing (base64 decode) adds negligible latency (~0.01ms) compared to full verification (~1-5ms). The security trade-off is minimal: the worst an attacker can do with a forged `sub` is consume another user's rate limit bucket, which refills in 60 seconds.

### Why fail-open instead of fail-closed

If the rate limiting middleware itself crashes (unexpected exception, memory corruption), failing closed would block all API requests. Rate limiting is defense-in-depth, not a security boundary. The actual security enforcement (authentication, authorization, data isolation) happens in route handlers. A rate limiter crash should log an error and allow the request through.

### Why `BaseHTTPMiddleware` instead of pure ASGI middleware

`BaseHTTPMiddleware` is simpler to implement and test (standard `async def dispatch` method with access to `Request` and `Response` objects). Pure ASGI middleware requires manually handling the ASGI protocol (scope, receive, send), which is more complex and error-prone. The performance difference is negligible for the rate limiting use case, and `BaseHTTPMiddleware` is the pattern used by Starlette's own middleware (including `CORSMiddleware`).

### Why exempt health endpoint by path, not by lack of auth

The health endpoint has no auth, but other unauthenticated endpoints (login, register) should still be rate-limited (by IP). Exempting by auth-absence would also exempt login/register, which is undesirable. Path-based exemption is explicit and minimal.

---

## 9. Notes for Developers

### For backend-dev

- The `backend/app/middleware/` directory does not exist yet. Create it with an `__init__.py`.
- Similarly, `backend/tests/middleware/` does not exist. Create it with an `__init__.py`.
- Use `time.monotonic()` for all timing, consistent with `core/auth.py`. Never use `time.time()` or `datetime.now()`.
- The `extract_user_key` function must be robust against all malformed input. Use `try/except Exception` around the JWT parsing. Never let it raise.
- For the path matching regex in `classify_request`, use `re.compile()` at module level (not inside the function) to avoid recompilation on every request.
- The `BaseHTTPMiddleware` import is `from starlette.middleware.base import BaseHTTPMiddleware`. It is re-exported by FastAPI but importing from Starlette directly is more explicit.
- When adding the middleware in `main.py`, add it AFTER the CORS middleware `add_middleware` call. Due to Starlette's reverse middleware ordering, this means the rate limiter runs BEFORE CORS in the request phase, but CORS headers are still applied to the response (including 429 responses).
- The `Retry-After` header value must be a non-negative integer (ceiling of the float seconds). Use `math.ceil()`.
- The `X-RateLimit-Reset` header should be a Unix timestamp (integer). Calculate as `int(time.time()) + seconds_until_full_refill`.
- Config fields go in the `Settings` class alongside existing fields. Group them with a `# Rate Limiting` comment, similar to the existing `# Chat context` grouping.
- The stale bucket cleanup is an optimization, not a correctness requirement. If testing it is complex, a simpler initial implementation that skips cleanup is acceptable for the first iteration, as long as the cleanup method exists and is testable.

### For backend-tester

- The middleware tests need the FastAPI test client (`httpx.AsyncClient` with `ASGITransport`). Use the existing `conftest.py` pattern.
- For tests that verify rate limit exhaustion, send requests in a tight loop and verify the N+1th request returns 429. Mock `time.monotonic()` to prevent time-based refill during the test.
- For tests that verify refill behavior, advance `time.monotonic()` by the appropriate amount and verify the next request succeeds.
- The `extract_user_key` tests can construct mock `Request` objects using Starlette's `Request` class with a custom scope dict. Alternatively, use the full test client with crafted `Authorization` headers.
- Verify that the 429 response body is valid JSON with the exact key `"detail"` (not `"error"` or `"message"`).
- Verify CORS headers are present on 429 responses by checking `Access-Control-Allow-Origin` in the response headers.
