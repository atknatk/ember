# Feature Spec: P01-08 -- Memory Endpoints

**Feature ID**: P01-08
**Phase**: 1
**Layer**: backend
**GitHub Issue**: #10
**Date**: 2026-02-24
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature exposes four REST endpoints that allow mobile clients to read and delete Mem0 memories associated with characters. All operations are pure Mem0 SDK calls -- no database reads or writes are needed beyond looking up the character's `mem0_agent_id` and the user's `mem0_user_id`.

The four endpoints are:

1. **GET /api/v1/characters/:id/memories** -- Retrieves all memories stored by Mem0 for a specific character. Uses the character's `mem0_agent_id` and the user's `mem0_user_id` to scope the query. This lets users see what a particular character "knows" about them.

2. **DELETE /api/v1/characters/:id/memories/:memory_id** -- Deletes a single memory from Mem0 by its Mem0-assigned ID. The user can remove specific facts they do not want the character to retain.

3. **DELETE /api/v1/characters/:id/memories** -- Deletes ALL memories for a specific character from Mem0. This is the "clear character memory" action. The character's `mem0_agent_id` scopes the deletion.

4. **GET /api/v1/memories** -- Retrieves global (General Friend) memories. These are memories stored without an `agent_id`, meaning they are visible to all characters. Uses only the user's `mem0_user_id`.

### Why It Exists

Per `docs/05-ai-bellek.md` Section "Memory Transparency Principles": "Users can always see what has been stored (per character)" and "Each record can be deleted, which actually removes it from Mem0." These endpoints are the backend implementation of that commitment. Without them, users have no visibility into or control over what the AI remembers about them.

### Dependencies

- **Requires**: P01-05 (character-crud -- Character model, character lookup + ownership check patterns)
- **Requires**: P01-01 (project-setup -- FastAPI scaffold, config with `mem0_api_key`)
- **Requires**: P01-02 (database-schema -- Profile model with `mem0_user_id`, Character model with `mem0_agent_id`)
- **Requires**: P01-03 (cognito-auth-middleware -- `get_current_user` dependency)
- **Uses patterns from**: P01-06 (chat-streaming -- `MemoryClient` usage with `asyncio.to_thread()` wrapping)

### What This Feature Does NOT Do

- It does not add or update memories. Memory creation happens automatically during the chat flow (P01-06, `_persist_exchange`).
- It does not display memories in the mobile UI. Mobile memory display screens are a future feature.
- It does not interact with the database beyond looking up the character's `mem0_agent_id` and verifying ownership. Memories live entirely in Mem0.
- It does not implement memory export (JSON download). That is a separate future feature.

---

## 2. Data Models

### No New Tables

This feature does not create or alter any database tables.

### No New Columns

All required columns already exist:

| Table | Column | Usage in This Feature |
|-------|--------|----------------------|
| `characters.id` | UUID PK | Path parameter for character-scoped endpoints |
| `characters.user_id` | UUID FK -> profiles | Ownership verification |
| `characters.mem0_agent_id` | TEXT UNIQUE | Passed to Mem0 SDK as `agent_id` |
| `characters.is_active` | BOOLEAN | Only active characters are accessible |
| `profiles.mem0_user_id` | TEXT UNIQUE | Passed to Mem0 SDK as `user_id` |

### Mem0 Operations

| Endpoint | Mem0 SDK Method | Parameters |
|----------|----------------|------------|
| GET /characters/:id/memories | `client.get_all(user_id=..., agent_id=...)` | `user_id`: profile.mem0_user_id, `agent_id`: character.mem0_agent_id |
| DELETE /characters/:id/memories/:memory_id | `client.delete(memory_id)` | `memory_id`: the Mem0-assigned UUID from the URL path |
| DELETE /characters/:id/memories | `client.delete_all(user_id=..., agent_id=...)` | `user_id`: profile.mem0_user_id, `agent_id`: character.mem0_agent_id |
| GET /memories | `client.get_all(user_id=...)` | `user_id`: profile.mem0_user_id (no agent_id -- global memories only) |

