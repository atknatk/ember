# Backend Dev Handoff: Messages Pagination

**Date**: 2026-02-24
**Agent**: backend-dev
**Status**: COMPLETE

## Implemented Files

- `backend/app/routes/chat.py` -- Updated cursor parsing: replaced `datetime.fromisoformat()` with `_decode_cursor()` (base64 composite cursor). Invalid cursors now return HTTP 400 with `{"detail": "Invalid cursor format"}`.
- `backend/app/services/chat_service.py` -- Added `MessageCursor` frozen dataclass, `_encode_cursor()`, `_decode_cursor()` helpers. Modified `get_messages()` to accept `MessageCursor | None` and use `sqlalchemy.tuple_()` for row-value comparison `(created_at, id) < (cursor.ts, cursor.id)`. Updated `next_cursor` encoding from plain ISO timestamp to base64 URL-safe JSON.
- `backend/tests/test_chat_routes.py` -- Updated 3 existing tests to use base64 cursors. Added 10 new tests for invalid cursor variants (not base64, bad JSON, missing fields, bad types, empty string, old format) and valid cursor acceptance.
- `backend/tests/test_chat_service.py` -- Updated 2 existing tests (`test_cursor_filter_applied`, `test_next_cursor_matches_last_item`) to use `MessageCursor`. Added 14 new tests: cursor helper unit tests (U1-U7), same-timestamp tiebreaker tests (S1-S3), cursor roundtrip test (S4), garbage input test (S5).

## Endpoints Modified

- `GET /api/v1/characters/{character_id}/messages` -- Cursor format changed from plain ISO 8601 timestamp to base64 URL-safe JSON `{"ts": "<ISO 8601>", "id": "<UUID>"}`. Invalid cursor now returns HTTP 400 instead of 500.

## Test Results

- pytest: 913 passed, 0 failed (120 in chat test files)
- ruff: clean on production code (`backend/app/`)
- No regressions in any other test file

## Test Command

```bash
cd backend && python -m pytest tests/test_chat_routes.py tests/test_chat_service.py -v
```

## Known Issues / Deviations from Spec

- None. Implementation follows the spec exactly.
- The 3 pre-existing ruff F841 warnings in test files (unused variables at lines 1132, 1829, 1929 of `test_chat_service.py`) are from P01-06 code and were not introduced by this change.

## Notes for Backend Tester

### Cursor Encoding Details

- Cursor is base64 URL-safe encoded JSON: `{"ts": "2026-02-23T14:30:00+00:00", "id": "550e8400-..."}`
- Padding (`=`) is stripped on encode, restored on decode using `cursor + "=" * (-len(cursor) % 4)`
- `_encode_cursor(ts, msg_id)` and `_decode_cursor(cursor_str)` are importable from `app.services.chat_service`

### Mock Requirements

- Route tests mock `app.services.chat_service.ChatService.get_messages` (returns `MessageListResponse`)
- Service tests mock `db.execute` with call_count pattern (1=character, 2=conversation, 3=messages)
- Import `_encode_cursor` from `app.services.chat_service` to build valid test cursors
- Import `MessageCursor` for service-level tests that pass cursor objects

### Edge Cases to Pay Attention To

- **Same-timestamp tiebreaker**: Two messages with identical `created_at` but different UUIDs must be paginated correctly. The `tuple_()` comparison ensures deterministic ordering by `(created_at DESC, id DESC)`.
- **Empty cursor string**: `?cursor=` (empty string) must return 400, not 200.
- **Old-format cursor**: Plain ISO 8601 timestamp like `2026-02-23T14:30:00+00:00` must return 400 (not backward compatible -- no client has shipped).
- **Various malformed base64**: Each type of malformation (not base64, valid base64 but not JSON, valid JSON but missing fields, valid JSON but wrong types) all produce the same 400 error with `"Invalid cursor format"`.

### What Changed vs P01-06

| Aspect | P01-06 (before) | P01-07 (after) |
|--------|-----------------|----------------|
| Cursor format | Plain ISO 8601 timestamp string | Base64 URL-safe JSON `{"ts": ..., "id": ...}` |
| Cursor type in service | `datetime \| None` | `MessageCursor \| None` |
| WHERE clause | `created_at < cursor` | `tuple_(created_at, id) < tuple_(ts, id)` |
| next_cursor encoding | `items[-1].created_at.isoformat()` | `_encode_cursor(items[-1].created_at, items[-1].id)` |
| Invalid cursor handling | Unhandled `ValueError` -> 500 | `HTTPException(400, "Invalid cursor format")` |
