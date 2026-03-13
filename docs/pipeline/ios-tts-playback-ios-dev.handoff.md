# iOS Dev Handoff: iOS TTS Playback (P05-04)

**Date**: 2026-03-13
**Agent**: ios-dev
**Status**: COMPLETE

## Implemented Files

### New Files
- `ios/Ember/Core/Models/TTSModels.swift` — TTSRequest (Encodable) and TTSResponse (Decodable) models
- `ios/Ember/Features/Chat/AudioPlayerManager.swift` — @Observable AVPlayer wrapper with progress tracking, speed control, one-at-a-time enforcement
- `ios/Ember/Features/Chat/AudioProgressView.swift` — Compact inline progress bar with play/pause, scrubber, time labels, speed toggle

### Modified Files
- `ios/Ember/Core/Extensions/EmberSymbol.swift` — Added `speaker`, `speakerFill`, `audioPlay`, `audioPause` constants
- `ios/Ember/Core/Network/APIEndpoint.swift` — Added `.synthesizeSpeech` case (POST /api/v1/tts)
- `ios/Ember/Features/Chat/ChatService.swift` — Added `synthesizeSpeech(request:)` to protocol + implementation
- `ios/Ember/Features/Chat/ChatViewModel.swift` — Added `audioPlayer`, `isRequestingTTS`, `requestTTS()`, `stopTTS()`, `TTSError` enum
- `ios/Ember/Features/Chat/MessageBubbleView.swift` — Added optional `audioPlayer`, `onListenTapped` params; TTS section with Listen button / AudioProgressView
- `ios/Ember/Features/Chat/ChatView.swift` — Passes audioPlayer/TTS state to MessageBubbleView; stops TTS on disappear
- `ios/EmberTests/Mocks/MockChatService.swift` — Added `synthesizeSpeech` stub with call tracking

## Screens Implemented
- ChatView: Listen button on AI message bubbles, inline audio progress bar with scrubber and speed control

## Deviations from Spec
- None

## Notes for iOS Tester
- `AudioPlayerManager` is @Observable — test state changes (isPlaying, currentTime, duration) via the mock service
- `ChatViewModel.requestTTS()` calls `service.synthesizeSpeech()` — inject `MockChatService` with `stubbedTTSResponse`
- Test one-at-a-time: calling `requestTTS` for message B while message A is playing should stop A
- Test speed cycling: `cycleSpeed()` should rotate through 0.75 -> 1.0 -> 1.25 -> 1.5 -> 0.75
- Test error case: set `shouldThrow` on MockChatService and verify `errorMessage` is set
- MessageBubbleView's Listen button only appears for `.assistant` role and non-streaming messages
- Audio playback stops when navigating away from ChatView (`.onDisappear`)
