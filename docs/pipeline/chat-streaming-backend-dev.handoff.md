# Backend Dev Handoff: Chat Streaming (P01-06)

**Date**: 2026-02-23
**Agent**: backend-dev
**Status**: COMPLETE

## Implemented Files

- `backend/app/routes/chat.py` -- 2 endpoints (POST streaming, GET paginated)
- `backend/app/services/chat_service.py` -- ChatService class (9 methods) + 2 module-level functions
- `backend/app/schemas/chat.py` -- 8 schemas (1 request, 3 response, 4 SSE events)
- `backend/app/main.py` -- Modified: added chat router registration
- `backend/app/config.py` -- Modified: added `max_context_messages: int = 50`

## Endpoints Implemented

- `POST /api/v1/characters/{character_id}/messages` -- Send message, returns SSE stream
- `GET /api/v1/characters/{character_id}/messages` -- Cursor-based paginated message history

## SSE Event Format

All SSE events follow the spec format:

```
data: {"type": "chunk", "content": "partial text here"}
data: {"type": "action", "action": "SET_ALARM", "payload": {"time": "07:00"}}
data: {"type": "done", "message_id": "uuid-here"}
data: {"type": "error", "message": "AI service temporarily unavailable"}
```

## Architecture Decisions

1. **Validation-before-streaming pattern**: `validate_send_message()` runs BEFORE the
   `StreamingResponse` is created, so HTTPExceptions (403, 404) produce proper JSON
   error responses. The `stream_response()` async generator only runs inside the
   StreamingResponse after validation succeeds.

2. **Background persistence**: Messages are persisted via `asyncio.create_task()` calling
   the module-level `_persist_exchange()` function. This function creates its own DB
   session via `AsyncSessionLocal()` because the request-scoped session closes when the
   StreamingResponse finishes.

3. **Mem0 resilience**: `asyncio.gather(..., return_exceptions=True)` is used for parallel
   Mem0 + DB operations. Mem0 failures are caught and logged; the chat continues with
   empty memories rather than failing.

4. **Intent extraction**: Claude Haiku extracts device action intents (SET_ALARM,
   ADD_CALENDAR_EVENT) from the assistant response. Failures are silently handled.

## Test Results

- pytest: 64 passed (19 schema, 20 route, 25 service), 0 failed
- ruff: clean (all new/modified files)
- Full suite: 824 passed, 13 skipped, 0 failed

## Test Files

- `backend/tests/test_chat_schemas.py` -- 19 tests: request validation, response serialization, SSE events
- `backend/tests/test_chat_routes.py` -- 20 tests: 11 POST streaming, 9 GET pagination
- `backend/tests/test_chat_service.py` -- 25 tests: validation, streaming, system prompt, pagination, intent, persist, dedup

## Known Issues / Deviations from Spec

- None. Implementation follows the architect spec exactly.

## Notes for Backend Tester

- Mock `app.services.chat_service.MemoryClient` for all Mem0 tests
- Mock `app.services.chat_service.AsyncAnthropic` for Claude API tests
- SSE streaming tests: mock `validate_send_message` (returns context dict) and
  `stream_response` (returns async generator) separately
- Route tests use `httpx.AsyncClient` -- SSE response body is consumed as text
- The `_persist_exchange` function uses `AsyncSessionLocal` directly (not the
  request-scoped `db` session) -- mock `app.services.chat_service.AsyncSessionLocal`
- `_extract_intent` has multiple code paths (valid JSON, "none", invalid JSON,
  exception) -- ensure coverage of all branches
- `_build_system_prompt` conditionally includes memory block -- test with and without
  memories
- `_deduplicate_memories` prioritizes character memories over global -- verify order