All Mem0 SDK methods are synchronous. Every call is wrapped in `asyncio.to_thread()` per the established pattern in `chat_service.py`.

---

## 3. API Endpoints

All endpoints are under the `/api/v1` prefix. All four require `Authorization: Bearer <jwt>`.

---

### GET /api/v1/characters/{character_id}/memories

Retrieves all memories stored in Mem0 for a specific character.

```
Auth: Bearer JWT required
Content-Type: application/json
```

**Path Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `character_id` | UUID string | Character ID |

**Query Parameters:** None.

**Response 200 OK:**

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

| Response Field | Type | Notes |
|----------------|------|-------|
| `memories` | array | All memories for this character. May be empty. |
| `memories[].id` | string | Mem0-assigned memory ID. Used for single-memory deletion. |
| `memories[].memory` | string | The memory content text. |
| `memories[].created_at` | string (ISO 8601) or null | When the memory was created. Null if Mem0 does not return a timestamp. |

**Notes:**
- The response wraps Mem0 SDK's `get_all()` result. The Mem0 SDK returns a list of dicts with at minimum `id` and `memory` fields. The `created_at` field may or may not be present depending on the Mem0 API version.
- This is NOT paginated. Mem0's `get_all()` returns all memories for the user+agent pair. The number of memories per character is expected to be in the dozens to low hundreds, not thousands.
- An empty `memories` array is returned when the character has no stored memories (not 404).

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 401 | Missing or invalid JWT | `{"detail": "Invalid or expired token"}` |
| 403 | Character does not belong to the authenticated user | `{"detail": "Character does not belong to user"}` |
| 404 | Character not found or inactive | `{"detail": "Character not found"}` |
| 503 | Mem0 API unavailable | `{"detail": "Memory service unavailable"}` |

---

### DELETE /api/v1/characters/{character_id}/memories/{memory_id}

Deletes a single memory from Mem0.

```
Auth: Bearer JWT required
```

**Path Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `character_id` | UUID string | Character ID (for ownership verification) |
| `memory_id` | string | Mem0-assigned memory ID |

**Response 204 No Content:**

Empty body.

**Notes:**
- The `character_id` is used only for ownership verification. The actual deletion is performed by Mem0 using only the `memory_id`.
- The `memory_id` is a string, not a UUID. While Mem0 currently uses UUID-like strings, the API should not enforce UUID format on Mem0's internal IDs.
- If the `memory_id` does not exist in Mem0, the Mem0 SDK may either succeed silently or raise an error. The endpoint should treat both cases as success (return 204). A memory that does not exist is effectively already deleted.

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 401 | Missing or invalid JWT | `{"detail": "Invalid or expired token"}` |
| 403 | Character does not belong to the authenticated user | `{"detail": "Character does not belong to user"}` |
| 404 | Character not found or inactive | `{"detail": "Character not found"}` |
| 503 | Mem0 API unavailable | `{"detail": "Memory service unavailable"}` |

---

### DELETE /api/v1/characters/{character_id}/memories

Deletes ALL memories for a specific character from Mem0.

```
Auth: Bearer JWT required
```

**Path Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `character_id` | UUID string | Character ID |

**Response 204 No Content:**

Empty body.

**Notes:**
- Uses `client.delete_all(user_id=..., agent_id=...)` which deletes all memories scoped to that agent.
- If the character has no memories, the call succeeds silently and returns 204.
- This does NOT delete global (no-agent) memories. It only deletes memories that were stored with the character's `mem0_agent_id`.

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 401 | Missing or invalid JWT | `{"detail": "Invalid or expired token"}` |
| 403 | Character does not belong to the authenticated user | `{"detail": "Character does not belong to user"}` |
| 404 | Character not found or inactive | `{"detail": "Character not found"}` |
| 503 | Mem0 API unavailable | `{"detail": "Memory service unavailable"}` |

---

### GET /api/v1/memories

Retrieves global memories (not scoped to any character). These are the "General Friend" memories visible to all characters.

```
Auth: Bearer JWT required
Content-Type: application/json
```

