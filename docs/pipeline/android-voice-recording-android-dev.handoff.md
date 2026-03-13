# Android Dev Handoff: Voice Recording (P05-05)

**Date**: 2026-03-13
**Agent**: android-dev
**Status**: COMPLETE

## Implemented Files

### New Files
- `android/app/src/main/java/ai/ember/app/features/chat/VoiceRecordingState.kt` -- Sealed state interface for voice recording lifecycle
- `android/app/src/main/java/ai/ember/app/features/chat/VoiceApi.kt` -- Retrofit API for upload-url and STT endpoints with request/response models
- `android/app/src/main/java/ai/ember/app/features/chat/VoiceRecorder.kt` -- MediaRecorder wrapper with amplitude polling for waveform
- `android/app/src/main/java/ai/ember/app/features/chat/WaveformBars.kt` -- Animated vertical bar waveform composable
- `android/app/src/main/java/ai/ember/app/features/chat/VoiceRecordingOverlay.kt` -- Recording overlay with pulsing dot, timer, waveform, cancel hint

### Modified Files
- `android/app/src/main/java/ai/ember/app/features/chat/ChatInputBar.kt` -- Added MicButton with drag-to-cancel, VoiceRecordingOverlay, processing indicator
- `android/app/src/main/java/ai/ember/app/features/chat/ChatViewModel.kt` -- Added voice recording flow (start/stop/cancel recording, upload+STT pipeline)
- `android/app/src/main/java/ai/ember/app/features/chat/ChatRepository.kt` -- Added getUploadUrl, uploadAudioFile, transcribeAudio methods + VoiceApi dependency
- `android/app/src/main/java/ai/ember/app/features/chat/ChatModule.kt` -- Added VoiceApi provider
- `android/app/src/main/java/ai/ember/app/features/chat/ChatScreen.kt` -- Added voiceState collection, permission launcher, snackbar for voice errors
- `android/app/src/main/res/values/strings.xml` -- Added voice recording string resources
- `android/app/src/main/AndroidManifest.xml` -- Added RECORD_AUDIO permission

## Screens Implemented
- ChatScreen: Voice recording integration with hold-to-record mic button, waveform overlay, upload+transcription pipeline

## strings.xml Keys Added
- `voice_record`: "Record voice message"
- `voice_slide_to_cancel`: "Slide up to cancel"
- `voice_transcribing`: "Transcribing..."
- `voice_uploading`: "Uploading audio..."
- `voice_permission_denied`: "Microphone permission is required to record voice messages"
- `voice_recording_a11y`: "Recording in progress. %1$s elapsed"
- `voice_cancel_a11y`: "Cancel recording"
- Updated `chat_voice_message`: removed "coming soon" suffix

## Deviations from Spec
- None

## Notes for Android Tester
- VoiceRecorder depends on `Context` via `@ApplicationContext` -- use `ApplicationProvider.getApplicationContext()` in tests
- ChatViewModel now requires `VoiceRecorder` in constructor -- add `mockk<VoiceRecorder>()` to test setup
- ChatRepository now requires `VoiceApi` in constructor -- add `mockk<VoiceApi>()` to test setup
- Voice flow: `startRecording()` -> `stopRecording()` triggers async upload+STT
- Mock `VoiceRecorder.state` as a `MutableStateFlow<VoiceRecordingState>` for state assertions
- Test cancel flow: verify `VoiceRecorder.cancel()` is called and state resets to Idle
- Upload uses raw OkHttp PUT (not Retrofit) -- test `uploadAudioFile` with MockWebServer
- Permission handling is in ChatScreen composable -- use Compose test rules with `GrantPermissionRule` for instrumented tests
- The drag-to-cancel threshold is 100dp upward
