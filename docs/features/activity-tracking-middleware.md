# Activity Tracking Middleware

> Silently records when each user was last active and when they last sent a chat message, powering the proactive notification system without adding any latency to API responses.

**Status**: Released
**Added in**: Phase 2 (P02-01)
**Platforms**: Backend
**GitHub Issue**: #13

---

## Overview

Every authenticated API request to Ember now has a silent side effect: it updates the `user_activity` table with the current timestamp. When the request is specifically a chat message (`POST /api/v1/characters/{id}/messages`), a second column — `last_chat_at` — is also updated. All other authenticated requests update only `last_active_at`.

This feature was built to feed the proactive notification system described in `docs/06-bildirimler.md`. Notifications like "morning check-in" or "we haven't talked in a while" need reliable signal about when a user was last active and when they last had a conversation. Without this middleware, the `user_activity` table would remain empty and the notification scheduler would have no data on which to act.

The implementation is entirely transparent to API callers: no response bodies, headers, or status codes change. The database write runs after the response is sent as a Starlette `BackgroundTask`, so it adds zero latency. If the write fails for any reason — connection pool exhausted, database timeout, programming error — the failure is logged at warning level and discarded. The original response is always returned unchanged. This is the same fail-open philosophy used by the rate limiting middleware.

---

## Architecture

### How It Works (Data Flow)

The middleware sits as the innermost layer of the middleware stack, just inside the rate limiting middleware and just outside the route handlers.

1. An HTTP request arrives and passes through `RequestIDMiddleware` (outermost), then `CORSMiddleware`, then `RateLimitMiddleware`.
2. `ActivityTrackingMiddleware.dispatch()` is called. It immediately calls `await call_next(request)` — the route handler runs and produces a response.
3. After the response object is in hand, the middleware attempts to extract the `sub` claim from the `Authorization: Bearer` header using `_extract_sub_from_jwt()`. This is a lightweight base64 decode of the JWT payload — no signature verification.
4. If `sub` is `None` (no header, malformed token, or missing `sub` field), the response is returned immediately with no side effect.
5. If `sub` is present, the middleware checks whether the request is a chat request: `method == "POST"` and the path matches the compiled regex `^/api/v1/characters/[^/]+/messages$`.
6. A `BackgroundTask` is created wrapping `update_user_activity(user_id=sub, is_chat_request=is_chat)`.
7. If the response already has a `background` attribute set (a route handler assigned its own background task), both tasks are chained using `BackgroundTasks` so neither is lost.
8. The response is returned to the client. Only after the response is sent does Starlette execute the background task.
9. `update_user_activity` opens its own `AsyncSessionLocal()` session (the request-scoped session is already closed at this point), executes the upsert, commits, and closes the session.

### Upsert Logic

The service uses a raw SQL upsert via `sqlalchemy.text()` rather than the ORM-level `insert().on_conflict_do_update()` pattern. This was chosen for clarity and because the `user_activity` table has no relationships that require ORM tracking.

For a non-chat request:
```sql
INSERT INTO user_activity (user_id, last_active_at, notifications_sent_today, updated_at)
VALUES (:user_id, :now, '[]'::jsonb, :now)
ON CONFLICT (user_id) DO UPDATE SET
    last_active_at = :now,
    updated_at = :now
```

For a chat request:
```sql
INSERT INTO user_activity (user_id, last_active_at, last_chat_at, notifications_sent_today, updated_at)
VALUES (:user_id, :now, :now, '[]'::jsonb, :now)
ON CONFLICT (user_id) DO UPDATE SET
    last_active_at = :now,
    last_chat_at = :now,
    updated_at = :now
```

The `ON CONFLICT` target is `(user_id)` — the primary key. The non-chat variant deliberately omits `last_chat_at` from the `DO UPDATE SET` clause, ensuring a subsequent non-chat request cannot overwrite a previously recorded chat timestamp.

`notifications_sent_today` is included in the `INSERT` values with a default of `'[]'::jsonb` for the first-ever request case. It is not touched by the `ON CONFLICT DO UPDATE` clause so existing values are preserved.

