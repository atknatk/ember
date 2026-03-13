# Architect Handoff: Android Memory List

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## Feature
- **ID**: P04-06
- **Name**: android-memory-list
- **Layer**: android
- **Phase**: 4

## Spec Location
`shared/feature-specs/android-memory-list.md`

## Key Decisions
- Mirrors iOS MemoriesView behavior (segment picker, swipe-to-delete, empty state)
- Uses `SwipeToDismissBox` (Material 3) for swipe-to-delete
- Confirmation dialog before deletion (per iOS parity)
- `MemorySegment` sealed interface for Global vs Character selection
- Reuses `Character` and `CharacterListResponse` from core models
- New `MemoryItem` and `MemoryListResponse` in core models (shared with future features)
- No pagination on memory list (backend returns all memories in one response)
- Relative time formatting for `created_at` timestamps

## Dependencies
- P04-01 (android-scaffold): Navigation, theme, Hilt
- P04-03 (android-home-view): Character models
- P01-08 (memory-endpoints): Backend APIs
- P1.5-08 (global-memory-delete): Global memory delete endpoint

## Handoff To
android-dev
