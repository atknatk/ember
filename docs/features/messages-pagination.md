# Messages Pagination

> Upgrades the message history endpoint to use a composite `(created_at, id)` cursor encoded as base64 URL-safe JSON, eliminating duplicate/skipped messages when timestamps collide and adding graceful error handling for invalid cursors.

**Status**: Released
**Added in**: Phase 1 (P01-07)
**Platforms**: Backend
**GitHub Issue**: #9

---

## Overview

Messages pagination (P01-07) hardens the cursor-based pagination on the `GET /api/v1/characters/{character_id}/messages` endpoint that was initially delivered in P01-06 (chat-streaming). The original implementation used a plain ISO 8601 timestamp as the cursor, which has a correctness bug: when two messages share the same `created_at` value, the `created_at < $cursor` filter can skip one message or return it twice on different pages.

This scenario is not theoretical. The `_persist_exchange` background task inserts the user message and assistant message in a single database transaction. PostgreSQL's `server_default=func.now()` assigns both rows the same `created_at` timestamp. If the client paginates and the cursor lands on that shared timestamp, the result set is ambiguous.

P01-07 replaces the plain timestamp cursor with a composite `(created_at, id)` cursor. The UUID acts as a deterministic tiebreaker when timestamps collide. The cursor is encoded as base64 URL-safe JSON, making it opaque to clients and preventing manual construction. Invalid cursor values now return HTTP 400 instead of crashing with an unhandled 500 error.

---

## Architecture

### How It Works (Data Flow)

1. The mobile client sends `GET /api/v1/characters/{character_id}/messages` with an optional `cursor` query parameter and an optional `limit` parameter (default 20, max 100).
2. The route handler extracts `user_id` from the JWT via the `get_current_user` dependency.
3. If a `cursor` string is present, `_decode_cursor()` base64-decodes it, JSON-parses the result, and extracts a `datetime` (`ts`) and a `UUID` (`id`) into a frozen `MessageCursor` dataclass. Any failure at any step raises `HTTPException(400, "Invalid cursor format")`.
4. `ChatService.get_messages()` validates character ownership (403 if mismatch) and looks up the conversation (404 if not found).
5. The service builds a SQLAlchemy query ordered by `(created_at DESC, id DESC)` with `LIMIT = limit + 1`. If a cursor is provided, the query adds a row-value comparison filter: `(created_at, id) < (cursor.ts, cursor.id)`.
6. The extra row (limit + 1) determines `has_more`. Only the first `limit` rows are returned.
7. If `has_more` is true, `_encode_cursor()` serializes the last returned message's `(created_at, id)` as base64 URL-safe JSON to produce `next_cursor`.
8. The response is returned as `MessageListResponse` with `items`, `next_cursor`, and `has_more`.

### Cursor Encoding and Decoding

The cursor is a base64url-encoded JSON object with two fields:

```json
{"ts": "2026-02-23T14:30:00+00:00", "id": "550e8400-e29b-41d4-a716-446655440088"}
```

**Encoding** (building `next_cursor` for the response):
1. Take the last message's `created_at` (ISO 8601) and `id` (UUID string).
2. Serialize as JSON: `{"ts": "<ISO 8601>", "id": "<UUID>"}`.
3. Encode with `base64.urlsafe_b64encode()`.
4. Strip trailing `=` padding characters.

**Decoding** (parsing the `cursor` query parameter):
1. Restore base64 padding: append `=` characters until `len(cursor) % 4 == 0`.
2. `base64.urlsafe_b64decode()` the padded string.
3. `json.loads()` the decoded bytes.
4. Extract `ts` and parse with `datetime.fromisoformat()`.
5. Extract `id` and parse with `uuid.UUID()`.
6. Return a `MessageCursor(ts=..., id=...)` frozen dataclass.
7. If any step fails, raise `HTTPException(status_code=400, detail="Invalid cursor format")`.

### SQL Query Pattern

The row-value comparison `(created_at, id) < ($cursor_ts, $cursor_id)` is standard SQL. PostgreSQL evaluates it as:

```
created_at < $cursor_ts
OR (created_at = $cursor_ts AND id < $cursor_id)
```

This correctly handles the tiebreaker when two messages share the same timestamp. In SQLAlchemy, this is expressed using `sqlalchemy.tuple_()`:

```python
from sqlalchemy import tuple_

stmt = stmt.where(
    tuple_(Message.created_at, Message.id) < tuple_(cursor.ts, cursor.id)
)
```

### Database Tables Involved

| Table | Operation | Notes |
|-------|-----------|-------|
| `characters` | SELECT | Ownership check: `user_id = $user_id`, active check |
| `conversations` | SELECT | Look up conversation by `character_id` |
| `messages` | SELECT | Cursor-based pagination with `(created_at DESC, id DESC)` ordering |

No new tables or columns were added. The existing composite index `idx_messages_conv_time` on `(conversation_id, created_at DESC)` supports the query. The `id` tiebreaker operates on the small result set (max `limit + 1` rows) after the index scan, so no additional index is needed.

---

## API Reference

See [`docs/04-veri-api.md`](../04-veri-api.md) for the full API contract.

### GET /api/v1/characters/{character_id}/messages

**Auth**: Bearer JWT required
**Success Status**: `200 OK`

Retrieves paginated message history for a character's conversation using composite cursor-based pagination.

**Query Parameters**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `cursor` | string | no | none | Base64 URL-safe encoded JSON: `{"ts": "<ISO 8601>", "id": "<UUID>"}`. Messages strictly older than this cursor position are returned. When absent, the newest messages are returned. |
| `limit` | integer | no | 20 | Number of messages per page. Min 1, max 100. |

