# Feature Spec: doc-code-sync (P1.5-07)

**Issue**: #89
**Layer**: backend
**Dependencies**: P01-10 (media-upload)
**Date**: 2026-03-13

---

## 1. Overview

This feature resolves all documentation-code contradictions that have accumulated during Phase 1 development. As the codebase evolved, several docs fell out of sync with the actual implementation. This spec catalogs every contradiction found, declares the authoritative source (code wins when it is already working and tested), and prescribes the exact doc updates needed. It also defines a CI check script to prevent future drift.

No code logic changes are required. This is a docs-only + CI tooling feature.

---

## 2. Contradiction Catalog

Below is the complete list of contradictions found between documentation and the working codebase. Each entry states:

- **ID**: Sequential identifier for tracking
- **Location**: Which doc and which code file
- **What the doc says** vs **what the code does**
- **Verdict**: Which is correct
- **Fix**: Exact change required

---

### C-01: User model vs Profile model naming

**Doc locations**: `docs/standards/backend.md` (sections 2, 5, 15), `docs/standards/testing.md` (section 3)
**Code**: `backend/app/models/profile.py` defines `class Profile`, `__tablename__ = "profiles"`

**What docs say**:
- `docs/standards/backend.md` section 2 references `from app.models.user import User` (line 142)
- `docs/standards/backend.md` section 5 references `from app.models.profile import Profile` (line 386) -- correct here
- `docs/standards/backend.md` section 5 route example uses `current_user: User` type hint (line 151)
- `docs/standards/backend.md` section 15 conftest references `from app.models.user import User` and `User(id=..., cognito_sub=..., email=...)` (lines 963, 988)
- `docs/standards/testing.md` section 3 conftest references `from app.models.user import User` and constructs `User(id=..., cognito_sub=..., email=...)` (lines 116, 142-146)
- `docs/04-veri-api.md` correctly uses table name `profiles`

**What code does**: The model class is `Profile` in `app.models.profile`. There is no `app/models/user.py` file. There is no `User` class anywhere. The `Profile` model does not have a `cognito_sub` column -- the `id` column IS the Cognito sub UUID.

**Verdict**: Code wins. The model has always been `Profile`.

**Fix**:
1. In `docs/standards/backend.md`:
   - Section 2 route example: change `from app.models.user import User` to `from app.models.profile import Profile`
   - Section 2 route example: change `current_user: User` to `current_user: Profile`
   - Section 5 route example: change `current_user: User` to `current_user: Profile`
   - Section 13 usage comment: change `current_user: User` to `current_user: Profile`
   - Section 15 conftest: change `from app.models.user import User` to `from app.models.profile import Profile`
   - Section 15 conftest: change `fake_user = User(id=..., cognito_sub=..., email=...)` to `fake_user = Profile(id=..., email=..., name=..., mem0_user_id=...)`
2. In `docs/standards/testing.md`:
   - Section 3 conftest: change `from app.models.user import User` to `from app.models.profile import Profile`
   - Section 3 fake_user fixture: change `User(id=..., cognito_sub=..., email=...)` to `Profile(id=..., email=..., name=..., mem0_user_id=...)`

---

### C-02: Profile model has no `cognito_sub` column

**Doc locations**: `docs/standards/backend.md` section 15, `docs/standards/testing.md` section 3
**Code**: `backend/app/models/profile.py` -- the `id` column is the Cognito sub UUID directly

**What docs say**: Test fixtures construct `User(id="test-user-id", cognito_sub="test-sub", email="test@ember.ai")` implying a separate `cognito_sub` column.

**What code does**: `Profile.id` IS the Cognito sub UUID. There is no `cognito_sub` column. The `dependencies.py` file does `Profile.id == cognito_sub` (line 55).

**Verdict**: Code wins. The `id` is the Cognito sub.

**Fix**: Already covered by C-01 fixture updates. The test fixture should construct `Profile(id=uuid.UUID("..."), email="test@ember.ai", name="Test User", mem0_user_id="test-mem0-id")`.

---

### C-03: AsyncMemoryClient vs sync MemoryClient

**Doc locations**: `docs/standards/backend.md` section 9
**Code**: `backend/app/services/memory_service.py`, `backend/app/services/chat_service.py`

