# iOS Chat View

> Presents a full-screen, real-time conversation between the user and an AI character, with SSE streaming, message bubbles, typing indicator, and cursor-based infinite-scroll history.

**Status**: Released
**Added in**: Phase 3 (P03-07)
**Platforms**: iOS

---

## Overview

The iOS Chat View is the core conversation screen of the Ember app. It is the place where users actually talk to their AI characters. Every character in Ember has one continuous conversation that persists indefinitely (see ADR-003), so the chat screen must handle two distinct data flows: loading historical messages from the server and streaming new responses in real time.

When the user navigates to a character from the Home screen, the Chat View loads the most recent page of messages from `GET /api/v1/characters/{character_id}/messages` and displays them chronologically (oldest at the top, newest at the bottom). As the user scrolls up, older pages load automatically via cursor-based pagination — no OFFSET queries, no page numbers. When the user types a message and taps send, the message appears in the bubble list immediately, an empty assistant bubble is appended as a streaming placeholder, and chunks arrive over SSE and are appended to that bubble in real time. On the `done` SSE event the placeholder is committed with its server-assigned message ID and the `isStreaming` flag is cleared.

The feature consists of two files (`ChatViewModel.swift` and `ChatService.swift`) and depends entirely on the network infrastructure from P03-02. No new API endpoints were added — the screen consumes `POST /api/v1/characters/{character_id}/messages` (streaming) and `GET /api/v1/characters/{character_id}/messages` (pagination) defined in the backend chat-streaming (P01-06) and messages-pagination (P01-07) features.

---

## Architecture

### How It Works (Data Flow)

**Loading history on screen appear:**

1. `HomeView` calls `router.push(.chat(characterId: id))` when the user taps a character card or the daily summary card.
2. `NavigationStack` in `MainTabView` resolves `.chat(characterId:)` to `ChatView(characterId:characterName:)`.
3. `ChatView.task` calls `viewModel.loadHistory()`.
4. `ChatViewModel.loadHistory()` calls `ChatService.loadMessages(characterId:cursor:limit:)` with `cursor: nil` and `limit: 20`.
5. `ChatService` delegates to `APIClient.request(endpoint: .listMessages(characterId:cursor:limit:), responseType: MessageListResponse.self)`.
6. The `APIClient` constructs `GET /api/v1/characters/{character_id}/messages?limit=20`, attaches the Bearer JWT, and executes it with `URLSession`.
7. The JSON response (`items`, `nextCursor`, `hasMore`) is decoded into `MessageListResponse`.
8. `ChatViewModel` maps `MessagePreview` values to `ChatMessage` values, reverses the array (API returns newest-first; the view renders oldest-first), and stores them in `messages`.
9. `nextCursor` and `hasMore` are stored for the next load-more call.

**Loading older messages (infinite scroll upward):**

1. The view detects the user has scrolled near the top and calls `viewModel.loadMoreIfNeeded()`.
2. The ViewModel guards against concurrent or impossible loads (`hasMore`, `!isLoadMoreInProgress`, `!isStreaming`, `nextCursor != nil`).
3. `ChatService.loadMessages(characterId:cursor:limit:)` is called with the stored `nextCursor`.
4. Older messages are prepended to the front of `messages`; `nextCursor` and `hasMore` are updated.
5. If the load fails, the error is silently dropped — the user can scroll up again to retry.

**Sending a message and receiving a streaming response:**

1. The user types in the input field (bound to `viewModel.inputText`) and taps the send button.
2. `viewModel.sendMessage()` trims the input, clears the field, sets `isStreaming = true`.
3. A `ChatMessage.userMessage(content:)` is appended to `messages` immediately for instant feedback.
4. A `ChatMessage.streamingPlaceholder()` (empty assistant message with `isStreaming: true`) is also appended.
5. `ChatService.streamMessage(characterId:content:)` opens an `AsyncThrowingStream<SSEEvent, Error>` via `APIClient.streamSSE(endpoint: .streamMessage(characterId:), body: SendMessageBody(content:))`.
6. The ViewModel iterates the stream with `for try await event in ...`:
   - `.chunk(let chunk)`: appends `chunk` to `assistantMessage.content` and calls `updateLastMessage()` to replace the tail of `messages`.
   - `.done(let messageId)`: sets `assistantMessage.id = messageId` and `assistantMessage.isStreaming = false`, then commits via `updateLastMessage()`.
   - `.action`: logged but not acted upon in Phase 3 (device-action integration is future work).
   - `.error(let message)`: removes the empty assistant placeholder via `removeLastAssistantIfEmpty()`, sets `errorMessage`, triggers `HapticManager.notification(.error)`.
   - `.moderation(let message)`: same as `.error`.
7. If the stream throws, the same cleanup and error path runs.
8. `isStreaming` is set back to `false` in all exit paths.

### SSE Parsing Layer

`ChatViewModel` consumes `SSEEvent` values produced by `SSEDelegate` (defined in `ios/Ember/Core/Network/SSEClient.swift`). The delegate buffers incoming UTF-8 data, splits on `\n\n` to extract complete SSE event blocks, strips the `data: ` prefix, and decodes each JSON payload into one of five `SSEEvent` cases. The ViewModel does not interact with raw HTTP bytes — the abstraction boundary is `AsyncThrowingStream<SSEEvent, Error>`.

