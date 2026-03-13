# Android Voice Recording (P05-05)

## Overview

Adds voice recording to Android ChatScreen. Users hold the mic button to record audio, which is uploaded to S3 and transcribed via the STT endpoint. The transcript appears in the message input for review before sending.

## Features

- **Hold-to-record**: Long press mic button to start recording
- **MPEG_4/AAC format**: MediaRecorder at 44100Hz mono
- **2-minute max**: Auto-stops recording at limit
- **Drag to cancel**: Swipe up 100dp during recording to cancel
- **Waveform animation**: 12 animated bars from amplitude polling (100ms)
- **Transcription flow**: S3 upload → POST /stt → transcript in input
- **Permission handling**: Runtime RECORD_AUDIO permission request

## Architecture

### New Files
- `VoiceRecordingState.kt` — Sealed interface with Idle/Recording/Uploading/Transcribing/Error
- `VoiceApi.kt` — Retrofit interface + STT data classes
- `VoiceRecorder.kt` — @Singleton MediaRecorder wrapper with StateFlow
- `WaveformBars.kt` — Animated bar composable
- `VoiceRecordingOverlay.kt` — Recording UI with timer and cancel hint

### Modified Files
- `ChatInputBar.kt` — Mic button with drag-to-cancel gesture
- `ChatViewModel.kt` — Recording flow and upload→STT pipeline
- `ChatRepository.kt` — Upload URL, S3 upload, STT API methods
- `ChatModule.kt` — Hilt provider for VoiceApi
- `ChatScreen.kt` — Permission launcher, snackbar errors, haptics
- `AndroidManifest.xml` — RECORD_AUDIO permission
- `strings.xml` — Voice recording strings
