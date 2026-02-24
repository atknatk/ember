# Architect Handoff: Memory Endpoints

**Date**: 2026-02-24
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

Four REST endpoints that expose Mem0 memory read and delete operations to mobile clients. Three endpoints are character-scoped (get memories, delete single memory, delete all memories) and one is global (get user-wide memories). All operations are pure Mem0 SDK calls with no database writes -- only character lookup and ownership verification use PostgreSQL.

## Spec Location

`shared/feature-specs/memory-endpoints.md`

## Layer

backend

## Key Decisions

- **No pagination on memory lists**: Mem0 `get_all()` does not natively support cursor pagination, and memory counts per character are expected to be in the dozens to low hundreds. Pagination can be added later if needed.
- **Idempotent single-memory delete**: If the memory_id does not exist in Mem0, the endpoint returns 204 (success) rather than 404. This simplifies client logic and handles race conditions.
- **Two routers in one module**: `memories.py` defines `global_router` (prefix `/api/v1`) and `character_router` (prefix `/api/v1/characters`) to avoid splitting related code across files.
- **`memory_id` is `str` not `uuid.UUID`**: Mem0's internal IDs are treated as opaque strings. Enforcing UUID format on an external service's IDs would be fragile.
- **Character ownership checked on all character-scoped operations**: Defense-in-depth prevents unauthorized memory deletion via guessed memory_id values.
- **Mem0 calls wrapped in `asyncio.to_thread()`**: Consistent with the existing pattern in `chat_service.py`. The Mem0 Python SDK is synchronous.
- **503 for Mem0 failures**: All Mem0 errors surface as HTTP 503 "Memory service unavailable" to the client, per `docs/standards/common.md` Section 7.
- **Field named `memory` not `content`**: Matches Mem0 SDK response format. `docs/04-veri-api.md` example shows `content` but since data comes from Mem0 (not our DB), we keep Mem0's terminology.

## File Manifest

```
Backend:
  CREATE  backend/app/routes/memories.py
  CREATE  backend/app/services/memory_service.py
  CREATE  backend/app/schemas/memory.py
  MODIFY  backend/app/main.py
  CREATE  backend/tests/test_memory_routes.py
  CREATE  backend/tests/test_memory_service.py
  CREATE  backend/tests/test_memory_schemas.py

Shared:
  CREATE  shared/feature-specs/memory-endpoints.md
  CREATE  docs/pipeline/memory-endpoints-architect.handoff.md
```

| Action | Count |
|--------|-------|
| CREATE | 6 |
| MODIFY | 1 |
| **Total** | **7** |

## Assumptions Made

- The Mem0 Python SDK (`mem0ai` package, already in requirements.txt) supports `client.get_all()`, `client.delete()`, and `client.delete_all()` methods with the documented parameters.
- `client.get_all(user_id=X)` without `agent_id` returns only agent-less (global) memories, not all memories for that user across all agents. If this assumption is wrong, the service must filter client-side.
- Mem0 `get_all()` returns a list of dicts with at minimum `id` and `memory` keys. The `created_at` key may or may not be present.
- Memory counts per user-character pair will remain manageable (low hundreds at most) for the foreseeable future, making pagination unnecessary.

## Dependencies

- Requires: P01-01 (project-setup), P01-02 (database-schema), P01-03 (cognito-auth-middleware), P01-05 (character-crud)
- Blocks: Mobile memory display screens (future Phase 2 feature)

## Notes for Developers

- **Mem0 SDK patterns**: See `chat_service.py` lines 377-404 for the established `asyncio.to_thread()` wrapping pattern. Follow it exactly.
- **Router registration**: Two routers from one module, registered with different prefixes in `main.py`. See spec Section 6 for details.
- **No new config values**: `mem0_api_key` already exists in `config.py`.
- **No new dependencies**: `mem0ai` is already installed.
- **Character lookup reuse**: The `_get_owned_character()` helper mirrors `ChatService._get_active_character()` plus the ownership check. Keep it as a private method in `MemoryService` for now.

## Next Steps

backend-dev should read the spec and implement. No iOS or Android work is needed for this backend-only feature.
