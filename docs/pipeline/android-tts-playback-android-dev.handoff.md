# Android Dev Handoff: Android TTS Playback

**Date**: 2026-03-13
**Agent**: android-dev
**Status**: COMPLETE

## Implemented Files

### New Files
- `android/app/src/main/java/ai/ember/app/features/chat/AudioPlaybackState.kt` — Sealed interface for playback states + speed options
- `android/app/src/main/java/ai/ember/app/features/chat/AudioPlayerManager.kt` — @Singleton Hilt class wrapping Media3 ExoPlayer
- `android/app/src/main/java/ai/ember/app/features/chat/AudioProgressBar.kt` — Compact progress bar composable for message bubbles

### Modified Files
- `android/app/src/main/java/ai/ember/app/features/chat/VoiceApi.kt` — Added TTSRequest, TTSResponse, synthesizeSpeech endpoint
- `android/app/src/main/java/ai/ember/app/features/chat/ChatRepository.kt` — Added requestTTS method
- `android/app/src/main/java/ai/ember/app/features/chat/ChatViewModel.kt` — Added AudioPlayerManager injection, TTS request/playback/speed methods
- `android/app/src/main/java/ai/ember/app/features/chat/MessageBubble.kt` — Added speaker icon on AI messages, AudioProgressBar integration
- `android/app/src/main/java/ai/ember/app/features/chat/ChatScreen.kt` — Passes audio state to ChatContent/MessageBubble, stops audio on dispose
- `android/app/build.gradle.kts` — Added Media3 ExoPlayer dependency
- `android/gradle/libs.versions.toml` — Added media3 version and library entry
- `android/app/src/main/res/values/strings.xml` — Added TTS string resources

## Screens Implemented
- ChatScreen: TTS listen button on AI message bubbles, compact audio progress bar with play/pause/speed controls

## strings.xml Keys Added
- `tts_listen`: "Listen"
- `tts_pause`: "Pause"
- `tts_resume`: "Resume"
- `tts_stop`: "Stop"
- `tts_speed_label`: "Playback speed %1$s"
- `tts_loading`: "Loading audio..."
- `tts_error`: "Could not play audio"
- `tts_progress_a11y`: "Audio playback at %1$s of %2$s"

## Deviations from Spec
- None

## Notes for Android Tester
- ViewModel depends on `AudioPlayerManager` — use MockK `mockk<AudioPlayerManager>(relaxed = true)`
- AudioPlayerManager.playbackState is a StateFlow — use Turbine `.test { }` for assertions
- TTS flow: mock `chatRepository.requestTTS()` to return `Result.success(TTSResponse(audioUrl = "...", durationSeconds = 5.0f))`
- Speed cycling: 0.75f -> 1.0f -> 1.25f -> 1.5f -> 0.75f (wraps around)
- Listen button only visible on AI messages that are not empty and not streaming
- ExoPlayer is lazily initialized — no real playback in unit tests, mock the manager