**Query Parameters:** None.

**Response 200 OK:**

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

Response shape is identical to `GET /characters/:id/memories`.

**Notes:**
- Calls `client.get_all(user_id=mem0_user_id)` WITHOUT an `agent_id` parameter. This returns memories that were stored without agent_id scope.
- Per `docs/05-ai-bellek.md`, global memories are "basic user information visible to all characters" (name, profession, goals, etc.).
- Not paginated, same rationale as the character-scoped endpoint.

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 401 | Missing or invalid JWT | `{"detail": "Invalid or expired token"}` |
| 503 | Mem0 API unavailable | `{"detail": "Memory service unavailable"}` |

---

## 4. Backend Logic

### MemoryService Class

A new `MemoryService` class in `backend/app/services/memory_service.py` encapsulates all Mem0 memory read and delete operations. Route handlers delegate to this service.

```
class MemoryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_character_memories(
        self,
        character_id: uuid.UUID,
        user_id: uuid.UUID,
        mem0_user_id: str,
    ) -> list[MemoryItem]:
        """Get all Mem0 memories for a specific character."""

    async def delete_character_memory(
        self,
        character_id: uuid.UUID,
        user_id: uuid.UUID,
        memory_id: str,
    ) -> None:
        """Delete a single memory from Mem0."""

    async def delete_all_character_memories(
        self,
        character_id: uuid.UUID,
        user_id: uuid.UUID,
        mem0_user_id: str,
    ) -> None:
        """Delete all Mem0 memories for a specific character."""

    async def get_global_memories(
        self,
        mem0_user_id: str,
    ) -> list[MemoryItem]:
        """Get all global (non-character-scoped) Mem0 memories."""
```

### Get Character Memories Flow

```
Client sends: GET /api/v1/characters/{character_id}/memories
Authorization: Bearer <jwt>
    |
    v
1. get_current_user extracts user_id and mem0_user_id from JWT/Profile
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
4. Call Mem0 SDK (via asyncio.to_thread):
   client = MemoryClient(api_key=settings.mem0_api_key)
   results = client.get_all(
       user_id=profile.mem0_user_id,
       agent_id=character.mem0_agent_id,
   )
    |
    +--> Mem0 API error --> 503 "Memory service unavailable"
    |
    v
5. Map results to MemoryItem response objects:
   For each result dict, extract:
     - id: result["id"]
     - memory: result["memory"]
     - created_at: result.get("created_at", None)
    |
    v
6. Return 200 { memories: [...] }
```

### Delete Single Memory Flow

```
Client sends: DELETE /api/v1/characters/{character_id}/memories/{memory_id}
Authorization: Bearer <jwt>
    |
    v
1. get_current_user extracts user_id from JWT/Profile
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
4. Call Mem0 SDK (via asyncio.to_thread):
   client = MemoryClient(api_key=settings.mem0_api_key)
   client.delete(memory_id)
    |
    +--> Mem0 API error (not "not found") --> 503 "Memory service unavailable"
    +--> Mem0 "not found" error --> treat as success (memory already gone)
    |
    v
5. Return 204 (no body)
```

### Delete All Character Memories Flow

```
Client sends: DELETE /api/v1/characters/{character_id}/memories
Authorization: Bearer <jwt>
    |
    v
1. get_current_user extracts user_id and mem0_user_id from JWT/Profile
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
4. Call Mem0 SDK (via asyncio.to_thread):
   client = MemoryClient(api_key=settings.mem0_api_key)
   client.delete_all(
       user_id=profile.mem0_user_id,
       agent_id=character.mem0_agent_id,
   )
    |
    +--> Mem0 API error --> 503 "Memory service unavailable"
    |
    v
5. Return 204 (no body)
```

### Get Global Memories Flow

```
Client sends: GET /api/v1/memories
Authorization: Bearer <jwt>
    |
    v
1. get_current_user extracts mem0_user_id from JWT/Profile
    |
    v
2. Call Mem0 SDK (via asyncio.to_thread):
   client = MemoryClient(api_key=settings.mem0_api_key)
   results = client.get_all(user_id=profile.mem0_user_id)
    |
    +--> Mem0 API error --> 503 "Memory service unavailable"
    |
    v
3. Map results to MemoryItem response objects (same as step 5 above)
    |
    v
4. Return 200 { memories: [...] }
```

