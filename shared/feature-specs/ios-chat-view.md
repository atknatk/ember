# Feature Spec: P03-07 -- iOS Chat View

**Feature ID**: P03-07
**Phase**: 3
**Layer**: ios
**GitHub Issue**: #23
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature replaces the placeholder `Text("Chat")` destination in `MainTabView.destinationView(for:)` with the production ChatView screen. ChatView is the core interaction screen of Ember -- it is where the user converses with an AI character via real-time SSE streaming.

The screen consists of:

1. **Navigation bar** -- Displays the character's name and a template-based avatar icon. A back button returns to HomeView.

2. **Message list** -- A vertically scrolling list of message bubbles. User messages appear on the right with `Color.emberPrimary` background and white text. AI messages appear on the left with a subtle gradient background (`Color.emberAIBubbleStart` to `Color.emberAIBubbleEnd`) and `Color.emberTextPrimary` text. Each bubble shows a timestamp below it. AI messages support Markdown rendering via the `swift-markdown` package (or a lightweight attributed string approach).

3. **Typing indicator** -- When the AI is streaming a response, a three-dot bounce animation appears as a temporary bubble on the left side before the first chunk arrives. Once the first chunk arrives, the typing indicator is replaced by the streaming assistant message bubble.

4. **Chat input bar** -- A text field with a send button. The send button uses the `EmberSymbol.send` icon and is disabled when the input is empty or a stream is in progress. Photo and voice buttons are shown but disabled (Phase 5 features).

5. **Cursor-based pagination** -- When the user scrolls to the top of the message list, older messages are loaded using `GET /api/v1/characters/:id/messages?cursor=...&limit=20`. A loading indicator appears at the top while fetching. Loading stops when `hasMore` is false.

6. **Long-press to copy** -- Long-pressing a message bubble presents a context menu with a "Copy" action that copies the message content to the clipboard.

### Why It Exists

Chat is the primary interaction mode in Ember. Without this screen, users cannot converse with their AI characters. The SSE streaming provides a responsive experience where the AI's response appears word-by-word, making the interaction feel natural and conversational.

### Dependencies

- **P03-06** (ios-home-view) -- Provides the navigation source: tapping a character card calls `router.push(.chat(characterId:))`.
- **P03-02** (ios-network-layer) -- Provides `APIClient` with `request()`, `streamSSE()`, `APIEndpoint`, `SSEEvent`, `SSEDelegate`.
- **P03-03** (ios-cognito-auth) -- Provides `AuthService.getAccessToken()` for authenticated API calls.
- **P03-01** (ios-scaffold) -- Provides `AppContainer`, `AppRouter`, design system extensions, `HapticManager`, `EmberSymbol`.
- **P01-06** (chat-stream, backend) -- Provides `POST /api/v1/characters/:id/messages` SSE streaming endpoint.
- **P01-07** (messages-pagination, backend) -- Provides `GET /api/v1/characters/:id/messages` cursor-paginated endpoint.

### What This Feature Does NOT Do

- It does not implement photo sending or voice recording. The photo and microphone buttons are visible but disabled with a "Coming in a future update" tooltip. These are Phase 5 features.
- It does not implement TTS playback for AI messages.
- It does not implement Markdown rendering with full fidelity. Phase 3 uses a lightweight approach: bold and italic via `AttributedString`, with full `swift-markdown` integration deferred to a later phase if needed.
- It does not change any backend code. Both endpoints already exist and are fully functional.
- It does not implement character switching from within the chat screen. The user navigates back to HomeView and taps a different character.

---

## 2. Data Models

No database changes. This is an iOS-only feature.

### Swift Models

#### Message (new model file)

A full message model for the chat view, richer than `MessagePreview` used by HomeView.

```
struct Message: Codable, Identifiable, Equatable {
    let id: String
    let role: MessageRole
    var content: String
    let mediaUrl: String?
    let metadata: MessageMetadata?
    let createdAt: Date

    enum MessageRole: String, Codable {
        case user
        case assistant
    }
}
```

Note: `content` is `var` because during SSE streaming, the assistant message's content is appended to incrementally.

#### MessageMetadata (optional, for future action support)

```
struct MessageMetadata: Codable, Equatable {
    let action: String?
    let payload: [String: String]?
}
```

#### SendMessageRequest (request body)

