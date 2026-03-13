# Architect Handoff: iOS Chat View

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

The production ChatView screen for iOS, replacing the placeholder Text("Chat") in MainTabView. The screen includes SSE streaming message display, message bubbles with role-based styling, a typing indicator (three-dot bounce), a chat input bar with send button, and cursor-based pagination for loading older messages on scroll-to-top.

## Spec Location

`shared/feature-specs/ios-chat-view.md`

## Layer

ios

## Key Decisions

- **Route carries full Character object**: Changed `AppRouter.Route.chat(characterId: String)` to `chat(character: Character)`. This avoids a redundant API call to fetch the character name for the nav bar. `Character` already conforms to `Hashable`, so it works with `NavigationPath`.

- **Separate ChatMessageListResponse type**: Rather than reusing `MessageListResponse` (which uses `MessagePreview`), a new `ChatMessageListResponse` with full `Message` objects is introduced. This keeps the lightweight `MessagePreview` for HomeView and provides the richer `Message` type (with `mediaUrl`, `metadata`) for ChatView.

- **Typing indicator vs streaming bubble**: The typing indicator (three-dot bounce) is shown only while `isStreaming == true` AND the assistant message content is empty. Once the first chunk arrives, the indicator disappears and the streaming text bubble is shown. This avoids showing both simultaneously.

- **Markdown via AttributedString**: Phase 3 uses `AttributedString(markdown:)` (built-in iOS 15+) for basic bold/italic rendering in AI messages. Full `swift-markdown` integration is deferred to a later phase.

- **Photo and voice buttons disabled**: The camera and microphone buttons are rendered in the input bar but disabled with reduced opacity. These are Phase 5 features and this decision keeps the UI future-ready without implementing the functionality.

- **Message content is `var`**: The `Message.content` property is `var` (not `let`) because during SSE streaming, content is appended incrementally to the assistant message.

- **Stream cancellation on disappear**: `ChatView.onDisappear` calls `viewModel.cancelStream()` to cancel any active SSE stream task, preventing background work after the user navigates away.

- **Custom bubble shape**: Uses `UnevenRoundedRectangle` (iOS 17+) for the characteristic chat bubble tail (one corner with a smaller 4pt radius).

## File Manifest

```
iOS:
  CREATE  ios/Ember/Features/Chat/ChatView.swift
  CREATE  ios/Ember/Features/Chat/ChatViewModel.swift
  CREATE  ios/Ember/Features/Chat/MessageBubbleView.swift
  CREATE  ios/Ember/Features/Chat/TypingIndicatorView.swift
  CREATE  ios/Ember/Features/Chat/ChatInputBar.swift
  CREATE  ios/Ember/Features/Chat/ChatBubbleShape.swift
  CREATE  ios/Ember/Core/Models/ChatModels.swift
  MODIFY  ios/Ember/App/MainTabView.swift
  MODIFY  ios/Ember/App/AppRouter.swift
  MODIFY  ios/Ember/Features/Home/HomeView.swift
  MODIFY  ios/Ember/Features/Home/DailySummaryCard.swift
  MODIFY  ios/Ember/Core/Extensions/EmberSymbol.swift
  CREATE  ios/EmberTests/Features/Chat/ChatViewModelTests.swift

Shared:
  CREATE  shared/feature-specs/ios-chat-view.md
  CREATE  docs/pipeline/ios-chat-view-architect.handoff.md
```

## Assumptions Made

- The `Character` struct (from P03-06) already conforms to `Hashable`, making it safe to embed in `NavigationPath` via the route enum.
- The backend `POST /api/v1/characters/:id/messages` SSE endpoint (P01-06) is fully operational and returns the event types documented in the spec: `chunk`, `action`, `done`, `error`, `moderation`.
- The backend `GET /api/v1/characters/:id/messages` endpoint (P01-07) returns full message objects including `media_url` and `metadata` fields (not just the lightweight preview fields).
- The `MockAPIClient` from P03-02 can handle both `request()` and `streamSSE()` calls in the same test without interference.

## Dependencies

- Requires: P03-06 (ios-home-view), P03-02 (ios-network-layer), P03-01 (ios-scaffold), P01-06 (chat-stream backend), P01-07 (messages-pagination backend)
- Blocks: ios-dev (implements this spec)

## Notes for Developers

- The `AppRouter.Route.chat` case change from `characterId: String` to `character: Character` is a breaking change. Update ALL call sites in HomeView and DailySummaryCard before compiling.
- The SSE stream handling in ChatViewModel maps directly to the existing `SSEEvent` enum cases from `SSEClient.swift`. No new SSE parsing is needed.
- The `ChatMessageListResponse` type must decode `media_url` and `metadata` fields. Verify the backend actually includes these in the list response (check `backend/app/schemas/chat.py`). If the backend omits them for the list endpoint, make them optional in the Swift model.
- Date separators between message groups require comparing `Calendar.current.isDate(_:inSameDayAs:)` across consecutive messages. Extract this logic into a helper function, not inline in the view.
- The scroll-to-bottom behavior uses `ScrollViewReader` and `.scrollTo(id:anchor:)`. The anchor should be `.bottom` to ensure the latest content is visible during streaming.

## Next Steps

ios-dev should read the spec and implement all files in the manifest.
