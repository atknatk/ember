# iOS Memory List

> Replaces the placeholder Memories tab with a production screen that lets users browse, inspect, and delete everything their AI characters have learned about them via Mem0.

**Status**: Released
**Added in**: Phase 3 (P03-08)
**Platforms**: iOS
**GitHub Issue**: #24

---

## Overview

The Memory List screen gives Ember users full transparency over the long-term memories stored in Mem0. Ember is not session-based — each AI character accumulates memories about the user indefinitely — so it is important that users can see exactly what any character "knows" and remove individual memories if they choose. This is the primary user-control surface for the AI memory system described in `docs/05-ai-bellek.md`.

The screen lives on the second tab of `MainTabView`. On first load, it shows a horizontally scrollable character segment picker at the top with "Global" selected by default. Global memories are facts visible to all characters (e.g., "User's name is Alex, prefers short responses"); character memories are scoped to a single character's `agent_id`. The user switches segments to inspect any character, and swipes left on any row to delete a single memory with a confirmation alert.

This feature is iOS-only and introduces no backend changes. All four API endpoints it uses — list/delete per-character memories and list/delete global memories — were fully implemented in P01-08 (memory-endpoints). The feature's only backend-side addition is two new `APIEndpoint` enum cases on the iOS side for the global memory endpoints, which previously had no client-side routing.

---

## Architecture

### How It Works (Data Flow)

**Initial screen load:**

1. The user taps the "Memories" tab (brain icon) in `MainTabView`.
2. `MemoriesView.task` calls `viewModel.loadInitialData()`.
3. `loadInitialData()` calls `APIClient.request(endpoint: .listCharacters, responseType: CharacterListResponse.self)` to populate the segment picker.
4. On success, `selectedSegment` is set to `.global` and `loadMemories()` is called.
5. `loadMemories()` calls `APIClient.request(endpoint: .listGlobalMemories, responseType: MemoryListResponse.self)`.
6. The response `[MemoryItem]` array is assigned to `viewModel.memories` and the view renders the list.

**Switching to a character segment:**

1. The user taps a character pill in `CharacterPickerView`.
2. The pill's `onSelect` closure fires `HapticManager.selection()` and calls `Task { await viewModel.selectSegment(.character(id:name:)) }`.
3. `selectSegment()` guards against no-op taps (same segment) and calls `loadMemories()`.
4. `loadMemories()` calls `APIClient.request(endpoint: .listMemories(characterId: id), responseType: MemoryListResponse.self)`.
5. The new `[MemoryItem]` array replaces `viewModel.memories`.

**Deleting a memory:**

1. The user swipes left on a `MemoryRowView` and taps the "Delete" action.
2. The swipe action sets `viewModel.memoryToDelete = memory`, which flips `showDeleteConfirmation` to `true` and presents the confirmation alert.
3. The user taps "Delete" in the alert; `Task { await viewModel.confirmDelete() }` is called.
4. `confirmDelete()` routes to:
   - `APIClient.requestVoid(endpoint: .deleteGlobalMemory(memoryId:))` when segment is `.global`
   - `APIClient.requestVoid(endpoint: .deleteMemory(characterId:memoryId:))` when segment is `.character`
5. On success, the memory is removed from `memories` inside `withAnimation { ... }` and `HapticManager.impact(.medium)` fires.
6. `memoryToDelete` is set to `nil`, dismissing the confirmation alert.

### MemorySegment Enum

The ViewModel tracks the selected segment as a `MemorySegment` enum rather than an optional `Character`. This cleanly separates the two API paths without the ambiguity of `nil` meaning "global":

```swift
enum MemorySegment: Hashable {
    case global
    case character(id: String, name: String)
}
```

All `loadMemories()` and `confirmDelete()` branching is a single `switch` on this enum.

### New APIEndpoint Cases

The global memory endpoints did not previously have `APIEndpoint` cases. Two were added in `APIEndpoint.swift`:

| Case | Path | Method |
|------|------|--------|
| `.listGlobalMemories` | `/api/v1/memories` | GET |
| `.deleteGlobalMemory(memoryId:)` | `/api/v1/memories/{memoryId}` | DELETE |

The `requiresAuth` default (`true`) and `queryItems` default (`nil`) cover both cases without additional changes.

### Data Models

`MemoryModels.swift` defines two new Codable structs:

```swift
struct MemoryItem: Codable, Identifiable, Equatable {
    let id: String
    let memory: String
    let createdAt: Date?
}

struct MemoryListResponse: Codable {
    let memories: [MemoryItem]
}
```

Both are decoded with `JSONDecoder.ember`, which converts `snake_case` keys to `camelCase` automatically. `createdAt` is optional because Mem0 may omit it; if absent, the timestamp row in `MemoryRowView` is simply hidden.

