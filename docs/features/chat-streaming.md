# Chat Streaming

> Sends a user message to an AI character and streams the response in real time via Server-Sent Events, integrating Mem0 long-term memory and device action intent detection.

**Status**: Released
**Added in**: Phase 1 (P01-06)
**Platforms**: Backend
**GitHub Issue**: #8

---

## Overview

Chat streaming is the core interaction endpoint of Ember. It powers every conversation between a user and their AI characters. When a user sends a message, the backend gathers context from two sources in parallel -- recent conversation history from PostgreSQL and long-term memories from Mem0 -- then streams the AI response token-by-token via Server-Sent Events (SSE). This gives the user a responsive experience where text appears incrementally rather than after a multi-second wait.

Beyond basic chat, the endpoint performs post-stream intent extraction using Claude Haiku. If the assistant's response contains a device action intent (such as setting an alarm or adding a calendar event), the backend emits an `action` SSE event that the mobile client can act on. This is the foundation for Ember's device integration capabilities.

A second endpoint provides cursor-based paginated retrieval of message history, enabling infinite-scroll message loading on mobile clients. Messages are persisted asynchronously as background tasks after the stream completes, keeping time-to-first-token low.

---

## Architecture

### How It Works (Data Flow)

**Streaming a message (POST):**

1. The mobile client sends `POST /api/v1/characters/{character_id}/messages` with the user's message text and a Bearer JWT.
2. The route handler extracts `user_id` from the JWT via the `get_current_user` dependency.
3. `ChatService.validate_send_message()` runs **before** the `StreamingResponse` is created, so any validation failures (403, 404) return proper JSON error responses.
4. The character is looked up by ID (must be active); ownership is verified against the JWT user.
5. The character's conversation is looked up (or auto-created defensively if missing).
6. Three parallel fetches run via `asyncio.gather(return_exceptions=True)`:
   - Mem0 global memory search (up to 5 results, no `agent_id` filter)
   - Mem0 character-specific memory search (up to 5 results, filtered by `agent_id`)
   - Last 50 messages from PostgreSQL (configurable via `settings.max_context_messages`)
7. The system prompt is constructed from three blocks: character definition, Mem0 memories, and daily context (date/time/timezone/language).
8. Message history is formatted in chronological order with the new user message appended last.
9. A `StreamingResponse` is returned with `Content-Type: text/event-stream`.
10. Claude Sonnet streams the response; each text chunk is yielded as an SSE `chunk` event.
11. After the full response is assembled, Claude Haiku analyzes it for device action intents.
12. If an intent is detected, an SSE `action` event is emitted before the final `done` event.
13. The `done` event includes the UUID of the persisted assistant message.
14. A background task fires via `asyncio.create_task()` to persist both messages, update timestamps, and add the exchange to Mem0.

**Retrieving message history (GET):**

1. The client sends `GET /api/v1/characters/{character_id}/messages` with optional `cursor` and `limit` query parameters.
2. Character ownership is verified.
3. The conversation is looked up; if not found, a 404 is returned.
4. Messages are queried with cursor-based pagination (`WHERE created_at < $cursor ORDER BY created_at DESC LIMIT $limit + 1`).
5. The extra row determines `has_more`. The response includes `items`, `next_cursor`, and `has_more`.

### Mem0 Memory Integration

- **Global memories**: Searched without an `agent_id`, returning memories visible across all characters for the user.
- **Character-specific memories**: Searched with `agent_id = character.mem0_agent_id`, returning memories isolated to this character.
- **Search query**: The user's message text is used as the search query.
- **Memory limit**: Up to 5 global + 5 character-specific = 10 total memories. De-duplicated by exact string match, with character-specific memories taking priority.
- **Memory storage**: After the stream completes, the user-assistant message pair is added to Mem0 via `mem0_client.add()` as a background task.
- **Failure resilience**: Mem0 search failures are caught and logged; the stream continues with empty memories. Mem0 add failures are caught and logged; message persistence is unaffected.

### System Prompt Construction

The system message sent to Claude is built from three blocks, following the architecture in `docs/05-ai-bellek.md`:

| Block | Source | Content |
|-------|--------|---------|
| 1 -- Character Definition | `characters.system_prompt` | The stored system prompt generated during character creation (P01-05) |
| 2 -- Learned Knowledge | Mem0 search results | `"What you know about this user:\n- {memory_1}\n- {memory_2}\n..."` (omitted if no memories) |
| 3 -- Daily Context | Profile + server time | Current date/time in user's timezone, timezone name, preferred language |

