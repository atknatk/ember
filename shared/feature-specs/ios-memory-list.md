# Feature Spec: P03-08 -- iOS Memory List View

**Feature ID**: P03-08
**Phase**: 3
**Layer**: ios
**GitHub Issue**: #24
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature replaces the `MemoriesPlaceholderView` in `MainTabView` with a production `MemoriesView` screen. MemoriesView shows the user what their AI characters "know" about them by displaying Mem0 memories grouped by character, with the ability to delete individual memories.

The screen consists of:

1. **Character segment picker** -- A horizontally scrollable row of pill-shaped chips at the top. Each chip shows a character name. An additional "Global" chip appears first. Tapping a chip selects that character and loads its memories. The selected chip is highlighted with `Color.emberPrimary`.

2. **Memory list** -- A `LazyVStack` displaying memory items for the currently selected character (or global memories when "Global" is selected). Each memory item shows the memory text and a relative timestamp. Memories are not paginated (the backend returns all memories in a single response; see Key Decision P01-08).

3. **Swipe-to-delete** -- Swiping a memory item left reveals a red "Delete" action. Tapping it shows a confirmation alert. On confirmation, the memory is deleted from Mem0 via the appropriate DELETE endpoint. The item is removed from the list with a slide-out animation.

4. **Empty state** -- When a character has no memories, a centered illustration-style empty state is shown with a message such as "No memories yet. Start chatting and I'll remember what matters."

5. **Loading state** -- A `ProgressView` centered on screen while memories are being fetched.

6. **Error state** -- An error alert with "OK" (dismiss) and "Retry" buttons when the API call fails.

### Why It Exists

Mem0 transparency is a core principle of Ember (see `docs/05-ai-bellek.md`, "Memory Transparency Principles"). Users must be able to see exactly what each character has learned about them and delete any memory they want removed. This builds trust and gives users control over their AI companion's knowledge.

### Dependencies

- **P03-06** (ios-home-view) -- Provides `Character` and `CharacterListResponse` models, and the `HomeViewModel.templateIcon(for:)` helper that maps template strings to SF Symbols.
- **P03-02** (ios-network-layer) -- Provides `APIClient` with `request()` and `requestVoid()`, `APIEndpoint`, `APIError`.
- **P03-03** (ios-cognito-auth) -- Provides `AuthService.getAccessToken()` for authenticated API calls.
- **P03-01** (ios-scaffold) -- Provides `AppContainer`, `AppRouter`, design system extensions (`Color+Ember`, `Font+Ember`, `CGFloat+Ember`), `HapticManager`, `EmberSymbol`.
- **P01-08** (memory-endpoints, backend) -- Provides `GET /api/v1/characters/:id/memories`, `DELETE /api/v1/characters/:id/memories/:memoryId`, `GET /api/v1/memories`, `DELETE /api/v1/memories/:memoryId`.

### What This Feature Does NOT Do

- It does not implement "Delete All" for a character's memories. While the backend supports `DELETE /api/v1/characters/:id/memories`, the iOS UI only exposes individual memory deletion in this phase. Bulk delete can be added later.
- It does not implement memory category grouping (Fitness, Nutrition, Personality, etc.). Mem0 does not return a `category` field in its API response. The memories are shown as a flat list. Category grouping is a future enhancement that would require either Mem0 metadata or client-side classification.
- It does not implement memory search or filtering.
- It does not change any backend code. All endpoints are fully implemented.

---

## 2. Data Models

No database changes. This is an iOS-only feature.

### Swift Models

#### MemoryItem (new model file)

Maps to the backend's `MemoryItem` Pydantic schema (see `backend/app/schemas/memory.py`).

```
struct MemoryItem: Codable, Identifiable, Equatable {
    let id: String
    let memory: String
    let createdAt: Date?
}
```

#### MemoryListResponse (new model)

Maps to the backend's `MemoryListResponse` Pydantic schema.

```
struct MemoryListResponse: Codable {
    let memories: [MemoryItem]
}
```

These structs are decoded using `JSONDecoder.ember` which converts `snake_case` keys to `camelCase` properties automatically.

---

## 3. API Endpoints

No new endpoints. This feature calls existing backend endpoints.

### GET /api/v1/characters/:id/memories

```
GET /api/v1/characters/:id/memories
Auth: Bearer JWT required
Request headers: none (beyond Authorization)
Request body: none

Response 200:
{
    "memories": [
        {
            "id": "mem0-uuid-string",
            "memory": "Prefers morning workouts",
            "created_at": "2026-02-20T10:00:00Z"
        }
    ]
}

Response 401: { "detail": "..." }
Response 404: { "detail": "Character not found" }
Response 503: { "detail": "Memory service unavailable" }
```