**What docs say**: Section 9 shows `from mem0 import AsyncMemoryClient` and uses `await self.client.add(...)`, `await self.client.search(...)`, `await self.client.get_all(...)` directly. The note at line 648 says "Prefer `AsyncMemoryClient` if available. The sync `MemoryClient` with `asyncio.to_thread()` is acceptable as fallback."

**What code does**: Both `memory_service.py` and `chat_service.py` use `from mem0 import MemoryClient` (sync client) wrapped in `asyncio.to_thread()`. The `AsyncMemoryClient` class does not exist in the mem0 SDK as currently installed.

**Verdict**: Code wins. The sync `MemoryClient` + `asyncio.to_thread()` is the actual working pattern.

**Fix**: In `docs/standards/backend.md` section 9:
1. Change the import from `from mem0 import AsyncMemoryClient` to `from mem0 import MemoryClient`
2. Change all direct await calls to `asyncio.to_thread()` wrapped calls
3. Change the variable type from `AsyncMemoryClient` to `MemoryClient`
4. Update the note to say "The mem0 SDK provides a sync `MemoryClient`. All calls must be wrapped in `asyncio.to_thread()` to avoid blocking the event loop."
5. Show the circuit breaker integration pattern since it is now used in all Mem0 calls

---

### C-04: Cognito verification module path

**Doc locations**: `docs/standards/backend.md` section 5
**Code**: `backend/app/core/auth.py`

**What docs say**: `# app/utils/cognito.py` with function `verify_token(token: str) -> dict`

**What code does**: The module is at `app/core/auth.py` with function `verify_cognito_token(token: str) -> dict[str, object]`. It uses a `CognitoJWKSProvider` class with TTL-based caching (10 min), key rotation handling, and issuer validation. The `dependencies.py` imports `from app.core.auth import verify_cognito_token`.

**Verdict**: Code wins.

**Fix**: In `docs/standards/backend.md` section 5:
1. Change the file path comment from `# app/utils/cognito.py` to `# app/core/auth.py`
2. Change the function name from `verify_token` to `verify_cognito_token`
3. Change the return type annotation from `-> dict:` to `-> dict[str, object]:`
4. Update the code example to reflect the `CognitoJWKSProvider` pattern with TTL caching
5. Update the `dependencies.py` example to import from `app.core.auth` instead of `app.utils.cognito`

---

### C-05: Context window size — 20 vs 30-50 messages

**Doc locations**: `CLAUDE.md` line 27, `docs/05-ai-bellek.md` line 125, `docs/standards/common.md` lines 69-73
**Code**: `backend/app/config.py` field `max_context_messages: int = 50`

**What CLAUDE.md says**: "Context window: last 20 messages + Mem0 semantic search results (max 10 memories)."
**What docs/05-ai-bellek.md says**: "Sadece son 20 mesaj Claude'a gonderilir."
**What docs/standards/common.md says**: "Include the last 30-50 messages from the conversation" with example `Context = system_prompt + mem0_memories + last_50_messages + new_user_message`
**What code does**: `settings.max_context_messages = 50`

**Verdict**: Code wins. The value is 50 (configurable). The `common.md` is closest to correct. `CLAUDE.md` and `docs/05-ai-bellek.md` have the stale "20" value.

**Fix**:
1. In `CLAUDE.md` line 27: change "last 20 messages" to "last 50 messages (configurable via `max_context_messages`)"
2. In `docs/05-ai-bellek.md` line 125: change "son 20 mesaj" to "son 50 mesaj (max_context_messages config ile ayarlanabilir)"

---

### C-06: Default pagination limit — 30 vs 20

**Doc locations**: `docs/standards/common.md` line 281, `docs/standards/backend.md` lines 165-166
**Code**: `backend/app/routes/chat.py` line 73

**What common.md says**: "Default `limit`: 30. Maximum `limit`: 100."
**What backend.md says**: Route example uses `limit: int = 30`
**What code does**: `limit: int = Query(default=20, ge=1, le=100)` -- default is 20

**Verdict**: Code wins. 20 is the implemented default.

**Fix**:
1. In `docs/standards/common.md` line 281: change "Default `limit`: 30" to "Default `limit`: 20"
2. In `docs/standards/backend.md` section 2 route example: change `limit: int = 30` to `limit: int = 20`

