# Feature Spec: P01-06 -- Chat Streaming

**Feature ID**: P01-06
**Phase**: 1
**Layer**: backend
**GitHub Issue**: #8
**Date**: 2026-02-23
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature implements the core messaging endpoint for Ember: `POST /api/v1/characters/:id/messages`. It is the single most important endpoint in the application -- it receives a user's message, retrieves context (recent messages + Mem0 memories), streams the AI response via Server-Sent Events (SSE), and persists both messages as background tasks after the stream completes.

Additionally, the feature implements `GET /api/v1/characters/:id/messages` for cursor-based retrieval of message history, enabling the mobile clients to load conversation history with infinite scroll.

**The streaming endpoint performs these steps in order:**

1. Validate the character belongs to the authenticated user and is active.
2. Look up (or auto-create) the character's single conversation.
3. Run `asyncio.gather()` to fetch Mem0 memories and recent DB messages in parallel.
4. Build the full LLM prompt: system prompt (character template) + Mem0 memories + date/time context + last 50 messages + the new user message.
5. Open an Anthropic Claude Sonnet streaming session and yield SSE `chunk` events as tokens arrive.
6. After the full response is assembled, run Claude Haiku intent extraction on the complete assistant response to detect device action intents (SET_ALARM, ADD_CALENDAR_EVENT). If an intent is found, yield an SSE `action` event.
7. Yield a final SSE `done` event with the assistant message's UUID.
8. Fire-and-forget background tasks: save user message + assistant message to DB, update `conversations.last_message_at`, add the exchange to Mem0, update `user_activity.last_chat_at`.

### Why It Exists

Without this endpoint, users cannot converse with their AI characters. Chat is the primary interaction mode in Ember. Streaming provides a responsive UX (the user sees tokens appear in real-time rather than waiting for the full response). Mem0 integration makes the AI remember past conversations, which is Ember's core differentiator.

### Dependencies

- **Requires**: P01-01 (project-setup -- FastAPI scaffold, config, logging)
- **Requires**: P01-02 (database-schema -- Message, Conversation, Character, Profile, UserActivity models)
- **Requires**: P01-03 (cognito-auth-middleware -- `get_current_user` dependency)
- **Requires**: P01-04 (auth-endpoints -- user can register and obtain a JWT)
- **Requires**: P01-05 (character-crud -- user can create characters, conversation auto-created)
- **Blocks**: All mobile chat UI features, voice features, notification features that depend on message data

### What This Feature Does NOT Do

- It does not implement media upload or image analysis. The `media_url` field is accepted in the request and stored, but no vision processing occurs in this feature.
- It does not implement TTS (text-to-speech). The `tts_url` field on messages remains null.
- It does not implement the memory display endpoints (`GET /characters/:id/memories`). That is a separate feature.
- It does not implement proactive notifications. That is a Phase 3+ feature.
- It does not enforce subscription-tier message limits. That is a Phase 2 feature.

---

## 2. Data Models

### No New Tables

This feature does not create any new database tables. It reads from and writes to existing tables defined in P01-02 (documented in `docs/04-veri-api.md`):

- **messages** -- User and assistant messages are inserted here after stream completion.
- **conversations** -- The `last_message_at` column is updated after each exchange. The conversation row is looked up by `character_id`.
- **characters** -- Read to obtain `system_prompt`, `mem0_agent_id`, `template`, and `name` for prompt building.
- **profiles** -- Read via `get_current_user` for `timezone`, `preferred_language`, `name`, and `mem0_user_id`.
- **user_activity** -- `last_chat_at` is updated as a background task.

### Key Column References

| Table | Column | Usage in This Feature |
|-------|--------|----------------------|
| `messages.id` | UUID PK | Generated server-side for both user and assistant messages |
| `messages.conversation_id` | UUID FK | Links message to the character's conversation |
| `messages.user_id` | UUID FK | Set from JWT user_id |
| `messages.role` | TEXT | `"user"` for the incoming message, `"assistant"` for the AI response |
| `messages.content` | TEXT | User message text from request, or accumulated streamed AI text |
| `messages.media_url` | TEXT / NULL | Passed through from request for user message, null for assistant |
| `messages.metadata_` | JSONB / NULL | Stores intent action data on the assistant message if detected |
| `messages.created_at` | TIMESTAMPTZ | Server-default `now()` |
| `conversations.character_id` | UUID UNIQUE FK | Used to find the conversation for a given character |
| `conversations.last_message_at` | TIMESTAMPTZ | Updated to `now()` after the exchange |
| `characters.system_prompt` | TEXT | Included as Block 1 of the LLM prompt |
| `characters.mem0_agent_id` | TEXT | Passed to Mem0 search and add calls |
| `characters.template` | TEXT | Used for mem0_agent_id validation |
| `profiles.timezone` | TEXT | Included in Block 3 (daily context) of the LLM prompt |
| `profiles.preferred_language` | TEXT | Included in Block 3 for language context |
| `profiles.name` | TEXT | Included in Block 3 for personalization |
| `profiles.mem0_user_id` | TEXT | Passed to all Mem0 API calls as `user_id` |
| `user_activity.last_chat_at` | TIMESTAMPTZ | Updated as background task |

### Mem0 Operations

This feature makes the following Mem0 API calls:

**Search (before streaming, parallel with DB query):**

Two searches run in parallel via `asyncio.gather()`:

1. **Global memories** -- memories visible to all characters:
   ```
   mem0.search(query=user_message_content, user_id=profile.mem0_user_id)
   ```
   No `agent_id` filter. Returns up to 5 results.

2. **Character-specific memories** -- memories isolated to this character:
   ```
   mem0.search(query=user_message_content, user_id=profile.mem0_user_id, agent_id=character.mem0_agent_id)
   ```
   Returns up to 5 results.

