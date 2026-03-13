# Global Memory Delete

> Allows authenticated users to delete individual global Mem0 memories, completing the memory CRUD surface and fulfilling GDPR right-to-erasure requirements.

**Status**: Released
**Added in**: Phase 1.5 (P1.5-08), 2026-03-13
**Platforms**: Backend only

---

## Overview

Global memories are facts about a user that are not tied to any specific character — things like their name, profession, or long-term goals. These memories are stored in Mem0 without an `agent_id` and are visible to all characters ("General Friend" memories). Before this feature, users could list global memories via `GET /api/v1/memories` and delete character-scoped memories via `DELETE /api/v1/characters/:id/memories/:memId`, but had no way to remove individual global memories.

This feature adds `DELETE /api/v1/memories/{memory_id}`, which allows a user to remove a specific global memory by the ID returned from the list endpoint. The endpoint performs direct ownership validation via a Mem0 `client.get()` call before deletion — necessary because global memories have no associated character whose ownership can be checked indirectly.

The motivation is twofold: usability (users can see and delete any fact Ember has stored about them) and GDPR compliance. The Memory Transparency Principles in `docs/05-ai-bellek.md` state that every stored record must be individually deletable, and this feature closes the gap for global memories.

---

## Architecture

### How It Works (Data Flow)

1. Client sends `DELETE /api/v1/memories/{memory_id}` with `Authorization: Bearer {jwt}`.
2. `get_current_user()` extracts the authenticated `Profile`, including `mem0_user_id`.
3. The route handler delegates entirely to `MemoryService.delete_global_memory(mem0_user_id, memory_id)`.
4. The service calls `_check_circuit()`. If the Mem0 circuit breaker is OPEN, it returns 503 immediately without contacting Mem0.
5. The service fetches the memory from Mem0: `client.get(memory_id)` (wrapped in `asyncio.to_thread` and `breaker.call_with_breaker`).
   - If the exception message contains `"not found"` or `"404"` (case-insensitive), the method returns without error (idempotent).
   - Any other exception returns 503.
6. The service compares `memory["user_id"]` against `mem0_user_id`. A mismatch raises 403 and `client.delete()` is never called.
7. The service calls `client.delete(memory_id)` (wrapped in `asyncio.to_thread` and `breaker.call_with_breaker`).
   - A `"not found"` / `"404"` exception at this step is also treated as success (handles the race condition where the memory was deleted between step 5 and step 7).
   - Any other exception returns 503.
8. The route handler returns HTTP 204 with an empty body.

### Ownership Validation Strategy

Character-scoped memory endpoints validate ownership indirectly: the service confirms the user owns the character, and the character's `mem0_agent_id` scopes the memories. Global memories have no character, so ownership must be validated directly by fetching the memory from Mem0 and comparing its `user_id` field to the authenticated user's `mem0_user_id`.

The Mem0 `client.get()` response includes a `user_id` field that matches the value passed during `client.add()`. The comparison is a simple string equality check (`memory.get("user_id") != mem0_user_id`). This check costs one extra Mem0 round-trip per delete, but is required to prevent a user from deleting another user's memory by guessing Mem0 IDs.

### Idempotency

The endpoint returns 204 even when the memory does not exist in Mem0. This is consistent with `DELETE /characters/:id/memories/:memId` and avoids forcing clients to handle a 404 that represents an already-satisfied intent. "Not found" detection uses case-insensitive string matching on the exception message (`"not found"` or `"404"`), consistent with the existing `delete_character_memory()` pattern.

### Circuit Breaker Integration

Both Mem0 calls — `client.get()` and `client.delete()` — go through the existing Mem0 circuit breaker (P1.5-04). The service calls `_check_circuit()` at the start to fail fast when the breaker is OPEN, then wraps each SDK call in `breaker.call_with_breaker()`. `CircuitOpenError` is caught and re-raised as HTTP 503.

### Database Tables Involved

| Table | Operation | Notes |
|-------|-----------|-------|
| `profiles` | SELECT (implicit) | `get_current_user()` loads the profile to retrieve `mem0_user_id` |

No other tables are read or written. The operation is entirely against Mem0.

---

## API Reference

See [`docs/04-veri-api.md`](../04-veri-api.md) for the full API contract. This feature implements the `DELETE /memories/:memId` entry already defined there.