---

### C-07: Memories router prefix inconsistency

**Doc locations**: `docs/standards/backend.md` section 2 (line 123)
**Code**: `backend/app/main.py` lines 92-93

**What docs say**: `app.include_router(memories.router, prefix="/api/v1", tags=["memories"])`

**What code does**: The memories module exports two routers:
- `app.include_router(memories.global_router, prefix="/api/v1", tags=["memories"])`
- `app.include_router(memories.character_router, prefix="/api/v1/characters", tags=["memories"])`

**Verdict**: Code wins. The dual-router pattern was implemented during the memory-endpoints feature.

**Fix**: In `docs/standards/backend.md` section 2, update the `create_app` example to show both memory routers.

---

### C-08: Error response format inconsistency

**Doc locations**: `docs/04-veri-api.md` lines 464-470, `docs/standards/common.md` lines 317-322
**Code**: `backend/app/main.py`, all route handlers

**What docs/04-veri-api.md says**: Error format is `{"error": {"code": "UNAUTHORIZED", "message": "Invalid or expired token."}}`
**What common.md says**: Error format is `{"detail": "Human-readable error message"}`
**What code does**: Uses FastAPI's default `{"detail": "..."}` format consistently.

**Verdict**: Code and `common.md` win. The `04-veri-api.md` error format is outdated.

**Fix**: In `docs/04-veri-api.md`, update the error format section (lines 462-480) to use `{"detail": "..."}` and remove the nested `error.code` / `error.message` structure.

---

### C-09: Agent name format in commits — inconsistent between docs

**Doc locations**: `CLAUDE.md` lines 190-198, `docs/standards/common.md` lines 127-143

**What CLAUDE.md says**: Agent names are `backend-dev`, `ios-dev`, `android-dev`, etc.
**What common.md says**: Agent names are `backend-agent`, `ios-agent`, `android-agent`, `qa-agent`, etc.

**Verdict**: `CLAUDE.md` wins. The actual pipeline uses `-dev` and `-tester` suffixes as shown in the pipeline agent table.

**Fix**: In `docs/standards/common.md` section 2, change agent name list:
- `backend-agent` to `backend-dev`
- `ios-agent` to `ios-dev`
- `android-agent` to `android-dev`
- `qa-agent` to `backend-tester` / `ios-tester` / `android-tester`
- Update the commit examples to match

---

### C-10: Missing routes/modules in backend.md project structure

**Doc locations**: `docs/standards/backend.md` section 1 (lines 33-81)
**Code**: Actual project structure

**What docs say**: Lists `routes/` as: auth, characters, chat, memories, voice. Services as: character_service, message_service, memory_service, llm_service, voice_service. No mention of `core/`, `middleware/`, or `services/llm/` package. No mention of onboarding, media, profile, or health routes/services.

**What code has**:
- Additional routes: `onboarding.py`, `media.py`, `profile.py`, `health.py`
- Additional services: `auth_service.py`, `onboarding_service.py`, `profile_service.py`, `health_service.py`, `media_service.py`, `chat_service.py`
- `core/` directory: `auth.py`, `rate_limit.py`, `logging.py`, `sentry.py`, `circuit_breaker.py`
- `middleware/` directory: `rate_limit.py`, `request_id.py`
- `services/llm/` package: `provider.py`, `anthropic_provider.py`, `openai_provider.py`, `router.py`, `exceptions.py`
- No `routes/voice.py` or `services/voice_service.py` exist yet (Phase 3)
- The service is named `chat_service.py` not `message_service.py`

**Verdict**: Code wins.

**Fix**: Update `docs/standards/backend.md` section 1 project structure to reflect the actual file tree. Remove voice route/service (add a comment that they are planned for Phase 3). Add all missing entries: core/, middleware/, services/llm/, onboarding, media, profile, health.

---

### C-11: LLM service module structure

**Doc locations**: `docs/standards/backend.md` section 10
**Code**: `backend/app/services/llm/` package

**What docs say**: Shows a single file `app/services/llm_service.py` with `LLMProvider`, `ClaudeProvider`, `OpenAIProvider`, and `get_llm_provider()` all in one file.

