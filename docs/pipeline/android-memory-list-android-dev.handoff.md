# Android Dev Handoff: Android Memory List

**Date**: 2026-03-13
**Agent**: android-dev
**Status**: COMPLETE

## Implemented Files
- `android/app/src/main/java/ai/ember/app/core/models/MemoryModels.kt`
- `android/app/src/main/java/ai/ember/app/features/memories/MemoryApi.kt`
- `android/app/src/main/java/ai/ember/app/features/memories/MemoriesRepository.kt`
- `android/app/src/main/java/ai/ember/app/features/memories/MemoriesUiState.kt`
- `android/app/src/main/java/ai/ember/app/features/memories/MemoriesViewModel.kt`
- `android/app/src/main/java/ai/ember/app/features/memories/MemoriesModule.kt`
- `android/app/src/main/java/ai/ember/app/features/memories/MemoriesScreen.kt`
- `android/app/src/main/res/values/strings.xml` (modified)
- `android/app/src/test/java/ai/ember/app/features/memories/MemoriesViewModelTest.kt`
- `android/app/src/test/java/ai/ember/app/features/memories/MemoriesRepositoryTest.kt`

## Screens Implemented
- **MemoriesScreen**: Full memory list screen with segment picker (Global + per-character), memory list with swipe-to-delete, delete confirmation dialog, empty state, loading state, error state with retry

## strings.xml Keys Added
- `memories_segment_global`: "Global"
- `memories_global_a11y`: "Global memories"
- `memories_character_a11y`: "%1$s memories"
- `memories_empty_title`: "No memories yet"
- `memories_empty_subtitle`: "Start chatting and I'll remember what matters."
- `memories_retry`: "Retry"
- `memories_delete_title`: "Delete Memory?"
- `memories_delete_message`: "This memory will be permanently removed. This action cannot be undone."
- `memories_delete_confirm`: "Delete"
- `memories_delete_cancel`: "Cancel"
- `memories_delete_a11y`: "Delete memory"
- `memories_row_a11y_prefix`: "Memory: "

## Deviations from Spec
- None

## Notes for Android Tester
- ViewModel depends on `MemoriesRepository` -- use MockK `mockk<MemoriesRepository>()`
- `MemoriesRepository` depends on `MemoryApi` -- use MockK `mockk<MemoryApi>()`
- Turbine is configured in project -- use `.test { }` for StateFlow assertions
- Segment switching: call `viewModel.selectSegment(MemorySegment.CharacterSegment(id, name))`
- Delete flow: call `viewModel.deleteMemory(memoryItem)` -- uses different API based on selected segment
- Swipe-to-delete triggers a confirmation dialog before calling delete
- Haptic feedback fires on segment chip tap (`VIRTUAL_KEY`) and delete confirmation (`LONG_PRESS`)
- `formatRelativeTime()` is a private utility function handling ISO 8601 timestamps
- Memory deletion is optimistic removal after successful API response (not optimistic update)
