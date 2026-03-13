# Feature Spec: P1.5-08 -- Global Memory Delete

**Feature ID**: P1.5-08
**Phase**: 1.5
**Layer**: backend
**GitHub Issue**: #90
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature adds a single new REST endpoint:

**DELETE /api/v1/memories/{memory_id}** -- Deletes a single global (non-character-scoped) memory from Mem0.

Currently, users can delete character-scoped memories via `DELETE /api/v1/characters/:id/memories/:memId`, but there is no endpoint to delete individual global memories. The `GET /api/v1/memories` endpoint already exists (P01-08) and returns global memories with their IDs. This feature closes the gap by allowing users to delete any specific global memory they see in that list.

### Why It Exists

Per `docs/05-ai-bellek.md` Section "Memory Transparency Principles": "Each record can be deleted, which actually removes it from Mem0." The existing implementation only honors this for character-scoped memories. Global memories (name, profession, goals -- the "General Friend" memories visible to all characters) cannot currently be deleted individually. This is both a usability gap and a GDPR compliance concern, since users must be able to remove any personal data the system stores about them.

The API contract in `docs/04-veri-api.md` already defines `DELETE /memories/:memId` returning 204. This feature implements that contract.

### Dependencies

- **Requires**: P01-08 (memory-endpoints -- existing `MemoryService`, `global_router`, `MemoryItem` schema, Mem0 client patterns)
- **Requires**: P01-01 (project-setup -- FastAPI scaffold, config with `mem0_api_key`)
- **Requires**: P01-03 (cognito-auth-middleware -- `get_current_user` dependency)
- **Extends**: P1.5-04 (mem0-circuit-breaker -- circuit breaker pattern used for Mem0 calls)

### What This Feature Does NOT Do

- It does not delete character-scoped memories. That already exists at `DELETE /characters/:id/memories/:memId`.
- It does not delete ALL global memories at once. That can be a future endpoint if needed.
- It does not add mobile UI screens. This is a backend-only feature.
- It does not modify the existing `GET /api/v1/memories` endpoint.

---

## 2. Data Models

### No New Tables

This feature does not create or alter any database tables.

### No New Columns

No database changes are required. The feature operates entirely against Mem0.

### Mem0 Operations

| Endpoint | Mem0 SDK Method | Parameters |
|----------|----------------|------------|
| DELETE /api/v1/memories/{memory_id} | `client.delete(memory_id)` | `memory_id`: the Mem0-assigned ID from the URL path |

Before calling `client.delete()`, the endpoint must verify that the memory belongs to the authenticated user. This is done by calling `client.get(memory_id)` first and checking that the returned memory's `user_id` matches the authenticated user's `mem0_user_id`.

---

## 3. API Endpoints

### DELETE /api/v1/memories/{memory_id}

Deletes a single global (non-character-scoped) memory from Mem0.

```
Auth: Bearer JWT required
```

**Path Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `memory_id` | string | Mem0-assigned memory ID (returned by `GET /api/v1/memories`) |

**Response 204 No Content:**

Empty body.

**Notes:**
- The `memory_id` is a string, not a UUID. While Mem0 currently uses UUID-like strings, the API does not enforce UUID format on Mem0's internal IDs. This is consistent with the existing character-scoped delete endpoint.
- Ownership validation: Before deleting, the service fetches the memory from Mem0 via `client.get(memory_id)` and verifies that the memory's `user_id` matches the authenticated user's `mem0_user_id`. This prevents a user from deleting another user's memory by guessing IDs.
- Idempotent: If the `memory_id` does not exist in Mem0, the endpoint returns 204. A memory that does not exist is effectively already deleted.
- This endpoint only deletes global memories (those stored without an `agent_id`). However, from Mem0's perspective, `client.delete(memory_id)` deletes any memory regardless of scope. The ownership check via `client.get()` ensures the memory belongs to the user, and that is sufficient authorization. There is no need to verify that the memory is specifically "global" vs "character-scoped" because the user owns both.

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 401 | Missing or invalid JWT | `{"detail": "Invalid or expired token"}` |
| 403 | Memory does not belong to the authenticated user | `{"detail": "Memory does not belong to user"}` |
| 404 | Memory not found in Mem0 | Treated as 204 (idempotent delete) |
| 503 | Mem0 API unavailable or circuit breaker open | `{"detail": "Memory service temporarily unavailable"}` |

