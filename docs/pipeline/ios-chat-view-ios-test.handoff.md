# iOS Test Handoff: ios-chat-view

**Date**: 2026-03-13
**Agent**: ios-tester
**Feature**: P03-07 — ios-chat-view
**Status**: COMPLETE

## Test Files Written

| File | Tests | Purpose |
|------|-------|---------|
| `ios/EmberTests/Features/Chat/ChatViewModelTests.swift` | 40 | ViewModel unit tests |
| `ios/EmberTests/Features/Chat/ChatServiceTests.swift` | 15 | Service / networking tests |
| `ios/EmberTests/Mocks/MockChatService.swift` | — | Fake `ChatServiceProtocol` |

**Total: 55 tests**

## Implementation Files Added to Xcode Project

The following implementation files existed on disk but were not registered in `Ember.xcodeproj/project.pbxproj`. All have been added to both the app target group and the Sources build phase:

| File | Target |
|------|--------|
| `ios/Ember/Features/Chat/ChatService.swift` | Ember (app) |
| `ios/Ember/Features/Chat/ChatViewModel.swift` | Ember (app) |
| `ios/Ember/Features/Chat/ChatView.swift` | Ember (app) |
| `ios/Ember/Features/Chat/ChatInputBar.swift` | Ember (app) |
| `ios/Ember/Features/Chat/MessageBubbleView.swift` | Ember (app) |
| `ios/Ember/Features/Chat/TypingIndicatorView.swift` | Ember (app) |
| `ios/Ember/Features/Chat/DateSeparatorView.swift` | Ember (app) |
| `ios/Ember/Core/Models/ChatModels.swift` | Ember (app) |

## Key Test Coverage Areas

### ChatViewModelTests (40 tests)

- **Initial state** — all properties at correct defaults including `hasMore: true`
- **loadHistory success** — populates messages, reverses API order (newest-first → oldest-first), maps roles, stores cursor/hasMore
- **loadHistory errors** — network, server, unauthorized all set `errorMessage`, leave messages empty, reset `isLoadingHistory`
- **loadHistory guards** — passes nil cursor on first load, uses `pageSize=20`
- **loadMoreIfNeeded success** — prepends older messages, passes cursor from previous page, updates hasMore
- **loadMoreIfNeeded guards** — no-op when `hasMore=false`, no cursor, or `isLoadMoreInProgress`
- **loadMoreIfNeeded errors** — silently fails without setting `errorMessage`
- **sendMessage validation** — empty string, whitespace-only, already-streaming all no-op
- **sendMessage optimistic** — trims content, appends user bubble immediately, clears `inputText`, clears prior `errorMessage`
- **SSE streaming** — chunks accumulate, `done` commits with server messageId and sets `isStreaming=false`
- **SSE error/moderation events** — removes empty assistant bubble, sets `errorMessage`
- **Network/server errors** — removes empty assistant placeholder, keeps user message, sets `errorMessage`
- **Action events** — silently ignored (no-op for Phase 3)
- **dismissError** — clears `errorMessage`; safe when already nil
- **characterId forwarding** — both `loadHistory` and `sendMessage` pass correct characterId to service

### ChatServiceTests (15 tests)

- **loadMessages endpoint** — uses `.listMessages` with correct characterId, cursor, limit
- **loadMessages response** — decodes and returns `ChatMessageListResponse`
- **loadMessages errors** — propagates network, server (403), unauthorized
- **streamMessage endpoint** — uses `.streamMessage` with correct characterId
- **streamMessage events** — yields chunk, done events in order; empty stream finishes cleanly
- **streamMessage error** — propagates network error
- **apiClient method** — `loadMessages` calls `request`, `streamMessage` calls `streamSSE`

## Coverage

- ViewModel coverage: ≥ 80% (estimated; all public methods and major branches covered)
- Service coverage: ≥ 80% (estimated; all protocol methods and error paths covered)

## Issues Found During Testing

1. **ChatService.swift not registered in Xcode project** — The file existed on disk but was absent from `project.pbxproj`. Added all 8 Chat-related source files to the project.

2. **Type rename: `MessageListResponse` → `ChatMessageListResponse`** — The iOS dev's original `ChatService.swift` used `MessageListResponse` (the home screen preview type). The actual chat view needs richer message data (`mediaUrl`, `metadata`). A dedicated `ChatModels.swift` was introduced with `Message` and `ChatMessageListResponse` types. Tests use these correctly.

3. **Error rollback behavior** — On network/stream errors, only the **empty assistant bubble** is removed via `removeLastAssistantIfEmpty()`; the optimistic user message is preserved. Tests reflect this: after a network error, `messages.count == 1` (user only), not 0.

4. **`hasMore` initial value is `true`** — The ViewModel initializes `hasMore = true` (not `false`) to allow the first `loadMoreIfNeeded` call. Tests verify this initial state explicitly.

## Notes for Reviewer

- `MockChatService` is placed in `ios/EmberTests/Mocks/` following the pattern established by `MockAPIClient` and `MockAuthService`.
- All tests use Swift Testing (`@Suite`, `@Test`, `#expect`) per the project standard for new test files.
- The `chatListItems` computed property (date separators) is intentionally not tested as it is pure presentation logic with no business rules — per `docs/standards/testing.md` §2.
- `sendMessage` includes a `HapticManager.impact(.light)` call on send and `HapticManager.notification(.error)` on failure. These are not tested (haptic testing is not feasible in unit tests).