```
struct SendMessageRequest: Encodable {
    let content: String
    let mediaUrl: String?
}
```

#### MessageListResponse

Already exists in `ios/Ember/Core/Models/MessageModels.swift` as `MessageListResponse`. This feature reuses it but the items need to be decoded as full `Message` objects rather than `MessagePreview`. The implementation should either:
- (a) Add a second response type `ChatMessageListResponse` with `items: [Message]`, or
- (b) Extend the existing `MessageListResponse` to use `Message` type and update `MessagePreview` to be a computed subset.

The recommended approach is (a): create a separate `ChatMessageListResponse` since `MessagePreview` and `Message` serve different purposes and have different fields (`MessagePreview` omits `mediaUrl`, `metadata`).

```
struct ChatMessageListResponse: Codable {
    let items: [Message]
    let nextCursor: String?
    let hasMore: Bool
}
```

---

## 3. API Endpoints

No new endpoints. This feature calls existing backend endpoints.

### POST /api/v1/characters/:id/messages (SSE Streaming)

```
POST /api/v1/characters/:id/messages
Auth: Bearer JWT required
Request headers: Content-Type: application/json, Accept: text/event-stream
Request body: { "content": "string", "media_url": "string | null" }

Response: text/event-stream

SSE event sequence:
  data: {"type": "chunk", "content": "word "}
  data: {"type": "chunk", "content": "by word "}
  ...
  data: {"type": "action", "action": "SET_ALARM", "payload": {"time": "07:00"}}  (optional)
  data: {"type": "done", "message_id": "uuid-string"}

Error events:
  data: {"type": "error", "message": "LLM service unavailable"}
  data: {"type": "moderation", "message": "Content moderated"}
```

The `APIEndpoint.streamMessage(characterId:)` case already maps to this path with POST method. The `APIClient.streamSSE()` method handles the SSE delegate setup, `Accept: text/event-stream` header, and yields `SSEEvent` values.

### GET /api/v1/characters/:id/messages

```
GET /api/v1/characters/:id/messages?cursor={opaque_base64}&limit=20
Auth: Bearer JWT required

Response 200:
{
    "items": [
        {
            "id": "uuid",
            "role": "assistant",
            "content": "Message text...",
            "media_url": null,
            "metadata": null,
            "created_at": "2026-03-12T14:31:00Z"
        }
    ],
    "next_cursor": "eyJ0cyI6...",
    "has_more": true
}

Response 401: { "detail": "..." }
Response 404: { "detail": "Character not found" }
```

The `APIEndpoint.listMessages(characterId:cursor:limit:)` case already maps to this path.

---

## 4. Backend Logic

Not applicable. This is an iOS-only feature. The backend endpoints are implemented in `backend/app/routes/chat.py`.

---

## 5. iOS Screens and Components

### 5.1 ChatView

**File path**: `ios/Ember/Features/Chat/ChatView.swift`

**Navigation**: The user arrives here by tapping a character card on HomeView, which calls `router.push(.chat(characterId:))`. The `.navigationDestination(for:)` in `MainTabView` routes to `ChatView(character:)`. The user returns to HomeView via the system back button or swipe-back gesture.

**View structure**:

```
VStack(spacing: 0) {
    messageList
    typingIndicator (conditionally)
    chatInputBar
}
.background(Color.emberBackground.ignoresSafeArea())
.navigationBarTitleDisplayMode(.inline)
.toolbar {
    ToolbarItem(placement: .principal) {
        characterHeader (avatar icon + name)
    }
}
.task { await viewModel.loadInitialMessages() }
.alert(error handling)
.onDisappear { viewModel.cancelStream() }
```

**State binding**: `@State private var viewModel: ChatViewModel`

**ViewModel initialization**: `ChatView` receives a `Character` object (passed from HomeView which already has it loaded). The ViewModel is initialized in `init(character:)`:

```
init(character: Character, apiClient: APIClientProtocol = APIClient.shared) {
    _viewModel = State(initialValue: ChatViewModel(character: character, apiClient: apiClient))
}
```

**Scroll behavior**: The message list auto-scrolls to the bottom when a new message is sent or when the streaming response completes. Uses `ScrollViewReader` with `.scrollTo(id:anchor:)` keyed on the last message ID.

