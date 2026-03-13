# Architect Handoff: iOS Memory List View

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed
The MemoriesView screen for iOS, replacing the placeholder. It displays Mem0 memories grouped by character via a horizontal segment picker (with a "Global" option), supports swipe-to-delete with confirmation, and handles empty/loading/error states. No backend changes are needed -- all endpoints already exist.

## Key Decisions
- **Global memories as default segment**: The "Global" chip is selected first on load because global memories (visible to all characters) are the most general and give the user an immediate overview. Character-specific memories are one tap away.
- **No category grouping in this phase**: Mem0 does not return a `category` field. Memories are displayed as a flat list. Category-based grouping (Fitness, Nutrition, etc.) would require client-side NLP classification or Mem0 metadata, which is deferred.
- **No "Delete All" UI**: While the backend supports `DELETE /characters/:id/memories` (clear all), the UI only offers individual deletion. Bulk delete is a power-user action better suited for a future settings or danger-zone screen.
- **Two new APIEndpoint cases required**: The existing `APIEndpoint` enum has `listMemories(characterId:)` and `deleteMemory(characterId:memoryId:)` for character-scoped operations, but global memory endpoints (`GET /memories`, `DELETE /memories/:id`) had no corresponding enum cases. The spec adds `listGlobalMemories` and `deleteGlobalMemory(memoryId:)`.
- **MemorySegment enum**: Rather than tracking selected character as an optional Character, a dedicated `MemorySegment` enum (`.global` vs `.character(id:name:)`) cleanly models the two API paths without ambiguity.

## Spec Location
`shared/feature-specs/ios-memory-list.md`

## Assumptions Made
- The `Character` and `CharacterListResponse` models created in P03-06 (ios-home-view) are available in `ios/Ember/Core/Models/CharacterModels.swift`.
- `MockAPIClient` from P03-02 test infrastructure supports adding response stubs per endpoint. The test plan assumes the mock can handle the new global memory endpoint cases.
- The character list is small enough (1-6 characters) that fetching all characters for the segment picker is a single non-paginated call.

## Dependencies
- Requires: P03-06 (Character models), P03-02 (network layer), P03-03 (auth), P03-01 (scaffold), P01-08 (backend memory endpoints)
- Blocks: ios-dev (implements this spec)

## Next Steps
ios-dev should read the spec and implement. No backend or Android work needed.
