# Memory Endpoints

> Exposes four REST endpoints that let users view and delete Mem0 memories -- both per-character and global -- giving users full transparency and control over what the AI remembers about them.

**Status**: Released
**Added in**: Phase 1 (P01-08)
**Platforms**: Backend
**GitHub Issue**: #10

---

## Overview

Ember stores long-term facts about users in Mem0 so that characters can recall personal details across conversations. Memory Endpoints (P01-08) is the backend feature that lets users see what has been stored and remove anything they want deleted. It implements the "Memory Transparency Principles" described in `docs/05-ai-bellek.md`: users can always see what a character knows, and they can delete individual facts or clear an entire character's memory.

The feature provides four endpoints. Three are character-scoped (list memories, delete a single memory, delete all memories) and one is global (list memories that are visible to all characters). All operations are pure Mem0 SDK calls. The only database interaction is looking up a character record to verify ownership. No database rows are created, updated, or deleted by this feature.

Memory creation is NOT part of this feature. Memories are created automatically during the chat flow (P01-06, `_persist_exchange`). These endpoints are read-and-delete only.

---

## Architecture

### How It Works (Data Flow)

**Listing character memories** (the most common operation):

1. The mobile client sends `GET /api/v1/characters/{character_id}/memories` with a JWT in the `Authorization` header.
2. The route handler resolves the authenticated user via the `get_current_user` dependency, which provides the `Profile` with `id` and `mem0_user_id`.
3. `MemoryService.get_character_memories()` queries PostgreSQL for the character: `SELECT * FROM characters WHERE id = $id AND is_active = true`.
4. If the character is not found or inactive, the service raises HTTP 404. If `character.user_id` does not match the JWT user, it raises HTTP 403.
5. The service instantiates a fresh `MemoryClient` and calls `client.get_all(user_id=profile.mem0_user_id, agent_id=character.mem0_agent_id)` wrapped in `asyncio.to_thread()` (because the Mem0 Python SDK is synchronous).
6. The raw Mem0 response (a list of dicts) is mapped to `MemoryItem` schema objects, extracting `id`, `memory`, and optionally `created_at`.
7. The route handler wraps the items in a `MemoryListResponse` and returns HTTP 200.

**Deleting a single memory** follows the same ownership-check flow, then calls `client.delete(memory_id)`. If Mem0 reports "not found," the service treats it as success (idempotent delete) and returns HTTP 204.

**Deleting all character memories** calls `client.delete_all(user_id=..., agent_id=...)` after ownership verification, returning HTTP 204.

**Listing global memories** skips the character lookup entirely. It calls `client.get_all(user_id=mem0_user_id)` without an `agent_id`, returning only memories that were stored without character scope (the "General Friend" memories such as name, profession, and goals).

### Mem0 Memory Isolation

- **Character-scoped agent_id format**: `{template}_{user_id}` (e.g., `emma_usr_abc123`). Stored in the `characters.mem0_agent_id` column.
- **Global memories**: Stored without an `agent_id`. Retrieved by calling `get_all(user_id=...)` with no `agent_id` parameter.
- **User-scoped user_id**: Stored in the `profiles.mem0_user_id` column. Ensures one user cannot access another user's memories.

### Database Tables Involved

| Table | Operation | Notes |
|-------|-----------|-------|
| `characters` | SELECT | Lookup by `id` + `is_active = true`, then ownership check (`user_id = $jwt_user_id`) |
| `profiles` | (none directly) | `mem0_user_id` is provided by the `get_current_user` dependency |

No INSERT, UPDATE, or DELETE operations are performed on any database table.

### Service Architecture

All business logic lives in `MemoryService`, a class that receives an `AsyncSession` in its constructor. Route handlers instantiate the service and delegate to it, keeping the route layer thin.

The service has two private helpers:
- `_get_owned_character()` -- looks up an active character and verifies ownership. Raises HTTP 404 or 403 on failure.
- `_map_memories()` -- static method that converts Mem0 SDK response dicts into `MemoryItem` Pydantic models.

A fresh `MemoryClient` instance is created per method call (not shared across calls). This avoids shared state and keeps the service testable.

---

## API Reference

All endpoints are under the `/api/v1` prefix. All require `Authorization: Bearer <jwt>`.