### JWT Extraction

The middleware reuses `_extract_sub_from_jwt()` imported directly from `backend/app/middleware/request_id.py`. This function base64url-decodes the JWT payload (the middle segment), parses it as JSON, and returns the `sub` string. All exceptions are caught and `None` is returned. No JWKS verification is performed: the middleware only needs the `sub` claim to key the upsert, and a forged `sub` would at worst update the wrong user's `last_active_at`, which has no security impact. Full token verification happens in `get_current_user()` within the route handler.

### Chat Path Detection

The path is matched against a module-level compiled regex:

```
_CHAT_PATH_RE = re.compile(r"^/api/v1/characters/[^/]+/messages$")
```

Matching requires both this regex and `method == "POST"`. This intentionally mirrors the same path pattern used by the rate limiting middleware's chat group, ensuring both features agree on what constitutes a chat request. The regex is strict: `/api/v1/characters/id/messages/extra` does not match (the `$` anchor prevents suffix paths), and `/api/v1/characters/id/memories` does not match.

### Middleware Registration Order

In `backend/app/main.py`, `add_middleware()` calls are in reverse of execution order (Starlette applies the last-registered middleware outermost). The registration order and resulting execution order are:

| Registration order | Middleware | Execution order (request flow) |
|-------------------|-----------|-------------------------------|
| 1st (first `add_middleware` call) | `ActivityTrackingMiddleware` | 4th (innermost) |
| 2nd | `RateLimitMiddleware` | 3rd |
| 3rd | `CORSMiddleware` | 2nd |
| 4th (last `add_middleware` call) | `RequestIDMiddleware` | 1st (outermost) |

The critical consequence: a request that is rejected by the rate limiter with 429 never reaches `ActivityTrackingMiddleware`. Activity is only recorded for requests that actually reach the route handlers.

### Database Tables Involved

| Table | Operation | Notes |
|-------|-----------|-------|
| `user_activity` | INSERT ... ON CONFLICT DO UPDATE | PK-based upsert, single row per user |

No other tables are read or written. No Mem0 operations are performed.

---

## API Reference

This feature introduces no new endpoints. All existing authenticated endpoints gain the side effect described above. No response bodies or headers change.

### Affected Endpoints (representative examples)

| Method | Path | Side effect |
|--------|------|-------------|
| `GET` | `/api/v1/characters` | Updates `last_active_at` |
| `POST` | `/api/v1/characters` | Updates `last_active_at` |
| `POST` | `/api/v1/characters/{id}/messages` | Updates `last_active_at` AND `last_chat_at` |
| `GET` | `/api/v1/memories` | Updates `last_active_at` |
| `GET` | `/api/v1/health` | No update (unauthenticated by design) |

Unauthenticated requests and rate-limited (429) requests produce no update.

---

## iOS Implementation

Not applicable. This is a backend-only feature with no mobile code changes.

---

## Android Implementation

Not applicable. This is a backend-only feature with no mobile code changes.

---

## Testing

### Coverage Summary

| Platform | File | Tests | Result |
|----------|------|-------|--------|
| Backend | `tests/middleware/test_activity_tracking.py` | 14 | 22 passed, 0 failed |
| Backend | `tests/services/test_activity_service.py` | 8 | (included in above total) |

The backend-dev handoff reports 22 tests passing across all test files (middleware tests, service tests, and the doc-code sync suite).

### Test Approach

**Regex unit tests** (`TestChatPathRegex`): Four tests verify the `_CHAT_PATH_RE` regex directly — correct match on the chat path, and non-matches on `/characters`, nested paths like `/messages/extra`, and sibling paths like `/memories`.

**Middleware unit tests** (`TestActivityTrackingMiddleware`): The middleware is instantiated directly and `dispatch()` is called with manually constructed `Request` objects (no HTTP server needed). `update_user_activity` is mocked via `unittest.mock.patch`. Test JWTs are constructed by base64url-encoding a JSON payload — no real Cognito key required. Tests verify:
- Authenticated GET calls `update_user_activity(is_chat_request=False)`.
- Authenticated POST to chat endpoint calls `update_user_activity(is_chat_request=True)`.
- Unauthenticated and malformed-JWT requests do not call `update_user_activity`.
- POST to `/api/v1/characters` (not `/messages`) calls with `is_chat_request=False`.
- The response is returned before the background task executes.
- A background task failure does not affect the response.
- An existing `response.background` task is chained, not replaced.