---

## 4. Backend Logic

### New Service Method

A new public method `delete_global_memory()` is added to the existing `MemoryService` class in `backend/app/services/memory_service.py`.

```
async def delete_global_memory(
    self,
    mem0_user_id: str,
    memory_id: str,
) -> None:
    """Delete a single global memory from Mem0.

    Validates that the memory belongs to the authenticated user by
    fetching the memory from Mem0 and checking its user_id metadata.

    Idempotent: returns successfully even if memory_id does not exist.

    Raises:
        HTTPException(403): Memory does not belong to user.
        HTTPException(503): Mem0 API unavailable or circuit breaker open.
    """
```

### Delete Global Memory Flow

```
Client sends: DELETE /api/v1/memories/{memory_id}
Authorization: Bearer <jwt>
    |
    v
1. get_current_user extracts mem0_user_id from JWT/Profile
    |
    v
2. Check circuit breaker state
    |
    +--> OPEN --> 503 "Memory service temporarily unavailable"
    |
    v
3. Fetch memory from Mem0 (via asyncio.to_thread):
   client = MemoryClient(api_key=settings.mem0_api_key)
   memory = client.get(memory_id)
    |
    +--> Mem0 API error with "not found" / 404 --> treat as success, return (idempotent)
    +--> Mem0 API error (other) --> 503 "Memory service temporarily unavailable"
    |
    v
4. Ownership check: memory["user_id"] == mem0_user_id
    |
    +--> Mismatch --> 403 "Memory does not belong to user"
    |
    v
5. Delete memory from Mem0 (via asyncio.to_thread):
   client.delete(memory_id)
    |
    +--> Mem0 API error with "not found" --> treat as success (race condition: deleted between get and delete)
    +--> Mem0 API error (other) --> 503 "Memory service temporarily unavailable"
    |
    v
6. Return (route handler sends 204)
```

### Ownership Validation Strategy

The character-scoped delete endpoint (`DELETE /characters/:id/memories/:memId`) validates ownership indirectly: it verifies the user owns the character, and the character's `mem0_agent_id` implicitly scopes the memories. For global memories there is no character to check against, so direct memory ownership validation is required.

The Mem0 SDK's `client.get(memory_id)` returns a dict that includes a `user_id` field. The service compares this against `current_user.mem0_user_id`. If they do not match, the request is rejected with 403.

**Implementation detail:** The Mem0 `client.get()` method returns a dict like:
```json
{
  "id": "mem-uuid",
  "memory": "Works as a freelance engineer",
  "user_id": "user_550e8400...",
  "agent_id": null,
  "created_at": "2026-02-15T08:00:00Z"
}
```

The `user_id` field in this response is the Mem0 user ID (same as `profile.mem0_user_id`), not the Ember database UUID. The comparison is a simple string equality check.

### Circuit Breaker Integration

The method follows the same circuit breaker pattern used by all other `MemoryService` methods:

1. Call `self._check_circuit()` at the start to fail fast if the breaker is OPEN.
2. Wrap both the `client.get()` and `client.delete()` calls with `breaker.call_with_breaker()`.
3. Catch `CircuitOpenError` and re-raise as HTTP 503.

### Error Handling

All Mem0 SDK calls are wrapped in try/except. On any exception:
- Log the error at ERROR level with the operation name and memory_id (no PII).
- If the exception string contains "not found" or "404", treat as success (idempotent delete).
- Otherwise, raise `HTTPException(status_code=503, detail="Memory service temporarily unavailable")`.