### GET /api/v1/characters/{character_id}/memories

List all Mem0 memories for a specific character.

**Auth**: Bearer JWT required
**Success Status**: `200 OK`

**Path Parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `character_id` | UUID | Character ID |

**Response Body (200 OK)**:

```json
{
  "memories": [
    {
      "id": "mem0-assigned-uuid-string",
      "memory": "Confuses 'affect' vs 'effect'",
      "created_at": "2026-02-20T10:00:00Z"
    },
    {
      "id": "mem0-assigned-uuid-string-2",
      "memory": "Prefers short, direct corrections",
      "created_at": "2026-02-18T15:30:00Z"
    }
  ]
}
```

**Response Fields**:

| Field | Type | Notes |
|-------|------|-------|
| `memories` | array | All memories for this character. May be empty `[]`. |
| `memories[].id` | string | Mem0-assigned memory ID. Pass this to the single-delete endpoint. |
| `memories[].memory` | string | The memory content text. |
| `memories[].created_at` | string (ISO 8601) or null | When the memory was created. Null if Mem0 does not return a timestamp. |

**Notes**:
- Not paginated. Mem0's `get_all()` returns all memories for the user+agent pair. Expected volume is dozens to low hundreds per character.
- An empty `memories` array is returned when the character has no stored memories (not a 404).

**Error Responses**:

| Status | Detail | When |
|--------|--------|------|
| 401 | `"Invalid or expired token"` | Missing or invalid JWT |
| 403 | `"Character does not belong to user"` | Ownership mismatch |
| 404 | `"Character not found"` | Non-existent or inactive character |
| 503 | `"Memory service unavailable"` | Mem0 API error |

---

### DELETE /api/v1/characters/{character_id}/memories/{memory_id}

Delete a single memory from Mem0.

**Auth**: Bearer JWT required
**Success Status**: `204 No Content`

**Path Parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `character_id` | UUID | Character ID (used for ownership verification) |
| `memory_id` | string | Mem0-assigned memory ID (treated as opaque string, not UUID) |

**Response**: Empty body.

**Notes**:
- **Idempotent**: Returns 204 even if the `memory_id` does not exist in Mem0 (the memory is effectively already gone).
- The `character_id` is used only for ownership verification. The actual Mem0 deletion uses only `memory_id`.
- The service detects Mem0 "not found" errors by checking for "not found" or "404" in the exception message string (case-insensitive).

**Error Responses**:

| Status | Detail | When |
|--------|--------|------|
| 401 | `"Invalid or expired token"` | Missing or invalid JWT |
| 403 | `"Character does not belong to user"` | Ownership mismatch |
| 404 | `"Character not found"` | Non-existent or inactive character |
| 503 | `"Memory service unavailable"` | Mem0 API error (non "not found") |

---

### DELETE /api/v1/characters/{character_id}/memories

Delete ALL memories for a specific character from Mem0.

**Auth**: Bearer JWT required
**Success Status**: `204 No Content`

**Path Parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `character_id` | UUID | Character ID |

**Response**: Empty body.

**Notes**:
- Calls `client.delete_all(user_id=..., agent_id=...)`, scoped to the character's `mem0_agent_id`.
- If the character has no memories, the call succeeds silently and returns 204.
- Does NOT delete global (agent-less) memories. Only character-scoped memories are affected.

**Error Responses**:

| Status | Detail | When |
|--------|--------|------|
| 401 | `"Invalid or expired token"` | Missing or invalid JWT |
| 403 | `"Character does not belong to user"` | Ownership mismatch |
| 404 | `"Character not found"` | Non-existent or inactive character |
| 503 | `"Memory service unavailable"` | Mem0 API error |

---

### GET /api/v1/memories

List global (non-character-scoped) memories. These are the "General Friend" memories visible to all characters.

**Auth**: Bearer JWT required
**Success Status**: `200 OK`

**Response Body (200 OK)**:

```json
{
  "memories": [
    {
      "id": "mem0-assigned-uuid-string",
      "memory": "Works as a freelance software engineer",
      "created_at": "2026-02-15T08:00:00Z"
    },
    {
      "id": "mem0-assigned-uuid-string-2",
      "memory": "Prefers morning workouts",
      "created_at": "2026-02-14T09:00:00Z"
    }
  ]
}
```