**Important notes about global memories:**

The Mem0 SDK's `get_all(user_id=...)` without an `agent_id` parameter returns memories that were stored without an `agent_id`. However, this behavior depends on the Mem0 API version and configuration. During implementation, the developer should verify that calling `get_all(user_id=X)` does NOT return memories that were stored with `agent_id=Y` -- it should only return agent-less (global) memories. If the Mem0 SDK returns all memories regardless, the service must filter client-side to exclude memories that have an `agent_id`.

### Shared Helper: Character Lookup and Ownership Check

All three character-scoped endpoints perform the same two steps: look up the active character, verify ownership. This pattern already exists in `ChatService._get_active_character()` (from P01-06). The `MemoryService` should reuse a similar private helper method or import a shared utility.

```
async def _get_owned_character(
    self,
    character_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Character:
    """Look up an active character and verify ownership.

    Raises HTTPException(404) if not found/inactive.
    Raises HTTPException(403) if ownership mismatch.
    """
```

### Mem0 Client Instantiation

Following the existing pattern in `chat_service.py`, the `MemoryClient` is instantiated per-call (not as a class attribute). This avoids shared state issues and keeps the service testable.

```python
from mem0 import MemoryClient
from app.config import settings

client = MemoryClient(api_key=settings.mem0_api_key)
```

### Error Handling for Mem0 Calls

All Mem0 SDK calls are wrapped in try/except. On any exception:
- Log the error at ERROR level with the operation name, user_id, and agent_id (but NOT the memory content -- no PII in logs).
- Raise `HTTPException(status_code=503, detail="Memory service unavailable")`.

The single exception is `client.delete(memory_id)` where a "not found" error from Mem0 should be treated as success (return 204). The developer should inspect the Mem0 SDK's exception types to determine the correct exception class for "not found".

---

## 5. Pydantic Schemas

All schemas are defined in `backend/app/schemas/memory.py`.

### Response Schemas

```
class MemoryItem(BaseModel):
    """A single memory entry from Mem0."""

    id: str
    memory: str
    created_at: datetime | None = None
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Mem0-assigned memory ID |
| `memory` | string | The memory content text |
| `created_at` | string (ISO 8601) or null | When the memory was created. Null if Mem0 does not provide it. |

```
class MemoryListResponse(BaseModel):
    """Response for memory list endpoints."""

    memories: list[MemoryItem]
```

### No Request Schemas

All endpoints use path parameters and query parameters only. No request bodies.

---

## 6. Router Registration

### Memory Router

The memory router handles the global `GET /memories` endpoint. It is registered at the `/api/v1` prefix level.

The character-scoped memory endpoints (`GET /characters/:id/memories`, `DELETE /characters/:id/memories`, `DELETE /characters/:id/memories/:memory_id`) are in a separate router registered under `/api/v1/characters` (same prefix as the existing character and chat routers).

**Two routers in one module:**

To avoid prefix conflicts, the memory module defines two routers:

```python
# Registered under /api/v1 (for global memories)
global_router = APIRouter()

# Registered under /api/v1/characters (for character-scoped memories)
character_router = APIRouter()
```

In `main.py`:

```python
from app.routes import memories

