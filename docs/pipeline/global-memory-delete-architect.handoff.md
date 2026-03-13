# Architect Handoff: Global Memory Delete

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

A single new endpoint `DELETE /api/v1/memories/{memory_id}` that allows users to delete individual global (non-character-scoped) memories from Mem0. The endpoint validates memory ownership by fetching the memory from Mem0 and comparing the `user_id` field against the authenticated user's `mem0_user_id`. This completes the memory CRUD surface: users can already list global memories (`GET /api/v1/memories`) and delete character-scoped memories, but could not delete individual global memories until now.

## Key Decisions

- **Ownership via Mem0 `client.get()`**: Since global memories have no associated character, ownership is validated by fetching the memory from Mem0 and checking its `user_id` metadata. This adds one extra Mem0 call per delete but is necessary for security.
- **No scope enforcement**: The endpoint does not verify that the memory is specifically "global" (no `agent_id`). The ownership check is sufficient authorization -- the user owns all their memories regardless of scope.
- **Idempotent deletion**: Consistent with the existing character-scoped delete, non-existent memory IDs return 204 rather than 404.
- **No `main.py` changes**: The new route is added to the existing `global_router` which is already registered under `/api/v1`.
- **Circuit breaker integration**: Both the `client.get()` and `client.delete()` calls go through the existing Mem0 circuit breaker.

## Spec Location

`shared/feature-specs/global-memory-delete.md`

## Assumptions Made

- The Mem0 SDK's `client.get(memory_id)` returns a dict that includes a `user_id` field matching the value passed during `client.add()`. This is based on the Mem0 API documentation and SDK behavior.
- The Mem0 `client.get()` raises an exception (containing "not found" or "404" in the message) when the memory does not exist, consistent with how `client.delete()` behaves for missing memories.

## Dependencies

- Requires: P01-08 (memory-endpoints) -- must be implemented first (existing code confirms it is)
- Requires: P1.5-04 (mem0-circuit-breaker) -- must be implemented first (existing code confirms it is)
- Blocks: backend-dev, backend-tester (they wait for this spec)

## Next Steps

backend-dev should read the spec and implement. backend-tester follows after implementation.