Response shape is identical to `GET /characters/{character_id}/memories`.

**Notes**:
- Calls `client.get_all(user_id=mem0_user_id)` WITHOUT an `agent_id`. Returns only memories stored without character scope.
- Per `docs/05-ai-bellek.md`, global memories are basic user information visible to all characters (name, profession, goals, etc.).
- Not paginated, same rationale as the character-scoped endpoint.
- No character lookup or ownership check is performed. Only the authenticated user's `mem0_user_id` is needed.

**Error Responses**:

| Status | Detail | When |
|--------|--------|------|
| 401 | `"Invalid or expired token"` | Missing or invalid JWT |
| 503 | `"Memory service unavailable"` | Mem0 API error |

---

## Configuration

No new configuration values were introduced for this feature. All required settings already exist from prior features.

| Setting | Source | Description |
|---------|--------|-------------|
| `mem0_api_key` | `app/config.py` (AWS Secrets Manager) | API key for Mem0.ai cloud. Used by `MemoryClient`. |

The `mem0ai` Python package was already a dependency (installed for P01-06 chat-streaming). No new packages were added.

---

## Files

| File | Role |
|------|------|
| `backend/app/routes/memories.py` | Route handlers. Defines `global_router` (registered at `/api/v1`) and `character_router` (registered at `/api/v1/characters`). Four route functions, all delegating to `MemoryService`. |
| `backend/app/services/memory_service.py` | `MemoryService` class with 4 public methods (`get_character_memories`, `delete_character_memory`, `delete_all_character_memories`, `get_global_memories`) and 2 private helpers (`_get_owned_character`, `_map_memories`). |
| `backend/app/schemas/memory.py` | `MemoryItem` and `MemoryListResponse` Pydantic models. No request schemas (all endpoints use path parameters only). |
| `backend/app/main.py` | Modified to import `memories` and register both routers. |

### Router Registration Pattern

The memory module defines two routers because the global endpoint (`GET /memories`) and character-scoped endpoints live under different URL prefixes:

```python
# In main.py:
app.include_router(memories.global_router, prefix="/api/v1", tags=["memories"])
app.include_router(memories.character_router, prefix="/api/v1/characters", tags=["memories"])
```

The two DELETE routes on the character router (`/{character_id}/memories` and `/{character_id}/memories/{memory_id}`) are distinct path patterns and FastAPI handles them without ambiguity.

---

## Testing

### Coverage Summary

| File | Tests | Line Coverage | Branch Coverage |
|------|-------|---------------|-----------------|
| `test_memory_routes.py` | 22 (spec scenarios R1-R22) | 100% | 100% |
| `test_memory_routes_extended.py` | 22 (edge cases) | -- | -- |
| `test_memory_service.py` | 16 (spec scenarios S1-S16) | 100% | 100% |
| `test_memory_service_extended.py` | 28 (edge cases) | -- | -- |
| `test_memory_schemas.py` | 6 (spec scenarios T1-T4 + extras) | 100% | 100% |
| `test_memory_schemas_extended.py` | 16 (edge cases) | -- | -- |
| **Total** | **110 passed, 0 failed** | **100%** (routes, service, schemas) | **100%** |

Full backend suite after this feature: 1062 passed, 0 failed, 0 skipped.

### Key Test Scenarios

**Route tests** cover all four endpoints across auth failure (401), ownership mismatch (403), character not found (404), Mem0 failure (503), empty results, and successful operations.

**Service tests** verify that Mem0 SDK methods are called with the correct parameters, that `asyncio.to_thread()` wrapping is in place, that ownership checks happen before Mem0 calls, and that the idempotent delete handles both "not found" and "404" in exception messages.

**Schema tests** verify Pydantic serialization/deserialization, optional `created_at` handling, JSON round-trips, and validation of required fields.

### Running Tests

Memory tests only:

```bash
cd backend && python -m pytest tests/test_memory_schemas.py tests/test_memory_service.py tests/test_memory_routes.py -v
```

All memory tests (including extended edge cases):

```bash
cd backend && python -m pytest tests/test_memory_schemas.py tests/test_memory_schemas_extended.py tests/test_memory_service.py tests/test_memory_service_extended.py tests/test_memory_routes.py tests/test_memory_routes_extended.py -v
```

