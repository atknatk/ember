# Android Dev Handoff: Android Chat

**Date**: 2026-03-13
**Agent**: android-dev
**Status**: COMPLETE

## Implemented Files
- `android/app/src/main/java/ai/ember/app/features/chat/ChatModels.kt`
- `android/app/src/main/java/ai/ember/app/features/chat/ChatApi.kt`
- `android/app/src/main/java/ai/ember/app/features/chat/ChatRepository.kt`
- `android/app/src/main/java/ai/ember/app/features/chat/ChatModule.kt`
- `android/app/src/main/java/ai/ember/app/features/chat/ChatUiState.kt`
- `android/app/src/main/java/ai/ember/app/features/chat/ChatViewModel.kt`
- `android/app/src/main/java/ai/ember/app/features/chat/ChatScreen.kt`
- `android/app/src/main/java/ai/ember/app/features/chat/ChatInputBar.kt`
- `android/app/src/main/java/ai/ember/app/features/chat/MessageBubble.kt`
- `android/app/src/main/java/ai/ember/app/features/chat/TypingIndicator.kt`
- `android/app/src/main/java/ai/ember/app/features/chat/DateSeparator.kt`

## Modified Files
- `android/app/src/main/java/ai/ember/app/core/navigation/EmberNavHost.kt` — replaced Chat placeholder with ChatScreen
- `android/app/src/main/res/values/strings.xml` — added chat string resources

## Test Files
- `android/app/src/test/java/ai/ember/app/features/chat/ChatViewModelTest.kt`
- `android/app/src/test/java/ai/ember/app/features/chat/ChatRepositoryTest.kt`

## Screens Implemented
- ChatScreen: Full chat screen with message list, input bar, typing indicator, date separators, error/loading states

## strings.xml Keys Added
- `chat_navigate_back`: "Go back"
- `chat_input_placeholder`: "Message..."
- `chat_send_message`: "Send message"
- `chat_attach_photo`: "Attach photo, coming soon"
- `chat_voice_message`: "Voice message, coming soon"
- `chat_copy`: "Copy"
- `chat_retry`: "Retry"
- `chat_typing_indicator`: "AI is typing"
- `chat_message_you`: "You"
- `chat_message_a11y`: "%1$s message: %2$s"

## Deviations from Spec
- None

## Notes for Android Tester
- ViewModel depends on `ChatRepository` — use MockK `mockk<ChatRepository>()`
- SSE flow: create a test flow with `flowOf(chunkEvent, doneEvent)` and return from mock
- `loadHistory()` uses cursor pagination — verify no offset in mock calls
- Turbine is configured in project — use `.test { }` for StateFlow assertions
- `ChatViewModel` reads `characterId` and `characterName` from `SavedStateHandle`
- Test `SavedStateHandle` setup: `SavedStateHandle(mapOf("characterId" to "...", "characterName" to "..."))`
- Long-press copy uses `combinedClickable` + `DropdownMenu` — needs instrumented test for full verification
- Typing indicator shows only when `isStreaming && lastMessage.role == USER` (no chunks yet)