**Keyboard handling**: The input bar rises with the keyboard. Use `.scrollDismissesKeyboard(.interactively)` on the ScrollView so the user can drag-dismiss the keyboard.

### 5.2 MessageListView

**File path**: inline in `ChatView.swift` as a private subview, or extracted to `ios/Ember/Features/Chat/MessageListView.swift` if the file grows large.

**Purpose**: Renders the scrollable list of message bubbles with scroll-to-top pagination.

**UI elements**:

- `ScrollViewReader` wrapping a `ScrollView` with a `LazyVStack(spacing: .emberSpacing8)`.
- Each message rendered as a `MessageBubbleView`.
- At the top of the list: if `viewModel.hasMoreMessages` is true, show a "load more" trigger. This is implemented as an invisible `Color.clear.frame(height: 1)` with an `.onAppear` modifier that calls `Task { await viewModel.loadMoreMessages() }`. While loading, show a small `ProgressView()` at the top.
- Date separators between messages from different calendar days: a centered label with the date (e.g., "Today", "Yesterday", "March 10") in `.emberCaption` font, `Color.emberTextSecondary`.

**Scroll-to-bottom**: When `viewModel.shouldScrollToBottom` transitions to true, scroll to the last message ID using `proxy.scrollTo(lastMessageId, anchor: .bottom)` with animation. Reset `shouldScrollToBottom` after scrolling.

### 5.3 MessageBubbleView

**File path**: `ios/Ember/Features/Chat/MessageBubbleView.swift`

**Purpose**: Renders a single message bubble with role-appropriate styling.

**User message (role == .user)**:

- Alignment: trailing (right side).
- Background: `Color.emberPrimary` with `RoundedRectangle(cornerRadius: .emberRadius16)`. The bottom-right corner uses a smaller radius (4pt) for a characteristic "tail" effect, achieved via `.clipShape(ChatBubbleShape(isUser: true))` or UnevenRoundedRectangle (iOS 17+).
- Text: `.emberBody` font, `Color.white`.
- Max width: 75% of screen width.
- Timestamp: below the bubble, trailing aligned, `.emberMicro` font, `Color.emberTextSecondary`, formatted as "HH:mm" (e.g., "14:32").

**AI message (role == .assistant)**:

- Alignment: leading (left side).
- Background: Linear gradient from `Color.emberAIBubbleStart` to `Color.emberAIBubbleEnd` (top-leading to bottom-trailing) with `RoundedRectangle(cornerRadius: .emberRadius16)`. Bottom-left corner uses a smaller radius (4pt).
- Text: `.emberBody` font, `Color.emberTextPrimary`. Basic Markdown support: **bold** and *italic* rendered via `AttributedString(markdown:)` (iOS 15+ built-in).
- Max width: 75% of screen width.
- Timestamp: below the bubble, leading aligned, `.emberMicro` font, `Color.emberTextSecondary`.

**Long-press context menu**:

```
.contextMenu {
    Button {
        UIPasteboard.general.string = message.content
        HapticManager.notification(.success)
    } label: {
        Label("Copy", systemImage: "doc.on.doc")
    }
}
```

**Accessibility**:

- `accessibilityLabel("{role} message: {content}")` where role is "You" or the character name.
- `accessibilityHint("Long press to copy")`.
- Custom accessibility action: "Copy message".

**Animation**: New messages slide in from the bottom with a fade: `.transition(.asymmetric(insertion: .move(edge: .bottom).combined(with: .opacity), removal: .opacity))`.

### 5.4 TypingIndicatorView

**File path**: `ios/Ember/Features/Chat/TypingIndicatorView.swift`

**Purpose**: Displays a three-dot bounce animation when the AI is processing but no chunks have arrived yet.

**When shown**: When `viewModel.isStreaming` is true AND the current assistant message content is empty (no chunks received yet).

**UI elements**:

- Left-aligned bubble matching the AI message style (gradient background, same corner radius).
- Three circles (6pt diameter) with `Color.emberTextSecondary`, spaced 4pt apart.
- Animation: Each dot bounces vertically (offset Y -4pt and back) with a 400ms period, staggered 133ms between dots. Use `.animation(.easeInOut(duration: 0.4).repeatForever(), value: animating)` with delayed phase offsets.

**Accessibility**: `accessibilityLabel("{characterName} is typing")`.

### 5.5 ChatInputBar