Full backend suite:

```bash
cd backend && python -m pytest tests/ -v --ignore=tests/test_migration.py
```

---

## Known Limitations

- **No pagination on memory list endpoints**: Mem0's `get_all()` does not natively support cursor-based pagination. The number of memories per user-character pair is expected to be in the dozens to low hundreds. If memory counts grow significantly, pagination can be added by fetching all and slicing, or by using the Mem0 REST API's `page` and `page_size` parameters.
- **No memory creation or update endpoints**: Memories are created automatically during the chat flow. Users cannot manually add or edit memories through the API.
- **No mobile UI**: These endpoints provide the backend for future mobile memory display screens. No iOS or Android UI was built as part of this feature.
- **No memory export**: JSON export of memories is a separate future feature.
- **Mem0 "not found" detection is string-based**: The idempotent single-delete checks for "not found" or "404" in the exception message string. If the Mem0 SDK changes its error format, this detection may need updating.
- **Global memory isolation assumption**: `client.get_all(user_id=X)` without `agent_id` is assumed to return only agent-less memories. If the Mem0 SDK version changes this behavior, client-side filtering may be needed.

---

## Design Decisions

### Why `memory` field name instead of `content`

The Mem0 SDK returns a dict with a `memory` key. Using the same name avoids confusion and makes it clear this is Mem0-native data. While `docs/04-veri-api.md` uses `content` in some examples, that refers to database-stored message content, not Mem0 memories.

### Why character ownership is checked on single-memory delete

The `memory_id` alone is sufficient for Mem0 to delete a memory. However, without the ownership check, a user could delete another user's memories by guessing memory IDs. The `character_id` path parameter and ownership verification provide defense-in-depth.

### Why "not found" on single delete is treated as success

The single-memory delete is idempotent. If the user taps "delete" twice or the memory was already removed, the user's intent (memory should not exist) is satisfied. Returning 404 would confuse clients and require error handling for a case that is not an error.

### Why two routers in one module

The global endpoint and character-scoped endpoints share the same service class, schemas, and conceptual domain. Two routers in one module (`memories.py`) is a standard FastAPI pattern for different prefix registrations of related functionality. Splitting into two files would scatter related code.

### Why `memory_id` is `str` not `uuid.UUID`

Mem0's internal IDs are treated as opaque strings. While they currently resemble UUIDs, enforcing UUID format on an external service's identifiers would be fragile and could break if Mem0 changes its ID format.

### Why a fresh MemoryClient per call

Following the established pattern in `chat_service.py`, the `MemoryClient` is instantiated inside each method (not as a class attribute). This avoids shared state issues across concurrent requests and keeps the service easily testable.

---

## Extending This Feature

**Adding memory search**: To add a search/filter endpoint, create a new route `GET /api/v1/characters/{character_id}/memories/search?q=...` on the `character_router`. Use `client.search(query=q, user_id=..., agent_id=...)` in the service, wrapped in `asyncio.to_thread()`.

**Adding pagination**: If memory lists grow large, add `page` and `page_size` query parameters to the GET endpoints. Fetch all memories from Mem0, then slice the list server-side. Alternatively, use the Mem0 REST API directly (instead of the Python SDK) which supports native pagination.

**Adding memory export**: Create a new endpoint `GET /api/v1/memories/export` that fetches all memories (global + per-character) and returns them as a JSON download. This would call `get_all()` for the user and for each of their characters.

**Building mobile memory screens**: The iOS and Android apps will consume these endpoints to display memory lists and provide delete actions. Use the `MemoryItem.id` field as the identifier for single-delete operations.

---

## Related Documentation

- [AI Memory System](../05-ai-bellek.md) -- Mem0 integration design and memory categories
- [Chat Streaming](./chat-streaming.md) -- P01-06, where memories are created during `_persist_exchange`
- [Character CRUD](./character-crud.md) -- character model with `mem0_agent_id` field
- [Database Schema and API Endpoints](../04-veri-api.md) -- character and profile table definitions
- [Cognito Auth Middleware](./cognito-auth-middleware.md) -- JWT verification and `get_current_user` dependency