Combined: up to 10 memories injected into Block 2 of the prompt.

**Add (background task after stream completion):**

```
mem0.add(
    messages=[user_message_content, assistant_response_content],
    user_id=profile.mem0_user_id,
    agent_id=character.mem0_agent_id
)
```

This runs as a background task. Failure is logged but does not affect the user-facing response.

---

## 3. API Endpoints

All endpoints are under the `/api/v1` prefix. Both require `Authorization: Bearer <jwt>`.

---

### POST /api/v1/characters/:id/messages

Sends a message to a character and streams the AI response via Server-Sent Events.

```
Auth: Bearer JWT required
Content-Type: application/json
Accept: text/event-stream
```

**Path Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `id` | UUID string | Character ID |

**Request Body:**

```json
{
  "content": "I want to practice English today!",
  "media_url": null
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `content` | string | yes | Min 1 char, max 4000 chars, whitespace-trimmed |
| `media_url` | string or null | no | Valid URL format if provided, max 2048 chars |

**Response: `text/event-stream` (SSE)**

The response uses `Transfer-Encoding: chunked` with `Content-Type: text/event-stream; charset=utf-8` and `Cache-Control: no-cache`. The connection stays open until the `done` event is sent.

**SSE Event Sequence:**

```
data: {"type":"chunk","content":"Great"}

data: {"type":"chunk","content":"! Let's"}

data: {"type":"chunk","content":" start"}

data: {"type":"chunk","content":" with some"}

data: {"type":"chunk","content":" conversation practice."}

data: {"type":"action","action":"SET_ALARM","payload":{"time":"2026-02-24T07:00:00","label":"Morning practice"}}

data: {"type":"done","message_id":"550e8400-e29b-41d4-a716-446655440099"}

```

Each SSE line is prefixed with `data: ` and followed by two newlines (`\n\n`). The JSON payload is a single line (no pretty-printing).

**SSE Event Types:**

| Event Type | Fields | Description |
|------------|--------|-------------|
| `chunk` | `type`, `content` | A text fragment of the streaming AI response. `content` is a string (may be a single token or a few tokens). |
| `action` | `type`, `action`, `payload` | A device action intent detected in the response. Sent after streaming completes but before `done`. Zero or one per response. |
| `done` | `type`, `message_id` | Signals the stream is complete. `message_id` is the UUID of the persisted assistant message. Always the last event. |
| `error` | `type`, `message` | Signals an error occurred mid-stream. Sent instead of `done` if an unrecoverable error occurs during streaming. |

**Action Event Payloads:**

| Action | Payload Fields | Example |
|--------|---------------|---------|
| `SET_ALARM` | `time` (ISO 8601), `label` (string) | `{"time":"2026-02-24T07:00:00","label":"Wake up"}` |
| `ADD_CALENDAR_EVENT` | `title` (string), `date` (ISO 8601 date), `time` (ISO 8601 time), `duration_minutes` (integer) | `{"title":"Dentist","date":"2026-02-24","time":"15:00","duration_minutes":60}` |

**Error Responses (non-streaming, before SSE starts):**

| Status | Condition | Body |
|--------|-----------|------|
| 400 | Content is empty or exceeds 4000 chars | `{"detail": "Message content must be between 1 and 4000 characters"}` |
| 401 | Missing or invalid JWT | `{"detail": "Invalid or expired token"}` |
| 403 | Character does not belong to the authenticated user | `{"detail": "Character does not belong to user"}` |
| 404 | Character not found or inactive | `{"detail": "Character not found"}` |
| 422 | Pydantic validation failure | Standard FastAPI 422 response |

**Error during streaming (after SSE has started):**

If the Claude API fails mid-stream, an `error` event is sent and the connection is closed:

```
data: {"type":"error","message":"AI service temporarily unavailable"}

```

The user message is NOT persisted if the stream fails before producing any content. If the stream fails after producing partial content, neither the user message nor the partial assistant message is persisted.

**Notes:**

- The HTTP response status is always 200 once the SSE stream starts, even if an error occurs mid-stream. This is a constraint of the SSE protocol. Errors before streaming begins (validation, auth, not found) return standard HTTP error codes.
- The `message_id` in the `done` event is the UUID of the assistant message that was saved to the database. The mobile client uses this to correlate the streamed response with the persisted message.
- The user message is also saved to the database (as a background task), but its `id` is not returned in the SSE stream. The client generates a local UUID for the user message displayed in the UI.
- If the character has no existing conversation (edge case -- should not happen since P01-05 auto-creates one), the endpoint auto-creates a conversation row before proceeding.
- The `media_url` is stored on the user message but is NOT processed in this feature. Photo analysis is a separate future feature.

---

### GET /api/v1/characters/:id/messages

Retrieves the message history for a character's conversation, using cursor-based pagination.

```
Auth: Bearer JWT required
Content-Type: application/json
```

**Path Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `id` | UUID string | Character ID |

**Query Parameters:**

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `cursor` | string (ISO 8601 timestamp) | no | none | The `created_at` of the last loaded message. Messages older than this are returned. |
| `limit` | integer | no | 20 | Number of messages to return. Min 1, max 100. |

**Response 200 OK:**

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

| Response Field | Type | Notes |
|----------------|------|-------|
| `items` | array | Messages in reverse chronological order (newest first) |
| `items[].id` | string (UUID) | Message primary key |
| `items[].role` | string | `"user"` or `"assistant"` |
| `items[].content` | string | Message text |
| `items[].media_url` | string or null | S3 URL for attached media |
| `items[].metadata` | object or null | Intent action data or other metadata |
| `items[].created_at` | string (ISO 8601) | Message creation timestamp |
| `next_cursor` | string or null | Timestamp to use as `cursor` for the next page. Null when no more messages. |
| `has_more` | boolean | True if there are older messages beyond this page |

**SQL pattern for cursor pagination:**

```sql
SELECT id, role, content, media_url, metadata, created_at
FROM messages
WHERE conversation_id = $1
  AND ($cursor IS NULL OR created_at < $cursor)
