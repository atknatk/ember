---
name: ios-memory-list test patterns
description: Patterns established during P03-08 iOS Memory List View testing — MockMemoriesAPIClient with endpoint routing, MemorySegment equality, showDeleteConfirmation computed property, pbxproj already registered by ios-dev
type: project
---

The memories feature (P03-08) ViewModel uses `APIClientProtocol` directly (not a custom service protocol). The mock is a local `MockMemoriesAPIClient` defined inside the test file.

Key mock properties:
- `characterListResponse: CharacterListResponse` — returned for `.listCharacters`
- `memoryListResponse: MemoryListResponse` — returned for `.listGlobalMemories`
- `characterMemoryResponses: [String: MemoryListResponse]` — keyed by characterId, returned for `.listMemories(characterId:)`
- `requestError: Error?` — throws on all `request()` calls (both character fetch and memory fetch)
- `deleteError: Error?` — throws on `requestVoid()` calls (delete operations only)
- `requestCallCount: Int` — tracks total `request()` call count for no-op guard tests
- `requestVoidCallCount: Int` — tracks total `requestVoid()` call count
- `lastEndpoint: APIEndpoint?` — records last endpoint used in both `request` and `requestVoid`
- `lastDeleteEndpoint: APIEndpoint?` — records only the last `requestVoid` endpoint (for delete routing verification)

Key test facts for memories:
- `loadInitialData()` fetches characters first, then auto-loads global memories. If character fetch fails, early return prevents memory fetch. Test by verifying `requestCallCount == 1`.
- `selectSegment()` guard: same segment is a no-op. Call count before/after must be equal.
- `loadMemories()` clears `errorMessage = nil` at start but does NOT reset `showError = false`. `showError` is only set to `true` on error; the UI dismisses it via the alert binding. Do not test `showError == false` after a successful load if it was previously `true`.
- `confirmDelete()` always clears `memoryToDelete = nil` in the finally block, regardless of success or failure.
- `showDeleteConfirmation` is a computed property: getter = `memoryToDelete != nil`, setter (false) = `memoryToDelete = nil`. Setting to `true` has no effect.
- `MemorySegment` is `Hashable` — test equality for both `.global` and `.character(id:name:)` cases since the guard depends on `!=`.
- Endpoint routing in `confirmDelete`: `.global` → `.deleteGlobalMemory(memoryId:)`, `.character(id:name:)` → `.deleteMemory(characterId:memoryId:)`. Verify with `if case .xxx = mock.lastDeleteEndpoint`.

pbxproj notes:
- The ios-dev already registered `MemoriesViewModelTests.swift` in the pbxproj during feature development. No pbxproj changes needed by ios-tester.
- fileRef UUID: `67F5A74CBDE0E187C55FFF79`
- buildFile UUID: `4EEE472BC8875201034D2628`
- Sources build phase: `91FC9734A1965EA61C9B43FF` (same as all other test files)

**Why:** The memories feature uses the same `APIClientProtocol` injection as Home view (unlike Chat which uses a dedicated `ChatServiceProtocol`). The per-endpoint routing mock pattern from P03-06 (HomeViewModel) is reused here.

**How to apply:** For any future ViewModel that injects `APIClientProtocol` directly, create a local `MockXxxAPIClient` in the test file that routes different endpoints via `switch endpoint`. Use `requestError` for GET failures and a separate `deleteError`/`createError` for mutation failures to allow independent error path testing.