### Intent Extraction via Claude Haiku

After the full Sonnet response is assembled, a separate non-streaming call to Claude Haiku determines whether the response contains a device action intent. Supported actions:

| Action | Payload Fields | Description |
|--------|---------------|-------------|
| `SET_ALARM` | `time` (ISO 8601), `label` (string) | The assistant is setting an alarm or reminder |
| `ADD_CALENDAR_EVENT` | `title`, `date` (YYYY-MM-DD), `time` (ISO 8601), `duration_minutes` (integer) | The assistant is adding a calendar event |

If Haiku returns valid JSON with a supported action, the `action` SSE event is emitted. If Haiku returns `"none"`, returns invalid JSON, or fails entirely, the action event is skipped silently.

### Background Task Persistence

Background tasks run via `asyncio.create_task()` after the SSE stream completes. They use a **separate database session** (via `AsyncSessionLocal()`) because the request-scoped session is closed when the `StreamingResponse` finishes.

The background task performs these operations:

1. Insert the user message (`role="user"`, with `media_url` if provided)
2. Insert the assistant message (`role="assistant"`, with `metadata_` containing action data if detected)
3. Update `conversations.last_message_at`
4. Update `user_activity.last_chat_at`
5. Commit the database transaction
6. Call `mem0_client.add()` with the user-assistant message pair (outside the DB transaction)

Database and Mem0 failures are logged but do not crash the application.

### Database Tables Involved

| Table | Operation | Notes |
|-------|-----------|-------|
| `characters` | SELECT | Look up character, read `system_prompt` and `mem0_agent_id` |
| `conversations` | SELECT, INSERT, UPDATE | Look up/auto-create conversation; update `last_message_at` |
| `messages` | SELECT, INSERT | Fetch recent messages for context; persist user + assistant messages |
| `profiles` | SELECT | Read via `get_current_user` for timezone, language, name, `mem0_user_id` |
| `user_activity` | UPDATE | Update `last_chat_at` in background task |

---

## API Reference

For the full API contract, see [`docs/04-veri-api.md`](../04-veri-api.md). All endpoints below are under `/api/v1/characters` and require `Authorization: Bearer <jwt>`.

### POST /api/v1/characters/{character_id}/messages

**Auth**: Bearer JWT required
**Content-Type**: `application/json`
**Success Status**: `200 OK` (SSE stream)

Sends a message to a character and streams the AI response via Server-Sent Events.

**Request Body**:

```json
{
  "content": "I want to practice English today!",
  "media_url": null
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `content` | string | yes | 1-4000 chars, whitespace-trimmed, rejected if empty after trim |
| `media_url` | string or null | no | Must be a valid HTTP/HTTPS URL if provided, max 2048 chars |

**Response**: `text/event-stream` with `Cache-Control: no-cache` and `X-Accel-Buffering: no`.

**SSE Event Sequence**:

```
data: {"type":"chunk","content":"Great"}

data: {"type":"chunk","content":"! Let's"}

data: {"type":"chunk","content":" start with some conversation practice."}

data: {"type":"action","action":"SET_ALARM","payload":{"time":"2026-02-24T07:00:00","label":"Morning practice"}}

data: {"type":"done","message_id":"550e8400-e29b-41d4-a716-446655440099"}

```

Each SSE line is prefixed with `data: ` and followed by two newlines (`\n\n`). The JSON payload is a single line.

**SSE Event Types**:

| Event Type | Fields | Description |
|------------|--------|-------------|
| `chunk` | `type`, `content` | A text fragment of the streaming AI response |
| `action` | `type`, `action`, `payload` | A device action intent detected in the response. Zero or one per response. Sent after streaming, before `done`. |
| `done` | `type`, `message_id` | Signals the stream is complete. `message_id` is the UUID of the persisted assistant message. Always the last event. |
| `error` | `type`, `message` | Signals an error occurred mid-stream. Sent instead of `done`. |

**Error Responses (before SSE starts)**:

| Status | Detail | When |
|--------|--------|------|
| 400 | `"Message content must be between 1 and 4000 characters"` | Content empty or exceeds 4000 chars |
| 401 | `"Invalid or expired token"` | Missing or invalid JWT |
| 403 | `"Character does not belong to user"` | Ownership mismatch |
| 404 | `"Character not found"` | Non-existent or inactive character |
| 422 | Standard FastAPI validation error | Pydantic validation failure |

**Error during streaming (after SSE has started)**:

If the Claude API fails mid-stream, an `error` event is emitted and the connection is closed. The HTTP status remains 200 (SSE protocol constraint). No messages are persisted.

```
data: {"type":"error","message":"AI service temporarily unavailable"}