ORDER BY created_at DESC
LIMIT $limit + 1;
```

Fetching `limit + 1` rows allows determining `has_more` without an extra count query. If `limit + 1` rows are returned, `has_more = true` and the extra row is discarded. The `next_cursor` is the `created_at` of the last returned item.

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 401 | Missing or invalid JWT | `{"detail": "Invalid or expired token"}` |
| 403 | Character does not belong to the authenticated user | `{"detail": "Character does not belong to user"}` |
| 404 | Character not found or inactive | `{"detail": "Character not found"}` |
| 404 | Character has no conversation (edge case) | `{"detail": "Conversation not found"}` |

**Notes:**

- Messages are returned newest-first (reverse chronological). The mobile client displays them bottom-up (newest at the bottom).
- The `tts_url` field exists in the DB but is NOT included in this response. It will be added in the voice feature (Phase 3+).
- The existing composite index `idx_messages_conv_time` on `(conversation_id, created_at DESC)` supports this query efficiently.

---

## 4. Backend Logic

### ChatService Class

The `ChatService` class in `backend/app/services/chat_service.py` encapsulates all messaging business logic. Route handlers delegate to this service.

```
class ChatService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def send_message_stream(
        self,
        character_id: uuid.UUID,
        user_id: uuid.UUID,
        profile: Profile,
        content: str,
        media_url: str | None,
    ) -> AsyncGenerator[str, None]:
        """Stream an AI response for a user message via SSE events.

        Yields SSE-formatted strings: 'data: {"type":"chunk","content":"..."}\n\n'
        """

    async def get_messages(
        self,
        character_id: uuid.UUID,
        user_id: uuid.UUID,
        cursor: datetime | None,
        limit: int,
    ) -> MessageListResponse:
        """Retrieve paginated message history for a character's conversation."""
```

### Send Message Flow (Streaming)

```
Client sends: POST /api/v1/characters/:id/messages
    { content, media_url }
    |
    v
1. Validate request body (Pydantic)
   - content: 1-4000 chars, whitespace-trimmed
   - media_url: optional, valid URL format
    |
    v
2. Look up character by id:
   SELECT * FROM characters WHERE id = $id AND is_active = true
    |
    +--> Not found --> 404 "Character not found"
    |
    v
3. Ownership check: character.user_id == jwt_user_id
    |
    +--> Mismatch --> 403 "Character does not belong to user"
    |
    v
4. Look up conversation:
   SELECT * FROM conversations WHERE character_id = $character_id
    |
    +--> Not found --> Auto-create conversation row
    |    (defensive: should exist from P01-05 character creation)
    |
    v
5. Parallel fetch via asyncio.gather():
   a) Mem0 global memory search (top 5)
   b) Mem0 character-specific memory search (top 5)
   c) DB: last 50 messages for this conversation
      ORDER BY created_at DESC LIMIT 50
      Then reverse to chronological order for the prompt
    |
    v
6. Build the LLM prompt:
   [system message] = Block 1 (character system_prompt)
                    + Block 2 (Mem0 memories, max 10)
                    + Block 3 (current date/time/timezone)
   [messages] = last 50 messages (alternating user/assistant)
              + the new user message
    |
    v
7. Open Claude Sonnet streaming session:
   client.messages.stream(
       model=settings.claude_model,  # claude-sonnet-4-6
       system=system_message,
       messages=message_history,
       max_tokens=2048,
   )
    |
    v
8. Yield SSE chunk events as tokens arrive:
   Accumulate the full response text as chunks stream.
   Each chunk: data: {"type":"chunk","content":"<token>"}\n\n
    |
    +--> Claude API error mid-stream -->
    |    yield: data: {"type":"error","message":"AI service temporarily unavailable"}\n\n
    |    return (do not persist anything)
    |
    v
9. Intent extraction (after full response is assembled):
   Call Claude Haiku with the complete assistant response:
   "Does this response contain a device action intent?
    Respond with JSON or 'none'."
    |
    +--> Intent detected -->
    |    yield: data: {"type":"action","action":"SET_ALARM","payload":{...}}\n\n
    +--> No intent / Haiku error --> skip (log error if Haiku fails)
    |
    v
10. Generate assistant message UUID
    yield: data: {"type":"done","message_id":"<uuid>"}\n\n
    |
    v
11. Background tasks (fire-and-forget via asyncio.create_task):
    a) Save user message to DB (role="user")
    b) Save assistant message to DB (role="assistant", metadata=action if any)
    c) UPDATE conversations SET last_message_at = now() WHERE character_id = $id
    d) Mem0 add: [user_content, assistant_content] with agent_id
    e) UPSERT user_activity SET last_chat_at = now() WHERE user_id = $id
