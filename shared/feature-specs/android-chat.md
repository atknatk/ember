# Feature Spec: P04-05 -- Android Chat

**Feature ID**: P04-05
**Phase**: 4
**Layer**: android
**GitHub Issue**: #32
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature replaces the placeholder Chat destination in `EmberNavHost` with the production ChatScreen. ChatScreen is the core interaction screen of Ember on Android -- it is where the user converses with an AI character via real-time SSE streaming.

The screen consists of:

1. **Top bar** -- Displays the character's name with an avatar initial and a back button.

2. **Message list** -- A LazyColumn (reversed scroll) of message bubbles. User messages appear on the right with `EmberPrimary` background and white text. AI messages appear on the left with a gradient background (`EmberAIBubbleStart` to `EmberAIBubbleEnd`) and primary text color. Each bubble shows a timestamp below it. Bubbles have characteristic "tail" corners.

3. **Typing indicator** -- When the AI is streaming a response but no chunks have arrived yet, a three-dot bounce animation appears as a temporary bubble on the left side.

4. **Chat input bar** -- A TextField with send, photo (disabled), and voice (disabled) buttons. Send button fires haptic feedback and is disabled when empty or streaming.

5. **Cursor-based pagination** -- When the user scrolls near the top, older messages are loaded using `GET /api/v1/characters/:id/messages?cursor=...&limit=20`.

6. **Long-press to copy** -- Long-pressing a message bubble shows a context menu with "Copy".

7. **Date separators** -- Date labels ("Today", "Yesterday", "March 10") between messages from different days.

### Dependencies

- **P04-06** (android-home-screen) -- Provides navigation source: tapping a character card navigates to `Screen.Chat.createRoute(characterId, characterName)`.
- **P04-04** (android-scaffold) -- Provides `EmberNavHost`, `Screen` routes, theme, spacing.
- **P01-06** (chat-stream, backend) -- Provides `POST /api/v1/characters/:id/messages` SSE streaming endpoint.
- **P01-07** (messages-pagination, backend) -- Provides `GET /api/v1/characters/:id/messages` cursor-paginated endpoint.

### What This Feature Does NOT Do

- It does not implement photo sending or voice recording. Buttons are visible but disabled.
- It does not implement TTS playback.
- It does not implement Markdown rendering (deferred).
- It does not change any backend code.

---

## 2. Data Models

### Kotlin Models

- `ChatMessage` -- Full message with id, role, content, mediaUrl, metadata, createdAt.
- `MessageMetadata` -- Optional action/payload for future device integration.
- `SendMessageRequest` -- Request body for POST endpoint.
- `ChatMessageListResponse` -- Paginated response with items, nextCursor, hasMore.
- `SseEvent` -- Represents a single SSE event (chunk, done, error, action).
- `MessageRole` -- Constants for "user" and "assistant".

---

## 3. API Endpoints

No new endpoints. Calls existing backend endpoints:

- `POST /api/v1/characters/:id/messages` -- SSE streaming
- `GET /api/v1/characters/:id/messages?cursor=...&limit=20` -- Message history

---

## 4. Android Screens and Components

### 4.1 ChatScreen
Main composable: top bar, message list with date separators, typing indicator, input bar. Uses Scaffold with imePadding for keyboard handling.

### 4.2 ChatViewModel
@HiltViewModel with StateFlow<ChatUiState>. Handles loadHistory, loadMoreMessages, sendMessage (SSE), cancelStream.

### 4.3 ChatInputBar
TextField + send/photo/voice buttons. Haptic on send. Photo and voice disabled (Phase 5).

### 4.4 MessageBubble
User (right, primary) and AI (left, gradient) bubbles with timestamps and long-press copy.

### 4.5 TypingIndicator
Three-dot bounce animation during AI processing.

### 4.6 DateSeparator
Centered date label between message groups.

---

## 5. File Manifest

```
Android:
  CREATE  android/.../features/chat/ChatModels.kt
  CREATE  android/.../features/chat/ChatApi.kt
  CREATE  android/.../features/chat/ChatRepository.kt
  CREATE  android/.../features/chat/ChatModule.kt
  CREATE  android/.../features/chat/ChatUiState.kt
  CREATE  android/.../features/chat/ChatViewModel.kt
  CREATE  android/.../features/chat/ChatScreen.kt
  CREATE  android/.../features/chat/ChatInputBar.kt
  CREATE  android/.../features/chat/MessageBubble.kt
  CREATE  android/.../features/chat/TypingIndicator.kt
  CREATE  android/.../features/chat/DateSeparator.kt
  MODIFY  android/.../core/navigation/EmberNavHost.kt (replace placeholder with ChatScreen)
  MODIFY  android/.../res/values/strings.xml (add chat strings)

Tests:
  CREATE  android/.../test/.../features/chat/ChatViewModelTest.kt
  CREATE  android/.../test/.../features/chat/ChatRepositoryTest.kt

Shared:
  CREATE  shared/feature-specs/android-chat.md (this file)
  CREATE  docs/pipeline/android-chat-architect.handoff.md
  CREATE  docs/pipeline/android-chat-android-dev.handoff.md
```