**What code does**: The LLM layer is a package at `app/services/llm/` with:
- `provider.py` — `LLMProvider` ABC (with additional `complete_fast` method)
- `anthropic_provider.py` — `AnthropicProvider`
- `openai_provider.py` — `OpenAIProvider`
- `router.py` — `LLMRouter` class and `get_llm_router()` singleton
- `exceptions.py` — `LLMProviderError`

The class names differ: `ClaudeProvider` (docs) vs `AnthropicProvider` (code), `get_llm_provider` (docs) vs `get_llm_router` (code). The `LLMProvider` ABC in code has a `complete_fast()` method not shown in docs.

**Verdict**: Code wins.

**Fix**: Update `docs/standards/backend.md` section 10:
1. Change file path from `app/services/llm_service.py` to package `app/services/llm/`
2. Rename `ClaudeProvider` to `AnthropicProvider`
3. Rename `get_llm_provider()` to `get_llm_router()` returning `LLMRouter`
4. Add `complete_fast()` to the `LLMProvider` ABC
5. Update the status note -- LLM abstraction is now implemented (not planned for P1.5-05)

---

### C-12: characters list response field name

**Doc locations**: `docs/04-veri-api.md` lines 215-227
**Code**: `backend/app/schemas/character.py` lines 115-118

**What docs say**: Response wraps list in `"characters"` key: `{"characters": [...]}`
**What code does**: Same -- `CharacterListResponse(characters=...)` -- this is consistent.

**Verdict**: No contradiction. Both match.

---

### C-13: Memory response field name — `content` vs `memory`

**Doc locations**: `docs/04-veri-api.md` lines 276-286
**Code**: `backend/app/schemas/memory.py`

**What docs say**: Memory items have field `"content"`: `{"id": "...", "content": "Confuses 'affect' vs 'effect'", "created_at": "..."}`
**What code does**: Memory items have field `"memory"`: `MemoryItem(id=..., memory=..., created_at=...)`

**Verdict**: Code wins. The Mem0 SDK returns a `memory` field, and the schema matches that.

**Fix**: In `docs/04-veri-api.md`, update the memory response examples to use `"memory"` instead of `"content"` as the field name.

---

### C-14: Rate limiting — flat 20 req/min vs grouped limits

**Doc locations**: `CLAUDE.md` line 114, `docs/08-guvenlik-performans.md` line 11
**Code**: `backend/app/config.py`, `backend/app/main.py`

**What docs say**: "Rate limiting: 20 req/min per user" (flat single limit)
**What code does**: Grouped rate limits:
- `rate_limit_chat: int = 10` (chat endpoints)
- `rate_limit_write: int = 20` (write endpoints)
- `rate_limit_read: int = 60` (read endpoints)

**Verdict**: Code wins. Grouped limits are more sophisticated and already implemented.

**Fix**:
1. In `CLAUDE.md` line 114: change to "Rate limiting — grouped: 10/min chat, 20/min write, 60/min read (see `config.py`)"
2. In `docs/08-guvenlik-performans.md` line 11: update to reflect grouped limits

---

### C-15: docs/standards/backend.md section 2 — missing routes in create_app example

**Doc locations**: `docs/standards/backend.md` lines 97-129
**Code**: `backend/app/main.py`

**What docs say**: `create_app()` registers: health, auth, characters, chat, memories, voice
**What code does**: `create_app()` registers: health, auth, characters, chat, memories (2 routers), media, onboarding, profile. No voice. Also adds `RateLimitMiddleware`, `RequestIDMiddleware`, and configures CORS from settings.

**Verdict**: Code wins.

**Fix**: Update the `create_app` example in `docs/standards/backend.md` section 2 to match the actual `main.py`. Remove the voice router. Add media, onboarding, profile routers. Add middleware registration. Add CORS from settings.

---

### C-16: Message cursor uses `created_at` ISO string vs composite cursor

**Doc locations**: `docs/04-veri-api.md` line 325, `docs/standards/common.md` lines 279-280
**Code**: `backend/app/services/chat_service.py`

