# Feature Spec: P01-07 -- Messages Pagination

**Feature ID**: P01-07
**Phase**: 1
**Layer**: backend
**GitHub Issue**: #9
**Date**: 2026-02-24
**Author**: architect

---

## 1. Overview

### What This Feature Does

P01-07 hardens and completes the cursor-based message pagination endpoint (`GET /api/v1/characters/:id/messages`) that was initially implemented as part of P01-06 (chat-streaming). While P01-06 delivered a working endpoint, it used a simplified cursor mechanism (plain ISO 8601 timestamp) that does not comply with the project's pagination standard in `docs/standards/common.md` Section 6 and has correctness issues when multiple messages share the same `created_at` value.

This feature delivers three categories of work:

1. **Cursor encoding upgrade**: Replace the plain ISO 8601 cursor with a composite `(created_at, id)` cursor encoded as base64 URL-safe JSON. This eliminates the possibility of skipping or duplicating messages when two messages share the same timestamp (common during background persistence, which inserts the user and assistant messages in a single transaction with the same server clock time).

2. **Error handling hardening**: Add graceful handling for invalid cursor values (malformed strings, invalid base64, invalid JSON) so the endpoint returns HTTP 400 with a clear error message instead of an unhandled 500 error.

3. **Comprehensive test coverage**: Add targeted tests for the pagination edge cases that P01-06 tests did not cover: identical-timestamp messages, multi-page sequential pagination, invalid cursor format, and cursor boundary conditions.

### Why It Exists

The current plain-timestamp cursor is incorrect in a specific but realistic scenario. When a user sends a message and receives a response, the `_persist_exchange` background task inserts both the user message and the assistant message in a single DB transaction. PostgreSQL's `now()` server default assigns both messages the same `created_at` timestamp. If the client paginates and the cursor equals this shared timestamp, the `created_at < $cursor` filter may skip one of the two messages or include it twice on different pages, depending on insertion order.

The composite `(created_at, id)` cursor with a `(created_at, id)` ordering in the query eliminates this ambiguity. The `id` (UUID) breaks the tie deterministically.

### Dependencies

- **Requires**: P01-06 (chat-streaming -- provides the existing endpoint, service, schema, and tests)
- **Blocks**: Mobile chat UI scroll-back functionality (must have correct pagination before mobile implements infinite scroll)

### What Already Exists from P01-06

All of the following files were created in P01-06 and will be MODIFIED (not created) in this feature:

| File | What Exists | What Changes |
|------|-------------|--------------|
| `backend/app/routes/chat.py` | `get_messages()` route with `cursor: str`, parses via `datetime.fromisoformat()` | Cursor parsing switches to base64 decode + JSON parse. Error handling for invalid cursor. |
| `backend/app/services/chat_service.py` | `ChatService.get_messages()` with `cursor: datetime`, query uses `created_at < cursor` | Cursor type changes to a `MessageCursor` dataclass. Query adds `id` as tiebreaker. `next_cursor` encoding changes to base64 JSON. |
| `backend/app/schemas/chat.py` | `MessageListResponse` with `next_cursor: str` | No schema changes. The `next_cursor` field type stays `str | None`. Only its content format changes (from ISO timestamp to base64 JSON). |
| `backend/tests/test_chat_routes.py` | `TestGetMessages` + `TestGetMessagesAdditional` classes | Add new tests for invalid cursor, base64 cursor format, same-timestamp messages. |
| `backend/tests/test_chat_service.py` | `TestGetMessages` + `TestGetMessagesAdditional` classes | Add new tests for composite cursor query, tiebreaker ordering, cursor encoding/decoding. |

---

## 2. Data Models

### No New Tables

This feature does not create or alter any database tables.

### No New Columns

All required columns already exist on the `messages` table (see `docs/04-veri-api.md`).

### Index Consideration

The existing composite index `idx_messages_conv_time` on `(conversation_id, created_at DESC)` supports the current query. The upgraded query adds `id DESC` as a secondary sort column. PostgreSQL can use the existing index for the `conversation_id` and `created_at` filter; the `id` tiebreaker operates on the small result set after the index scan (max `limit + 1` rows), so no additional index is needed for Phase 1.

If performance profiling later shows that the `id` tiebreaker causes issues on very large conversations, a new index `(conversation_id, created_at DESC, id DESC)` can be added. This is NOT required now.

### Mem0 Operations

None. This feature does not interact with Mem0.

---

## 3. API Changes

### Modified Endpoint: GET /api/v1/characters/:id/messages