### `DELETE /api/v1/memories/{memory_id}`

**Auth**: Bearer JWT required
**Content-Type**: Not applicable (no request body)

**Path Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `memory_id` | string | Mem0-assigned memory ID from `GET /api/v1/memories` |

The `memory_id` is treated as an opaque string. The API does not enforce UUID format because Mem0 internal IDs are not guaranteed to remain UUID-shaped across SDK versions.

**Response**: `204 No Content` — empty body on success.

**Error Responses**:

| Status | Condition | Body |
|--------|-----------|------|
| 401 | Missing or invalid JWT | `{"detail": "Invalid or expired token"}` |
| 403 | Memory exists but belongs to a different user | `{"detail": "Memory does not belong to user"}` |
| 503 | Mem0 API unavailable, network error, or circuit breaker OPEN | `{"detail": "Memory service temporarily unavailable"}` |

Note: A memory that does not exist returns 204, not 404.

---

## iOS Implementation

Not applicable. This is a backend-only feature. Mobile UI for global memory management is a future feature.

---

## Android Implementation

Not applicable. This is a backend-only feature. Mobile UI for global memory management is a future feature.

---

## Testing

### Coverage Summary

| Platform | File | Scenarios |
|----------|------|-----------|
| Backend routes | `backend/tests/routes/test_memories_global_delete.py` | 6 (R1–R6) |
| Backend service | `backend/tests/services/test_memories_global_delete.py` | 9 (S1–S8 + S4b) |

All tests passed at implementation time: `pytest: 1973 passed, 13 skipped, 0 failed`.

### Running Tests

**Backend (all memory delete tests)**:
```bash
cd backend && python -m pytest tests/routes/test_memories_global_delete.py tests/services/test_memories_global_delete.py -v
```

**Backend (full suite)**:
```bash
cd backend && python -m pytest -v
```

### Test Mocking Pattern

All tests mock `app.services.memory_service.MemoryClient` directly. The `client.get()` return value simulates the Mem0 ownership check; the `client.delete()` return value simulates the actual deletion. Circuit breaker OPEN state is tested by mocking `app.services.memory_service.get_mem0_circuit_breaker` to return a mock breaker whose `.state` attribute equals `"open"`.

---

## Known Limitations

- The endpoint deletes any memory the user owns, regardless of whether it is truly global (no `agent_id`) or character-scoped. If a client passes a character-scoped `memory_id` to this endpoint, the deletion will succeed as long as the user owns the memory. The character-scoped delete endpoint (`DELETE /characters/:id/memories/:memId`) is the canonical path for character memories, but this endpoint does not enforce that boundary. This is an intentional design decision — ownership is sufficient authorization.
- There is no bulk-delete endpoint for global memories. Deleting all global memories requires one request per memory ID from the `GET /api/v1/memories` list.
- The ownership validation costs one extra Mem0 round-trip (`client.get()` before `client.delete()`). Under high load this doubles the Mem0 call count for delete operations.

---

## Extending This Feature

**Adding a bulk global memory delete endpoint**: The `MemoryService` class in `backend/app/services/memory_service.py` is the right place to add a `delete_all_global_memories()` method, following the pattern of `delete_all_character_memories()`. Use `client.delete_all(user_id=mem0_user_id)` without an `agent_id` argument to target only global memories.

**Adding mobile UI**: When the mobile memory management screen is built, use `GET /api/v1/memories` to list global memories and `DELETE /api/v1/memories/{memory_id}` to remove them. The `id` field from each `MemoryItem` in the list response is the value to pass as `memory_id`.

**Modifying error handling for "not found"**: The `"not found"` / `"404"` string matching in `delete_global_memory()` mirrors the pattern in `delete_character_memory()`. If Mem0 SDK error types become more structured in the future, update both methods together to use typed exceptions instead of string matching.

---

## Related Documentation

- [AI Memory System](../05-ai-bellek.md) — Memory Transparency Principles, Mem0 architecture
- [Database Schema and API](../04-veri-api.md) — Full API contract including `DELETE /memories/:memId`
- [Mem0 Circuit Breaker](./mem0-circuit-breaker.md) — Circuit breaker pattern used by this feature
- [Memory Endpoints](./memory-endpoints.md) — P01-08, which this feature extends