**What docs/04-veri-api.md says**: `GET /characters/:id/messages?cursor={created_at_iso}` -- cursor is a plain ISO timestamp
**What common.md says**: "Cursor encodes `(created_at, id)` as base64 URL-safe JSON."
**What code does**: Composite cursor encoding `{"ts": "<iso>", "id": "<uuid>"}` as base64 URL-safe JSON, matching `common.md`.

**Verdict**: Code and `common.md` win.

**Fix**: In `docs/04-veri-api.md` line 325, change `cursor={created_at_iso}` to `cursor={opaque_base64_cursor}` and add a note: "The cursor is an opaque base64-encoded string returned in `next_cursor`. Do not construct it manually."

---

### C-17: message pagination response — `items` vs docs example

**Doc locations**: `docs/04-veri-api.md` lines 325-328
**Code**: `backend/app/schemas/chat.py` `MessageListResponse`

**What docs say**: The GET messages endpoint description does not show the response shape. It only says "Cursor-based sayfalı mesaj listesi" (page-based message list).

**What code does**: Returns `{"items": [...], "next_cursor": "...", "has_more": true}` matching `common.md` section 6 pagination response shape.

**Verdict**: No contradiction, but `docs/04-veri-api.md` is missing the response schema. Should be added for completeness.

**Fix**: Add the response schema to `docs/04-veri-api.md` under the GET messages endpoint.

---

### C-18: `docs/standards/backend.md` section 12 — missing config fields

**Doc locations**: `docs/standards/backend.md` section 12 (lines 800-856)
**Code**: `backend/app/config.py`

**What docs say**: Settings class with fields: aws_region, aws_secret_name, database_url, cognito_user_pool_id, cognito_app_client_id, llm_provider, claude_model, anthropic_api_key, openai_api_key, openai_model, mem0_api_key, debug.

**What code has (additional fields not in docs)**:
- `app_name`, `app_version`, `log_level`
- `claude_haiku_model`, `openai_fast_model`
- `mem0_circuit_failure_threshold`, `mem0_circuit_recovery_timeout`, `mem0_cache_ttl`, `mem0_retry_queue_max_size`
- `max_context_messages`
- `elevenlabs_api_key`
- `s3_bucket_name`
- `firebase_credentials_json`
- `rate_limit_chat`, `rate_limit_write`, `rate_limit_read`
- `cors_origins`
- `sentry_dsn`, `sentry_environment`, `sentry_traces_sample_rate`
- `health_check_timeout`, `health_check_degraded_threshold`
- `log_request_body`

**Verdict**: Code wins.

**Fix**: Update `docs/standards/backend.md` section 12 Settings class example to include all config fields currently in `config.py`.

---

### C-19: SSE event format — `data: {"delta": chunk}` vs `data: {"type": "chunk", "content": "..."}`

**Doc locations**: `docs/standards/backend.md` section 8 (line 550)
**Code**: `backend/app/schemas/chat.py`, `backend/app/services/chat_service.py`

**What docs say**: SSE events use format `data: {"delta": chunk}` and terminate with `data: [DONE]`
**What code does**: SSE events use typed events:
- `data: {"type": "chunk", "content": "..."}`
- `data: {"type": "action", "action": "...", "payload": {...}}`
- `data: {"type": "done", "message_id": "..."}`
- `data: {"type": "error", "message": "..."}`

No `data: [DONE]` sentinel -- the `done` event is a proper JSON object.

**Verdict**: Code wins. The typed event system is more robust and matches `docs/04-veri-api.md` SSE format.

**Fix**: Update `docs/standards/backend.md` section 8 SSE streaming example to use the typed event models (`ChunkEvent`, `ActionEvent`, `DoneEvent`, `ErrorEvent`). Remove `data: [DONE]` and replace with `data: {"type": "done", "message_id": "..."}`.

---

### C-20: `docs/standards/backend.md` dependency injection — outdated pattern

**Doc locations**: `docs/standards/backend.md` section 13 (lines 866-901)
**Code**: `backend/app/dependencies.py`, `backend/app/routes/chat.py`

**What docs say**: Shows `get_memory_service()` and `get_llm()` as injectable dependencies. Shows route using `memory: MemoryService = Depends(get_memory_service)` and `llm: LLMProvider = Depends(get_llm)`.