The endpoint path, auth requirement, and response schema are unchanged. Only the cursor format and error handling change.

```
Method: GET
Path: /api/v1/characters/{character_id}/messages
Auth: Bearer JWT required
```

**Query Parameters (unchanged path, new cursor semantics):**

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `cursor` | string | no | none | Base64 URL-safe encoded JSON object `{"ts": "<ISO 8601>", "id": "<UUID>"}`. Messages strictly older than this cursor are returned. When absent, the newest messages are returned. |
| `limit` | integer | no | 20 | Number of messages to return per page. Min 1, max 100. |

**Cursor Format:**

The cursor is a base64url-encoded JSON string containing two fields:

```json
{"ts": "2026-02-23T14:30:00+00:00", "id": "550e8400-e29b-41d4-a716-446655440088"}
```

Encoded example: `eyJ0cyI6ICIyMDI2LTAyLTIzVDE0OjMwOjAwKzAwOjAwIiwgImlkIjogIjU1MGU4NDAwLWUyOWItNDFkNC1hNzE2LTQ0NjY1NTQ0MDA4OCJ9`

The `ts` field is the `created_at` ISO 8601 timestamp of the last message on the previous page. The `id` field is the UUID of that same message. Together they define a unique position in the ordered message list.

**Backward Compatibility Note:**

The cursor format is opaque to the client. Clients receive `next_cursor` from one response and pass it as `cursor` on the next request. Since no mobile clients have shipped yet (Phase 1 backend-only), there is no backward compatibility concern. Old-format cursors (plain ISO timestamps) from P01-06 will not be supported -- they will return HTTP 400. This is acceptable because no client has persisted old cursors.

**Response 200 OK (unchanged schema):**

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

Note in the example above: both messages share the same `created_at` value (`14:30:05`). The composite cursor ensures the next page starts after the correct message.

**New Error Response:**

| Status | Condition | Body |
|--------|-----------|------|
| 400 | Invalid cursor format (not valid base64, not valid JSON, missing `ts` or `id` fields, `ts` not a valid ISO 8601 timestamp, `id` not a valid UUID) | `{"detail": "Invalid cursor format"}` |

Previously, a malformed cursor would produce an unhandled `ValueError` exception, causing an HTTP 500.

**Unchanged Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 401 | Missing or invalid JWT | `{"detail": "Invalid or expired token"}` |
| 403 | Character does not belong to user | `{"detail": "Character does not belong to user"}` |
| 404 | Character not found or inactive | `{"detail": "Character not found"}` |
| 404 | Character has no conversation | `{"detail": "Conversation not found"}` |
| 422 | Invalid limit (< 1 or > 100) or invalid UUID path param | Standard FastAPI 422 |

**SQL Pattern for Composite Cursor Pagination:**

```sql
-- First page (no cursor):
SELECT id, role, content, media_url, metadata, created_at
FROM messages
WHERE conversation_id = $conversation_id
ORDER BY created_at DESC, id DESC
LIMIT $limit + 1;

-- Subsequent pages (with cursor):
SELECT id, role, content, media_url, metadata, created_at
FROM messages
WHERE conversation_id = $conversation_id
  AND (created_at, id) < ($cursor_ts, $cursor_id)
ORDER BY created_at DESC, id DESC
LIMIT $limit + 1;
```

The `(created_at, id) < ($cursor_ts, $cursor_id)` is a row-value comparison. PostgreSQL evaluates this as: `created_at < $cursor_ts OR (created_at = $cursor_ts AND id < $cursor_id)`. This correctly handles the tiebreaker when two messages have the same timestamp.

In SQLAlchemy, this is expressed using `sqlalchemy.tuple_()`:

```python
from sqlalchemy import tuple_

stmt = stmt.where(
    tuple_(Message.created_at, Message.id) < tuple_(cursor.ts, cursor.id)
)
```

---

## 4. Backend Logic

### Cursor Encoding and Decoding

A new helper module or set of utility functions handles cursor encoding and decoding. These can live in the chat service file or as a small utility.

**Encoding (when building `next_cursor` in the response):**

```
1. Take the last message item's (created_at, id).
2. Build a JSON string: {"ts": "<ISO 8601>", "id": "<UUID>"}
3. Encode with base64.urlsafe_b64encode().
4. Decode bytes to string (strip padding if desired, but standard base64 with padding is fine).
```

**Decoding (when parsing the `cursor` query parameter):**