### Cursor Pagination Design

The backend returns messages newest-first. The ViewModel reverses the initial page so `messages[0]` is the oldest and `messages.last` is the newest — the natural display order. When older pages are prepended, the same reversal is applied to the incoming page before it is inserted at index 0 with `messages.insert(contentsOf: olderMessages, at: 0)`. The cursor is an opaque string (`nextCursor`) returned by the backend; the client stores it and passes it verbatim on the next request.

### State Guard Logic

`loadMoreIfNeeded()` is guarded by four conditions to prevent race conditions:

| Guard | Reason |
|-------|--------|
| `hasMore` | No point requesting if the backend says there are no earlier messages |
| `!isLoadMoreInProgress` | Prevents duplicate concurrent load-more requests |
| `!isLoadingHistory` | Prevents conflict with the initial history load |
| `!isStreaming` | Prevents pagination during an active SSE stream |

### ChatMessage Model

`ChatMessage` is a local struct used only within the Chat feature. It differs from `MessagePreview` (the network model from `MessageModels.swift`), which is also used by `HomeViewModel` for last-message previews on the home screen.

```swift
struct ChatMessage: Identifiable, Equatable {
    let id: String
    let role: MessageRole   // .user | .assistant
    var content: String
    let createdAt: Date
    var isStreaming: Bool
}
```

The `content` and `isStreaming` properties are `var` because the streaming path mutates them in place via `updateLastMessage()`. All other properties are `let`.

---

## API Reference

See [`docs/04-veri-api.md`](../04-veri-api.md) for the full API contract. The chat screen uses two endpoints.

### GET /api/v1/characters/{character_id}/messages

**Auth**: Bearer JWT required

Retrieves a page of message history. Used on screen appear and on load-more.

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `cursor` | string | no | Opaque cursor from the previous response. Omit for the first page. |
| `limit` | integer | no | Page size. Client sends 20. |

**Response** (200 OK):

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "role": "assistant",
      "content": "Hello! How can I help you today?",
      "created_at": "2026-03-13T10:00:00Z"
    }
  ],
  "next_cursor": "2026-03-12T09:59:00Z_550e8400-e29b-41d4-a716-446655440000",
  "has_more": true
}
```

Items are returned newest-first. The client reverses them before display.

### POST /api/v1/characters/{character_id}/messages

**Auth**: Bearer JWT required
**Content-Type**: `application/json`

Sends a user message and streams the AI response via SSE.

**Request Body**:

```json
{
  "content": "Tell me something interesting."
}
```

**Response**: `text/event-stream`

```
data: {"type":"chunk","content":"Did you know"}

data: {"type":"chunk","content":" that honey never spoils?"}

data: {"type":"done","message_id":"550e8400-e29b-41d4-a716-446655440099"}

```

**SSE Event Types**:

| Type | Fields | Client Handling |
|------|--------|----------------|
| `chunk` | `content` | Appended to the streaming assistant bubble |
| `done` | `message_id` | Commits the assistant bubble with the server ID; clears `isStreaming` |
| `action` | `action`, `payload` | Received and discarded in Phase 3; reserved for device integration |
| `error` | `message` | Removes empty placeholder; sets `errorMessage`; triggers error haptic |
| `moderation` | `message` | Same as `error` |

**Error Responses (before SSE starts)**:

| Status | When |
|--------|------|
| 400 | Content is empty or exceeds 4000 characters |
| 401 | Missing or invalid JWT |
| 403 | Character belongs to another user |
| 404 | Character not found or inactive |

---

## iOS Implementation

**Files**:
- `ios/Ember/Features/Chat/ChatViewModel.swift` — `@Observable` ViewModel + `ChatMessage` model
- `ios/Ember/Features/Chat/ChatService.swift` — `ChatServiceProtocol` + `ChatService` network wrapper

No SwiftUI View file (`ChatView.swift`) was added in this feature phase. The ViewModel and service are complete; the view layer is the expected deliverable for the next phase or an in-progress task.

**Key Patterns**:

- `ChatViewModel` is `@Observable` (iOS 17+). Do not add `@Published` or convert to `ObservableObject`.
- `ChatService` conforms to `ChatServiceProtocol` for testability. Mock the protocol in tests; never mock `APIClient` directly from feature tests.
- `streamMessage` returns `AsyncThrowingStream<SSEEvent, Error>` — the same type produced by `APIClient.streamSSE`. No intermediate adapters.
- `updateLastMessage(_:)` mutates `messages[messages.count - 1]` in place. This is safe because `sendMessage()` appends the placeholder before the loop starts and is guarded by `!isStreaming`.
- `removeLastAssistantIfEmpty()` checks both that the last message is an assistant message AND that its content is empty before removing it. This prevents accidentally removing a partial response if an error arrives after some chunks have already been delivered.

**ViewModel State Properties**:

```swift
var messages: [ChatMessage] = []        // display list, oldest-first
var inputText: String = ""              // bound to text field
var isStreaming: Bool = false           // true during active SSE stream
var isLoadingHistory: Bool = false      // true during initial load
var isLoadingMore: Bool = false         // true during a load-more fetch
var errorMessage: String? = nil        // non-nil triggers error alert
var characterName: String               // displayed in navigation title

