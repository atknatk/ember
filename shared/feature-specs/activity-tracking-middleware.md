# Feature Spec: P02-01 -- Activity Tracking Middleware

**Feature ID**: P02-01
**Phase**: 2
**Layer**: backend
**GitHub Issue**: #13
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature adds a FastAPI middleware that tracks user activity by updating the `user_activity` table on every authenticated request. On every authenticated request, it sets `last_active_at` to the current UTC timestamp. When the request is specifically a `POST /api/v1/characters/{id}/messages` (the chat endpoint), it additionally sets `last_chat_at` to the current UTC timestamp. The write uses an `INSERT ... ON CONFLICT (user_id) DO UPDATE` (upsert) so that the row is created if it does not exist, or updated in-place if it does.

### Why It Exists

The `user_activity` table powers the proactive notification system described in `docs/06-bildirimler.md`. Notifications like "morning check-in" or "we haven't talked in a while" require knowing when the user was last active and when they last chatted. Without this middleware, the `user_activity` table would remain empty and the notification scheduler would have no data to make decisions.

### Dependencies

- **Requires**: P01-06 (chat-streaming) -- the chat endpoint must exist for `last_chat_at` detection
- **Requires**: P01-03 (cognito-auth-middleware) -- JWT verification and `get_current_user` for user identification
- **Requires**: P01-01 (project-setup) -- FastAPI scaffold, `main.py`, database session management
- **Requires**: P01-02 (database-schema) -- `user_activity` table and `UserActivity` model must exist

### What This Feature Does NOT Do

- It does not create or modify the `user_activity` table schema. The table already exists per `docs/04-veri-api.md` and the `UserActivity` model already exists at `backend/app/models/user_activity.py`.
- It does not modify the `notifications_sent_today` column. That column is managed by the notification sending system (a future feature).
- It does not expose any new API endpoints. It is purely a middleware that runs as a side effect on existing requests.
- It does not block or delay the response. The activity update runs as a background task after the response is sent.

---

## 2. Data Models

### No New Tables

The `user_activity` table already exists in `docs/04-veri-api.md` with columns: `user_id` (PK), `last_active_at`, `last_chat_at`, `notifications_sent_today`, `updated_at`.

### No Schema Changes

The existing `UserActivity` model at `backend/app/models/user_activity.py` already has all required columns. No `ALTER TABLE` statements are needed.

### No New Indexes

The `user_activity` table is keyed by `user_id` (PK). The upsert targets this primary key. No additional indexes are required because:
- The only access pattern is point lookup/upsert by `user_id` (PK).
- There is no pagination or range scan on this table in this feature.

### No Mem0 Operations

This feature does not interact with Mem0.

---

## 3. API Changes

### No New Endpoints

This feature does not introduce any new API endpoints.

### Modified Behavior on Authenticated Endpoints

Every authenticated request (one that carries a valid `Authorization: Bearer` header with a resolvable `sub` claim) now has the side effect of updating `user_activity.last_active_at` for that user. This update is invisible to the caller -- no response body or header changes.

For `POST /api/v1/characters/{id}/messages` specifically, `user_activity.last_chat_at` is also updated.

### No Response Changes

No response bodies or headers are modified by this middleware.

---

## 4. Backend Logic

### Middleware: `backend/app/middleware/activity_tracking.py`

**Class: `ActivityTrackingMiddleware`**

An ASGI middleware using Starlette's `BaseHTTPMiddleware` that updates user activity after each authenticated request.

```
Constructor:
    __init__(self, app: ASGIApp) -> None

Method:
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response
```

**`dispatch` method behavior**:

1. Call `response = await call_next(request)` first. The activity update must not delay the response.
2. After the response is obtained, determine if this is an authenticated request by extracting the `sub` claim from the JWT. Use the same lightweight JWT parsing approach as `RequestIDMiddleware` (base64 decode of the payload, no signature verification). Reuse the existing `_extract_sub_from_jwt` helper from `backend/app/middleware/request_id.py` by extracting it to a shared utility, or import it directly from that module.
3. If `sub` is None (unauthenticated request), return the response immediately with no side effect.
4. If `sub` is present, determine whether this is a chat request by checking: `request.method == "POST"` and the path matches the pattern `/api/v1/characters/{uuid}/messages`.
5. Schedule the database upsert as a Starlette `BackgroundTask` attached to the response. This ensures the upsert runs after the response is sent to the client, adding zero latency to the request.

**Why background task instead of inline await**: The activity update is a fire-and-forget side effect. The user should not wait for it. If it fails (e.g., database connection issue), the request should still succeed. Using `response.background` is the idiomatic Starlette approach for post-response work.

**Why not use FastAPI's `BackgroundTasks` dependency**: Middleware cannot use FastAPI dependency injection (`Depends`). Starlette's `response.background` is the middleware-compatible equivalent.