### SwiftUI List vs. ScrollView + LazyVStack

The architect spec called for a `ScrollView` + `LazyVStack`. The iOS dev switched to `List` with `.listStyle(.plain)` because SwiftUI's `.swipeActions` modifier only works inside a `List`. Visually the difference is invisible — row separators are hidden and the background is set to `Color.emberSurface2` — but developers extending this screen should keep the `List` container in place to preserve swipe action behavior.

---

## API Reference

See [`docs/04-veri-api.md`](../04-veri-api.md) for the full API contract. This feature uses four endpoints.

### GET /api/v1/memories

**Auth**: Bearer JWT required

Returns all global memories for the authenticated user.

**Response** (200 OK):

```json
{
  "memories": [
    {
      "id": "mem0-uuid-string",
      "memory": "Name is Alex, prefers short responses",
      "created_at": "2026-02-18T08:00:00Z"
    }
  ]
}
```

**Error Responses**:

| Status | When |
|--------|------|
| 401 | Missing or invalid JWT |
| 503 | Mem0 service unavailable |

### GET /api/v1/characters/{character_id}/memories

**Auth**: Bearer JWT required

Returns all memories scoped to a specific character.

**Error Responses**:

| Status | When |
|--------|------|
| 401 | Missing or invalid JWT |
| 404 | Character not found |
| 503 | Mem0 service unavailable |

### DELETE /api/v1/memories/{memory_id}

**Auth**: Bearer JWT required

Deletes a single global memory. Idempotent — returns 204 even if the memory does not exist.

**Response**: 204 No Content

### DELETE /api/v1/characters/{character_id}/memories/{memory_id}

**Auth**: Bearer JWT required

Deletes a single character-scoped memory. Idempotent — returns 204 even if the memory does not exist.

**Response**: 204 No Content

---

## iOS Implementation

**Files**:
- `ios/Ember/Features/Memories/MemoriesView.swift` — SwiftUI view with `CharacterPickerView` (inline private subview), loading/empty/error states, and delete confirmation alert
- `ios/Ember/Features/Memories/MemoriesViewModel.swift` — `@Observable` ViewModel
- `ios/Ember/Features/Memories/MemoryRowView.swift` — Individual memory row with icon, text, and relative timestamp
- `ios/Ember/Core/Models/MemoryModels.swift` — `MemoryItem` and `MemoryListResponse` Codable structs
- `ios/Ember/Core/Network/APIEndpoint.swift` — Modified: added `.listGlobalMemories` and `.deleteGlobalMemory(memoryId:)` cases
- `ios/Ember/App/MainTabView.swift` — Modified: replaced `MemoriesPlaceholderView()` with `MemoriesView()`
- `ios/Ember/Features/Memories/MemoriesPlaceholderView.swift` — Deleted

**Key Patterns**:
- `MemoriesViewModel` is `@Observable` (iOS 17+). Do not add `@Published` or convert to `ObservableObject`.
- `MemoriesView` initializes the ViewModel via `_viewModel = State(initialValue: MemoriesViewModel(apiClient: APIClient.shared))` so it owns the ViewModel's lifetime.
- The ViewModel accepts `APIClientProtocol` in its initializer, enabling full mock injection in tests without subclassing.
- `showDeleteConfirmation` is a computed property backed by `memoryToDelete`: it returns `memoryToDelete != nil`, and its setter clears `memoryToDelete` when set to `false`. This keeps the alert binding in sync with the delete queue without a second boolean.

**State Properties**:

```swift
var characters: [Character] = []
var selectedSegment: MemorySegment = .global
var memories: [MemoryItem] = []
var isLoading: Bool = false
var isLoadingCharacters: Bool = false
var errorMessage: String? = nil
var showError: Bool = false
var memoryToDelete: MemoryItem? = nil
var showDeleteConfirmation: Bool { get set }  // computed from memoryToDelete
```

**CharacterPickerView**: A `ScrollView(.horizontal, showsIndicators: false)` containing an `HStack` of pill-shaped `Capsule()` buttons. The first pill is always "Global". Each pill fires `HapticManager.selection()` on tap and animates its selected background color with `.animation(.easeInOut(duration: 0.2))`.

**Accessibility**:
- Each character picker pill has `accessibilityLabel("{characterName} memories")` and `.isButton` trait; the selected pill adds `.isSelected`.
- Each `MemoryRowView` has `accessibilityLabel("Memory: {memoryText}. Created {relativeTime}")`.
- The swipe-to-delete action has `accessibilityLabel("Delete memory")`.