```

### System Prompt Construction

The system message sent to Claude is constructed from three blocks, following the architecture in `docs/05-ai-bellek.md`:

**Block 1 -- Character Definition (from `characters.system_prompt`):**

This is the stored system prompt generated by Claude Haiku during character creation (P01-05). It is passed as the first segment. Per `docs/05-ai-bellek.md`, this block is relatively static and benefits from Anthropic prompt caching.

**Block 2 -- Learned Knowledge (from Mem0 search results):**

```
What you know about this user:
- {memory_1}
- {memory_2}
- ...
- {memory_N}
```

Up to 10 memories (5 global + 5 character-specific). Each memory is a single line of text. If no memories are found, this block is omitted. Memories from the global search and character-specific search are de-duplicated by content similarity (exact string match is sufficient for Phase 1).

**Block 3 -- Daily Context (dynamic):**

```
Current date and time: {weekday}, {date} {time}
Timezone: {profile.timezone}
User's preferred language: {profile.preferred_language}
```

The date/time is computed server-side at request time using the user's timezone from their profile.

**Message history:**

The last 50 messages from the conversation are passed as the `messages` array to Claude, in chronological order (oldest first). Each message has `role` (`"user"` or `"assistant"`) and `content`. The new user message is appended as the final entry.

Per `docs/05-ai-bellek.md`, the doc mentions "last 20 messages" for cost optimization, but CLAUDE.md says "last 30-50 messages." This spec uses 50 as the upper bound, configurable. The service should read this from a constant or config value, not a hardcoded literal.

### Intent Extraction via Claude Haiku

After the Claude Sonnet response is fully streamed and assembled, the service calls Claude Haiku to determine if the response contains a device action intent. This is a separate, non-streaming call.

**Haiku Intent Extraction Prompt:**

```
Analyze the following AI assistant response and determine if it contains an intent to perform a device action.

Supported actions:
- SET_ALARM: The assistant is setting an alarm or reminder. Extract time and label.
- ADD_CALENDAR_EVENT: The assistant is adding a calendar event. Extract title, date, time, duration.

If the response contains a device action intent, respond with ONLY this JSON:
{"action": "<ACTION_NAME>", "payload": {<relevant fields>}}

If the response does NOT contain any device action intent, respond with ONLY:
none

The "time" field must be in ISO 8601 format. The "date" field must be YYYY-MM-DD format.

User's timezone: {profile.timezone}
Current date: {current_date}

Assistant response to analyze:
{assistant_response_content}
```

**Processing the Haiku response:**

1. If the response is `"none"` or cannot be parsed as JSON: no action event is emitted.
2. If the response is valid JSON with an `action` field that matches a supported action: emit the `action` SSE event.
3. If the Haiku call fails (network error, rate limit): log the error and skip the action event. Do not fail the entire message flow.

**Why a separate Haiku call instead of instructing Sonnet to include actions in-stream:**

- Separating intent extraction from conversation keeps the main conversation natural. Sonnet should write a human-friendly response, not JSON-structured output.
- Haiku is cheaper and faster for structured extraction tasks.
- Intent extraction can evolve independently (new actions, better prompts) without affecting the conversation quality.
- Per `docs/05-ai-bellek.md`: Haiku is the designated model for "intent classification" tasks.

### Get Messages Flow (Paginated)

```
Client sends: GET /api/v1/characters/:id/messages?cursor=2026-02-23T14:30:00Z&limit=20
    |
    v
1. Look up character by id (active, ownership check)
    |
    v
2. Look up conversation by character_id
    |
    +--> Not found --> 404 "Conversation not found"
    |
    v
3. Query messages with cursor pagination:
   SELECT id, role, content, media_url, metadata, created_at
   FROM messages
   WHERE conversation_id = $conversation_id
     AND ($cursor IS NULL OR created_at < $cursor)
   ORDER BY created_at DESC
   LIMIT $limit + 1
    |
    v
4. Determine pagination:
   - If result count > limit: has_more=true, drop last row
   - next_cursor = last returned row's created_at (as ISO 8601 string)
   - If result count <= limit: has_more=false, next_cursor=null
    |
    v
5. Return 200 { items, next_cursor, has_more }
```

### Background Task Execution

Background tasks are fired after the SSE stream completes using `asyncio.create_task()`. They run within the same event loop but do not block the response.

**Critical design decision**: Background tasks use a NEW database session (not the request-scoped session). The request-scoped session is closed when the SSE response finishes. The background task creates its own session via `AsyncSessionLocal()`.

```
async def _persist_exchange(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    user_content: str,
    user_media_url: str | None,
    assistant_content: str,
    assistant_message_id: uuid.UUID,
    action_metadata: dict | None,
    mem0_user_id: str,
    mem0_agent_id: str,
) -> None:
    """Background task: persist messages, update timestamps, add to Mem0."""
    async with AsyncSessionLocal() as db:
        # Save user message
        user_msg = Message(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            user_id=user_id,
            role="user",
            content=user_content,
            media_url=user_media_url,
        )
        db.add(user_msg)

        # Save assistant message
        assistant_msg = Message(
            id=assistant_message_id,
            conversation_id=conversation_id,
            user_id=user_id,
            role="assistant",
            content=assistant_content,
            metadata_=action_metadata,
        )
        db.add(assistant_msg)

        # Update conversation timestamp
        await db.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(last_message_at=func.now())
        )

        # Update user activity
        await db.execute(
            update(UserActivity)
            .where(UserActivity.user_id == user_id)
            .values(last_chat_at=func.now())
        )

        await db.commit()

    # Mem0 add (outside DB transaction)
    try:
        mem0_client = MemoryClient(api_key=settings.mem0_api_key)
        await asyncio.to_thread(
            mem0_client.add,
            [
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": assistant_content},
            ],
            user_id=mem0_user_id,
            agent_id=mem0_agent_id,
        )
    except Exception:
        logger.exception("Mem0 add failed for agent_id=%s", mem0_agent_id)
```

**Error handling in background tasks:**

- DB persistence failure: logged at ERROR level. The user will not see the messages in history, but the streamed response was already delivered. This is an acceptable trade-off for Phase 1. A retry mechanism can be added later.
- Mem0 add failure: logged at ERROR level. Memory will not be updated for this exchange. This is non-critical.
- User activity update failure: logged at WARNING level. Non-critical.

### Mem0 Client Integration

The Mem0 Python SDK (`mem0ai` package, already in `requirements.txt`) provides a `MemoryClient` class. Since the SDK is synchronous, all calls are wrapped with `asyncio.to_thread()` to avoid blocking the event loop.

```python
from mem0 import MemoryClient

