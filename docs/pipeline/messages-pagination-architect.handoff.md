# Architect Handoff: Messages Pagination

**Date**: 2026-02-24
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

Hardening of the cursor-based message pagination endpoint (`GET /api/v1/characters/:id/messages`), which was initially implemented in P01-06. The main change is upgrading the cursor format from a plain ISO 8601 timestamp to a composite `(created_at, id)` cursor encoded as base64 URL-safe JSON. This fixes a correctness bug where two messages with identical timestamps could be skipped or duplicated during pagination. Additionally, invalid cursor input now returns HTTP 400 instead of an unhandled 500 error.

## Key Decisions

- **Composite cursor `(created_at, id)` over plain timestamp**: Two messages can share the same `created_at` (e.g., user and assistant messages persisted in one transaction). The plain timestamp cursor cannot distinguish between them. The composite cursor with UUID tiebreaker eliminates this bug. This also aligns with `docs/standards/common.md` Section 6.
- **Base64 URL-safe encoding**: Makes the cursor opaque to clients, prevents manual cursor construction, and avoids URL encoding issues. Follows `docs/standards/common.md` Section 6.
- **No backward compatibility for old cursors**: No mobile client has shipped. Old-format cursors (plain ISO timestamps) will return HTTP 400. Clean break avoids dead code.
- **No index changes**: The existing `idx_messages_conv_time` on `(conversation_id, created_at DESC)` is sufficient. The `id` tiebreaker operates on the small result set (max `limit + 1` rows) after the index scan.
- **Default limit stays at 20**: Matches the issue description. `docs/standards/common.md` says 30, but the issue says 20 and no client has shipped. Backend-dev may adjust if directed.
- **SQLAlchemy `tuple_()` for row-value comparison**: Generates correct `(a, b) < (c, d)` SQL. Cleaner and less error-prone than manual OR-based WHERE clause.
- **Single HTTPException(400) for all cursor parse failures**: Do not expose internal error details (bad base64 vs bad JSON) to the client. One message: "Invalid cursor format".

## Spec Location

`shared/feature-specs/messages-pagination.md`

## Assumptions Made

- PostgreSQL supports row-value comparison `(a, b) < (c, d)` natively (confirmed: this is standard SQL).
- SQLAlchemy's `tuple_()` function generates correct PostgreSQL SQL for row-value comparisons.
- No mobile client has persisted old-format cursors. There is no backward compatibility requirement.
- The existing `idx_messages_conv_time` index on `(conversation_id, created_at DESC)` provides adequate performance for the upgraded query. A three-column index `(conversation_id, created_at DESC, id DESC)` can be added later if profiling warrants it.

## Dependencies

- Requires: P01-06 (chat-streaming -- the existing endpoint, service, schema, and tests)
- Blocks: backend-dev, backend-tester (they implement and test the changes)

## File Manifest

```
Backend:
  MODIFY  backend/app/routes/chat.py           -- Cursor decoding, 400 error handling
  MODIFY  backend/app/services/chat_service.py  -- MessageCursor dataclass, tuple_ query, base64 encode/decode helpers
  MODIFY  backend/tests/test_chat_routes.py     -- Update existing cursor tests, add invalid cursor tests
  MODIFY  backend/tests/test_chat_service.py    -- Update existing cursor tests, add composite cursor tests, add cursor helper tests

Shared:
  CREATE  shared/feature-specs/messages-pagination.md
  CREATE  docs/pipeline/messages-pagination-architect.handoff.md
```

## Notes for Developers

### For backend-dev

- The scope is small: modify 2 production files, update 2 test files. No new files needed beyond the spec and handoff.
- Start with `MessageCursor` dataclass + `_encode_cursor()` + `_decode_cursor()` helpers in `chat_service.py`. Test them before modifying the route/service logic.
- Use `from sqlalchemy import tuple_` for the row-value comparison. This is the clean SQLAlchemy way to express `(created_at, id) < ($ts, $id)`.
- Handle base64 padding: strip `=` on encode, restore on decode (add `=` until `len % 4 == 0`).
- The route handler should catch cursor decode errors and return HTTP 400 with `{"detail": "Invalid cursor format"}`.
- Search for `cursor=` and `fromisoformat` in existing test files to find all tests that need updating.

### For backend-tester

- Focus on: (1) invalid cursor format tests (R1-R9 in spec), (2) same-timestamp tiebreaker test (S1), (3) cursor roundtrip test (S4, U1-U7), (4) no regressions in POST endpoint tests.
- The tiebreaker scenario is the most important correctness test. Create two messages with identical `created_at`, paginate with `limit=1`, verify no duplicates and no skips.

## Next Steps

backend-dev should read the spec at `shared/feature-specs/messages-pagination.md` and implement the cursor format upgrade and error handling. backend-tester follows with test coverage.