```

**Notes**:

- The `message_id` in the `done` event is the assistant message UUID. The user message UUID is not returned; the client generates a local UUID for the user message bubble.
- The `media_url` is stored on the user message but is not processed in this feature. Photo analysis is a separate future feature.
- If the character has no existing conversation (edge case), the endpoint auto-creates one.

### GET /api/v1/characters/{character_id}/messages

**Auth**: Bearer JWT required
**Success Status**: `200 OK`

Retrieves paginated message history for a character's conversation using cursor-based pagination.

**Query Parameters**:

| Param | Type | Required | Default | Constraints |
|-------|------|----------|---------|-------------|
| `cursor` | string (ISO 8601) | no | none | Messages older than this timestamp are returned |
| `limit` | integer | no | 20 | Min 1, max 100 |

**Response Body**:

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440088",
      "role": "assistant",
      "content": "Great! Let's start with some conversation practice.",
      "media_url": null,
      "metadata": null,
      "created_at": "2026-02-23T14:30:05Z"
    },
    {
      "id": "550e8400-e29b-41d4-a716-446655440087",
      "role": "user",
      "content": "I want to practice English today!",
      "media_url": null,
      "metadata": null,
      "created_at": "2026-02-23T14:30:00Z"
    }
  ],
  "next_cursor": "2026-02-23T14:25:00Z",
  "has_more": true
}
```

| Field | Type | Notes |
|-------|------|-------|
| `items` | array | Messages in reverse chronological order (newest first) |
| `items[].id` | string (UUID) | Message primary key |
| `items[].role` | string | `"user"` or `"assistant"` |
| `items[].content` | string | Message text |
| `items[].media_url` | string or null | S3 URL for attached media |
| `items[].metadata` | object or null | Intent action data or other metadata |
| `items[].created_at` | string (ISO 8601) | Message creation timestamp |
| `next_cursor` | string or null | Timestamp for the next page. Null when no more messages. |
| `has_more` | boolean | True if older messages exist beyond this page |

**Error Responses**:

| Status | Detail | When |
|--------|--------|------|
| 401 | `"Invalid or expired token"` | Missing or invalid JWT |
| 403 | `"Character does not belong to user"` | Ownership mismatch |
| 404 | `"Character not found"` | Non-existent or inactive character |
| 404 | `"Conversation not found"` | Character has no conversation (edge case) |
| 422 | Standard FastAPI validation error | Invalid limit range, invalid UUID |

---

## Pydantic Schemas

All schemas are defined in `backend/app/schemas/chat.py`.

**Request schemas**:

- `SendMessageRequest` -- validates `content` (1-4000 chars, whitespace-trimmed), `media_url` (optional, must be HTTP/HTTPS URL)

**Response schemas**:

- `MessageItem` -- a single message with `id` (UUID coerced to string), `role`, `content`, `media_url`, `metadata` (handles ORM `metadata_` mapping), `created_at`
- `MessageListResponse` -- wrapper containing `items`, `next_cursor`, `has_more`

**SSE event models** (used for serialization via `model_dump_json()`, not as FastAPI response models):

- `ChunkEvent` -- `{"type": "chunk", "content": "..."}`
- `ActionEvent` -- `{"type": "action", "action": "...", "payload": {...}}`
- `DoneEvent` -- `{"type": "done", "message_id": "..."}`
- `ErrorEvent` -- `{"type": "error", "message": "..."}`

---

## Configuration

One new configuration field was added to `backend/app/config.py`:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `max_context_messages` | int | 50 | Number of recent messages to include as context for the Claude API call |

Existing settings used by this feature:

| Variable | Purpose |
|----------|---------|
| `anthropic_api_key` | API key for both Claude Sonnet (streaming) and Claude Haiku (intent extraction) |
| `claude_model` | Model identifier for the main conversation (Claude Sonnet) |
| `claude_haiku_model` | Model identifier for intent extraction (Claude Haiku) |
| `mem0_api_key` | API key for Mem0 memory search and add operations |