app.include_router(memories.global_router, prefix="/api/v1", tags=["memories"])
app.include_router(memories.character_router, prefix="/api/v1/characters", tags=["memories"])
```

### Route Ambiguity: DELETE /characters/:id/memories vs DELETE /characters/:id/memories/:memory_id

These two DELETE routes on the same path prefix need careful ordering. FastAPI (Starlette) matches routes top-to-bottom. The route with the additional `/{memory_id}` path segment is more specific and will not conflict with the bare `/memories` route because:

- `DELETE /characters/{character_id}/memories` -- no trailing path segment
- `DELETE /characters/{character_id}/memories/{memory_id}` -- has a trailing path segment

These are distinct path patterns and FastAPI handles them correctly without ambiguity.

---

## 7. Test Requirements

### Route Tests (`backend/tests/test_memory_routes.py`)

These tests use the FastAPI test client. The `get_current_user` dependency is overridden to return a fake Profile. Mem0 calls are mocked.

| # | Scenario | Expected |
|---|----------|----------|
| R1 | GET /characters/:id/memories with valid character | 200, `{"memories": [...]}` with correct items |
| R2 | GET /characters/:id/memories with character that has no memories | 200, `{"memories": []}` |
| R3 | GET /characters/:id/memories with non-existent character | 404, `{"detail": "Character not found"}` |
| R4 | GET /characters/:id/memories with character belonging to another user | 403, `{"detail": "Character does not belong to user"}` |
| R5 | GET /characters/:id/memories with inactive character | 404, `{"detail": "Character not found"}` |
| R6 | GET /characters/:id/memories without auth header | 401 |
| R7 | GET /characters/:id/memories when Mem0 is down | 503, `{"detail": "Memory service unavailable"}` |
| R8 | DELETE /characters/:id/memories/:memory_id with valid character | 204, no body |
| R9 | DELETE /characters/:id/memories/:memory_id with non-existent character | 404, `{"detail": "Character not found"}` |
| R10 | DELETE /characters/:id/memories/:memory_id with wrong user | 403, `{"detail": "Character does not belong to user"}` |
| R11 | DELETE /characters/:id/memories/:memory_id without auth header | 401 |
| R12 | DELETE /characters/:id/memories/:memory_id when Mem0 is down | 503, `{"detail": "Memory service unavailable"}` |
| R13 | DELETE /characters/:id/memories/:memory_id when memory does not exist in Mem0 | 204 (idempotent) |
| R14 | DELETE /characters/:id/memories (clear all) with valid character | 204, no body |
| R15 | DELETE /characters/:id/memories (clear all) with non-existent character | 404 |
| R16 | DELETE /characters/:id/memories (clear all) with wrong user | 403 |
| R17 | DELETE /characters/:id/memories (clear all) without auth header | 401 |
| R18 | DELETE /characters/:id/memories (clear all) when Mem0 is down | 503 |
| R19 | GET /memories (global) returns global memories | 200, `{"memories": [...]}` |
| R20 | GET /memories (global) when user has no global memories | 200, `{"memories": []}` |
| R21 | GET /memories (global) without auth header | 401 |
| R22 | GET /memories (global) when Mem0 is down | 503, `{"detail": "Memory service unavailable"}` |

### Service Tests (`backend/tests/test_memory_service.py`)

These tests unit-test the `MemoryService` class directly. The database session and Mem0 client are mocked.

| # | Scenario | Expected |
|---|----------|----------|
| S1 | `get_character_memories()` calls Mem0 `get_all()` with correct user_id and agent_id | Mem0 called with exact parameters |
| S2 | `get_character_memories()` maps Mem0 response to MemoryItem list | Correct id, memory, created_at mapping |
| S3 | `get_character_memories()` handles Mem0 response without `created_at` field | MemoryItem.created_at is None |
| S4 | `get_character_memories()` raises 404 for non-existent character | HTTPException(404) |
| S5 | `get_character_memories()` raises 403 for wrong user | HTTPException(403) |
| S6 | `get_character_memories()` raises 503 when Mem0 fails | HTTPException(503) |
| S7 | `delete_character_memory()` calls Mem0 `delete()` with correct memory_id | Mem0 called with exact parameter |
| S8 | `delete_character_memory()` verifies character ownership before calling Mem0 | Ownership check happens first |
| S9 | `delete_character_memory()` treats Mem0 "not found" as success | No exception raised |
| S10 | `delete_character_memory()` raises 503 on Mem0 failure (non "not found") | HTTPException(503) |
| S11 | `delete_all_character_memories()` calls Mem0 `delete_all()` with correct user_id and agent_id | Mem0 called with exact parameters |
| S12 | `delete_all_character_memories()` verifies character ownership before calling Mem0 | Ownership check happens first |
| S13 | `delete_all_character_memories()` raises 503 when Mem0 fails | HTTPException(503) |
| S14 | `get_global_memories()` calls Mem0 `get_all()` with user_id only (no agent_id) | Mem0 called WITHOUT agent_id |
| S15 | `get_global_memories()` maps Mem0 response correctly | Correct mapping |
| S16 | `get_global_memories()` raises 503 when Mem0 fails | HTTPException(503) |

### Schema Tests (`backend/tests/test_memory_schemas.py`)

| # | Scenario | Expected |
|---|----------|----------|
| T1 | `MemoryItem` with all fields populated | All fields correctly set |
| T2 | `MemoryItem` with `created_at` as None | Defaults to None |
| T3 | `MemoryListResponse` with empty memories list | `{"memories": []}` |
| T4 | `MemoryListResponse` with multiple items | Correct serialization |

### How to Mock Mem0

```python
from unittest.mock import patch, MagicMock

