# iOS Dev Handoff: Memory List View

**Date**: 2026-03-13
**Agent**: ios-dev
**Status**: COMPLETE

## Implemented Files
- `ios/Ember/Features/Memories/MemoriesView.swift` (CREATE)
- `ios/Ember/Features/Memories/MemoriesViewModel.swift` (CREATE)
- `ios/Ember/Features/Memories/MemoryRowView.swift` (CREATE)
- `ios/Ember/Core/Models/MemoryModels.swift` (CREATE)
- `ios/EmberTests/Features/Memories/MemoriesViewModelTests.swift` (CREATE)
- `ios/Ember/Core/Network/APIEndpoint.swift` (MODIFY -- added `listGlobalMemories` and `deleteGlobalMemory` cases)
- `ios/Ember/App/MainTabView.swift` (MODIFY -- replaced `MemoriesPlaceholderView` with `MemoriesView`)
- `ios/Ember/Features/Memories/MemoriesPlaceholderView.swift` (DELETE)

## Screens Implemented
- **MemoriesView**: Full memories screen with character segment picker, memory list with swipe-to-delete, empty state, loading state, and error alerts
- **MemoryRowView**: Individual memory row with brain icon, memory text, and relative timestamp

## Deviations from Spec
- Changed memory list from `ScrollView` + `LazyVStack` to `List` with `.listStyle(.plain)` because `swipeActions` modifier only works inside a `List` in SwiftUI. Visual appearance is preserved with hidden separators and custom row backgrounds.

## Notes for iOS Tester
- ViewModel uses `APIClientProtocol` -- create a `MockMemoriesAPIClient` implementing this protocol (see test file for reference implementation)
- `MemorySegment` enum has two cases: `.global` and `.character(id:name:)` -- test both code paths for memory loading and deletion
- `loadInitialData()` fetches characters first, then auto-loads global memories -- test failure at both stages
- `selectSegment()` has a guard that prevents re-loading when the same segment is tapped -- test that no API call is made
- `confirmDelete()` routes to different endpoints based on `selectedSegment` (`.deleteGlobalMemory` vs `.deleteMemory`) -- test both paths
- `showDeleteConfirmation` is a computed property backed by `memoryToDelete` -- setting it to `false` clears `memoryToDelete`
- The mock in tests uses separate `requestError` and `deleteError` properties so you can test delete failures independently from fetch failures