---

## Files

| File | Role |
|------|------|
| `backend/app/routes/chat.py` | Route handlers: `send_message` (POST, returns `StreamingResponse`) and `get_messages` (GET, returns `MessageListResponse`). Delegates all logic to `ChatService`. |
| `backend/app/services/chat_service.py` | `ChatService` class with 2 public methods (`validate_send_message`, `stream_response`, `get_messages`) and 6 private helpers. Module-level `_persist_exchange` background task and `_deduplicate_memories` utility. |
| `backend/app/schemas/chat.py` | 7 Pydantic schemas: `SendMessageRequest`, `MessageItem`, `MessageListResponse`, `ChunkEvent`, `ActionEvent`, `DoneEvent`, `ErrorEvent`. |
| `backend/app/config.py` | Modified: added `max_context_messages: int = 50`. |
| `backend/app/main.py` | Modified: registered chat router at `/api/v1/characters` with `tags=["chat"]`. |

### Service Layer

`ChatService` is instantiated per-request with the database session: `ChatService(db)`. Route handlers create the service and delegate entirely -- they contain no business logic.

The streaming flow is split into two methods for a deliberate reason:

- `validate_send_message()` runs before the `StreamingResponse` is created, allowing `HTTPException` to propagate as proper JSON error responses.
- `stream_response()` is the async generator that runs inside the `StreamingResponse`. At this point, the HTTP status is already 200 and errors can only be communicated via SSE `error` events.

Key private helpers:

- `_get_active_character(character_id)` -- queries for an active character, raises 404 if not found
- `_get_or_create_conversation(character_id, user_id)` -- finds the conversation, auto-creates if missing
- `_search_memories(query, mem0_user_id, agent_id, limit)` -- searches Mem0 via `asyncio.to_thread()`, returns empty list on failure
- `_get_recent_messages(conversation_id)` -- fetches the last N messages in DESC order, reverses to chronological
- `_build_system_prompt(...)` -- constructs the 3-block system prompt
- `_format_messages(recent_messages, new_content)` -- formats message history for the Claude API
- `_extract_intent(assistant_response, user_timezone)` -- calls Claude Haiku for intent extraction

---

## Testing

### Coverage Summary

| File | Tests | Line Coverage | Branch Coverage |
|------|-------|---------------|-----------------|
| `test_chat_routes.py` | 34 | 100% | 100% |
| `test_chat_service.py` | 65 | 100% | 100% |
| `test_chat_schemas.py` | 31 | 100% | 100% |
| **Total** | **130** | **100%** (274/274 lines) | **100%** (50/50 branches) |

Target was >= 80% line coverage. Both line and branch coverage are at 100%.

### Running Tests

Chat tests only:

```bash
cd backend && python -m pytest tests/test_chat_routes.py tests/test_chat_service.py tests/test_chat_schemas.py -v
```

Full backend suite:

```bash
cd backend && python -m pytest tests/ -v --ignore=tests/test_migration.py
```

### Test Approach

- **Route tests**: Use `httpx.AsyncClient`. The `get_current_user` dependency is overridden. SSE response body is consumed as text and parsed line-by-line.
- **Service tests**: Unit-test `ChatService` directly with mock database session, mock Anthropic client, and mock Mem0 client.
- **Schema tests**: Validate Pydantic schemas directly -- content trimming, length boundaries, URL validation, UUID-to-string coercion, SSE event serialization.
- **Mocking**: All external services (Claude Sonnet streaming, Claude Haiku non-streaming, Mem0 search/add) are mocked. No real API calls are made.

---

## Known Limitations

- **No offline support**: Messages require network connectivity. There is no local queue or retry mechanism for failed sends.
- **Maximum 4000 characters per message**: Longer messages are rejected with a 422 validation error.
- **No media processing**: The `media_url` field is accepted and stored but not processed. Photo analysis is a separate future feature.
- **No TTS integration**: The `tts_url` field exists in the database but is not populated. Voice features are Phase 3+.
- **No subscription-tier enforcement**: Any authenticated user can send unlimited messages. Free-tier message limits are a Phase 2 feature.
- **Background task failure risk**: If the background persistence task fails, messages are lost (the user saw the streamed response but it is not saved to the database). This is an accepted trade-off for Phase 1 to keep time-to-first-token low. A retry mechanism can be added later.
- **No streaming retry**: If the Claude API fails mid-stream, an error event is emitted and the conversation stops. The client must retry the message manually.
- **Mem0 SDK is synchronous**: All Mem0 calls are wrapped in `asyncio.to_thread()`. This uses a thread from the default executor pool, which could become a bottleneck under high concurrency.