**What code does**: MemoryService and ChatService are instantiated directly in route handlers: `service = ChatService(db)`. The LLM router is accessed via `get_llm_router()` singleton, not via DI. `dependencies.py` only exports `get_db` and `get_current_user`.

**Verdict**: Code wins. The DI pattern via `Depends()` for services was not adopted.

**Fix**: Update `docs/standards/backend.md` section 13 to show the actual pattern: services are constructed in route handlers with `service = SomeService(db)`. Remove `get_memory_service()` and `get_llm()` dependency examples.

---

### C-21: `docs/standards/backend.md` testing conftest — outdated pattern

**Doc locations**: `docs/standards/backend.md` section 15, `docs/standards/testing.md` section 3

**What docs say**: Tests use a real PostgreSQL test database (`TEST_DB_URL`), create tables with `Base.metadata.create_all`, and override `get_current_user` with a fake user.

**What code does**: `tests/conftest.py` overrides `get_db` with a `AsyncMock()` (no real database). Does NOT override `get_current_user` in the base conftest -- individual test files handle auth mocking. Uses `os.environ.setdefault("DEBUG", "true")` to prevent AWS Secrets Manager calls.

**Verdict**: Code wins for the base conftest. The docs describe a more complete integration test setup that should be labeled as "integration test pattern" rather than the default.

**Fix**:
1. In `docs/standards/backend.md` section 15 and `docs/standards/testing.md` section 3: update the default conftest example to show the actual mock-based pattern from `tests/conftest.py`
2. Label the real-DB conftest as "integration test conftest pattern" to be used when integration tests are added

---

### C-22: `docs/05-ai-bellek.md` — Mem0 API call signatures

**Doc locations**: `docs/05-ai-bellek.md` lines 9-14, 28-32, 137-145, 152-166
**Code**: `backend/app/services/chat_service.py`, `backend/app/services/memory_service.py`

**What docs say**:
- Uses `mem0.add([messages], {"user_id": mem0_user_id})` dict-style params
- Uses `mem0.search(query, {"filters": {"user_id": user_id}})` dict-style params
- Uses `mem0.search_async(...)` (non-existent method)

**What code does**:
- Uses `client.add(messages, user_id=mem0_user_id, agent_id=agent_id)` keyword-style params
- Uses `client.search(query, user_id=mem0_user_id, agent_id=agent_id, limit=limit)` keyword-style params
- Uses sync `MemoryClient` wrapped in `asyncio.to_thread()` -- no `search_async` method

**Verdict**: Code wins.

**Fix**: Update `docs/05-ai-bellek.md` memory API examples to use the actual keyword-argument syntax of the `MemoryClient`. Replace `mem0.search_async()` with `asyncio.to_thread(client.search, ...)`.

---

### C-23: GET /characters response — missing `last_conversation_at` vs `last_message_at`

**Doc locations**: `docs/04-veri-api.md` lines 223
**Code**: `backend/app/schemas/character.py` `CharacterListItem`

**What docs say**: Character list items have `"last_conversation_at": "2026-02-23T14:30:00Z"`
**What code does**: Character list items have `last_message_at: datetime | None`

**Verdict**: Code wins. The field name in the schema is `last_message_at`, matching the `conversations.last_message_at` column.

**Fix**: In `docs/04-veri-api.md`, change `last_conversation_at` to `last_message_at`.

---

### C-24: POST /characters/:id/messages — doc shows `modality` field, code uses `media_url`

**Doc locations**: `docs/standards/backend.md` section 4 Pydantic example (lines 285-293)
**Code**: `backend/app/schemas/chat.py` `SendMessageRequest`

**What docs say**: `MessageRequest` has `content` and `modality: Literal["text", "voice"] = "text"`
**What code does**: `SendMessageRequest` has `content` and `media_url: str | None`

**Verdict**: Code wins. The `modality` field was replaced by `media_url` during implementation.

**Fix**: Update `docs/standards/backend.md` section 4 Pydantic example to show the actual `SendMessageRequest` with `media_url` instead of `modality`.

---

### C-25: POST /characters/:id/messages response — doc says SSE but missing SSE event schema

**Doc locations**: `docs/04-veri-api.md` lines 302-322
**Code**: `backend/app/schemas/chat.py`

**What docs say**: Shows SSE events with `type` field: chunk, action, done. This matches code.
**What code does**: Additionally defines an `ErrorEvent` type not in docs.

