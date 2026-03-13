---
name: ios-chat-view test patterns
description: Patterns established during P03-07 iOS Chat View testing — MockChatService, ChatMessageListResponse, error rollback behavior, pbxproj group IDs for chat tests
type: project
---

The chat feature (P03-07) uses a dedicated `MockChatService` (at `ios/EmberTests/Mocks/MockChatService.swift`) that implements `ChatServiceProtocol`. Set `mock.stubbedPage = ChatMessageListResponse(...)` for history loads and `mock.stubbedSSEEvents = [.chunk(content: "..."), .done(messageId: "...")]` for streaming.

Key test facts for chat:

- `ChatMessageListResponse` (not `MessageListResponse`) is the paginated chat type. It wraps `[Message]` (the richer model in `ChatModels.swift` with `mediaUrl`, `metadata`) rather than `[MessagePreview]`.
- `loadHistory()` reverses the API's newest-first order: `messages = mapResponseToMessages(response).reversed()`. Test with API items `["2", "1"]` → expect `vm.messages.first?.id == "1"`.
- `ChatViewModel.hasMore` starts as `true` (not `false`) — the initial value allows `loadMoreIfNeeded` to eventually fire.
- On network errors inside `sendMessage()`, only the **empty assistant placeholder** is removed via `removeLastAssistantIfEmpty()`; the optimistic user message is preserved. After a network throw, `vm.messages.count == 1` (user only).
- `loadMoreIfNeeded` silently fails on error — no `errorMessage` is set.
- `isLoadMoreInProgress` (private) prevents duplicate load-more calls. The public `isLoadingMore` tracks the loading state.
- `sendMessage` guarded by `!isStreaming` — a second send while streaming is a no-op.

pbxproj group IDs for chat tests:
- Chat app group (under Features `9676E6B923643864824D45B5`): `C1D2E3F4A1B2C3D4E5F6A1B2`
- Chat test group (under EmberTests Features `5CA5541570A18674DB4101FF`): `C2D3E4F5A2B3C4D5E6F7A2B3`
- Sources build phase for EmberTests: `91FC9734A1965EA61C9B43FF` (same as all other test files)

**Why:** First feature with a custom service-layer mock (`MockChatService`) rather than routing through `MockAPIClient`. This is because `ChatServiceProtocol` is the injection point for `ChatViewModel`, not `APIClientProtocol`.

**How to apply:** For any future ViewModel that depends on a custom service protocol (not directly on `APIClientProtocol`), create a `MockXxxService` in `ios/EmberTests/Mocks/`. Use `MockAPIClient` only when testing the service layer itself.
