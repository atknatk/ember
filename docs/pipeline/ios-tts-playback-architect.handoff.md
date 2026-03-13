# Architect Handoff: iOS TTS Playback (P05-04)

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## Spec Location
- `shared/feature-specs/ios-tts-playback.md`

## Scope
- iOS only (layer: ios)
- Adds TTS playback to ChatView AI message bubbles
- Uses existing backend `POST /api/v1/tts` endpoint

## Key Decisions
- AudioPlayerManager as @Observable class shared via ChatViewModel (not per-bubble)
- One audio at a time enforced at the manager level
- AVPlayer with CMTime periodic observer for progress
- Inline progress bar inside message bubble (not a separate overlay)
- Speed persists within chat session, resets on exit

## Files to Create
1. `ios/Ember/Core/Models/TTSModels.swift`
2. `ios/Ember/Features/Chat/AudioPlayerManager.swift`
3. `ios/Ember/Features/Chat/AudioProgressView.swift`

## Files to Modify
4. `ios/Ember/Core/Extensions/EmberSymbol.swift` — add TTS icons
5. `ios/Ember/Core/Network/APIEndpoint.swift` — add `.synthesizeSpeech`
6. `ios/Ember/Features/Chat/ChatService.swift` — add `synthesizeSpeech` to protocol + impl
7. `ios/Ember/Features/Chat/ChatViewModel.swift` — add TTS state + `requestTTS` method
8. `ios/Ember/Features/Chat/MessageBubbleView.swift` — add Listen button + AudioProgressView
9. `ios/Ember/Features/Chat/ChatView.swift` — pass audioPlayer to bubbles, cleanup on disappear
10. `ios/EmberTests/Mocks/MockChatService.swift` — add TTS stub

## Dependencies
- P03-07 (ios-chat-view) — DONE
- P05-02 (tts-endpoint) — DONE