### Service: `backend/app/services/activity_service.py`

**Function: `update_user_activity`**

```
async def update_user_activity(
    user_id: str,
    is_chat_request: bool,
) -> None
```

This function:
1. Creates its own database session using `AsyncSessionLocal()` context manager (it cannot share the request's session because it runs after the response is sent and the request session is closed).
2. Executes an upsert using SQLAlchemy's `insert(...).on_conflict_do_update(...)` on the `user_activity` table.
3. The upsert sets:
   - `last_active_at = NOW()` (always)
   - `last_chat_at = NOW()` (only when `is_chat_request` is True)
   - `updated_at = NOW()` (always)
4. If `is_chat_request` is False, the `ON CONFLICT DO UPDATE` clause must NOT overwrite `last_chat_at`. It should only update `last_active_at` and `updated_at`.
5. Commits the transaction.
6. Catches all exceptions and logs them at `warning` level. A failure to update activity must never propagate or affect the user.

**SQL equivalent of the upsert**:

For a non-chat request:
```sql
INSERT INTO user_activity (user_id, last_active_at, notifications_sent_today, updated_at)
VALUES ($1, NOW(), '[]'::jsonb, NOW())
ON CONFLICT (user_id) DO UPDATE SET
    last_active_at = NOW(),
    updated_at = NOW();
```

For a chat request:
```sql
INSERT INTO user_activity (user_id, last_active_at, last_chat_at, notifications_sent_today, updated_at)
VALUES ($1, NOW(), NOW(), '[]'::jsonb, NOW())
ON CONFLICT (user_id) DO UPDATE SET
    last_active_at = NOW(),
    last_chat_at = NOW(),
    updated_at = NOW();
```

### Chat Path Detection

The middleware identifies chat requests using the same regex pattern as the rate limiting middleware: `^/api/v1/characters/[^/]+/messages$` combined with `method == "POST"`. Compile the regex at module level.

### Registration in `main.py`

The middleware is registered in `create_app()`. The registration order matters. This middleware should be registered BEFORE the rate limiting middleware (so it runs after rate limiting in the request flow, since Starlette applies middleware in reverse registration order). The activity tracking middleware should only fire for requests that pass rate limiting.

Target middleware execution order (request flow): RequestID -> CORS -> RateLimit -> ActivityTracking -> route handler.

In `main.py` registration order (reverse of execution):
1. `RateLimitMiddleware` (registered first, runs third)
2. `CORSMiddleware` (registered second, runs second)
3. `RequestIDMiddleware` (registered last, runs first)

`ActivityTrackingMiddleware` should be registered before `RateLimitMiddleware` so that it is the innermost middleware (closest to the route handler). This ensures it only runs for requests that pass rate limiting -- a rate-limited (429) request should NOT update activity.

Updated registration order in `main.py`:
```
# Activity tracking middleware (innermost — only runs for non-rate-limited requests)
app.add_middleware(ActivityTrackingMiddleware)

# Rate limiting middleware
app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)

# CORS middleware
app.add_middleware(CORSMiddleware, ...)

# Request ID middleware (outermost — registered last)
app.add_middleware(RequestIDMiddleware)
```

### Error Handling

- The middleware itself (dispatch method) wraps the background task scheduling in a try/except. If anything fails before `call_next`, the request proceeds normally.
- The `update_user_activity` function catches all exceptions internally and logs at `warning` level. It never raises.
- If the database session cannot be created (e.g., connection pool exhausted), the activity update is silently skipped.
- This is a fail-open design consistent with the rate limiting middleware pattern.

### Throttling Consideration

On high-frequency polling endpoints (e.g., if a mobile client calls `GET /characters` every few seconds), this middleware would issue an upsert on every request. For Phase 2, this is acceptable because:
- The upsert is a single-row operation on a primary key, which is fast (~1ms).
- It runs in a background task, so it does not affect response latency.
- The mobile clients are rate-limited to 60 reads/min, bounding the maximum upsert frequency.

If this becomes a concern at scale, a future optimization could throttle updates to once per 60 seconds per user (using an in-memory timestamp cache). This is NOT in scope for P02-01.

---

## 5. iOS Screens and Components

Not applicable. This is a backend-only feature with no mobile UI changes.

---

## 6. Android Screens and Components

Not applicable. This is a backend-only feature with no mobile UI changes.

---

## 7. Test Plan

### Backend Tests

#### Unit Tests: `backend/tests/middleware/test_activity_tracking.py`

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Authenticated GET request triggers `last_active_at` update | `update_user_activity` is called with `is_chat_request=False` |
| 2 | Authenticated `POST /api/v1/characters/{uuid}/messages` triggers both `last_active_at` and `last_chat_at` update | `update_user_activity` is called with `is_chat_request=True` |
| 3 | Unauthenticated request (no Authorization header) does NOT trigger any update | `update_user_activity` is never called |
| 4 | Request with malformed JWT does NOT trigger any update | `update_user_activity` is never called |
| 5 | `POST /api/v1/characters` (not the messages endpoint) triggers only `last_active_at` | `update_user_activity` is called with `is_chat_request=False` |
| 6 | Middleware does not delay the response (background task pattern) | Response is returned before `update_user_activity` completes |
| 7 | If `update_user_activity` raises an exception, the response is still returned successfully | Middleware fail-open behavior |

#### Unit Tests: `backend/tests/services/test_activity_service.py`

| # | Scenario | Expected |
|---|----------|----------|
| 8 | `update_user_activity(user_id, is_chat_request=False)` inserts a new row | Row exists with `last_active_at` set and `last_chat_at` NULL |
| 9 | `update_user_activity(user_id, is_chat_request=True)` inserts a new row | Row exists with both `last_active_at` and `last_chat_at` set |
| 10 | Calling `update_user_activity` twice for the same user updates existing row (upsert) | Only one row exists, `last_active_at` is updated |
| 11 | `update_user_activity(user_id, is_chat_request=False)` does NOT overwrite existing `last_chat_at` | `last_chat_at` retains its previous value |
| 12 | `update_user_activity(user_id, is_chat_request=True)` after a non-chat update sets `last_chat_at` | `last_chat_at` is now set |
| 13 | Database error is caught and logged, does not raise | Function returns normally, warning logged |

#### Integration Tests: `backend/tests/middleware/test_activity_tracking_integration.py`

Using the FastAPI test client with the middleware registered:

| # | Scenario | Expected |
|---|----------|----------|
| 14 | Send authenticated GET to any endpoint, verify `user_activity` row is created/updated | Row exists with `last_active_at` set |
| 15 | Send authenticated POST to chat endpoint, verify both timestamps are set | Row has both `last_active_at` and `last_chat_at` set |
| 16 | Send unauthenticated request, verify no `user_activity` row is created | Table remains empty for that user |

#### How to Mock

- For middleware unit tests, mock `update_user_activity` to verify it is called with the correct arguments. Use `unittest.mock.patch("app.middleware.activity_tracking.update_user_activity")`.
- For service unit tests, use a real test database (async SQLite or PostgreSQL test instance per the existing test setup). Verify rows directly with SELECT queries.
- For the JWT extraction, construct a minimal JWT by base64url-encoding a JSON payload with a `sub` field (same approach as rate limiting tests).

---

## 8. Acceptance Criteria

1. Given any authenticated API request, when the request completes successfully, then the `user_activity` table contains a row for that user with `last_active_at` set to approximately the current time (within 5 seconds).

2. Given an authenticated `POST /api/v1/characters/{id}/messages` request, when the request completes, then the `user_activity` row for that user has both `last_active_at` and `last_chat_at` set to approximately the current time.

3. Given an authenticated `GET /api/v1/characters` request (not a chat endpoint), when the request completes, then `last_active_at` is updated but `last_chat_at` is NOT modified from its previous value.

4. Given a user with no prior `user_activity` row, when they make their first authenticated request, then a new row is inserted with `user_id` matching the JWT `sub`, `last_active_at` set, and `notifications_sent_today` defaulting to `[]`.

5. Given a user with an existing `user_activity` row, when they make another authenticated request, then the existing row is updated (not a second row inserted) and `updated_at` reflects the new time.

6. Given an unauthenticated request (no Authorization header), when the request completes, then no `user_activity` row is created or modified.

7. Given a request that is rate-limited (returns 429), when the rate limiter rejects it, then no `user_activity` update occurs for that request.

8. Given a database connection failure during the background activity update, when the update fails, then the original API response is unaffected and a warning is logged.

9. Given the activity tracking middleware is registered, when any API endpoint is called, then the response latency is not increased (the update runs as a background task, not inline).

10. Given the backend source code, when a developer runs `ruff check backend/app/middleware/activity_tracking.py backend/app/services/activity_service.py`, then zero errors are reported.

11. Given the backend test suite, when a developer runs `pytest backend/tests/middleware/test_activity_tracking.py backend/tests/services/test_activity_service.py -v`, then all tests pass with exit code 0.

---

## 9. File Manifest

```
Backend:
  CREATE  backend/app/middleware/activity_tracking.py
  CREATE  backend/app/services/activity_service.py
  MODIFY  backend/app/main.py                          (register ActivityTrackingMiddleware)
  CREATE  backend/tests/middleware/test_activity_tracking.py
  CREATE  backend/tests/services/test_activity_service.py

Shared:
  CREATE  shared/feature-specs/activity-tracking-middleware.md    (this file)
  CREATE  docs/pipeline/activity-tracking-middleware-architect.handoff.md
```

### Summary

| Action | Count |
|--------|-------|
| CREATE | 5 |
| MODIFY | 1 |
| DELETE | 0 |
| **Total** | **6** |

### Files NOT Modified

- `backend/app/models/user_activity.py` -- the model already has all required columns.
- `backend/app/config.py` -- no new configuration fields needed. The middleware has no configurable parameters.
- `backend/app/dependencies.py` -- middleware does not use FastAPI dependency injection.
- `backend/app/routes/` -- no route files are modified. Activity tracking is applied globally via middleware.
- `backend/requirements.txt` -- no new dependencies. Uses only SQLAlchemy (already installed) and Starlette's `BaseHTTPMiddleware` (included with FastAPI).

---

## 10. Design Decisions and Rationale

### Why background task instead of inline await

The activity update is a side effect that the user does not need to wait for. Running it inline would add ~1-5ms to every request (database round trip). Using Starlette's `response.background` pattern ensures zero impact on response latency. If the background task fails, the API response is already sent and unaffected.

### Why a separate database session

The background task runs after the response is sent. By that time, the request-scoped database session (from `get_db`) is closed. The activity service must create its own session via `AsyncSessionLocal()`. This is consistent with how background tasks handle database access in FastAPI applications.

### Why upsert instead of separate insert/update logic

The upsert (`INSERT ... ON CONFLICT DO UPDATE`) is a single atomic SQL statement. It handles both the first-ever request (insert) and subsequent requests (update) without a race condition. Using separate "check if exists, then insert or update" logic would require two queries and be vulnerable to TOCTOU race conditions under concurrent requests.

### Why reuse the JWT parsing from request_id middleware

The `_extract_sub_from_jwt` function in `request_id.py` already implements the lightweight JWT payload extraction pattern. Rather than duplicating this logic, the activity tracking middleware imports and reuses it. This function performs base64 decode only (no signature verification), which is appropriate because:
- Full JWT verification is done by the route handler's `get_current_user` dependency.
- The middleware only needs the `sub` claim to key the activity update.
- A forged `sub` would at worst update the wrong user's `last_active_at`, which has no security impact (the actual route handler still verifies the token).

### Why not throttle updates per user

A user making 60 read requests per minute would trigger 60 upserts. Each upsert is a fast PK-based operation (~1ms). At 60/min, this adds 60ms total of background database work per minute per user, which is negligible. Adding an in-memory throttle would introduce complexity (cache invalidation, memory management) for minimal benefit. This can be revisited if monitoring shows the upsert load becoming significant at scale.

---

## 11. Notes for Developers

### For backend-dev

- The `backend/app/middleware/` directory and `backend/tests/middleware/` directory already exist (created by the rate limiting middleware feature).
- Import `_extract_sub_from_jwt` from `backend/app/middleware/request_id.py`. If the underscore-prefix convention makes this feel like a private import, consider renaming it to `extract_sub_from_jwt` (removing the underscore) in a refactor. However, for this feature, importing the underscore-prefixed function is acceptable since both modules are in the same `middleware` package.
- For the SQLAlchemy upsert, use `from sqlalchemy.dialects.postgresql import insert` to get the PostgreSQL-specific `insert` that supports `on_conflict_do_update()`.
- The `on_conflict_do_update` call should target `index_elements=["user_id"]` (the primary key).
- When `is_chat_request` is False, the `set_` dict in `on_conflict_do_update` should include only `last_active_at` and `updated_at`. When True, it should also include `last_chat_at`.
- For attaching the background task, use `response.background = BackgroundTask(update_user_activity, user_id=sub, is_chat_request=is_chat)`. Import `BackgroundTask` from `starlette.background`.
- Note: if `response.background` already has a task (from a route handler), you need to chain them using `BackgroundTasks` (plural) from Starlette, or check and append. In practice, most Ember endpoints do not set background tasks, so this edge case is low-risk. Handle it defensively: if `response.background` is already set, create a `BackgroundTasks` instance containing both the existing task and the new one.
- Use `logging.getLogger("ember")` for the logger, consistent with other middleware modules.

### For backend-tester

- The middleware tests should mock `update_user_activity` to isolate middleware behavior from database concerns. Use `unittest.mock.patch`.
- The service tests should use the test database fixture from `conftest.py` to verify actual upsert behavior.
- Construct test JWTs using the same base64-encoding approach used in the rate limiting middleware tests.
- To test the "does not overwrite `last_chat_at`" scenario: first call with `is_chat_request=True`, then call with `is_chat_request=False`, and verify `last_chat_at` retains the value from the first call.
- To verify background task execution in integration tests, you may need to use `await asyncio.sleep(0.1)` or similar to allow the background task to complete before checking the database.