**Navigation**: The Memories screen is the root view of the second tab's `NavigationStack`. There is no inbound navigation from other screens in this phase — users arrive exclusively by tapping the "Memories" tab. Navigation back to any character's memories from elsewhere in the app is not wired.

---

## Android Implementation

Not applicable. This is an iOS-only feature.

---

## Testing

### Coverage Summary

| Platform | File | Coverage |
|----------|------|----------|
| iOS | `ios/EmberTests/Features/Memories/MemoriesViewModelTests.swift` | >= 80% lines |

### Test Scenarios Covered

The test file uses `MockAPIClient` (from P03-02 test infrastructure) with separate `requestError` and `deleteError` properties so fetch failures and delete failures can be tested independently.

| # | Scenario |
|---|----------|
| 1 | `loadInitialData` fetches characters then global memories |
| 2 | `loadInitialData` sets `showError` when character fetch fails |
| 3 | `selectSegment` loads character memories and updates `selectedSegment` |
| 4 | `selectSegment` with the same segment is a no-op (no API call made) |
| 5 | `loadMemories` sets `showError` when fetch fails (e.g., 503) |
| 6 | `confirmDelete` removes character memory on success |
| 7 | `confirmDelete` removes global memory on success |
| 8 | `confirmDelete` sets `showError` and leaves memory in list on failure |
| 9 | `confirmDelete` always clears `memoryToDelete` |
| 10 | `confirmDelete` does nothing when `memoryToDelete` is nil |
| 11 | `showDeleteConfirmation` mirrors `memoryToDelete` non-nil state |

### Running Tests

```bash
cd ios && xcodebuild test -scheme Ember -destination "platform=iOS Simulator,name=iPhone 16"
```

---

## Known Limitations

- **No "Delete All" UI**: The backend supports `DELETE /api/v1/characters/{id}/memories` (clear all), but this phase exposes only individual deletion. Bulk delete is better suited to a future settings or danger-zone screen.
- **No memory category grouping**: Mem0 does not return a `category` field. Memories are displayed as a flat list. The Fitness / Nutrition / Personality groupings described in `docs/05-ai-bellek.md` would require either Mem0 metadata or client-side classification and are deferred.
- **No memory search or filtering**: The full list is shown as-is; there is no text search or date filter.
- **No offline support**: All four endpoints require live network access. There is no local cache.
- **No pagination**: The backend returns all memories for a character in a single response. If a user accumulates a very large number of memories, the list may grow long. The spec notes this is an acceptable trade-off for Phase 3.
- **Implementation deviation from spec**: The spec specified `ScrollView` + `LazyVStack` for the memory list. The implementation uses `List` with `.listStyle(.plain)` because SwiftUI's `.swipeActions` modifier only functions inside a `List`. Visual appearance is equivalent.

---

## Extending This Feature

**Adding "Delete All" for a character**: Call `APIClient.requestVoid(endpoint: .clearCharacterMemories(characterId: id))` and clear `memories` on success. Add the `.clearCharacterMemories(characterId:)` case to `APIEndpoint.swift` pointing to `DELETE /api/v1/characters/{id}/memories`.

**Adding memory category grouping**: When Mem0 begins returning a `category` field, add an optional `category: String?` property to `MemoryItem`. Then in `MemoriesViewModel`, group `memories` by category using a `Dictionary(grouping:by:)`. Replace `MemoryRowView` rows with section headers per category. The view structure already uses a `List`, which supports `Section` natively.

**Adding memory search**: Add a `@State var searchText: String` to `MemoriesView` and filter `viewModel.memories` client-side with a `.filter { $0.memory.localizedCaseInsensitiveContains(searchText) }` before passing to `ForEach`. No API changes needed.

**Adding an iOS UI test**: Launch the app in an authenticated + onboarded state with a mock server that returns characters and memories. Verify the "Global" chip is selected by default, verify memory rows appear, tap a character chip and confirm the list updates, swipe a row left and confirm the delete action appears, confirm deletion and verify the row disappears with animation, and verify the empty state for a character with no memories.

---

## Related Documentation

- [Memory Endpoints (backend)](memory-endpoints.md) — the four API endpoints this feature consumes
- [iOS Network Layer](ios-network-layer.md) — `APIClient`, `APIEndpoint`, and `APIClientProtocol`
- [iOS Home View](ios-home-view.md) — provides `Character` and `CharacterListResponse` models used by the segment picker
- [iOS Scaffold](ios-scaffold.md) — design system tokens (`Color.emberPrimary`, `HapticManager`, etc.)
- [AI Memory System](../05-ai-bellek.md) — Mem0 memory isolation principles, agent_id format, memory transparency requirements
- [Database Schema & API](../04-veri-api.md)
- [Mobile Screens](../07-mobil.md)
- [Design System](../14-tasarim.md)