```
1. base64.urlsafe_b64decode() the cursor string.
2. json.loads() the result.
3. Extract "ts" -> datetime.fromisoformat()
4. Extract "id" -> uuid.UUID()
5. If any step fails, raise HTTPException(400, "Invalid cursor format").
```

The decoded cursor is represented as a dataclass or named tuple:

```
@dataclass(frozen=True)
class MessageCursor:
    ts: datetime
    id: uuid.UUID
```

### Modified Service Method: `ChatService.get_messages()`

**Signature change:**

```
Before:  cursor: datetime | None
After:   cursor: MessageCursor | None
```

The route handler decodes the cursor string into a `MessageCursor` before calling the service.

**Query change:**

```
Before:
  stmt = stmt.where(Message.created_at < cursor)
  .order_by(Message.created_at.desc(), Message.id.desc())

After:
  stmt = stmt.where(
      tuple_(Message.created_at, Message.id) < tuple_(cursor.ts, cursor.id)
  )
  .order_by(Message.created_at.desc(), Message.id.desc())
```

**next_cursor change:**

```
Before:
  next_cursor = items[-1].created_at.isoformat()

After:
  next_cursor = _encode_cursor(items[-1].created_at, items[-1].id)
```

Where `_encode_cursor(ts: datetime, id: uuid.UUID) -> str` produces the base64 JSON string.

### Modified Route Handler: `get_messages()`

**Before:**

```python
parsed_cursor: datetime | None = None
if cursor is not None:
    parsed_cursor = datetime.fromisoformat(cursor)
```

**After:**

```python
parsed_cursor: MessageCursor | None = None
if cursor is not None:
    parsed_cursor = _decode_cursor(cursor)
    # _decode_cursor raises HTTPException(400) on invalid format
```

### Error Handling

The `_decode_cursor()` function wraps all parsing in a try/except and raises a single `HTTPException(status_code=400, detail="Invalid cursor format")` for any failure mode: bad base64, bad JSON, missing fields, bad timestamp, bad UUID.

---

## 5. Test Requirements

### New Route Tests (add to `TestGetMessagesAdditional` in `test_chat_routes.py`)

| # | Scenario | Expected |
|---|----------|----------|
| R1 | Invalid cursor (not base64) returns 400 | HTTP 400, `{"detail": "Invalid cursor format"}` |
| R2 | Invalid cursor (valid base64, invalid JSON) returns 400 | HTTP 400, `{"detail": "Invalid cursor format"}` |
| R3 | Invalid cursor (valid JSON, missing `ts` field) returns 400 | HTTP 400, `{"detail": "Invalid cursor format"}` |
| R4 | Invalid cursor (valid JSON, missing `id` field) returns 400 | HTTP 400, `{"detail": "Invalid cursor format"}` |
| R5 | Invalid cursor (valid JSON, `ts` not ISO 8601) returns 400 | HTTP 400, `{"detail": "Invalid cursor format"}` |
| R6 | Invalid cursor (valid JSON, `id` not a UUID) returns 400 | HTTP 400, `{"detail": "Invalid cursor format"}` |
| R7 | Valid base64 cursor is accepted and passed to service | HTTP 200 |
| R8 | `next_cursor` in response is valid base64, decodes to JSON with `ts` and `id` | Decode and verify structure |
| R9 | Empty cursor string returns 400 | HTTP 400 |

### New Service Tests (add to `TestGetMessagesAdditional` in `test_chat_service.py`)

| # | Scenario | Expected |
|---|----------|----------|
| S1 | Two messages with same `created_at` but different `id` are correctly paginated | Second page returns the message with the smaller `id` |
| S2 | `next_cursor` encodes to valid base64 JSON with `ts` and `id` | Decode and verify |
| S3 | Service method accepts `MessageCursor` and applies tuple comparison | Query executes without error |
| S4 | `_encode_cursor()` roundtrips with `_decode_cursor()` | Decode(encode(ts, id)) == (ts, id) |
| S5 | `_decode_cursor()` raises HTTPException(400) for garbage input | Correct exception |

### New Unit Tests for Cursor Helpers (add to `test_chat_service.py` or a separate `test_cursor.py`)

| # | Scenario | Expected |
|---|----------|----------|
| U1 | `_encode_cursor()` returns a string | Type check |
| U2 | `_encode_cursor()` output is valid base64 | base64 decode succeeds |
| U3 | `_decode_cursor()` returns a `MessageCursor` | Type check |
| U4 | `_decode_cursor()` with valid input returns correct `ts` and `id` | Value equality |
| U5 | `_decode_cursor()` with empty string raises 400 | HTTPException |
| U6 | `_decode_cursor()` with plain ISO timestamp (old format) raises 400 | HTTPException |
| U7 | `_decode_cursor()` with valid base64 but `ts` missing raises 400 | HTTPException |

