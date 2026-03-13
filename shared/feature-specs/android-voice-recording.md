# Feature Spec: Android Voice Recording (P05-05)

**Feature ID**: P05-05
**Layer**: Android
**Dependencies**: P04-05 (android-chat), P04-07 (android-profile)
**Status**: Designed

---

## Overview

Add voice recording capability to the Android ChatScreen. Users hold a mic button
to record audio, which is uploaded to S3 and transcribed via the STT endpoint. The
transcript is placed into the text input field for editing before sending.

---

## User Flow

1. User sees a mic icon button in the input bar (replaces the disabled mic placeholder).
2. User long-presses the mic button to begin recording.
3. Runtime RECORD_AUDIO permission is requested if not already granted.
4. During recording, a voice recording overlay appears showing:
   - Waveform animation (vertical bars driven by audio amplitude)
   - Recording duration timer (MM:SS)
   - "Slide up to cancel" hint text
   - Pulsing red recording indicator dot
5. User releases the button to stop recording and start transcription.
6. User can slide/drag upward to cancel the recording (audio is discarded).
7. Recording auto-stops at 2 minutes maximum.
8. After recording stops (not cancelled):
   a. Audio file is uploaded to S3 via presigned URL from `POST /api/v1/media/upload-url`.
   b. S3 file URL is sent to `POST /api/v1/stt` for transcription.
   c. Transcript text is set as the input field text for user review/edit.
9. User can then send the transcript as a normal text message.

---

## API Endpoints Used

### POST /api/v1/media/upload-url
Request:
```json
{
  "filename": "voice_1710345600000.m4a",
  "content_type": "audio/mp4",
  "type": "audio"
}
```
Response:
```json
{
  "upload_url": "https://s3...presigned-put-url",
  "file_url": "https://s3...permanent-url"
}
```

### PUT {upload_url}
Binary upload of the audio file with `Content-Type: audio/mp4`.

### POST /api/v1/stt
Request:
```json
{
  "audio_url": "https://s3...permanent-url"
}
```
Response:
```json
{
  "transcript": "Hello, how are you?",
  "language": "en",
  "confidence": 0.95,
  "duration_seconds": 3.2
}
```

---

## Audio Recording Spec

- **Format**: MPEG-4 container with AAC audio codec
- **Extension**: `.m4a`
- **Content-Type**: `audio/mp4`
- **Sample rate**: 44100 Hz
- **Channels**: Mono (1)
- **Max duration**: 120 seconds (auto-stop)
- **Output**: Temp file in app cache directory

---

## UI Components

### Modified: ChatInputBar
- When `inputText` is empty and not streaming: show mic button (enabled, EmberPrimary tint)
- When `inputText` is not empty: show mic button (disabled/hidden, current behavior)
- Mic button uses long-press gesture to start recording
- On long press: haptic feedback (LONG_PRESS), start recording
- On release: stop recording, begin upload/transcription
- On drag up (> 100dp threshold): cancel recording

### New: VoiceRecordingOverlay
- Full-width overlay that appears above the input bar during recording
- Background: EmberSurface with slight transparency
- Contains:
  - Red pulsing dot (recording indicator)
  - Duration timer text (MM:SS format)
  - Waveform visualization (animated bars)
  - "Slide up to cancel" text with upward arrow icon
- Slide up gesture cancels recording with haptic feedback

### New: WaveformBars
- Row of vertical bars (12 bars)
- Height driven by audio amplitude levels
- Animated with spring physics
- Color: EmberPrimary
- Bar width: 3dp, gap: 2dp, max height: 32dp

---

## ViewModel Changes

### New State: VoiceRecordingState
```kotlin
sealed interface VoiceRecordingState {
    data object Idle : VoiceRecordingState
    data class Recording(val durationMs: Long, val amplitudes: List<Float>) : VoiceRecordingState
    data object Uploading : VoiceRecordingState
    data object Transcribing : VoiceRecordingState
    data class Error(val message: String) : VoiceRecordingState
}
```

### New StateFlow in ChatViewModel
- `voiceState: StateFlow<VoiceRecordingState>` -- exposed to UI
- `startRecording()` -- begins MediaRecorder, starts amplitude polling
- `stopRecording()` -- stops recorder, triggers upload + STT pipeline
- `cancelRecording()` -- stops recorder, deletes temp file
- On successful transcription: sets `_inputText.value = transcript`

---

## New Files

1. `VoiceRecorder.kt` -- MediaRecorder wrapper class
2. `VoiceRecordingOverlay.kt` -- Recording UI overlay composable
3. `WaveformBars.kt` -- Animated waveform bar composable
4. `VoiceRecordingState.kt` -- Sealed state interface
5. `VoiceApi.kt` -- Retrofit interface for upload-url and STT endpoints

---

## Modified Files

1. `ChatInputBar.kt` -- Add mic button with long-press, recording overlay
2. `ChatViewModel.kt` -- Add voice recording flow
3. `ChatRepository.kt` -- Add upload URL, file upload, STT methods
4. `ChatModule.kt` -- Provide VoiceApi
5. `AndroidManifest.xml` -- Add RECORD_AUDIO permission
6. `strings.xml` -- Add voice recording strings

---

## Permission Handling

- Declare `android.permission.RECORD_AUDIO` in AndroidManifest.xml
- Request at runtime using `rememberLauncherForActivityResult(RequestPermission)`
- If denied: show a brief message, do not start recording
- If permanently denied: guide user to app settings (future enhancement)

---

## Error Handling

- Recording fails to start: show error via voiceState, clean up
- Upload fails: show error, allow retry
- STT fails: show error, allow retry
- Network offline: prevent recording start (check network state)
- Permission denied: show permission rationale

---

## Haptic Feedback

| Action | Constant |
|--------|----------|
| Start recording (long press) | `HapticFeedbackConstants.LONG_PRESS` |
| Stop recording (release) | `HapticFeedbackConstants.VIRTUAL_KEY` |
| Cancel recording (slide up) | `HapticFeedbackConstants.REJECT` |
| Transcription complete | `HapticFeedbackConstants.CONFIRM` |

---

## Accessibility

- Mic button: `contentDescription = "Record voice message"`
- Recording overlay: announce "Recording started" on appear
- Duration timer: live region for screen readers
- Cancel gesture: also provide a cancel button for accessibility
