# Architect Handoff: Chat Streaming

**Date**: 2026-02-23
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

Two backend API endpoints for the core chat functionality: `POST /api/v1/characters/:id/messages` (SSE streaming endpoint that receives a user message, gathers Mem0 memories + recent conversation history in parallel, streams Claude Sonnet's response as SSE chunk events, extracts device action intents via Claude Haiku, and persists everything as background tasks) and `GET /api/v1/characters/:id/messages` (cursor-based paginated message history retrieval).

## Key Decisions

- **SSE over WebSocket**: Chat is request-response, not bidirectional. SSE is simpler, works over standard HTTP, and is well-supported by FastAPI's `StreamingResponse`. WebSocket is reserved for real-time voice (Phase 5+).
- **Background task persistence**: User and assistant messages are persisted AFTER the stream completes, not inline. This minimizes time-to-first-token (target: <1s per `docs/08-guvenlik-performans.md`). Trade-off: messages could be lost if the background task fails. Acceptable for Phase 1.
- **Separate Haiku intent extraction**: Device action intents (SET_ALARM, ADD_CALENDAR_EVENT) are detected by a post-stream Haiku call, not by instructing Sonnet to embed structured JSON in the response. Keeps conversation natural, cheaper, and independently evolvable.
- **50 messages of context**: Configurable via `settings.max_context_messages`. CLAUDE.md says 30-50; `docs/05-ai-bellek.md` mentions 20. Using 50 for better quality in Phase 1, tunable later.
- **3 parallel fetches**: Global Mem0 search + character Mem0 search + DB last 50 messages all run via `asyncio.gather()`, following the architecture in `docs/05-ai-bellek.md`.
- **Background tasks use separate DB session**: The request-scoped session closes when the StreamingResponse finishes. Background tasks create their own session via `AsyncSessionLocal()`.
- **Mem0 SDK wrapped in asyncio.to_thread()**: The `mem0ai` package is synchronous. All calls are wrapped to avoid blocking the event loop.
- **New config field**: `max_context_messages: int = 50` added to Settings.
- **Auto-create conversation if missing**: Defensive handling for edge case where conversation row is absent despite P01-05 creating it.

## Spec Location

`shared/feature-specs/chat-streaming.md`

## Assumptions Made

- The `anthropic` package supports `client.messages.stream()` as an async context manager with `.text_stream` and `.get_final_message()`.
- The `mem0ai` package provides `MemoryClient` with synchronous `.search()` and `.add()` methods. The `.search()` accepts `user_id`, `agent_id`, and `limit` parameters.
- The existing `idx_messages_conv_time` index on `(conversation_id, created_at DESC)` from P01-02 is sufficient for the message history query and cursor pagination.
- The `user_activity` table has a row for every registered user (created during registration in P01-04). If not, the UPDATE query will silently affect 0 rows.
- Subscription tier enforcement (message limits per day) is deferred to Phase 2.

## Dependencies

- Requires: P01-01 (project-setup), P01-02 (database-schema), P01-03 (cognito-auth-middleware), P01-04 (auth-endpoints), P01-05 (character-crud)
- Blocks: backend-dev (implements the endpoints), backend-tester (writes tests)

## File Manifest

```
Backend:
  CREATE  backend/app/routes/chat.py
  CREATE  backend/app/services/chat_service.py
  CREATE  backend/app/schemas/chat.py
  MODIFY  backend/app/main.py
  MODIFY  backend/app/config.py
  CREATE  backend/tests/test_chat_routes.py
  CREATE  backend/tests/test_chat_service.py
  CREATE  backend/tests/test_chat_schemas.py

Shared:
  CREATE  shared/feature-specs/chat-streaming.md
  CREATE  docs/pipeline/chat-streaming-architect.handoff.md
```

## Notes for Developers

- **Router prefix**: Register the chat router with `prefix="/api/v1/characters"` and route decorators use `"/{character_id}/messages"`. This does NOT conflict with the existing characters router.
- **SSE format**: `data: {json}\n\n` (two newlines, no `event:` header). Use the `type` field in JSON instead.
- **Claude streaming**: Use `client.messages.stream()`, not `client.messages.create(stream=True)`.
- **Mem0 is synchronous**: Wrap all `MemoryClient` calls in `asyncio.to_thread()`.
- **Background task session**: Create new `AsyncSessionLocal()` inside background tasks, do NOT reuse the request session.
- **Reverse message order**: DB query returns DESC; reverse to chronological before passing to Claude.
- **Error mid-stream**: Emit `{"type":"error"}` SSE event; HTTP status stays 200 (SSE protocol constraint).

## Next Steps

backend-dev should read the spec at `shared/feature-specs/chat-streaming.md` and implement the endpoints. backend-tester follows with test coverage.