### Existing Tests That May Need Update

The following existing tests use plain ISO timestamp cursors and will break after the format change. They must be updated to use the new base64 cursor format:

- `TestGetMessages.test_get_messages_with_cursor` -- passes `?cursor=2026-02-23T14:30:00%2B00:00` as a plain ISO timestamp
- `TestGetMessagesAdditional.test_get_messages_next_cursor_format` -- asserts that `next_cursor` is a parseable ISO 8601 string (it will now be base64)
- `TestGetMessagesAdditional.test_cursor_filter_applied` (in service tests) -- passes a `datetime` as cursor (now needs `MessageCursor`)
- `TestGetMessagesAdditional.test_next_cursor_matches_last_item` (in service tests) -- asserts `next_cursor == messages[2].created_at.isoformat()` (now base64)

---

## 6. Acceptance Criteria

1. Given a valid `GET /api/v1/characters/:id/messages` request without a cursor, when the endpoint is called, then it returns the newest messages ordered by `(created_at DESC, id DESC)` with a base64-encoded `next_cursor` containing both `ts` and `id` fields.

2. Given a `next_cursor` value from a previous response, when it is passed as the `cursor` query parameter, then only messages strictly older than the cursor position are returned (no duplicates, no skips).

3. Given two messages with identical `created_at` timestamps but different UUIDs, when the client paginates with `limit=1` through them, then each message appears exactly once across the two pages.

4. Given an invalid cursor string that is not valid base64, when it is passed as the `cursor` parameter, then the endpoint returns HTTP 400 with `{"detail": "Invalid cursor format"}`.

5. Given a cursor string that is valid base64 but does not contain valid JSON, when it is passed as the `cursor` parameter, then the endpoint returns HTTP 400 with `{"detail": "Invalid cursor format"}`.

6. Given a cursor string that is valid base64 JSON but missing the `ts` field, when it is passed as the `cursor` parameter, then the endpoint returns HTTP 400 with `{"detail": "Invalid cursor format"}`.

7. Given a cursor string that is valid base64 JSON but the `id` field is not a valid UUID, when it is passed as the `cursor` parameter, then the endpoint returns HTTP 400 with `{"detail": "Invalid cursor format"}`.

8. Given the `next_cursor` field in any 200 response where `has_more` is true, when the cursor is base64-decoded and JSON-parsed, then it contains a `ts` field (valid ISO 8601 timestamp) and an `id` field (valid UUID string).

9. Given the `next_cursor` field in any 200 response where `has_more` is true, when the cursor's `ts` and `id` are compared to the last message in the `items` array, then they match exactly (the cursor points to the last returned message).

10. Given a conversation with zero messages, when the endpoint is called without a cursor, then the response is `{"items": [], "next_cursor": null, "has_more": false}`.

11. Given all existing test scenarios from P01-06 for the GET messages endpoint, when the tests are updated to use the new cursor format, then all tests pass with exit code 0.

12. Given the backend test suite, when `pytest` is run, then all new and updated tests pass and there are no regressions in other test files.

---

## 7. File Manifest

```
Backend:
  MODIFY  backend/app/routes/chat.py           -- Cursor decoding, 400 error handling
  MODIFY  backend/app/services/chat_service.py  -- MessageCursor dataclass, tuple_ query, base64 encode/decode helpers
  MODIFY  backend/tests/test_chat_routes.py     -- Update existing cursor tests, add invalid cursor tests
  MODIFY  backend/tests/test_chat_service.py    -- Update existing cursor tests, add composite cursor tests, add cursor helper tests

Shared:
  CREATE  shared/feature-specs/messages-pagination.md           (this file)
  CREATE  docs/pipeline/messages-pagination-architect.handoff.md
```

| Action | Count |
|--------|-------|
| CREATE | 2 |
| MODIFY | 4 |
| DELETE | 0 |
| **Total** | **6** |

### Files NOT Modified

- `backend/app/schemas/chat.py` -- The `MessageListResponse` schema is unchanged. The `next_cursor` field is already `str | None`, and its content format changing from plain ISO to base64 does not affect the Pydantic model.
- `backend/app/main.py` -- No router changes. The chat router is already registered.
- `backend/app/config.py` -- No new config values needed.
- `backend/app/models/message.py` -- No model changes. The existing `idx_messages_conv_time` index is sufficient.
- `backend/requirements.txt` -- No new dependencies. `base64` and `json` are Python stdlib.