The `APIEndpoint.listMemories(characterId:)` case already exists in `APIEndpoint.swift` (path: `/api/v1/characters/{id}/memories`, method: GET, requiresAuth: true).

### GET /api/v1/memories

```
GET /api/v1/memories
Auth: Bearer JWT required
Request headers: none (beyond Authorization)
Request body: none

Response 200:
{
    "memories": [
        {
            "id": "mem0-uuid-string",
            "memory": "Name is Alex, prefers short responses",
            "created_at": "2026-02-18T08:00:00Z"
        }
    ]
}

Response 401: { "detail": "..." }
Response 503: { "detail": "Memory service unavailable" }
```

This endpoint does NOT currently have an `APIEndpoint` case. A new case `listGlobalMemories` must be added.

### DELETE /api/v1/characters/:id/memories/:memoryId

```
DELETE /api/v1/characters/:id/memories/:memoryId
Auth: Bearer JWT required
Request body: none

Response 204: (no body)
Response 401: { "detail": "..." }
```

Idempotent -- returns 204 even if the memory does not exist. The `APIEndpoint.deleteMemory(characterId:memoryId:)` case already exists.

### DELETE /api/v1/memories/:memoryId

```
DELETE /api/v1/memories/:memoryId
Auth: Bearer JWT required
Request body: none

Response 204: (no body)
Response 401: { "detail": "..." }
```

Idempotent -- returns 204 even if the memory does not exist. This endpoint does NOT currently have an `APIEndpoint` case. A new case `deleteGlobalMemory(memoryId:)` must be added.

---

## 4. Backend Logic

Not applicable. This is an iOS-only feature. The backend endpoints are fully implemented in `backend/app/routes/memories.py` and `backend/app/services/memory_service.py`.

---

## 5. iOS Screens and Components

### 5.1 MemoriesView

**File path**: `ios/Ember/Features/Memories/MemoriesView.swift`

**Replaces**: `ios/Ember/Features/Memories/MemoriesPlaceholderView.swift` (this file is deleted)

**Navigation**: Shown as the second tab in `MainTabView`. The user arrives by tapping the "Memories" tab (brain icon). No inbound navigation from other screens in this phase.

**View structure**:

```
VStack(spacing: 0) {
    CharacterPickerView(
        characters: viewModel.characters,
        selectedSegment: $viewModel.selectedSegment,
        onSelect: { segment in viewModel.selectSegment(segment) }
    )
    .padding(.horizontal, .emberSpacing20)
    .padding(.vertical, .emberSpacing12)

    if viewModel.isLoading {
        // Centered ProgressView
    } else if viewModel.memories.isEmpty {
        // Empty state view
    } else {
        // Memory list
        ScrollView {
            LazyVStack(spacing: .emberSpacing8) {
                ForEach(viewModel.memories) { memory in
                    MemoryRowView(memory: memory)
                        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                            Button(role: .destructive) {
                                viewModel.memoryToDelete = memory
                            } label: {
                                Label("Delete", systemImage: "trash")
                            }
                        }
                }
            }
            .padding(.horizontal, .emberSpacing20)
        }
    }
}
.background(Color.emberBackground.ignoresSafeArea())
.navigationTitle("Memories")
.navigationBarTitleDisplayMode(.large)
.task { await viewModel.loadInitialData() }
.alert("Delete Memory?", isPresented: $viewModel.showDeleteConfirmation) { ... }
.alert("Error", isPresented: $viewModel.showError) { ... }
```

**State binding**: `@State private var viewModel: MemoriesViewModel`

**ViewModel initialization**: Initialized in `init()` via `_viewModel = State(initialValue: MemoriesViewModel(apiClient: APIClient.shared))`.

**Loading state**: When `viewModel.isLoading` is true, show a centered `ProgressView` with `.tint(Color.emberPrimary)`.

**Empty state**: When `viewModel.isLoading` is false and `viewModel.memories` is empty, show a `VStack` with:
- SF Symbol `brain.head.profile` in `Color.emberTextSecondary` at 48pt
- Title "No memories yet" in `.emberTitle` font, `Color.emberTextPrimary`
- Body "Start chatting and I'll remember what matters." in `.emberBody` font, `Color.emberTextSecondary`
- Centered vertically in the available space

**Error state**: When `viewModel.showError` is true, show a `.alert("Error", ...)` with `viewModel.errorMessage` and buttons "OK" (dismiss) and "Retry" (calls `Task { await viewModel.loadMemories() }`).