This is consistent with the existing `delete_character_memory()` error handling pattern.

### Route Handler

A new route function is added to the existing `global_router` in `backend/app/routes/memories.py`:

```
@global_router.delete(
    "/memories/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_global_memory(
    memory_id: str,
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a single global memory from Mem0.

    Validates that the memory belongs to the authenticated user.
    Idempotent: returns 204 even if the memory_id does not exist.
    """
    service = MemoryService(db)
    await service.delete_global_memory(
        mem0_user_id=current_user.mem0_user_id,
        memory_id=memory_id,
    )
```

No changes to `main.py` are needed because `global_router` is already registered under `/api/v1`.

---

## 5. iOS Screens and Components

Not applicable. This is a backend-only feature (layer: backend). Mobile UI for global memory management is a future feature.

---

## 6. Android Screens and Components

Not applicable. This is a backend-only feature (layer: backend).

---

## 7. Test Plan

### Route Tests (add to `backend/tests/routes/test_memories.py` or new `test_memories_global_delete.py`)

| # | Scenario | Expected |
|---|----------|----------|
| R1 | DELETE /api/v1/memories/{memory_id} with valid memory belonging to user | 204, empty body |
| R2 | DELETE /api/v1/memories/{memory_id} without auth header | 401 or 403 |
| R3 | DELETE /api/v1/memories/{memory_id} when memory belongs to another user | 403, `{"detail": "Memory does not belong to user"}` |
| R4 | DELETE /api/v1/memories/{memory_id} when memory does not exist in Mem0 | 204 (idempotent) |
| R5 | DELETE /api/v1/memories/{memory_id} when Mem0 API is unavailable | 503, `{"detail": "Memory service temporarily unavailable"}` |
| R6 | DELETE /api/v1/memories/{memory_id} when circuit breaker is OPEN | 503, `{"detail": "Memory service temporarily unavailable"}` |

### Service Tests (add to `backend/tests/services/test_memories.py` or new file)

| # | Scenario | Expected |
|---|----------|----------|
| S1 | `delete_global_memory()` calls `client.get(memory_id)` then `client.delete(memory_id)` | Both Mem0 methods called in sequence |
| S2 | `delete_global_memory()` with matching user_id succeeds | No exception raised |
| S3 | `delete_global_memory()` with mismatched user_id raises 403 | HTTPException(403) with detail "Memory does not belong to user" |
| S4 | `delete_global_memory()` when `client.get()` raises "not found" | No exception (idempotent) |
| S5 | `delete_global_memory()` when `client.get()` raises other error | HTTPException(503) |
| S6 | `delete_global_memory()` when `client.delete()` raises "not found" | No exception (race condition handled) |
| S7 | `delete_global_memory()` when `client.delete()` raises other error | HTTPException(503) |
| S8 | `delete_global_memory()` when circuit breaker is OPEN | HTTPException(503) |

### How to Mock Mem0

Follow the established pattern from `backend/tests/routes/test_memories.py`:

```python
# Mock for get (ownership check)
mock_client = MagicMock()
mock_client.get.return_value = {
    "id": "mem-1",
    "memory": "Works as a freelance engineer",
    "user_id": "user_550e8400-e29b-41d4-a716-446655440000",
    "created_at": "2026-02-15T08:00:00Z",
}
mock_client.delete.return_value = None

with patch("app.services.memory_service.MemoryClient") as mock_cls:
    mock_cls.return_value = mock_client
    # ... run test

# Mock for memory belonging to another user
mock_client.get.return_value = {
    "id": "mem-1",
    "memory": "Another user's memory",
    "user_id": "user_different-uuid",
    "created_at": "2026-02-15T08:00:00Z",
}

# Mock for non-existent memory
mock_client.get.side_effect = Exception("Memory not found")

# Mock for Mem0 failure
mock_client.get.side_effect = Exception("Connection timeout")
```

---

## 8. Acceptance Criteria

