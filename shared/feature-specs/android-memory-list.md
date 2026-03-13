# Feature Spec: P04-06 -- Android Memory List

**Feature ID**: P04-06
**Phase**: 4
**Layer**: android
**GitHub Issue**: #33
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature replaces the `MemoriesScreen` placeholder in the Android app with a production Memories screen. The screen shows the user what their AI characters "know" about them by displaying Mem0 memories with a segment picker, with the ability to delete individual memories.

The screen consists of:

1. **Character segment picker** -- A horizontally scrollable row of pill-shaped chips. First chip is "Global" (always present), followed by one chip per character. Selected chip uses `EmberPrimary` background. Tapping fires selection haptic.

2. **Memory list** -- A `LazyColumn` displaying memory items for the currently selected segment. Each item shows a brain icon, memory text, and relative timestamp. Memories are not paginated (backend returns all in one response).

3. **Swipe-to-delete** -- `SwipeToDismissBox` with end-to-start swipe revealing a red delete background. Triggers a confirmation dialog. On confirmation, DELETE API is called and item is removed from list.

4. **Empty state** -- Psychology icon with "No memories yet" message when a segment has no memories.

5. **Loading state** -- `CircularProgressIndicator` centered on screen during initial load and segment switches.

6. **Error state** -- Error icon with message and retry button when API calls fail.

### Dependencies

- **P04-01** (android-scaffold) -- Provides navigation, theme, bottom bar, Hilt setup.
- **P04-03** (android-home-view) -- Provides `Character`, `CharacterListResponse` models.
- **P01-08** (memory-endpoints) -- Backend memory endpoints.
- **P1.5-08** (global-memory-delete) -- Backend global memory delete endpoint.

### What This Feature Does NOT Do

- Does not implement "Delete All" for a character's memories.
- Does not implement memory category grouping (Fitness, Nutrition, etc.).
- Does not implement memory search or filtering.
- Does not change any backend code.

---

## 2. Data Models

### Kotlin Models

#### MemoryItem (new, in core/models/)

```kotlin
@Serializable
data class MemoryItem(
    val id: String,
    val memory: String,
    @SerialName("created_at") val createdAt: String? = null,
)
```

#### MemoryListResponse (new, in core/models/)

```kotlin
@Serializable
data class MemoryListResponse(
    val memories: List<MemoryItem>,
)
```

---

## 3. API Endpoints

No new endpoints. This feature calls existing backend endpoints:

- `GET /api/v1/characters` -- List characters for segment picker
- `GET /api/v1/characters/:id/memories` -- Character-scoped memories
- `DELETE /api/v1/characters/:id/memories/:memoryId` -- Delete character memory
- `GET /api/v1/memories` -- Global memories
- `DELETE /api/v1/memories/:memoryId` -- Delete global memory

---

## 4. Android Screens and Components

### 4.1 MemoriesScreen

Replaces the placeholder. Observes `MemoriesViewModel.uiState` via `collectAsStateWithLifecycle`. Renders `Loading`, `Success` (with sub-states for loading memories and empty), or `Error`.

### 4.2 CharacterPicker

`LazyRow` of pill-shaped chips. "Global" chip first, then character chips. Selected chip uses `EmberPrimary` background. Haptic feedback on tap.

### 4.3 MemoryRow

Card with brain icon (`Icons.Outlined.Psychology`), memory text, and relative timestamp. Wrapped in `SwipeToDismissBox` for swipe-to-delete.

### 4.4 DeleteConfirmationDialog

`AlertDialog` with "Delete Memory?" title, descriptive message, Cancel and Delete buttons. Delete button fires `HapticFeedbackConstants.LONG_PRESS`.

### 4.5 MemoriesViewModel

`@HiltViewModel` with `StateFlow<MemoriesUiState>`. Methods: `loadInitialData()`, `selectSegment()`, `deleteMemory()`, `retryLoadMemories()`.

### 4.6 MemoriesRepository

`@Singleton` with `@Inject` constructor. Wraps `MemoryApi` calls in `Result`. Handles error parsing following `HomeRepository` pattern.

### 4.7 MemoryApi

Retrofit interface with 5 endpoints for characters, character memories, global memories, and deletions.

---

## 5. File Manifest

```
Android:
  CREATE  android/app/src/main/java/ai/ember/app/core/models/MemoryModels.kt
  CREATE  android/app/src/main/java/ai/ember/app/features/memories/MemoryApi.kt
  CREATE  android/app/src/main/java/ai/ember/app/features/memories/MemoriesRepository.kt
  CREATE  android/app/src/main/java/ai/ember/app/features/memories/MemoriesUiState.kt
  CREATE  android/app/src/main/java/ai/ember/app/features/memories/MemoriesViewModel.kt
  CREATE  android/app/src/main/java/ai/ember/app/features/memories/MemoriesModule.kt
  MODIFY  android/app/src/main/java/ai/ember/app/features/memories/MemoriesScreen.kt
  MODIFY  android/app/src/main/res/values/strings.xml
  CREATE  android/app/src/test/java/ai/ember/app/features/memories/MemoriesViewModelTest.kt
  CREATE  android/app/src/test/java/ai/ember/app/features/memories/MemoriesRepositoryTest.kt

Shared:
  CREATE  shared/feature-specs/android-memory-list.md
  CREATE  docs/pipeline/android-memory-list-architect.handoff.md
  CREATE  docs/pipeline/android-memory-list-android-dev.handoff.md
```

---

## 6. Acceptance Criteria

1. Given the user taps the "Memories" tab, when the view loads, then the character picker shows "Global" chip followed by one chip per character, and "Global" is selected by default.

2. Given "Global" is selected, when the view loads, then global memories from `GET /api/v1/memories` are displayed.

3. Given the user taps a character chip, when tapped, then memories from `GET /api/v1/characters/:id/memories` are displayed.

4. Given a segment has no memories, then an empty state with "No memories yet" is shown.

5. Given the user swipes left on a memory row, then a red delete background is revealed and a confirmation dialog appears.

6. Given the user confirms deletion of a global memory, then `DELETE /api/v1/memories/:memoryId` is called and the memory is removed from the list.

7. Given the user confirms deletion of a character memory, then `DELETE /api/v1/characters/:id/memories/:memoryId` is called and the memory is removed from the list.

8. Given the user cancels deletion, then the memory remains in the list.

9. Given the API call to fetch memories fails, then an error state is shown with a retry button.

10. Given a character chip is tapped, then haptic feedback fires.

11. Given the app is in dark mode, then all elements use colors from the Ember theme.

12. Given memories are loading, then a centered progress indicator is shown.