**Response Body (200 OK)**:

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440088",
      "role": "assistant",
      "content": "Great! Let's start with some conversation practice.",
      "media_url": null,
      "metadata": null,
      "created_at": "2026-02-23T14:30:05+00:00"
    },
    {
      "id": "550e8400-e29b-41d4-a716-446655440087",
      "role": "user",
      "content": "I want to practice English today!",
      "media_url": null,
      "metadata": null,
      "created_at": "2026-02-23T14:30:05+00:00"
    }
  ],
  "next_cursor": "eyJ0cyI6ICIyMDI2LTAyLTIzVDE0OjI1OjAwKzAwOjAwIiwgImlkIjogIjU1MGU4NDAwLWUyOWItNDFkNC1hNzE2LTQ0NjY1NTQ0MDA4NiJ9",
  "has_more": true
}
```

Note: both messages in the example share the same `created_at` value (`14:30:05`). The composite cursor ensures the next page starts after the correct message.

**Response Fields**:

| Field | Type | Notes |
|-------|------|-------|
| `items` | array | Messages in reverse chronological order (newest first) |
| `items[].id` | string (UUID) | Message primary key |
| `items[].role` | string | `"user"` or `"assistant"` |
| `items[].content` | string | Message text |
| `items[].media_url` | string or null | S3 URL for attached media |
| `items[].metadata` | object or null | Intent action data or other metadata |
| `items[].created_at` | string (ISO 8601) | Message creation timestamp |
| `next_cursor` | string or null | Opaque base64-encoded cursor for the next page. Null when no more messages. |
| `has_more` | boolean | True if older messages exist beyond this page |

**Error Responses**:

| Status | Detail | When |
|--------|--------|------|
| 400 | `"Invalid cursor format"` | Cursor is not valid base64, not valid JSON, missing `ts` or `id` fields, `ts` is not a valid ISO 8601 timestamp, `id` is not a valid UUID, or cursor is an empty string |
| 401 | `"Invalid or expired token"` | Missing or invalid JWT |
| 403 | `"Character does not belong to user"` | Ownership mismatch |
| 404 | `"Character not found"` | Non-existent or inactive character |
| 404 | `"Conversation not found"` | Character has no conversation |
| 422 | Standard FastAPI validation error | Invalid limit range or invalid UUID path parameter |

### Cursor Format Details

The cursor is **opaque** to clients. Clients receive `next_cursor` from one response and pass it verbatim as the `cursor` parameter on the next request. Clients must not construct cursors manually or depend on the internal format.

**Encoded example**: `eyJ0cyI6ICIyMDI2LTAyLTIzVDE0OjMwOjAwKzAwOjAwIiwgImlkIjogIjU1MGU4NDAwLWUyOWItNDFkNC1hNzE2LTQ0NjY1NTQ0MDA4OCJ9`

**Decoded**: `{"ts": "2026-02-23T14:30:00+00:00", "id": "550e8400-e29b-41d4-a716-446655440088"}`

Old-format cursors (plain ISO 8601 timestamps from P01-06) are **not** supported and will return HTTP 400. This is acceptable because no mobile client has shipped and no client has persisted old cursors.

---

## Configuration

No new configuration values were added in P01-07. The pagination endpoint uses the same configuration established in P01-06.

**Relevant existing settings**:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| Default `limit` | int | 20 | Hardcoded as the FastAPI query parameter default. Min 1, max 100. |

Note: `docs/standards/common.md` Section 6 specifies a default limit of 30. The implementation uses 20 to match the original P01-06 behavior and issue description. This is documented here so the mobile team is aware of the default page size.

---

## Files

| File | Role |
|------|------|
| `backend/app/routes/chat.py` | Route handler for `get_messages`. Decodes the cursor string via `_decode_cursor()` and delegates to `ChatService.get_messages()`. |
| `backend/app/services/chat_service.py` | `MessageCursor` frozen dataclass, `_encode_cursor()` and `_decode_cursor()` helpers, and the `ChatService.get_messages()` method with `tuple_()` row-value comparison. |
| `backend/app/schemas/chat.py` | `MessageListResponse` schema (unchanged -- `next_cursor` is `str | None`; only its content format changed from plain ISO to base64 JSON). |

### What Changed vs P01-06

| Aspect | P01-06 (before) | P01-07 (after) |
|--------|-----------------|----------------|
| Cursor format | Plain ISO 8601 timestamp string | Base64 URL-safe JSON `{"ts": ..., "id": ...}` |
| Cursor type in service | `datetime | None` | `MessageCursor | None` |
| WHERE clause | `created_at < cursor` | `tuple_(created_at, id) < tuple_(ts, id)` |
| `next_cursor` encoding | `items[-1].created_at.isoformat()` | `_encode_cursor(items[-1].created_at, items[-1].id)` |
| Invalid cursor handling | Unhandled `ValueError` producing HTTP 500 | `HTTPException(400, "Invalid cursor format")` |

---

## Testing

### Coverage Summary

| File | Tests | Line Coverage | Branch Coverage |
|------|-------|---------------|-----------------|
| `test_chat_routes.py` | 62 total (18 new pagination edge-case tests) | 100% | 100% |
| `test_chat_service.py` | 97 total (21 new pagination edge-case tests) | 100% | 100% |
| **Combined (chat files)** | **192 passed, 0 failed** | **98% lines** | **Above 70% branches** |

Full backend suite: 952 passed, 0 failed, 0 skipped. No regressions.

### Key Test Scenarios

**Route-level tests** (`TestGetMessagesPaginationEdgeCases`):
- Invalid cursor variants: not base64, valid base64 but invalid JSON, missing `ts` field, missing `id` field, `ts` not ISO 8601, `id` not a UUID, empty string, null bytes, very long string, whitespace, old-format plain timestamp
- Valid cursor acceptance: base64 cursor with padding accepted, `next_cursor` decodes to valid JSON with `ts` and `id`
- Limit boundaries: limit=1, limit=100, negative limit, non-integer limit
- Multi-page sequential walk: no duplicate message IDs across pages
- Default limit: omitting the parameter returns 200

**Service-level tests** (`TestPaginationEdgeCases`, `TestCursorHelpersEdgeCases`):
- Same-timestamp tiebreaker: three messages with identical `created_at` paginated with limit=1 across three pages, each appearing exactly once
- Cursor roundtrip: `_decode_cursor(_encode_cursor(ts, id))` preserves values including microsecond precision and timezone offsets
- Boundary conditions: exactly `limit` messages (has_more=false), exactly `limit+1` messages (has_more=true), single message, cursor with future timestamp, cursor past oldest message
- `MessageCursor` immutability: frozen dataclass rejects attribute assignment
- Edge case inputs: nil UUID, max UUID, positive/negative timezone offsets

### Running Tests

Chat pagination tests only:

```bash
cd backend && python -m pytest tests/test_chat_routes.py tests/test_chat_service.py -v -k "pagination or cursor or Cursor"
```

All chat tests (includes P01-06 tests):

```bash
cd backend && python -m pytest tests/test_chat_routes.py tests/test_chat_service.py -v
```

Full backend suite:

```bash
cd backend && python -m pytest tests/ -v --ignore=tests/test_migration.py
```

---

## Known Limitations

- **No backward compatibility for old cursors**: Plain ISO 8601 timestamp cursors from P01-06 are rejected with HTTP 400. This is intentional since no mobile client has shipped.
- **Default limit is 20, not 30**: The `docs/standards/common.md` Section 6 standard specifies 30 as the default limit, but the implementation uses 20 to match the P01-06 behavior and issue description. Mobile clients should not hardcode this value and should respect the `has_more` flag.
- **No additional index for the id tiebreaker**: The existing index `idx_messages_conv_time` on `(conversation_id, created_at DESC)` does not include `id`. The `id` tiebreaker operates on the small result set after the index scan. If performance profiling on very large conversations shows issues, a three-column index `(conversation_id, created_at DESC, id DESC)` can be added.
- **Cursor expiry is not enforced**: Cursors do not expire. A cursor from an old response will still work as long as the referenced message exists. If a message is hard-deleted (not currently supported), the cursor will return messages older than the deleted message's position.

---

## Design Decisions

### Why composite `(created_at, id)` instead of plain timestamp

The plain timestamp cursor has a correctness bug when two messages share the same `created_at` (which happens every time `_persist_exchange` inserts a user-assistant pair in one transaction). The composite cursor with UUID tiebreaker is the only correct solution. This also aligns with `docs/standards/common.md` Section 6.

### Why base64 URL-safe encoding

Base64 makes the cursor opaque to clients. They cannot construct cursors manually or depend on the internal format. URL-safe base64 (using `-` and `_` instead of `+` and `/`) avoids URL encoding issues. Trailing `=` padding is stripped on encode and restored on decode for cleanliness.

### Why a single error message for all cursor failures

All cursor parse failures (bad base64, bad JSON, missing fields, wrong types) return the same `{"detail": "Invalid cursor format"}` message. Exposing internal parsing details (e.g., "invalid base64" vs. "missing ts field") would leak implementation details and provide no actionable information to the client.

### Why `MessageCursor` as a frozen dataclass

A frozen dataclass provides type safety, immutability, and semantic clarity. The cursor is decoded once and threaded through to the query. Using a plain tuple or dict would lose meaning and invite bugs.

### Why `tuple_()` instead of manual OR-based WHERE clause

SQLAlchemy's `tuple_()` generates a native PostgreSQL row-value comparison `(a, b) < (c, d)`, which is semantically correct, optimizable by the query planner, and less error-prone than writing the equivalent `(a < c) OR (a = c AND b < d)` manually.

---

## Extending This Feature

**Changing the default page size**: Modify the `default=20` value in the `limit` query parameter definition in `backend/app/routes/chat.py`. The `ge=1, le=100` constraints are also set there. No service-layer changes needed.

**Adding cursor expiry**: To reject cursors older than N hours, add a check in `_decode_cursor()` that compares `cursor.ts` against `datetime.now(UTC)` and raises HTTP 400 if the cursor is too old. This would force clients to re-fetch from the beginning if they have been idle too long.

**Migrating to a three-column index**: If performance profiling shows the `id` tiebreaker is slow on large conversations, create: `CREATE INDEX idx_messages_conv_time_id ON messages (conversation_id, created_at DESC, id DESC)`. The existing index can then be dropped. No application code changes are needed.

**Adding a `direction` parameter**: To support forward pagination (loading newer messages), add a `direction` query parameter (`before` or `after`). In the `after` case, reverse the comparison to `(created_at, id) > (cursor.ts, cursor.id)` and change the ORDER BY to `ASC`. This would enable real-time message polling.

---

## Related Documentation

- [Chat Streaming](./chat-streaming.md) -- the parent feature (P01-06) that created this endpoint
- [Database Schema](./database-schema.md) -- the `messages`, `conversations`, and `characters` tables
- [Cognito Auth Middleware](./cognito-auth-middleware.md) -- JWT verification used by this endpoint
- [Database Schema and API Endpoints](../04-veri-api.md) -- authoritative source for table definitions
- [Pagination Standard](../standards/common.md) -- Section 6 specifies the cursor encoding convention