1. Given an authenticated user, when the client sends `DELETE /api/v1/memories/{memory_id}` with a memory_id that belongs to the user, then the response is HTTP 204 with an empty body and the memory is removed from Mem0.

2. Given an authenticated user, when the client sends `DELETE /api/v1/memories/{memory_id}` with a memory_id that belongs to a different user, then the response is HTTP 403 with detail "Memory does not belong to user".

3. Given an authenticated user, when the client sends `DELETE /api/v1/memories/{memory_id}` with a memory_id that does not exist in Mem0, then the response is HTTP 204 (idempotent deletion).

4. Given no authentication, when the client sends `DELETE /api/v1/memories/{memory_id}`, then the response is HTTP 401.

5. Given the Mem0 API is unavailable, when the client sends `DELETE /api/v1/memories/{memory_id}`, then the response is HTTP 503 with detail "Memory service temporarily unavailable".

6. Given the Mem0 circuit breaker is in OPEN state, when the client sends `DELETE /api/v1/memories/{memory_id}`, then the response is HTTP 503 immediately without attempting a Mem0 call.

7. Given the `delete_global_memory()` service method, when a developer inspects the code, then all Mem0 SDK calls are wrapped in `asyncio.to_thread()` with circuit breaker integration.

8. Given the route handler code, when a developer inspects it, then all business logic is in `MemoryService` and the route handler only calls the service method and returns the response.

9. Given the backend test suite, when `pytest` is run on the new test scenarios, then all tests pass with exit code 0.

---

## 9. File Manifest

```
Backend:
  MODIFY  backend/app/routes/memories.py        (add delete_global_memory route to global_router)
  MODIFY  backend/app/services/memory_service.py (add delete_global_memory method to MemoryService)
  CREATE  backend/tests/routes/test_memories_global_delete.py
  CREATE  backend/tests/services/test_memories_global_delete.py

Shared:
  CREATE  shared/feature-specs/global-memory-delete.md     (this file)
  CREATE  docs/pipeline/global-memory-delete-architect.handoff.md
```

### Files NOT Modified

- `backend/app/main.py` -- No changes needed. The `global_router` is already registered under `/api/v1`. Adding a new route to that router is automatically picked up.
- `backend/app/schemas/memory.py` -- No new schemas needed. The endpoint returns 204 with no body.
- `backend/app/models/` -- No model changes.
- `backend/app/config.py` -- No new config values.
- `backend/requirements.txt` -- No new dependencies.

### Summary

| Action | Count |
|--------|-------|
| CREATE | 4 |
| MODIFY | 2 |
| DELETE | 0 |
| **Total** | **6** |

---

## 10. Design Decisions and Rationale

### Why ownership is validated via Mem0 `client.get()` instead of a database check

Global memories are not tied to a character, so there is no character ownership check to perform. The only way to verify that a memory belongs to a user is to fetch it from Mem0 and check the `user_id` field. This adds one extra Mem0 call per delete request, but security requires it. Without this check, any authenticated user could delete any other user's memories by guessing Mem0 IDs.

### Why the endpoint does not verify the memory is "global" (no agent_id)

From a security standpoint, the ownership check (memory.user_id == current_user.mem0_user_id) is sufficient. The user owns both their global and character-scoped memories. If a user happens to call this endpoint with a character-scoped memory ID, the deletion still only affects their own data. Restricting deletion to only agent_id-less memories would add complexity without security benefit. The character-scoped delete endpoint exists as the canonical way to delete character memories, but this endpoint does not need to enforce that boundary.

### Why the endpoint is idempotent

Consistent with the existing character-scoped delete endpoint. If a memory does not exist, the user's intent (memory should not exist) is satisfied. Returning 404 for a missing memory would confuse clients and require error handling for a non-error condition.

### Why tests are in separate files instead of appended to existing test files

The existing `test_memories.py` and `test_memories_extended.py` files are already substantial. Adding a new test class for a distinct endpoint in a separate file keeps test files focused and avoids merge conflicts with other concurrent work.