**Verdict**: Code wins.

**Fix**: Add `error` event type to `docs/04-veri-api.md` SSE event documentation: `data: {"type": "error", "message": "..."}`

---

### C-26: `.env.example` missing fields

**Doc locations**: `docs/standards/common.md` lines 229-239
**Code**: `backend/app/config.py`

**What docs say**: `.env.example` lists: DATABASE_URL, ANTHROPIC_API_KEY, OPENAI_API_KEY, MEM0_API_KEY, ELEVENLABS_API_KEY, COGNITO_USER_POOL_ID, COGNITO_APP_CLIENT_ID, AWS_REGION

**What code needs**: All the above plus: LLM_PROVIDER, CLAUDE_MODEL, CLAUDE_HAIKU_MODEL, OPENAI_MODEL, OPENAI_FAST_MODEL, S3_BUCKET_NAME, FIREBASE_CREDENTIALS_JSON, RATE_LIMIT_CHAT, RATE_LIMIT_WRITE, RATE_LIMIT_READ, CORS_ORIGINS, SENTRY_DSN, MAX_CONTEXT_MESSAGES, DEBUG, LOG_LEVEL, and circuit breaker settings.

**Verdict**: Doc is incomplete.

**Fix**: Update `docs/standards/common.md` `.env.example` to include all config fields.

---

### C-27: MessageItem response schema — missing `conversation_id` field

**Doc locations**: `docs/standards/backend.md` section 4 (lines 298-310)
**Code**: `backend/app/schemas/chat.py` `MessageItem`

**What docs say**: `MessageResponse` has: `id`, `conversation_id`, `role`, `content`, `created_at`
**What code does**: `MessageItem` has: `id`, `role`, `content`, `media_url`, `metadata`, `created_at` -- no `conversation_id` (by design, since conversations are hidden from users)

**Verdict**: Code wins. The `conversation_id` is intentionally excluded from the API response.

**Fix**: Update `docs/standards/backend.md` section 4 response schema example to match `MessageItem`: remove `conversation_id`, add `media_url` and `metadata`.

---

### C-28: Conversation auto-creation timing

**Doc locations**: `docs/standards/common.md` line 42
**Code**: `backend/app/services/character_service.py`

**What docs say**: "A conversation is created implicitly on the first `POST /characters/:id/messages`."
**What code does**: The conversation is created at character creation time (in `CharacterService.create_character()`), not on first message. The chat service has a defensive `_get_or_create_conversation` as fallback.

**Verdict**: Code wins. Creating at character creation time is cleaner.

**Fix**: In `docs/standards/common.md` line 42: change to "A conversation is auto-created when a character is created."

---

---

## 3. CI Check Script Design

### Purpose

A Python script that runs in CI to detect common doc-code drift patterns. It does not parse natural language in docs but checks for specific, mechanically verifiable assertions.

### Script: `scripts/check_doc_code_sync.py`

### Checks to implement

**Check 1: Model class existence**
- Scan all `from app.models.{x} import {Y}` statements in `docs/standards/backend.md` and `docs/standards/testing.md`
- Verify that the file `backend/app/models/{x}.py` exists and exports class `{Y}`
- FAIL if a referenced model file or class does not exist

**Check 2: Route file existence**
- Scan `docs/standards/backend.md` section 1 project structure for route files listed under `routes/`
- Verify each listed file exists in `backend/app/routes/`
- Verify no actual route file is missing from the doc listing
- FAIL if mismatch

**Check 3: Config field coverage**
- Parse all field names from `backend/app/config.py` `Settings` class
- Parse all field names from the Settings example in `docs/standards/backend.md` section 12
- WARN if a config field in code is not documented
- WARN if a documented field does not exist in code

**Check 4: Service file existence**
- Same as check 2 but for `services/`
- FAIL if mismatch

**Check 5: Mem0 client import check**
- Grep `docs/standards/backend.md` for `AsyncMemoryClient`
- If found, FAIL with message "AsyncMemoryClient does not exist in mem0 SDK -- use MemoryClient + asyncio.to_thread()"