**Delete confirmation alert**: When `viewModel.showDeleteConfirmation` is true, show `.alert("Delete Memory?", ...)` with message "This memory will be permanently removed. This action cannot be undone." and buttons "Cancel" (cancel role) and "Delete" (destructive role, calls `Task { await viewModel.confirmDelete() }`).

### 5.2 CharacterPickerView

**File path**: inline in `ios/Ember/Features/Memories/MemoriesView.swift` as a private subview, or extracted as a separate file if large

**Purpose**: Horizontally scrollable segment picker that lets the user switch between characters (and global memories).

**UI elements**:

- Container: `ScrollView(.horizontal, showsIndicators: false)`
- Content: `HStack(spacing: .emberSpacing8)` containing pill-shaped buttons
- First pill: "Global" -- represents global memories (no agent_id). Always present.
- Subsequent pills: One per character, showing the character's name.
- Selected pill: `Color.emberPrimary` background, white text, `.emberCaption` font, `.fontWeight(.semibold)`.
- Unselected pill: `Color.emberSurface2` background, `Color.emberTextSecondary` text, `.emberCaption` font.
- Pill shape: `Capsule()` with padding `.horizontal(.emberSpacing12)` and `.vertical(.emberSpacing8)`.
- Tap on pill: calls `onSelect` closure, triggers haptic `HapticManager.selection()`.

**Accessibility**: Each pill has `accessibilityLabel("{characterName} memories")` and `accessibilityAddTraits(.isButton)`. The selected pill adds `.isSelected` trait.

**Animation**: When selection changes, the selected pill background animates with `.animation(.easeInOut(duration: 0.2))`.

### 5.3 MemoryRowView

**File path**: `ios/Ember/Features/Memories/MemoryRowView.swift`

**Purpose**: Displays a single memory item in the list.

**UI elements**:

- Container: `HStack(alignment: .top, spacing: .emberSpacing12)` inside a `RoundedRectangle(cornerRadius: .emberRadius12)` filled with `Color.emberSurface2`, padded `.emberSpacing16`.
- Leading icon: SF Symbol `brain.head.profile` in `Color.emberPrimary`, 16pt, inside a 32pt circle of `Color.emberSurface3`.
- Memory text: The `memory` string in `.emberBody` font, `Color.emberTextPrimary`. Multi-line, no truncation.
- Timestamp: Below the memory text, the `createdAt` date formatted as relative time ("2 weeks ago") in `.emberMicro` font, `Color.emberTextSecondary`. If `createdAt` is nil, this line is omitted.

**Accessibility**: `accessibilityLabel("Memory: {memoryText}. Created {relativeTime}")`. The swipe-to-delete action has `accessibilityLabel("Delete memory")`.

**Animation**: When deleted, the row slides out to the trailing edge with `.transition(.asymmetric(insertion: .opacity, removal: .move(edge: .trailing).combined(with: .opacity)))`.

### 5.4 MemoriesViewModel

**File path**: `ios/Ember/Features/Memories/MemoriesViewModel.swift`

**Class definition**: `@Observable final class MemoriesViewModel`

**Properties**:

| Property | Type | Purpose |
|----------|------|---------|
| `characters` | `[Character]` | All active characters, fetched on initial load |
| `selectedSegment` | `MemorySegment` | Currently selected segment: `.global` or `.character(id: String, name: String)` |
| `memories` | `[MemoryItem]` | Memories for the currently selected segment |
| `isLoading` | `Bool` | True during memory fetch |
| `isLoadingCharacters` | `Bool` | True during initial character list fetch |
| `errorMessage` | `String?` | Non-nil when an error occurs |
| `showError` | `Bool` | Controls error alert presentation |
| `memoryToDelete` | `MemoryItem?` | Set when user swipes to delete; triggers confirmation |
| `showDeleteConfirmation` | `Bool` | Computed: `memoryToDelete != nil` (with setter that clears `memoryToDelete` on false) |

**Enum**:

```
enum MemorySegment: Hashable {
    case global
    case character(id: String, name: String)
}
```

**Private properties**:

| Property | Type | Purpose |
|----------|------|---------|
| `apiClient` | `APIClientProtocol` | Injected network client |

**Constructor**: `init(apiClient: APIClientProtocol = APIClient.shared)`

**Methods**:

`func loadInitialData() async`

1. Set `isLoadingCharacters = true`.
2. Fetch the character list: `apiClient.request(endpoint: .listCharacters, responseType: CharacterListResponse.self)`.
3. On success: set `characters` to the response's `characters` array.
4. On failure: set `errorMessage`, set `showError = true`, set `isLoadingCharacters = false`, return.
5. Set `isLoadingCharacters = false`.
6. Set `selectedSegment = .global` (default initial selection).
7. Call `await loadMemories()`.