**File path**: `ios/Ember/Features/Chat/ChatInputBar.swift`

**Purpose**: Text input field with send, photo, and voice buttons.

**UI elements**:

- Container: `HStack` with `Color.emberSurface` background, top border of 0.5pt `Color.emberSurface3`.
- Photo button (left): SF Symbol `"camera"` in `Color.emberTextDisabled`, 44x44pt tap target. Disabled with `.opacity(0.4)`. Accessibility label: "Attach photo, coming soon".
- Text field: `TextField("Message...", text: $viewModel.inputText, axis: .vertical)` with `.lineLimit(1...5)`. Background: `Color.emberSurface2`, corner radius `.emberRadius12`. Font: `.emberBody`. Text color: `Color.emberTextPrimary`. Placeholder color: `Color.emberTextDisabled`.
- Voice button (right of text field): SF Symbol `"mic"` in `Color.emberTextDisabled`, disabled. Accessibility label: "Voice message, coming soon".
- Send button (far right): SF Symbol `EmberSymbol.send` in `Color.emberPrimary`, 44x44pt tap target. Disabled when `viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty` OR `viewModel.isStreaming` is true. When disabled, `.opacity(0.4)`. When tapped:
  1. `HapticManager.impact(.light)` fires.
  2. `Task { await viewModel.sendMessage() }` is called.

**Keyboard**: The input bar is pinned to the bottom of the screen and moves up with the keyboard. The `VStack` containing the message list and input bar naturally handles this when inside a `NavigationStack`.

**Accessibility**: Send button: `accessibilityLabel("Send message")`. `accessibilityHint("Sends your typed message to {characterName}")`.

### 5.6 ChatViewModel

**File path**: `ios/Ember/Features/Chat/ChatViewModel.swift`

**Class definition**: `@Observable final class ChatViewModel`

**Properties**:

| Property | Type | Purpose |
|----------|------|---------|
| `messages` | `[Message]` | All loaded messages, ordered oldest-first |
| `inputText` | `String` | Current text in the input field |
| `isStreaming` | `Bool` | True while SSE stream is active |
| `isLoadingHistory` | `Bool` | True while fetching older messages |
| `hasMoreMessages` | `Bool` | False when all history is loaded |
| `shouldScrollToBottom` | `Bool` | Set to true to trigger scroll-to-bottom |
| `errorMessage` | `String?` | Non-nil when an error occurs |
| `character` | `Character` | The character this chat belongs to |

**Private properties**:

| Property | Type | Purpose |
|----------|------|---------|
| `apiClient` | `APIClientProtocol` | Injected network client |
| `nextCursor` | `String?` | Cursor for loading older messages |
| `streamTask` | `Task<Void, Never>?` | Reference to the active stream task for cancellation |

**Constructor**: `init(character: Character, apiClient: APIClientProtocol = APIClient.shared)`

**Methods**:

`func loadInitialMessages() async`

1. Set `isLoadingHistory = true`.
2. Call `apiClient.request(endpoint: .listMessages(characterId: character.id, cursor: nil, limit: 20), responseType: ChatMessageListResponse.self)`.
3. On success: set `messages` to `response.items.reversed()` (API returns newest-first, view needs oldest-first). Set `nextCursor = response.nextCursor`. Set `hasMoreMessages = response.hasMore`.
4. On failure: set `errorMessage`.
5. Set `isLoadingHistory = false`.
6. Set `shouldScrollToBottom = true` (scroll to latest message on initial load).

`func loadMoreMessages() async`

1. Guard: `!isLoadingHistory && hasMoreMessages && nextCursor != nil`.
2. Set `isLoadingHistory = true`.
3. Capture the ID of the current topmost message (for maintaining scroll position).
4. Call `apiClient.request(endpoint: .listMessages(characterId: character.id, cursor: nextCursor, limit: 20), responseType: ChatMessageListResponse.self)`.
5. On success: prepend `response.items.reversed()` to `messages`. Update `nextCursor` and `hasMoreMessages`.
6. On failure: set `errorMessage` (non-fatal, user can retry by scrolling up again).
7. Set `isLoadingHistory = false`.

`func sendMessage() async`