# Mock for get_all
mock_client = MagicMock()
mock_client.get_all.return_value = [
    {"id": "mem-1", "memory": "Likes morning workouts", "created_at": "2026-02-20T10:00:00Z"},
    {"id": "mem-2", "memory": "Left knee is sensitive", "created_at": "2026-02-18T15:30:00Z"},
]

with patch("app.services.memory_service.MemoryClient") as mock_cls:
    mock_cls.return_value = mock_client
    # ... run test

# Mock for delete (success)
mock_client.delete.return_value = None

# Mock for delete_all (success)
mock_client.delete_all.return_value = None

# Mock for Mem0 failure
mock_client.get_all.side_effect = Exception("Mem0 connection refused")
```

All Mem0 calls are wrapped in `asyncio.to_thread()`, so tests must account for this. Since `asyncio.to_thread()` runs the callable in a thread pool, the mock's methods are called synchronously within that thread. Standard `MagicMock` is sufficient (no `AsyncMock` needed for the Mem0 client methods themselves).

### How to Mock the Database

Follow the same pattern as P01-05. Override `get_db` for route tests. For service tests, pass a mock `AsyncSession` that returns predefined Character objects from `db.execute()`.

---

## 8. File Manifest

Every file to be created or modified, grouped by purpose.

### Route Handlers

```
Backend:
  CREATE  backend/app/routes/memories.py
```

Contains two routers: `global_router` (for `GET /memories`) and `character_router` (for character-scoped memory endpoints). Four route functions total, each delegating to `MemoryService`.

### Service Layer

```
Backend:
  CREATE  backend/app/services/memory_service.py
```

Contains the `MemoryService` class with four public methods and the private `_get_owned_character()` helper.

### Pydantic Schemas

```
Backend:
  CREATE  backend/app/schemas/memory.py
```

Contains `MemoryItem` and `MemoryListResponse`.

### Application Wiring

```
Backend:
  MODIFY  backend/app/main.py
```

Add import for `memories` module and register both routers:

```python
from app.routes import memories

app.include_router(memories.global_router, prefix="/api/v1", tags=["memories"])
app.include_router(memories.character_router, prefix="/api/v1/characters", tags=["memories"])
```

### Tests

```
Backend:
  CREATE  backend/tests/test_memory_routes.py
  CREATE  backend/tests/test_memory_service.py
  CREATE  backend/tests/test_memory_schemas.py
```

### Documentation (Pipeline)

```
Shared:
  CREATE  shared/feature-specs/memory-endpoints.md          (this file)
  CREATE  docs/pipeline/memory-endpoints-architect.handoff.md
