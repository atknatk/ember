# Feature Spec: iOS Voice Recording (P05-03)

## Overview

Add voice recording capability to the iOS ChatView. Users hold a mic button to record audio, which is uploaded to S3 and transcribed via STT, with the transcript inserted into the message input field.

## Layer

`ios`

## Dependencies

- P03-07 (ios-chat-view) -- already implemented
- P01-10 (media-upload backend) -- already implemented
- Voice STT backend endpoint (`POST /api/v1/stt`) -- already implemented

## User Stories

1. **As a user**, I want to hold a mic button to record a voice message so I can compose messages hands-free.
2. **As a user**, I want to see a visual recording indicator (waveform + timer) so I know recording is active.
3. **As a user**, I want to swipe up to cancel a recording so I can abort without sending.
4. **As a user**, I want my voice to be transcribed and placed in the text input so I can review/edit before sending.

## Technical Design

### Architecture

```
ChatInputBar (modified)
  └── mic button (long press gesture)
        ├── VoiceRecorder (@Observable, AVAudioRecorder wrapper)
        │     ├── startRecording() -> requests mic permission if needed
        │     ├── stopRecording() -> URL?
        │     └── cancelRecording()
        └── VoiceRecordingOverlay (SwiftUI view)
              ├── WaveformView (animated bars from audio levels)
              ├── Duration timer
              └── "Slide up to cancel" hint

ChatViewModel (modified)
  └── processVoiceRecording(audioURL: URL) async
        ├── Step 1: POST /api/v1/media/upload-url (get presigned URL)
        ├── Step 2: PUT to presigned URL (upload M4A file)
        └── Step 3: POST /api/v1/stt (get transcript)
              └── Sets inputText = transcript
```

### Audio Recording Configuration

- **Format**: M4A (AAC)
- **Sample rate**: 44100 Hz
- **Channels**: 1 (mono)
- **Max duration**: 2 minutes (auto-stop with timer)
- **Audio session category**: `.record`

### New Files

| File | Purpose |
|------|---------|
| `ios/Ember/Features/Chat/VoiceRecorder.swift` | @Observable class wrapping AVAudioRecorder |
| `ios/Ember/Features/Chat/VoiceRecordingOverlay.swift` | Recording overlay UI with waveform + timer |
| `ios/Ember/Features/Chat/WaveformView.swift` | Animated waveform bars |
| `ios/Ember/Core/Models/STTModels.swift` | STT request/response Codable models |

### Modified Files

| File | Change |
|------|--------|
| `ios/Ember/Features/Chat/ChatInputBar.swift` | Add mic button (shown when text is empty), long-press gesture |
| `ios/Ember/Features/Chat/ChatViewModel.swift` | Add VoiceRecorder, processVoiceRecording() method |
| `ios/Ember/Core/Network/APIEndpoint.swift` | Add `.transcribeAudio` case |
| `ios/Ember/Core/Extensions/EmberSymbol.swift` | Add voice recording symbols |

### API Endpoints Used

1. `POST /api/v1/media/upload-url` (existing `.uploadURL` endpoint)
   - Request: `{ "filename": "voice_xxx.m4a", "content_type": "audio/mp4", "type": "audio" }`
   - Response: `{ "upload_url": "...", "file_url": "..." }`

2. `PUT {presigned_url}` (direct S3 upload, no auth header)
   - Body: raw audio data
   - Content-Type: `audio/mp4`

3. `POST /api/v1/stt` (new endpoint case)
   - Request: `{ "audio_url": "..." }`
   - Response: `{ "transcript": "...", "language": "en", "confidence": 0.97 }`

### Microphone Permission

- `NSMicrophoneUsageDescription` must be added to Xcode project Info settings
- Permission requested on first recording attempt via `AVAudioSession.requestRecordPermission`
- Denied state: show alert directing user to Settings

### Gesture Design

- **Start recording**: Long press on mic button (min 0.3s)
- **Stop recording**: Release finger
- **Cancel recording**: Drag up > 60pt while holding
- Haptic feedback: `.rigid` on start, `.notification(.success)` on stop, `.notification(.warning)` on cancel

### Recording Overlay UI

- Full-width bar replacing the input bar during recording
- Left: red recording dot (pulsing animation)
- Center: WaveformView (animated bars) + duration timer (MM:SS)
- Bottom hint: "Slide up to cancel" with upward chevron
- Background: `Color.emberSurface` with slight opacity

### WaveformView

- 20-30 vertical bars
- Height driven by normalized audio power levels (0.0-1.0)
- Bars animate with spring physics
- Color: `Color.emberPrimary`

## Edge Cases

- Microphone permission denied: show alert with "Open Settings" button
- Recording exceeds 2 min: auto-stop and process
- Network failure during upload: show error via existing error banner
- STT returns empty transcript: show "Could not transcribe audio" error
- App backgrounded during recording: stop and discard recording
- Simultaneous streaming: disable mic button while AI is streaming

## Acceptance Criteria

1. Mic button appears when text input is empty
2. Long press starts recording with haptic feedback and visual overlay
3. Waveform animates based on audio levels
4. Duration timer counts up in MM:SS format
5. Releasing finger stops recording and initiates upload + STT flow
6. Swiping up > 60pt cancels recording with haptic feedback
7. Transcript appears in text input field after STT completes
8. 2-minute max recording enforced with auto-stop
9. Microphone permission requested on first use
10. All icon buttons have accessibilityLabel
11. Recording state properly cleaned up on cancel/error/background