1. Guard: input text is not empty after trimming whitespace.
2. Capture the trimmed content. Clear `inputText` immediately (optimistic UI).
3. Create a local user `Message` with a temporary UUID, role `.user`, and the content. Append to `messages`.
4. Create a local assistant `Message` with a temporary UUID, role `.assistant`, and empty content. Append to `messages`.
5. Set `isStreaming = true`. Set `shouldScrollToBottom = true`.
6. Clear `errorMessage`.
7. Start the SSE stream:
   ```
   streamTask = Task {
       do {
           let body = SendMessageRequest(content: content, mediaUrl: nil)
           for try await event in apiClient.streamSSE(endpoint: .streamMessage(characterId: character.id), body: body) {
               handleSSEEvent(event)
           }
       } catch {
           handleStreamError(error)
       }
       isStreaming = false
   }
   ```
8. Await `streamTask?.value` (or let it run detached if the view handles cancellation via `onDisappear`).

`private func handleSSEEvent(_ event: SSEEvent)`

- `.chunk(let content)`: Append `content` to the last message's content (which is the assistant message). Set `shouldScrollToBottom = true`.
- `.done(let messageId)`: Update the assistant message's `id` to the server-assigned `messageId`. Also update the user message's `id` if desired (the server persists it with its own UUID, but the client-side temporary UUID is acceptable for display). Set `isStreaming = false`.
- `.error(let message)`: Set `errorMessage = message`. Remove the empty assistant message if its content is still empty. Set `isStreaming = false`.
- `.moderation(let message)`: Set `errorMessage = message`. Remove the empty assistant message. Set `isStreaming = false`.
- `.action(let action, let payloadJSON)`: Store in the assistant message's metadata if needed. For Phase 3, no UI action is taken -- action handling is a future feature.

`private func handleStreamError(_ error: Error)`

1. Set `errorMessage` to the error's localized description.
2. If the last message is an assistant message with empty content, remove it.
3. Set `isStreaming = false`.

`func cancelStream()`

Called from `ChatView.onDisappear`. Cancels `streamTask` if active.

```
func cancelStream() {
    streamTask?.cancel()
    streamTask = nil
}
```

### 5.7 ChatBubbleShape

**File path**: `ios/Ember/Features/Chat/ChatBubbleShape.swift`

**Purpose**: A custom `Shape` that renders a rounded rectangle with one corner having a smaller radius, creating the characteristic chat bubble "tail".

**Implementation**: Uses `UnevenRoundedRectangle` (iOS 17+):

- User bubble: top-left 16pt, top-right 16pt, bottom-left 16pt, bottom-right 4pt.
- AI bubble: top-left 16pt, top-right 16pt, bottom-left 4pt, bottom-right 16pt.

### 5.8 DateSeparatorView

**File path**: inline in `MessageListView` or extracted as a small private view.

**Purpose**: Shows a date label between messages from different calendar days.

**UI elements**: Centered text in `.emberCaption` font, `Color.emberTextSecondary`. Shows "Today", "Yesterday", or the formatted date (e.g., "March 10").

### 5.9 MainTabView Update

**File path**: `ios/Ember/App/MainTabView.swift`

**Modification**: Replace the `.chat` case in `destinationView(for:)` from `Text("Chat")` to `ChatView(character:)`. This requires passing the character object through the route.

**Route change**: The `AppRouter.Route.chat` case needs to carry the full `Character` object instead of just `characterId: String`, so that ChatView can display the character name in the nav bar and pass it to the ViewModel without an additional API call.

Updated route definition:

```
case chat(character: Character)
```