private(set) var hasMore: Bool = true   // false when no older pages exist
private var nextCursor: String? = nil  // passed to the next load-more call
```

**Navigation**:

The Chat screen is reached by pushing `.chat(characterId: id)` onto `AppRouter.path`. The router is a `NavigationPath`-based `@Observable` class injected via `@Environment`. Entry points are:

- `HomeView` character grid: `router.push(.chat(characterId: character.id))` on card tap
- `HomeView` daily summary card: `router.push(.chat(characterId: defaultChar.id))` on card tap

Navigation back is the standard `NavigationStack` back gesture or back button. No custom pop logic is required because `ChatViewModel` does not hold resources that need explicit cleanup (the SSE stream cancels automatically via `continuation.onTermination` when the `Task` is cancelled).

**Error Handling**:

| Error Source | Behaviour |
|---|---|
| Initial `loadHistory()` throws | Sets `errorMessage`; view should show an alert with a Retry button |
| `loadMoreIfNeeded()` throws | Silently ignored; user can scroll up again |
| SSE `.error` or `.moderation` event | Removes empty placeholder, sets `errorMessage`, triggers error haptic |
| SSE stream throws | Same as SSE error event |

---

## Android Implementation

Not applicable. This is an iOS-only feature.

---

## Testing

No unit tests were added as part of this feature phase. The ViewModel and service are structured for testability:

- `ChatServiceProtocol` can be implemented by a mock that yields a controlled `AsyncThrowingStream`.
- `ChatViewModel` accepts a `ChatServiceProtocol` in its initialiser, so no `APIClient` patching is needed in tests.

When tests are added, they should live in `ios/EmberTests/Features/Chat/ChatViewModelTests.swift`.

### Running Tests

```bash
cd ios && xcodebuild test -scheme Ember -destination "platform=iOS Simulator,name=iPhone 16"
```

---

## Known Limitations

- **No ChatView.swift**: The ViewModel and service layer are complete, but the SwiftUI view that renders message bubbles, the input field, and the typing indicator has not been committed. The feature is not user-visible until a `ChatView` is added and wired into `AppRouter`'s `NavigationStack` destination resolver.
- **Action events are silently dropped**: The `case .action:` branch in `sendMessage()` does nothing in Phase 3. Device action intents (alarms, calendar events) emitted by the backend will be received but ignored.
- **No offline support**: All operations require network connectivity. There is no local message cache, no retry queue for failed sends, and no offline indicator.
- **Silent load-more failures**: When a pagination request fails, the error is discarded. The user receives no feedback and must scroll back up to trigger a retry.
- **No tests**: Unit tests for `ChatViewModel` were not delivered with this feature phase.

---

## Extending This Feature

**Adding the SwiftUI view**: Create `ios/Ember/Features/Chat/ChatView.swift` as a SwiftUI `View` that reads from `ChatViewModel`. Key considerations: the view must call `viewModel.loadMoreIfNeeded()` when the user scrolls near the top (e.g., when the first visible message comes into view using `.onAppear` on the oldest message bubble). The send button should be disabled when `viewModel.isStreaming` is `true` or `viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty`. Add a `.navigationTitle(viewModel.characterName)` and register the destination in `MainTabView` (or wherever `AppRouter.Route` cases are resolved to views).

**Handling action events**: To act on device action intents, replace the `case .action: break` branch in `ChatViewModel.sendMessage()` with dispatch logic. The `SSEEvent.action` case carries an `action: String` discriminator and `payloadJSON: Data`. Decode the payload as the appropriate struct (e.g., `SetAlarmPayload`) and post it via a notification or a dedicated delegate callback.

**Adding a typing indicator**: The streaming placeholder (`ChatMessage.streamingPlaceholder()`) already carries `isStreaming: true`. The view can render a typing animation on any bubble where `message.isStreaming && message.content.isEmpty`.

**Adding load-more tests**: Mock `ChatServiceProtocol` to return a controlled sequence of `MessageListResponse` pages. Verify that `messages` is prepended (not appended) with older messages, that `hasMore` reflects the response, and that the guard conditions prevent duplicate requests.

---

## Related Documentation

- [Chat Streaming (backend)](chat-streaming.md) — the backend endpoint this feature consumes
- [Messages Pagination (backend)](messages-pagination.md) — cursor-based pagination contract
- [iOS Network Layer](ios-network-layer.md) — `APIClient`, `SSEDelegate`, `SSEEvent`, and `APIEndpoint` used by `ChatService`
- [iOS Scaffold](ios-scaffold.md) — design system tokens
- [iOS Home View](ios-home-view.md) — entry point that pushes `.chat(characterId:)` onto the navigation stack
- [Database Schema](../04-veri-api.md)
- [AI Memory System](../05-ai-bellek.md)
- [Mobile Screens](../07-mobil.md)