**Check 6: User model reference check**
- Grep all `.md` files in `docs/standards/` for `from app.models.user import`
- If found, FAIL with message "app.models.user does not exist -- the model is Profile in app.models.profile"

**Check 7: Route prefix consistency**
- Parse `backend/app/main.py` for all `include_router(..., prefix=...)` calls
- Parse `docs/standards/backend.md` `create_app` example for the same
- WARN if sets differ

### Exit codes

- 0: All checks pass
- 1: At least one FAIL
- Warnings print to stderr but do not cause failure (exit 0)

### CI integration

Add to `.github/workflows/backend-ci.yml`:
```yaml
- name: Check doc-code sync
  run: python scripts/check_doc_code_sync.py
```

---

## 4. File Manifest

```
Backend:
  CREATE scripts/check_doc_code_sync.py

Docs (modifications):
  MODIFY docs/standards/backend.md
    - C-01: Fix User→Profile references throughout
    - C-03: Fix AsyncMemoryClient→MemoryClient pattern
    - C-04: Fix cognito module path
    - C-06: Fix default pagination limit
    - C-07: Fix memories router registration
    - C-10: Update project structure tree
    - C-11: Update LLM service module structure
    - C-15: Update create_app example
    - C-18: Update Settings class fields
    - C-19: Update SSE event format
    - C-20: Update dependency injection pattern
    - C-21: Update testing conftest pattern
    - C-24: Update Pydantic schema example
    - C-27: Update MessageResponse schema

  MODIFY docs/standards/testing.md
    - C-01: Fix User→Profile references in conftest
    - C-02: Fix cognito_sub column reference

  MODIFY docs/standards/common.md
    - C-09: Fix agent name format
    - C-06: Fix default pagination limit
    - C-26: Update .env.example
    - C-28: Fix conversation auto-creation timing

  MODIFY docs/04-veri-api.md
    - C-08: Fix error response format
    - C-13: Fix memory response field name
    - C-16: Fix cursor format description
    - C-17: Add GET messages response schema
    - C-23: Fix last_conversation_at→last_message_at
    - C-25: Add error event to SSE docs

  MODIFY docs/05-ai-bellek.md
    - C-05: Fix context window 20→50
    - C-22: Fix Mem0 API call signatures

  MODIFY CLAUDE.md
    - C-05: Fix context window 20→50
    - C-14: Fix rate limiting description

  MODIFY .github/workflows/backend-ci.yml
    - Add doc-code sync check step

Shared:
  CREATE shared/feature-specs/doc-code-sync.md (this file)
  CREATE docs/pipeline/doc-code-sync-architect.handoff.md
```

---

## 5. Acceptance Criteria

1. Given `docs/standards/backend.md`, when searching for `from app.models.user`, then zero matches are found.
2. Given `docs/standards/backend.md`, when searching for `AsyncMemoryClient`, then zero matches are found.
3. Given `docs/standards/backend.md` section 5, when reading the cognito module path, then it reads `app/core/auth.py`.
4. Given `docs/standards/backend.md` section 2, when reading the `create_app` example, then it includes media, onboarding, and profile routers and does NOT include a voice router.
5. Given `docs/04-veri-api.md`, when reading the error response format, then it shows `{"detail": "..."}` not `{"error": {"code": "...", "message": "..."}}`.
6. Given `docs/04-veri-api.md`, when reading the memory item response, then the text field is named `memory` not `content`.
7. Given `CLAUDE.md`, when reading the context window description, then it says 50 messages (not 20).
8. Given `CLAUDE.md`, when reading rate limiting, then it describes grouped limits (chat/write/read).
9. Given `docs/standards/common.md`, when reading default pagination limit, then it says 20 (not 30).
10. Given `scripts/check_doc_code_sync.py`, when running against the repo after all fixes, then it exits with code 0.
11. Given `scripts/check_doc_code_sync.py`, when a future developer adds `from app.models.user import User` to `docs/standards/backend.md`, then CI fails.
12. Given `docs/standards/backend.md` section 8, when reading the SSE event format, then it shows typed JSON events (`{"type": "chunk", ...}`) not `{"delta": "..."}` or `[DONE]`.
13. Given `docs/standards/common.md`, when reading agent names for commit format, then they match CLAUDE.md pipeline table names (backend-dev, ios-dev, etc.).