This is a breaking change to `AppRouter.Route`. All call sites (HomeView's character card tap) must be updated to pass the `Character` object.

If this is undesirable (because `Character` must conform to `Hashable`, which it already does), then alternatively keep `chat(characterId: String)` and also pass the character name separately: `chat(characterId: String, characterName: String)`. However, since `Character` already conforms to `Hashable`, the cleanest approach is `chat(character: Character)`.

---

## 6. Android Screens and Components

Not applicable. This is an iOS-only feature (layer: ios).

---

## 7. Test Plan

### iOS Tests

#### ChatViewModelTests (Swift Testing)

**File path**: `ios/EmberTests/Features/Chat/ChatViewModelTests.swift`

**Mock setup**: Use the existing `MockAPIClient`. Set `requestResult` for history loading and `sseEvents` for streaming.

**Test scenarios**:

1. **loadInitialMessages populates messages on success** -- Configure `MockAPIClient.requestResult` with a `ChatMessageListResponse` containing 3 messages. Call `loadInitialMessages()`. Assert `messages.count == 3`, messages are in oldest-first order, `isLoadingHistory == false`, `hasMoreMessages` matches response.

2. **loadInitialMessages sets errorMessage on failure** -- Configure `MockAPIClient.requestError` with `APIError.networkError(...)`. Call `loadInitialMessages()`. Assert `messages` is empty, `errorMessage` is not nil.

3. **loadInitialMessages sets shouldScrollToBottom** -- Call `loadInitialMessages()`. Assert `shouldScrollToBottom == true`.

4. **loadMoreMessages prepends older messages** -- Load initial messages (3 items, hasMore=true, nextCursor set). Then configure mock with 2 more items. Call `loadMoreMessages()`. Assert `messages.count == 5`, the 2 older messages are at the beginning.

5. **loadMoreMessages does nothing when hasMoreMessages is false** -- Load initial messages with `hasMore=false`. Call `loadMoreMessages()`. Assert no additional API call (check `requestCallCount`).

6. **loadMoreMessages does nothing when already loading** -- Set `isLoadingHistory = true` manually. Call `loadMoreMessages()`. Assert no additional API call.

7. **sendMessage appends user and assistant messages** -- Set `inputText = "Hello"`, configure mock with SSE events `[.chunk("Hi"), .chunk(" there"), .done("msg-1")]`. Call `sendMessage()`. Assert `messages.count == 2`, `messages[0].role == .user`, `messages[0].content == "Hello"`, `messages[1].role == .assistant`, `messages[1].content == "Hi there"`.

8. **sendMessage clears inputText immediately** -- Set `inputText = "Hello"`. Call `sendMessage()`. Assert `inputText` is empty before stream completes.

9. **sendMessage sets isStreaming during stream** -- Call `sendMessage()`. Assert `isStreaming == true` while stream is active, `isStreaming == false` after completion.

10. **sendMessage handles stream error** -- Configure mock to throw `APIError.serverError(statusCode: 503, detail: "Service unavailable")`. Set `inputText = "Hello"`. Call `sendMessage()`. Assert `errorMessage` is not nil, the empty assistant message is removed, `isStreaming == false`.

11. **sendMessage handles SSE error event** -- Configure mock with events `[.chunk("Partial"), .error("LLM down")]`. Call `sendMessage()`. Assert `errorMessage == "LLM down"`.

12. **sendMessage handles moderation event** -- Configure mock with events `[.moderation("Content blocked")]`. Call `sendMessage()`. Assert `errorMessage == "Content blocked"`, assistant message removed.

13. **sendMessage does nothing with empty input** -- Set `inputText = "   "` (whitespace only). Call `sendMessage()`. Assert `messages` is empty, no API call made.

14. **sendMessage fires haptic** -- Not directly testable in unit tests. Covered by acceptance criteria.

15. **cancelStream cancels the active stream task** -- Start a stream, then call `cancelStream()`. Assert `isStreaming` transitions to false.

16. **sendMessage updates assistant message ID on done event** -- Configure mock with `[.chunk("Hi"), .done("server-uuid")]`. Call `sendMessage()`. Assert last message's `id == "server-uuid"`.

#### MockAPIClient updates

The existing `MockAPIClient` uses a single `requestResult: Any?` property. For ChatViewModel tests that call both `request()` (for history) and `streamSSE()` (for sending), the mock needs to support both. The current design already supports this: `requestResult` is used for `request()` calls and `sseEvents` is used for `streamSSE()` calls. However, tests that call `loadInitialMessages()` followed by `sendMessage()` will need `requestResult` to stay set for the history call. This is handled naturally since the mock does not clear `requestResult` between calls.

If needed, extend MockAPIClient with a response queue pattern: `var requestResults: [Any] = []` that pops the first element on each `request()` call. This enables tests that make multiple `request()` calls with different responses (e.g., initial load + load more).

#### UI Tests (XCTest, optional stretch goal)

- Launch app with a pre-authenticated user and characters.
- Navigate to a character's chat from HomeView.
- Verify the character name appears in the navigation bar.
- Type a message and tap send.
- Verify the user message bubble appears on the right.
- Verify a streaming response appears on the left.
- Scroll up and verify older messages load.

---

## 8. Acceptance Criteria

1. Given the user taps a character card on HomeView, when the navigation completes, then ChatView is displayed with the character's name in the navigation bar.

2. Given the character has existing messages, when ChatView loads, then the most recent 20 messages are displayed with user messages on the right (primary color background) and AI messages on the left (gradient background), scrolled to the bottom.

3. Given the user types a message and taps the send button, then the user message appears immediately as a right-aligned bubble, a typing indicator appears briefly on the left, and the AI response streams in word-by-word on the left as chunks arrive.

4. Given the AI is streaming a response, when a chunk arrives, then the text in the assistant bubble updates incrementally without layout jumps, and the view auto-scrolls to keep the latest content visible.

5. Given the AI finishes streaming, when the "done" SSE event is received, then `isStreaming` is set to false, the send button is re-enabled, and the assistant message has the server-assigned message ID.

6. Given an SSE error event is received during streaming, then an error alert is displayed with the error message, any empty assistant bubble is removed, and the send button is re-enabled.

7. Given the user scrolls to the top of the message list, when there are older messages available (`hasMore == true`), then a loading indicator appears at the top and older messages are loaded and prepended to the list.

8. Given all message history has been loaded (`hasMore == false`), when the user scrolls to the top, then no additional fetch is triggered.

9. Given the user long-presses a message bubble, then a context menu appears with a "Copy" option that copies the message content to the clipboard.

10. Given the send button is tapped, then `HapticManager.impact(.light)` fires.

11. Given the input field is empty or contains only whitespace, then the send button is disabled (reduced opacity).

12. Given a stream is in progress, then the send button is disabled until the stream completes or errors.

13. Given VoiceOver is enabled, then all message bubbles have accessibility labels with role and content, the send button has "Send message" label, and the typing indicator has "{characterName} is typing" label.

14. Given the user navigates away from ChatView while a stream is in progress, then the stream task is cancelled.

15. Given the network call to load message history fails, then an error alert is shown with a retry option.

16. Given the app is in dark mode (forced), then all ChatView elements use colors from `Color+Ember.swift` and render correctly on a dark background.

---

## 9. File Manifest

```
iOS:
  CREATE  ios/Ember/Features/Chat/ChatView.swift
  CREATE  ios/Ember/Features/Chat/ChatViewModel.swift
  CREATE  ios/Ember/Features/Chat/MessageBubbleView.swift
  CREATE  ios/Ember/Features/Chat/TypingIndicatorView.swift
  CREATE  ios/Ember/Features/Chat/ChatInputBar.swift
  CREATE  ios/Ember/Features/Chat/ChatBubbleShape.swift
  CREATE  ios/Ember/Core/Models/ChatModels.swift
  MODIFY  ios/Ember/App/MainTabView.swift (replace Text("Chat") placeholder with ChatView)
  MODIFY  ios/Ember/App/AppRouter.swift (change Route.chat to carry Character instead of characterId)
  MODIFY  ios/Ember/Features/Home/HomeView.swift (update router.push(.chat(...)) call sites)
  MODIFY  ios/Ember/Features/Home/DailySummaryCard.swift (update onTap to pass Character)
  MODIFY  ios/Ember/Core/Extensions/EmberSymbol.swift (add chat-specific symbols: camera, copy)
  CREATE  ios/EmberTests/Features/Chat/ChatViewModelTests.swift

Shared:
  CREATE  shared/feature-specs/ios-chat-view.md (this file)
  CREATE  docs/pipeline/ios-chat-view-architect.handoff.md
```

### Modification Details

**MainTabView.swift**: In `destinationView(for:)`, replace:
```swift
case .chat:
    Text("Chat")
        .foregroundStyle(Color.emberTextPrimary)
```
with:
```swift
case .chat(let character):
    ChatView(character: character)
```

**AppRouter.swift**: Change `case chat(characterId: String)` to `case chat(character: Character)`. Since `Character` already conforms to `Hashable`, this works with `NavigationPath`.

**HomeView.swift**: Update all `router.push(.chat(characterId: character.id))` calls to `router.push(.chat(character: character))`.

**DailySummaryCard.swift**: The `onTap` closure in `HomeView` passes the default character. Update to pass the full `Character` object to the router.

**EmberSymbol.swift**: Add:
```
static let camera = "camera"
static let copy = "doc.on.doc"
```