**Service unit tests** (`TestUpdateUserActivity`): `AsyncSessionLocal` is mocked so no test database is needed. Tests inspect the literal SQL text to verify that the non-chat variant omits `last_chat_at` from the `ON CONFLICT DO UPDATE` clause, the chat variant includes it, the correct `user_id` parameter is passed, and exceptions are caught and logged at warning level without raising.

**Integration tests** (`TestActivityTrackingIntegrationViaClient`): Uses `httpx.AsyncClient` with the full FastAPI app. `update_user_activity` is mocked at the import path to intercept calls without a real database. Verifies authenticated requests trigger the update and unauthenticated requests do not.

### Running Tests

```bash
cd /path/to/ember/backend && python -m pytest tests/middleware/test_activity_tracking.py tests/services/test_activity_service.py -v
```

Full backend suite:

```bash
cd /path/to/ember/backend && python -m pytest tests/ -v
```

---

## Known Limitations

- **No per-user throttling**: A user polling aggressively at the 60 req/min read limit triggers 60 upserts per minute. Each upsert is a fast PK-based operation (~1ms), runs in a background task, and does not affect latency. At current scale this is acceptable, but could be revisited if monitoring reveals significant database load. The spec explicitly deferred throttling to a future feature.
- **In-memory JWT extraction only**: The middleware uses lightweight base64 decoding to extract `sub`. If a request carries a syntactically valid JWT with a `sub` claim but an invalid signature, the middleware will still record activity (with the `sub` from the forged token). Full verification happens in `get_current_user()` inside the route handler, so the actual route access is still denied — only the `user_activity` row for that `sub` is touched. This is considered an acceptable trade-off for zero-latency middleware.
- **No backend-tester handoff**: The backend-dev agent wrote both implementation and tests in a single pass (22 tests, all passing). A separate backend-tester agent handoff was not produced. The test suite passes and meets the spec's acceptance criteria, but was not reviewed by a dedicated tester agent.

---

## Extending This Feature

**Adding tracking for a new endpoint type**: If a new endpoint category needs a distinct timestamp column (for example, `last_voice_call_at` for a future real-time voice feature), follow this pattern: add the column to `user_activity` via Alembic migration, add a new compiled regex at the top of `activity_tracking.py`, extend the `is_chat` detection logic to a more general `tracking_flags` dict, and update `update_user_activity` to accept and act on those flags.

**Adding throttling**: To prevent high-frequency upserts per user, add an in-memory `dict[str, float]` keyed by `user_id` storing the last update timestamp. In `dispatch()`, skip scheduling the background task if `time.monotonic() - last_update[sub] < THROTTLE_SECONDS`. Guard this dict with a lock if the server becomes multi-threaded. This dict is ephemeral (resets on restart), which is acceptable for this use case.

**Extracting `_extract_sub_from_jwt` to a shared utility**: The function is currently prefixed with `_` (private convention) in `request_id.py`. If a third middleware needs it, consider moving it to `backend/app/core/jwt_utils.py` and updating the two existing importers. The function is a pure utility with no side effects.

---

## Related Documentation

- [Database Schema and API Endpoints](../04-veri-api.md) — `user_activity` table definition
- [Proactive Notification System](../06-bildirimler.md) — the consumer of `last_active_at` and `last_chat_at`
- [Security and Performance](../08-guvenlik-performans.md) — fail-open middleware philosophy
- [Rate Limiting Middleware](./rate-limiting-middleware.md) — P1.5-01, which established the middleware stack and the `_extract_sub_from_jwt` helper this feature reuses
- [Cognito Auth Middleware](./cognito-auth-middleware.md) — P01-03, which defines the JWT `sub` claim format