---

## 8. Design Decisions and Rationale

### Why composite `(created_at, id)` cursor instead of plain timestamp

The plain timestamp cursor has a correctness bug. When `_persist_exchange` inserts both the user message and assistant message in one transaction, PostgreSQL's `server_default=func.now()` assigns both the same `created_at`. If the cursor equals this timestamp, `created_at < cursor` may skip one message or include it twice depending on the query's secondary sort. The composite cursor with row-value comparison eliminates this ambiguity.

This is also what `docs/standards/common.md` Section 6 prescribes: "Cursor encodes `(created_at, id)` as base64 URL-safe JSON."

### Why base64 URL-safe encoding

Base64 encoding makes the cursor opaque to clients. They cannot construct cursors manually or depend on the internal format. URL-safe base64 avoids issues with URL encoding of `+` and `/` characters. This follows the pattern specified in `docs/standards/common.md` Section 6.

### Why not support old-format cursors (backward compatibility)

No mobile client has shipped yet. The only consumer of the old cursor format is the test suite, which we are updating. Adding backward-compatibility logic for a format that was live for zero days adds complexity with no benefit. A clean break is appropriate here.

### Why not change the default limit from 20 to 30

`docs/standards/common.md` Section 6 says "Default limit: 30." The issue description says "returns 20 messages." The current implementation uses 20. For consistency with the issue description and to avoid a behavioral change that could affect mobile client expectations (even though no client is shipped), this spec keeps the default at 20. If alignment with the common standard is preferred, the backend-dev can adjust to 30 -- the spec does not prescribe one value over the other. The important thing is that the default is documented and the mobile team knows it.

### Why MessageCursor as a frozen dataclass

A frozen dataclass provides type safety and immutability. The cursor is decoded once and passed through to the query. Using a plain tuple or dict would lose the semantic meaning and invite bugs.

### Why tuple_ comparison instead of OR-based WHERE clause

SQLAlchemy's `tuple_()` generates a PostgreSQL row-value comparison `(a, b) < (c, d)`, which is semantically correct and optimizable by the query planner. Writing the equivalent `(a < c) OR (a = c AND b < d)` manually is more error-prone and harder to read. PostgreSQL natively supports row-value comparisons and can use the composite index efficiently.

---

## 9. Notes for Developers

### For backend-dev

- **Start with the cursor helpers** (`_encode_cursor`, `_decode_cursor`, `MessageCursor` dataclass). Test them in isolation before modifying the service and route.

- **SQLAlchemy `tuple_` import**: Use `from sqlalchemy import tuple_` for the row-value comparison. This generates correct PostgreSQL SQL.

- **Error handling in `_decode_cursor`**: Wrap the entire decode chain in a single try/except that catches `Exception` and raises `HTTPException(status_code=400, detail="Invalid cursor format")`. Do not expose internal error messages (no "invalid base64" vs "invalid JSON" distinction to the client).

- **base64 padding**: `base64.urlsafe_b64encode()` may produce trailing `=` padding characters. These are valid in URLs but some clients may strip them. To be safe, strip padding on encode and add it back on decode. The standard formula: add `=` characters until `len(s) % 4 == 0`.

- **Test update scope**: Update the existing tests that pass plain ISO cursors. Search for `cursor=` in both test files to find them. The cursor tests in the service file pass `datetime` objects directly -- those change to `MessageCursor` objects.

- **Keep the route handler thin**: The route should decode the cursor and pass a `MessageCursor` to the service. All cursor encoding (for `next_cursor`) happens in the service. The route does not need to know the cursor internals beyond decoding.

### For backend-tester

- **Test the roundtrip**: Encode a cursor, decode it, verify the values match. This catches encoding bugs.

- **Test the tiebreaker scenario**: Create two mock messages with the exact same `created_at` but different UUIDs. Paginate with `limit=1`. First page should return the message with the larger `(created_at, id)` tuple. Second page (using first page's `next_cursor`) should return the other message.

- **Test invalid cursors exhaustively**: Each malformed cursor variant (bad base64, bad JSON, missing fields, wrong types) should produce HTTP 400 with the exact error message.

- **Verify no regressions**: After updating existing tests, run the full `test_chat_routes.py` and `test_chat_service.py` suites. All POST-endpoint tests should be completely unaffected.