`func selectSegment(_ segment: MemorySegment) async`

1. Guard that `segment != selectedSegment`, otherwise return.
2. Set `selectedSegment = segment`.
3. Call `await loadMemories()`.

Note: Because this is called from a Button tap, wrap in `Task { await viewModel.selectSegment(segment) }` at the call site.

`func loadMemories() async`

1. Set `isLoading = true`, clear `errorMessage`.
2. Based on `selectedSegment`:
   - `.global`: call `apiClient.request(endpoint: .listGlobalMemories, responseType: MemoryListResponse.self)`.
   - `.character(let id, _)`: call `apiClient.request(endpoint: .listMemories(characterId: id), responseType: MemoryListResponse.self)`.
3. On success: set `memories` to the response's `memories` array.
4. On failure: set `errorMessage` to the error description, set `showError = true`.
5. Set `isLoading = false`.

`func confirmDelete() async`

1. Guard `let memory = memoryToDelete` else return.
2. Based on `selectedSegment`:
   - `.global`: call `apiClient.requestVoid(endpoint: .deleteGlobalMemory(memoryId: memory.id))`.
   - `.character(let id, _)`: call `apiClient.requestVoid(endpoint: .deleteMemory(characterId: id, memoryId: memory.id))`.
3. On success:
   - Remove the memory from `memories` array with animation: `withAnimation { memories.removeAll { $0.id == memory.id } }`.
   - Fire `HapticManager.impact(.medium)` (memory deleted haptic per `docs/14-tasarim.md`).
4. On failure: set `errorMessage` to the error description, set `showError = true`.
5. Set `memoryToDelete = nil`.

---

## 6. Android Screens and Components

Not applicable. This is an iOS-only feature (layer: ios).

---

## 7. Test Plan

### iOS Tests

#### MemoriesViewModelTests (Swift Testing)

**File path**: `ios/EmberTests/Features/Memories/MemoriesViewModelTests.swift`

**Mock setup**: Use `MockAPIClient` (already exists in the test target from P03-02). The mock must support returning `CharacterListResponse` for `.listCharacters`, `MemoryListResponse` for `.listMemories(characterId:)` and `.listGlobalMemories`, and `Void` for `.deleteMemory(characterId:memoryId:)` and `.deleteGlobalMemory(memoryId:)`.

**Test scenarios**:

1. **loadInitialData fetches characters and then global memories** -- Configure mock to return 2 characters and 3 global memories. Call `loadInitialData()`. Assert `characters.count == 2`, `selectedSegment == .global`, `memories.count == 3`, `isLoading == false`.

2. **loadInitialData sets error when character fetch fails** -- Configure mock to throw `APIError.networkError(...)` for `.listCharacters`. Call `loadInitialData()`. Assert `characters` is empty, `showError == true`, `errorMessage` is not nil.

3. **selectSegment changes segment and loads character memories** -- Load initial data (global). Configure mock to return 2 character memories. Call `selectSegment(.character(id: "char-1", name: "Luna"))`. Assert `selectedSegment` is `.character(id: "char-1", ...)`, `memories.count == 2`.

4. **selectSegment with same segment is a no-op** -- Set `selectedSegment = .global`. Call `selectSegment(.global)`. Assert no API call was made (verify mock call count).

5. **loadMemories sets error on failure** -- Configure mock to throw `APIError.serverError(statusCode: 503, detail: "Memory service unavailable")`. Call `loadMemories()`. Assert `showError == true`, `errorMessage` contains "unavailable".

6. **confirmDelete removes memory from list on success (character memory)** -- Set `selectedSegment` to a character. Populate `memories` with 3 items. Set `memoryToDelete` to the second item. Configure mock to succeed for `.deleteMemory`. Call `confirmDelete()`. Assert `memories.count == 2`, the deleted memory is absent.

7. **confirmDelete removes memory from list on success (global memory)** -- Set `selectedSegment = .global`. Populate `memories` with 2 items. Set `memoryToDelete` to the first item. Configure mock to succeed for `.deleteGlobalMemory`. Call `confirmDelete()`. Assert `memories.count == 1`.

8. **confirmDelete sets error on failure** -- Set `memoryToDelete` to an item. Configure mock to throw. Call `confirmDelete()`. Assert `showError == true`, `memories` count is unchanged (memory was not removed).

9. **confirmDelete clears memoryToDelete** -- Set `memoryToDelete`. Call `confirmDelete()`. Assert `memoryToDelete == nil`.