```

### Summary

| Action | Count |
|--------|-------|
| CREATE | 6 |
| MODIFY | 1 |
| DELETE | 0 |
| **Total** | **7** |

### Files NOT Modified

- `backend/app/dependencies.py` -- Uses the existing `get_current_user` and `get_db`. No changes needed.
- `backend/app/config.py` -- `mem0_api_key` already exists. No new config values needed.
- `backend/app/models/` -- No model changes. Existing Character and Profile models are used as-is.
- `backend/app/schemas/__init__.py` -- Not modified (follow direct import pattern).
- `backend/app/services/__init__.py` -- Not modified (follow direct import pattern).
- `backend/requirements.txt` -- `mem0ai` is already a dependency (used by `chat_service.py`).
- `backend/app/routes/characters.py` -- Memory endpoints are in a separate `memories.py` file.
- `backend/app/routes/chat.py` -- Not modified.
- `backend/app/services/chat_service.py` -- Not modified. The existing Mem0 patterns are referenced but the code is not changed.

---

## 9. Acceptance Criteria

1. Given an authenticated user with a character that has stored Mem0 memories, when the client sends `GET /api/v1/characters/{character_id}/memories`, then the response is HTTP 200 with a `memories` array containing items with `id`, `memory`, and `created_at` fields.

2. Given an authenticated user with a character that has no Mem0 memories, when the client sends `GET /api/v1/characters/{character_id}/memories`, then the response is HTTP 200 with `{"memories": []}`.

3. Given a character belonging to another user, when the client sends `GET /api/v1/characters/{character_id}/memories`, then the response is HTTP 403 with detail "Character does not belong to user".

4. Given a non-existent or inactive character ID, when the client sends `GET /api/v1/characters/{character_id}/memories`, then the response is HTTP 404 with detail "Character not found".

5. Given a valid character and a valid Mem0 memory_id, when the client sends `DELETE /api/v1/characters/{character_id}/memories/{memory_id}`, then the response is HTTP 204 and the memory no longer exists in Mem0.

6. Given a valid character and a non-existent memory_id, when the client sends `DELETE /api/v1/characters/{character_id}/memories/{memory_id}`, then the response is HTTP 204 (idempotent deletion).

7. Given a valid character, when the client sends `DELETE /api/v1/characters/{character_id}/memories` (no memory_id suffix), then the response is HTTP 204 and ALL memories for that character are deleted from Mem0.

8. Given an authenticated user, when the client sends `GET /api/v1/memories`, then the response is HTTP 200 with a `memories` array containing only global (non-character-scoped) memories.

9. Given an authenticated user with no global memories, when the client sends `GET /api/v1/memories`, then the response is HTTP 200 with `{"memories": []}`.

10. Given any memory endpoint, when the Mem0 API is unavailable, then the response is HTTP 503 with detail "Memory service unavailable".

11. Given any protected memory endpoint, when the request has no `Authorization` header, then the response is HTTP 401.

12. Given the `MemoryService` code, when a developer inspects it, then all Mem0 SDK calls are wrapped in `asyncio.to_thread()` (no blocking calls in the async event loop).

13. Given the route handler code for all four endpoints, when a developer inspects the code, then all business logic is in `MemoryService` and route handlers only call service methods and return responses.

14. Given the backend test suite, when a developer runs `pytest` on the new test files, then all tests pass with exit code 0.

---

## 10. Design Decisions and Rationale

### Why no pagination on memory list endpoints

Mem0's `get_all()` does not natively support cursor-based pagination. Adding server-side pagination would require fetching all memories, sorting them, and slicing -- which is equivalent to no pagination with extra complexity. The number of memories per user-character pair is expected to be in the dozens to low hundreds. If memory counts grow significantly in the future, pagination can be added by fetching all and slicing, or by switching to the Mem0 REST API (which supports `page` and `page_size` parameters).

### Why character ownership is checked on single-memory delete

The `memory_id` alone is sufficient for Mem0 to delete a memory. However, without the character ownership check, a malicious user could delete another user's memories by guessing memory IDs. The character_id path parameter and ownership check ensure that only the character's owner can delete its memories. This defense-in-depth approach prevents unauthorized memory deletion.

### Why the Mem0 "not found" error on single delete is treated as success

The single-memory delete is an idempotent operation. If the user clicks "delete" twice or the memory was already removed by Mem0's internal cleanup, the user's intent (memory should not exist) is satisfied. Returning 404 for a missing memory would confuse clients and require them to handle an error case that is not really an error.

### Why two routers in one module (not two separate route files)

The global endpoint (`GET /memories`) and the character-scoped endpoints (`GET/DELETE /characters/:id/memories`) share the same service class, schemas, and conceptual domain. Splitting them into two files would scatter related code. Two routers in one module is a standard FastAPI pattern for different prefix registrations of related functionality.

### Why the `memory` field is named `memory` (not `content`)

The Mem0 SDK returns a dict with a `memory` key for the text content. Using the same field name avoids confusion and makes it clear this is a Mem0-native concept, not an Ember abstraction. The `docs/04-veri-api.md` example response also uses `"content"` as the field name, but since this data comes from Mem0 (not from our database) and Mem0 calls it `memory`, we keep Mem0's terminology.

### Why MemoryService has its own character lookup (not shared with ChatService)

While both services need to look up a character and check ownership, extracting this to a shared utility adds a coupling point. The helper is only 10-15 lines. If a third service needs it, refactoring to a shared helper is trivial. For now, each service has its own private `_get_owned_character()` or `_get_active_character()` method, keeping services self-contained.

---

## 11. Notes for Developers

### For backend-dev

- **Start with schemas** (`app/schemas/memory.py`), then the service (`app/services/memory_service.py`), then the routes (`app/routes/memories.py`), then wire up in `main.py`.

- **Mem0 SDK reference**: Look at `chat_service.py` lines 377-404 for the established pattern of wrapping `MemoryClient` calls in `asyncio.to_thread()`. Follow the same pattern for `get_all()`, `delete()`, and `delete_all()`.

- **Mem0 SDK method signatures**: The methods you need are:
  - `client.get_all(user_id=..., agent_id=...)` -- returns list of dicts
  - `client.get_all(user_id=...)` -- returns list of dicts (global memories)
  - `client.delete(memory_id)` -- deletes a single memory
  - `client.delete_all(user_id=..., agent_id=...)` -- deletes all memories for the scope

- **Router registration in `main.py`**: The character memory router is registered under `/api/v1/characters` (same prefix as the existing characters and chat routers). The route functions use relative paths: `@character_router.get("/{character_id}/memories")`, `@character_router.delete("/{character_id}/memories/{memory_id}")`, `@character_router.delete("/{character_id}/memories")`. The global router uses `@global_router.get("/memories")` and is registered under `/api/v1`.

- **Path parameter type for `memory_id`**: Use `memory_id: str` (NOT `uuid.UUID`) in the route signature. Mem0 memory IDs are strings. While they look like UUIDs, enforcing UUID format on an external service's IDs would be fragile.

- **Error handling pattern**: Wrap Mem0 calls in try/except at the service layer. Catch broad `Exception` (the Mem0 SDK may raise various exception types). Log the error and raise `HTTPException(503)`. For `client.delete()`, also check if the exception indicates "not found" and suppress it.

- **No database writes**: This feature only reads from the database (character lookup). There are no INSERT, UPDATE, or DELETE operations on PostgreSQL tables.

- **Existing import in main.py**: The current `from app.routes import auth, characters, chat, health` line needs to be extended with `memories`.

### For backend-tester

- **Mock Mem0 at the import level**: Patch `app.services.memory_service.MemoryClient` to return a mock client. Set return values for `get_all`, `delete`, and `delete_all`.

- **Test ownership checks thoroughly**: Create characters owned by different users and verify that one user cannot read or delete another user's character memories.

- **Test the 503 path**: Make the mock Mem0 client raise an exception and verify the endpoint returns 503 with the correct detail message.

- **Test idempotent deletion**: For single-memory delete, make the mock raise a "not found" style exception and verify 204 is still returned.

- **Test the global endpoint isolation**: Verify that `GET /memories` does not require a character_id and does not perform any character lookup.

- **Seed test data**: For route tests, seed the test database with Character objects (with `mem0_agent_id` and `user_id`). For service tests, mock `db.execute()` to return mock Character objects.