async def _search_memories(
    query: str,
    mem0_user_id: str,
    agent_id: str | None,
    limit: int = 5,
) -> list[str]:
    """Search Mem0 for relevant memories. Returns a list of memory text strings."""
    client = MemoryClient(api_key=settings.mem0_api_key)

    filters = {"user_id": mem0_user_id}
    if agent_id is not None:
        filters["agent_id"] = agent_id

    results = await asyncio.to_thread(
        client.search,
        query,
        user_id=mem0_user_id,
        agent_id=agent_id,
        limit=limit,
    )
    return [r["memory"] for r in results]
```

The two Mem0 searches (global + character-specific) are run in parallel:

```python
global_memories, character_memories = await asyncio.gather(
    _search_memories(content, profile.mem0_user_id, agent_id=None, limit=5),
    _search_memories(content, profile.mem0_user_id, agent_id=character.mem0_agent_id, limit=5),
)
```

### Anthropic Streaming Client

The streaming call uses the `anthropic` SDK's async streaming interface:

```python
client = AsyncAnthropic(api_key=settings.anthropic_api_key)

async with client.messages.stream(
    model=settings.claude_model,  # claude-sonnet-4-6
    system=system_prompt_text,
    messages=formatted_messages,
    max_tokens=2048,
) as stream:
    async for text in stream.text_stream:
        yield f'data: {json.dumps({"type": "chunk", "content": text})}\n\n'
    # After stream completes, get the full message
    response = await stream.get_final_message()
    full_response_text = response.content[0].text