10. **confirmDelete does nothing when memoryToDelete is nil** -- Set `memoryToDelete = nil`. Call `confirmDelete()`. Assert no API call made.

11. **showDeleteConfirmation is true when memoryToDelete is set** -- Set `memoryToDelete` to an item. Assert `showDeleteConfirmation == true`. Set `memoryToDelete = nil`. Assert `showDeleteConfirmation == false`.

#### UI Tests (XCTest, optional stretch goal)

- Launch app in authenticated + onboarded state with mock server returning characters and memories.
- Verify "Global" chip is selected by default.
- Verify memory items are visible.
- Tap a character chip and verify memory list updates.
- Swipe a memory left and verify "Delete" button appears.
- Tap "Delete", confirm in alert, and verify the memory row disappears.
- Verify empty state is shown when a character has no memories.

---

## 8. Acceptance Criteria

1. Given the user is authenticated and taps the "Memories" tab, when the view loads, then the character picker shows a "Global" chip followed by one chip per character, and "Global" is selected by default.

2. Given "Global" is selected, when the view loads, then global memories from `GET /api/v1/memories` are displayed in a list.

3. Given the user taps a character chip, when the chip is tapped, then the memory list updates to show memories from `GET /api/v1/characters/:id/memories` for that character.

4. Given a character has no memories, when that character is selected, then an empty state view is shown with the message "No memories yet" and a description.

5. Given the user swipes left on a memory row, when the "Delete" action is revealed, then a confirmation alert appears asking "Delete Memory?" with "Cancel" and "Delete" buttons.

6. Given the user confirms deletion of a character memory, when "Delete" is tapped in the alert, then `DELETE /api/v1/characters/:id/memories/:memoryId` is called, the memory row slides out of the list, and a medium haptic fires.

7. Given the user confirms deletion of a global memory, when "Delete" is tapped in the alert, then `DELETE /api/v1/memories/:memoryId` is called, the memory row slides out of the list, and a medium haptic fires.

8. Given the user cancels deletion, when "Cancel" is tapped in the alert, then the memory remains in the list unchanged.

9. Given the API call to fetch memories fails, when the view loads or a segment is selected, then an error alert is shown with "OK" and "Retry" buttons.

10. Given the API call to delete a memory fails, when deletion is confirmed, then an error alert is shown and the memory remains in the list.

11. Given VoiceOver is enabled, when the user navigates the Memories screen, then all character picker chips, memory rows, and the delete action have meaningful accessibility labels.

12. Given a character chip is tapped, then `HapticManager.selection()` fires.

13. Given the app is in dark mode (forced), then all Memories view elements use colors from `Color+Ember.swift` and render correctly on a dark background.

14. Given memories are loading, when the API call is in progress, then a centered progress indicator is shown.

---

## 9. File Manifest

```
iOS:
  CREATE  ios/Ember/Features/Memories/MemoriesView.swift
  CREATE  ios/Ember/Features/Memories/MemoriesViewModel.swift
  CREATE  ios/Ember/Features/Memories/MemoryRowView.swift
  CREATE  ios/Ember/Core/Models/MemoryModels.swift
  DELETE  ios/Ember/Features/Memories/MemoriesPlaceholderView.swift
  MODIFY  ios/Ember/App/MainTabView.swift (replace MemoriesPlaceholderView with MemoriesView)
  MODIFY  ios/Ember/Core/Network/APIEndpoint.swift (add listGlobalMemories and deleteGlobalMemory cases)
  CREATE  ios/EmberTests/Features/Memories/MemoriesViewModelTests.swift

Shared:
  CREATE  shared/feature-specs/ios-memory-list.md (this file)
  CREATE  docs/pipeline/ios-memory-list-architect.handoff.md
```

### Modification Details

**MainTabView.swift**: Replace `MemoriesPlaceholderView()` with `MemoriesView()` on line 34 inside the second tab's `NavigationStack`.

**APIEndpoint.swift**: Add two new cases:

```
// Global Memories
case listGlobalMemories
case deleteGlobalMemory(memoryId: String)
```

The `path` computed property must add:
- `.listGlobalMemories`: returns `"/api/v1/memories"`
- `.deleteGlobalMemory(let memoryId)`: returns `"/api/v1/memories/\(memoryId)"`

The `method` computed property must add:
- `.listGlobalMemories` to the `.get` list
- `.deleteGlobalMemory` to the `.delete` list

The `requiresAuth` property needs no change (the `default: return true` case covers both new endpoints).

The `queryItems` property needs no change (no query parameters for these endpoints).
