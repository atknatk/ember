# iOS Voice Recording (P05-03)

## Overview

Adds voice recording capability to the iOS ChatView. Users can hold the mic button to record audio, which is uploaded to S3 and transcribed via the STT endpoint. The transcript appears in the message input for review before sending.

## Features

- **Hold-to-record**: Long press mic button (0.3s) to start recording
- **M4A format**: AVAudioRecorder with AAC codec, 44100Hz, mono
- **2-minute max**: Auto-stops recording at 2-minute limit
- **Swipe to cancel**: Drag up 60pt during recording to cancel
- **Waveform animation**: Real-time audio level visualization (24 bars)
- **Transcription flow**: S3 upload → POST /stt → transcript in input field
- **Permission handling**: NSMicrophoneUsageDescription, settings redirect on denial

## User Flow

1. Text field empty → mic button visible (replaces send button)
2. Long press mic → recording starts, overlay replaces input bar
3. Release → recording stops, "Transcribing..." state shown
4. Audio uploaded to S3, sent to STT endpoint
5. Transcript appears in text input for user to review/edit
6. User can then send the message normally

## Architecture

### New Files
- `VoiceRecorder.swift` — @Observable AVAudioRecorder wrapper with level metering
- `VoiceRecordingOverlay.swift` — Recording UI with waveform, timer, cancel gesture
- `WaveformView.swift` — Animated bar visualization from audio levels
- `STTModels.swift` — STT request/response Codable models

### Modified Files
- `ChatInputBar.swift` — Mic button with long press gesture
- `ChatViewModel.swift` — Recording flow and S3→STT processing
- `ChatService.swift` — Upload URL, S3 upload, and STT API methods
- `ChatView.swift` — Recording overlay and permission alert
- `APIEndpoint.swift` — `.transcribeAudio` case

## Known Limitations

- Recording cancels when app goes to background
- Maximum 2-minute recording duration
- Transcript placed in input (not auto-sent) — user must tap send