```

### Config Changes

The `config.py` Settings class needs one new constant. Note that `claude_model` and `claude_haiku_model` already exist from P01-05.

```
max_context_messages: int = 50
```

This makes the message history depth configurable.

No changes to `requirements.txt` are needed. All required packages (`anthropic`, `mem0ai`, `fastapi`) are already listed.

---

## 5. Pydantic Schemas

All new schemas are defined in `backend/app/schemas/chat.py`.

### Request Schemas

```
class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    media_url: str | None = Field(default=None, max_length=2048)

    @field_validator("content")
    @classmethod
    def strip_content(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Message content must not be empty after trimming whitespace")
        return stripped

    @field_validator("media_url")
    @classmethod
    def validate_media_url(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            raise ValueError("media_url must be a valid HTTP or HTTPS URL")
        return v
```

### Response Schemas

```
class MessageItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    media_url: str | None
    metadata: dict | None
    created_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id_to_str(cls, v: object) -> str:
        return str(v)

    @field_validator("metadata", mode="before")
    @classmethod
    def coerce_metadata(cls, v: object) -> dict | None:
        """Handle the ORM column name metadata_ -> metadata."""
        return v
```

```
class MessageListResponse(BaseModel):
    items: list[MessageItem]
    next_cursor: str | None
    has_more: bool
```

**SSE Event Models (used for serialization, not as response_model):**

```
class ChunkEvent(BaseModel):
    type: str = "chunk"
    content: str

class ActionEvent(BaseModel):
    type: str = "action"
    action: str
    payload: dict

class DoneEvent(BaseModel):
    type: str = "done"
    message_id: str

class ErrorEvent(BaseModel):
    type: str = "error"
    message: str
```

These are used internally by `ChatService` to serialize SSE payloads via `model.model_dump_json()`. They are NOT FastAPI response models.

---

## 6. Test Requirements

### Route Tests (`backend/tests/test_chat_routes.py`)

These tests use the FastAPI test client. The `get_current_user` dependency is overridden to return a fake Profile. Claude and Mem0 are mocked.

#### POST /characters/:id/messages

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Valid message to own character | 200, SSE stream with chunk events, done event with message_id |
| 2 | Message to character belonging to another user | 403, "Character does not belong to user" |
| 3 | Message to non-existent character | 404, "Character not found" |
| 4 | Message to inactive character | 404, "Character not found" |
| 5 | Empty content (whitespace only) | 422, validation error |
| 6 | Content exceeds 4000 chars | 422, validation error |
| 7 | Missing Authorization header | 401 |
| 8 | SSE stream contains chunk, done events in correct order | Verify first events are chunks, last event is done |
| 9 | Claude API failure before streaming starts | 200 then error SSE event |
| 10 | Intent action detected in response | SSE stream includes action event before done |
| 11 | No intent detected | SSE stream has chunks and done, no action event |

#### GET /characters/:id/messages

| # | Scenario | Expected |
|---|----------|----------|
| 12 | Get messages without cursor (first page) | 200, items array, newest messages first |
| 13 | Get messages with cursor | 200, only messages older than cursor |
| 14 | Get messages with limit=5 | 200, at most 5 items |
| 15 | Get messages when conversation is empty | 200, `{"items": [], "next_cursor": null, "has_more": false}` |
| 16 | Get messages for character belonging to another user | 403 |
| 17 | Get messages for non-existent character | 404 |
| 18 | Get messages without auth | 401 |
| 19 | has_more is true when more messages exist | Verify by inserting more messages than limit |
| 20 | has_more is false on last page | Verify when all messages fit in one page |
| 21 | next_cursor value matches last item's created_at | Verify cursor format |

### Service Tests (`backend/tests/test_chat_service.py`)

Unit tests for `ChatService` with mocked DB, Claude, and Mem0.

| # | Scenario | Expected |
|---|----------|----------|
| 22 | `send_message_stream()` calls asyncio.gather for Mem0 + DB in parallel | Mock verify gather called with 3 coroutines |
| 23 | `send_message_stream()` builds system prompt with 3 blocks | Verify system prompt contains character prompt, memories, date/time |
| 24 | `send_message_stream()` passes last 50 messages to Claude | Verify message count in Claude call |
| 25 | `send_message_stream()` yields chunk events from Claude stream | Verify SSE format per chunk |
| 26 | `send_message_stream()` calls Haiku for intent extraction after stream | Verify Haiku called with assistant response |
| 27 | `send_message_stream()` yields action event when intent detected | Verify action SSE event emitted |
| 28 | `send_message_stream()` skips action when Haiku returns "none" | No action event in stream |
| 29 | `send_message_stream()` skips action when Haiku call fails | No action event, error logged |
| 30 | `send_message_stream()` yields done event with UUID | Verify done event format |
| 31 | `send_message_stream()` fires background task for persistence | Verify asyncio.create_task called |
| 32 | Background task persists user and assistant messages | Verify 2 Message inserts |
| 33 | Background task updates conversation.last_message_at | Verify UPDATE query |
| 34 | Background task calls Mem0 add with correct agent_id | Verify Mem0 add params |
| 35 | Background task handles DB error gracefully | Error logged, no crash |
| 36 | Background task handles Mem0 error gracefully | Error logged, no crash |
| 37 | `get_messages()` returns messages in DESC order | Verify ordering |
| 38 | `get_messages()` applies cursor filter correctly | Only messages before cursor |
| 39 | `get_messages()` calculates has_more and next_cursor | Verify pagination logic |
| 40 | `get_messages()` raises 404 for missing conversation | HTTPException(404) |
| 41 | Mem0 search failure does not crash send_message_stream | Stream continues with empty memories |
| 42 | System prompt includes user timezone and language | Verify Block 3 content |

### Schema Tests (`backend/tests/test_chat_schemas.py`)

| # | Scenario | Expected |
|---|----------|----------|
| 43 | `SendMessageRequest` strips whitespace from content | Trimmed correctly |
| 44 | `SendMessageRequest` rejects empty content after strip | ValidationError |
| 45 | `SendMessageRequest` rejects content > 4000 chars | ValidationError |
| 46 | `SendMessageRequest` accepts null media_url | Passes |
| 47 | `SendMessageRequest` rejects invalid media_url | ValidationError |
| 48 | `MessageItem` coerces UUID id to string | UUID -> string |
| 49 | `MessageListResponse` includes pagination fields | next_cursor, has_more present |

### How to Mock Claude Streaming

```python
from unittest.mock import AsyncMock, MagicMock, patch

# Mock the streaming context manager
mock_stream = AsyncMock()
mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
mock_stream.__aexit__ = AsyncMock(return_value=False)

# Mock text_stream as an async iterator
async def mock_text_iter():
    for chunk in ["Hello", ", ", "world", "!"]:
        yield chunk

mock_stream.text_stream = mock_text_iter()

# Mock get_final_message
mock_final = MagicMock()
mock_final.content = [MagicMock(text="Hello, world!")]
mock_stream.get_final_message = AsyncMock(return_value=mock_final)

with patch("app.services.chat_service.AsyncAnthropic") as mock_cls:
    mock_client = AsyncMock()
    mock_client.messages.stream = MagicMock(return_value=mock_stream)
    mock_cls.return_value = mock_client
    # ... run test
```

### How to Mock Mem0

```python
from unittest.mock import patch, MagicMock

mock_mem0 = MagicMock()
mock_mem0.search.return_value = [
    {"memory": "Prefers morning workouts"},
    {"memory": "Left knee is sensitive"},
]
mock_mem0.add.return_value = None

with patch("app.services.chat_service.MemoryClient", return_value=mock_mem0):
    # ... run test
```

Since Mem0 calls are wrapped in `asyncio.to_thread()`, the mock must work with synchronous calls.

### How to Test SSE Streaming

Use `httpx.AsyncClient` with `stream=True` to consume SSE events:

```python
async with httpx.AsyncClient(app=app) as client:
    async with client.stream(
        "POST",
        f"/api/v1/characters/{char_id}/messages",
        json={"content": "Hello"},
        headers={"Authorization": f"Bearer {token}"},
    ) as response:
        events = []
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

        assert events[-1]["type"] == "done"
        assert "message_id" in events[-1]
        assert all(e["type"] == "chunk" for e in events[:-1])
```

---

## 7. File Manifest

Every file to be created or modified, grouped by purpose.

### Route Handler

```
Backend:
  CREATE  backend/app/routes/chat.py
```

Contains two route functions: `send_message` (POST, returns `StreamingResponse`) and `get_messages` (GET, returns `MessageListResponse`). Each delegates to `ChatService`.

### Service Layer

```
Backend:
  CREATE  backend/app/services/chat_service.py
```

Contains the `ChatService` class with `send_message_stream()` and `get_messages()` methods. Contains the system prompt builder, Mem0 search wrapper, Haiku intent extractor, and the `_persist_exchange()` background task function.

### Pydantic Schemas

```
Backend:
  CREATE  backend/app/schemas/chat.py
```

Contains `SendMessageRequest`, `MessageItem`, `MessageListResponse`, `ChunkEvent`, `ActionEvent`, `DoneEvent`, `ErrorEvent`.

### Application Wiring

```
Backend:
  MODIFY  backend/app/main.py
```

Add `from app.routes import chat` and register the chat router:

```python
app.include_router(chat.router, prefix="/api/v1/characters", tags=["chat"])
```

Note: The chat router is registered under the `/api/v1/characters` prefix because the endpoints are `/{character_id}/messages`. This does NOT conflict with the existing characters router because the path patterns are distinct: the characters router handles `""`, `"/{character_id}"` while the chat router handles `"/{character_id}/messages"`.

### Configuration

```
Backend:
  MODIFY  backend/app/config.py
```

Add `max_context_messages: int = 50` to the `Settings` class.

### Tests

```
Backend:
  CREATE  backend/tests/test_chat_routes.py
  CREATE  backend/tests/test_chat_service.py
  CREATE  backend/tests/test_chat_schemas.py
```

### Documentation (Pipeline)

```
Shared:
  CREATE  shared/feature-specs/chat-streaming.md          (this file)
  CREATE  docs/pipeline/chat-streaming-architect.handoff.md
```

### Summary

| Action | Count |
|--------|-------|
| CREATE | 6 |
| MODIFY | 2 |
| DELETE | 0 |
| **Total** | **8** |

### Files NOT Modified

- `backend/app/dependencies.py` -- Uses the existing `get_current_user` and `get_db`. No changes needed.
- `backend/app/core/auth.py` -- JWT verification is handled by the existing middleware. No changes needed.
- `backend/app/models/` -- No model changes. Existing Message, Conversation, Character, Profile, UserActivity models from P01-02 are used as-is.
- `backend/app/schemas/__init__.py` -- Not modified (follow direct import pattern from route files).
- `backend/app/services/__init__.py` -- Not modified (follow direct import pattern).
- `backend/requirements.txt` -- Already includes `anthropic>=0.43.0,<1.0.0` and `mem0ai>=0.1.0`. No new dependencies needed.
- `backend/.env.example` -- Already has `ANTHROPIC_API_KEY` and `MEM0_API_KEY`. No changes needed.

---

## 8. Acceptance Criteria

1. Given an authenticated user with a character, when the client sends `POST /api/v1/characters/:id/messages` with valid content, then the response is HTTP 200 with `Content-Type: text/event-stream` and the stream contains at least one `chunk` event followed by a `done` event.

2. Given a streaming response in progress, when each SSE event is parsed, then every event is valid JSON with a `type` field that is one of `chunk`, `action`, `done`, or `error`.

3. Given a successful streaming response, when the `done` event is received, then it contains a `message_id` field that is a valid UUID string.

4. Given a successful streaming response, when the background tasks complete, then both a `user` message and an `assistant` message exist in the `messages` table with the correct `conversation_id`, `user_id`, `role`, and `content`.

5. Given a successful streaming response, when the background tasks complete, then `conversations.last_message_at` is updated to approximately the current time.

6. Given a successful streaming response, when the background tasks complete, then `user_activity.last_chat_at` is updated to approximately the current time.

7. Given a successful streaming response, when the background tasks complete, then `mem0.add()` is called with the user message content, assistant response content, the profile's `mem0_user_id`, and the character's `mem0_agent_id`.

8. Given a character whose conversation has existing messages, when `POST /characters/:id/messages` is called, then the Claude API receives the last 50 messages from the conversation as context.

9. Given a character with Mem0 memories, when `POST /characters/:id/messages` is called, then the system prompt sent to Claude includes the Mem0 memory content (up to 10 memories).

10. Given the system prompt sent to Claude, when a developer inspects the prompt, then it contains the character's `system_prompt` (Block 1), Mem0 memories (Block 2), and current date/time/timezone (Block 3).

11. Given an assistant response that includes an intent to set an alarm (e.g., "I've set an alarm for 7 AM tomorrow"), when the intent extraction completes, then the SSE stream includes an `action` event with `action: "SET_ALARM"` and a valid payload before the `done` event.

12. Given an assistant response with no device action intent, when the intent extraction completes, then the SSE stream contains only `chunk` events and a `done` event (no `action` event).

13. Given the Claude API failing mid-stream, when the error occurs, then the SSE stream emits an `error` event with a user-friendly message and no messages are persisted to the database.

14. Given Mem0 search failing during context gathering, when the error occurs, then the stream proceeds normally with an empty memory block and the error is logged.

15. Given the Mem0 add call failing in the background task, when the error occurs, then the error is logged but the user and assistant messages are still persisted to the database.

16. Given a character belonging to another user, when the client sends `POST /characters/:id/messages`, then the response is HTTP 403 with detail "Character does not belong to user".

17. Given a non-existent or inactive character ID, when the client sends `POST /characters/:id/messages`, then the response is HTTP 404 with detail "Character not found".

18. Given a message with content that is only whitespace, when the client sends `POST /characters/:id/messages`, then the response is HTTP 422 with a validation error.

19. Given an authenticated user with a character that has messages, when the client sends `GET /api/v1/characters/:id/messages`, then the response is HTTP 200 with `items` containing messages in reverse chronological order, plus `next_cursor` and `has_more` fields.

20. Given a `cursor` query parameter, when `GET /characters/:id/messages` is called, then only messages with `created_at` strictly less than the cursor are returned.

21. Given more messages exist than the requested `limit`, when `GET /characters/:id/messages` is called, then `has_more` is `true` and `next_cursor` contains the `created_at` of the last returned message.

22. Given all messages fit within the `limit`, when `GET /characters/:id/messages` is called, then `has_more` is `false` and `next_cursor` is `null`.

23. Given an empty conversation, when `GET /characters/:id/messages` is called, then the response is HTTP 200 with `{"items": [], "next_cursor": null, "has_more": false}`.

24. Given the backend test suite, when a developer runs `pytest` on the new test files, then all tests pass with exit code 0.

25. Given the route handler code, when a developer inspects it, then all business logic is in `ChatService` and route handlers only call service methods, validate input (Pydantic), and return responses.

---

## 9. Design Decisions and Rationale

### Why SSE instead of WebSocket

SSE (Server-Sent Events) is a simpler protocol for server-to-client streaming. Ember's chat is request-response (user sends a message, server streams a reply) -- not bidirectional real-time communication. SSE works over standard HTTP, is easier to test, and is well-supported by FastAPI's `StreamingResponse`. WebSocket would add complexity with no benefit for this use case. Real-time voice calls (Phase 5+) will use WebSocket via LiveKit.

### Why background tasks for persistence instead of inline writes

Writing messages to the database before or during the stream would add latency to the first-token time. Per `docs/08-guvenlik-performans.md`, the target TTFT (time to first token) is under 1 second. By deferring persistence to background tasks, the stream starts as soon as Claude begins generating tokens. The trade-off is that messages may be lost if the background task fails, but this is acceptable for Phase 1 -- the user already saw the response in real-time.

### Why 50 messages of context instead of 20

`docs/05-ai-bellek.md` mentions 20 messages for cost optimization, but `CLAUDE.md` specifies "last 30-50 messages." This spec uses 50 as a configurable upper bound via `settings.max_context_messages`. The cost difference is manageable for Phase 1, and more context produces better conversation quality. This can be tuned down later based on token usage data.

### Why a separate Haiku call for intent extraction

As detailed in Section 4, separating intent extraction from conversation keeps the main response natural and allows independent evolution of the intent system. Haiku is significantly cheaper than Sonnet for this structured extraction task. The latency cost (~200-400ms) is acceptable because it happens after the full response is streamed -- the user is already reading the response while intent extraction runs.

### Why the user message ID is not returned in the SSE stream

The mobile client generates a local UUID for the user message bubble immediately when the user taps "send." The actual DB-generated UUID for the user message is not needed by the client. Only the assistant message ID is useful (for correlating the streamed response with the persisted message for features like reply, copy, etc.). This keeps the SSE protocol simpler.

### Why auto-create conversation if missing

Although P01-05 creates a conversation when a character is created, defensive programming handles the edge case where the conversation row is missing (e.g., manual DB edit, data migration issue). Rather than returning a 500 error for what should be an invisible implementation detail, the endpoint auto-creates the missing conversation.

### Why metadata is stored on the assistant message

When an intent action is detected, the `metadata` JSONB column on the assistant message stores the full action payload. This allows the mobile client to re-display the action (e.g., "Alarm set for 7:00 AM") when loading message history, without needing to re-run intent extraction.

### Why Mem0 searches are parallel but not with DB query

Actually, all three fetches (global Mem0, character Mem0, DB last 50 messages) ARE parallel via a single `asyncio.gather()`. This is the approach specified in the issue description and follows the pattern from `docs/05-ai-bellek.md`.

---

## 10. Notes for Developers

### For backend-dev

- **Start with schemas** (`app/schemas/chat.py`), then the service (`app/services/chat_service.py`), then the route (`app/routes/chat.py`), then wire up in `main.py`.

- **StreamingResponse usage**: The POST endpoint returns `StreamingResponse(generator(), media_type="text/event-stream")`. FastAPI handles the chunked transfer encoding. Set headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no` (prevents nginx from buffering SSE).

- **Router registration path**: Register the chat router with `prefix="/api/v1/characters"`. The route decorators use relative paths: `@router.post("/{character_id}/messages")` and `@router.get("/{character_id}/messages")`. This does NOT conflict with the characters router (which handles `""` and `"/{character_id}"`) because FastAPI matches by full path pattern.

- **Anthropic streaming API**: Use `client.messages.stream()` (async context manager), not `client.messages.create(stream=True)`. The `.stream()` method provides a cleaner async iterator via `stream.text_stream` and a `get_final_message()` method to retrieve the complete response object.

- **Mem0 SDK is synchronous**: The `mem0ai` package's `MemoryClient` is blocking. Wrap all calls in `asyncio.to_thread()`. Do NOT call Mem0 methods directly in async functions.

- **Background task session management**: Do NOT use the request-scoped `db` session in background tasks. Create a new session via `AsyncSessionLocal()` inside the background task. The request session is closed when the StreamingResponse finishes.

- **SSE format**: Each event is `data: {json}\n\n` (note: TWO newlines). Do not add event type headers (`event:`) -- we use the `type` field inside the JSON payload instead. This simplifies client parsing.

- **Config change**: Add `max_context_messages: int = 50` to `Settings`. Use `settings.max_context_messages` in the service for the message history query limit.

- **Prompt caching**: Per `docs/05-ai-bellek.md`, Block 1 (character system prompt) can use Anthropic's `cache_control` parameter. For Phase 1, this is optional but recommended. To enable it, pass the system prompt as a list of content blocks with `cache_control: {"type": "ephemeral"}` on the first block.

- **Error handling during streaming**: Once the first SSE event has been sent, you cannot change the HTTP status code. If Claude fails mid-stream, emit `data: {"type":"error","message":"..."}\n\n` and return from the generator. The HTTP status remains 200.

- **Intent extraction confidence**: The Haiku prompt asks for structured JSON. If the response cannot be parsed as JSON or the action is not in the supported set, treat it as "no intent" and skip the action event. Log the raw Haiku response for debugging.

- **Message ordering in DB query for context**: The DB query fetches the last 50 messages in DESC order. You MUST reverse them to chronological order before sending to Claude (Claude expects messages in chronological order).

### For backend-tester

- **SSE testing**: Use `httpx.AsyncClient` with `stream=True`. Parse SSE events line by line. The test client must consume the entire stream before asserting.

- **Mock all external services**: Claude (both Sonnet streaming and Haiku non-streaming), Mem0 (search and add), and the background task database session.

- **Test SSE event ordering**: The correct order is: N chunk events, 0 or 1 action event, exactly 1 done event. Verify this ordering in integration tests.

- **Test background task execution**: Use `asyncio.create_task` with a mock. Verify that the task was created and that its arguments are correct. For deeper testing, run the background task function directly with mocked dependencies.

- **Test Mem0 failure resilience**: Mock Mem0 search to raise an exception. Verify that the stream still works with empty memories.

- **Test cursor pagination**: Seed the database with N messages with known `created_at` values. Verify that cursor correctly filters, that `has_more` is accurate, and that `next_cursor` matches the last item.