---

## Design Decisions

### Why SSE instead of WebSocket

SSE is a simpler protocol for server-to-client streaming. Ember's chat is request-response (user sends, server streams a reply) -- not bidirectional. SSE works over standard HTTP, is easier to test, and is well-supported by FastAPI's `StreamingResponse`. WebSocket is reserved for real-time voice calls (Phase 5+ via LiveKit).

### Why background tasks for persistence instead of inline writes

Writing messages to the database before or during the stream would add latency to the first-token time. The performance target from `docs/08-guvenlik-performans.md` is TTFT under 1 second. By deferring persistence to background tasks, the stream starts as soon as Claude begins generating tokens.

### Why 50 messages of context

`docs/05-ai-bellek.md` mentions 20 messages for cost optimization, but `CLAUDE.md` specifies "last 30-50 messages." The implementation uses 50 as a configurable upper bound via `settings.max_context_messages`. More context produces better conversation quality, and the cost difference is manageable for Phase 1.

### Why a separate Haiku call for intent extraction

Separating intent extraction from conversation keeps the main response natural. Sonnet writes human-friendly text, not structured JSON. Haiku is cheaper and faster for structured extraction. The latency (~200-400ms) is acceptable because it runs after the full response is streamed -- the user is already reading the response.

### Why the user message ID is not in the SSE stream

The mobile client generates a local UUID for the user message bubble immediately on send. Only the assistant message ID is returned (for correlating the streamed response with the persisted message). This keeps the SSE protocol simpler.

### Why background tasks use a separate DB session

The request-scoped database session is closed when the `StreamingResponse` finishes. Background tasks create their own session via `AsyncSessionLocal()` to avoid using a closed session.

### Why validation runs before StreamingResponse

The route handler calls `validate_send_message()` before creating the `StreamingResponse`. This ensures that `HTTPException` (403, 404) produces proper JSON error responses with correct HTTP status codes. Once inside the streaming generator, the HTTP status is already 200 and errors can only be communicated via SSE events.

---

## Extending This Feature

**Adding a new device action type** (e.g., `SEND_REMINDER`): Add the action name to the `_SUPPORTED_ACTIONS` frozenset in `backend/app/services/chat_service.py`. Update the `_INTENT_EXTRACTION_PROMPT` template to describe the new action and its expected payload fields. No schema changes are needed because `ActionEvent.payload` is a generic `dict`. Update mobile clients to handle the new action type.

**Changing the context window size**: Modify `max_context_messages` in `backend/app/config.py` or set the `MAX_CONTEXT_MESSAGES` environment variable. No code changes required.

**Adding subscription-tier message limits**: Add a count check at the beginning of `ChatService.validate_send_message()` that queries the number of messages sent by the user today and compares it against the tier limit. Return 429 if the limit is exceeded.

**Adding prompt caching**: Pass the system prompt as a list of content blocks with `cache_control: {"type": "ephemeral"}` on the first block (character definition). This leverages Anthropic's prompt caching to reduce cost and latency for repeated conversations with the same character.

**Adding media/image analysis**: Process the `media_url` field in `validate_send_message()` by downloading the image and including it as a vision content block in the Claude API call.

---

## Related Documentation

- [Character CRUD](./character-crud.md) -- character creation and the `system_prompt` / `mem0_agent_id` that this feature uses
- [Database Schema](./database-schema.md) -- the `messages`, `conversations`, `characters`, `profiles`, and `user_activity` tables
- [Cognito Auth Middleware](./cognito-auth-middleware.md) -- JWT verification used by both endpoints
- [Database Schema and API Endpoints](../04-veri-api.md) -- authoritative source for table definitions and API contracts
- [AI Memory System](../05-ai-bellek.md) -- Mem0 integration patterns, prompt architecture, and memory isolation
- [Security and Performance](../08-guvenlik-performans.md) -- TTFT performance target and rate limiting
- [Multi-Character System](../16-karakterler.md) -- character templates and memory isolation design
