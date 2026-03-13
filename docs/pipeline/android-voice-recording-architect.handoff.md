# Architect Handoff: Android Voice Recording (P05-05)

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## Summary

Designed voice recording feature for Android ChatScreen. Hold-to-record mic button
with MediaRecorder (MPEG-4/AAC), upload to S3 via presigned URL, transcribe via
POST /api/v1/stt, show transcript in text input for editing before send.

## Spec Location

`shared/feature-specs/android-voice-recording.md`

## Key Decisions

- Audio format: MPEG-4/AAC (.m4a) -- matches backend supported formats
- Transcript goes into text input (not auto-sent) so user can review/edit
- Max recording duration: 2 minutes with auto-stop
- Cancel via slide-up gesture (100dp threshold)
- VoiceRecordingState is a separate sealed interface from ChatUiState
- VoiceRecorder is a standalone class (not ViewModel) for testability

## API Endpoints

- `POST /api/v1/media/upload-url` (existing) -- get presigned S3 URL
- `PUT {presigned_url}` -- upload audio binary
- `POST /api/v1/stt` (existing) -- transcribe audio

## Files to Create

- `VoiceRecorder.kt` -- MediaRecorder wrapper
- `VoiceRecordingOverlay.kt` -- Recording UI overlay
- `WaveformBars.kt` -- Animated waveform visualization
- `VoiceRecordingState.kt` -- Sealed state interface
- `VoiceApi.kt` -- Retrofit API for media/STT endpoints

## Files to Modify

- `ChatInputBar.kt` -- Mic button with long-press
- `ChatViewModel.kt` -- Voice recording flow
- `ChatRepository.kt` -- Upload + STT methods
- `ChatModule.kt` -- Provide VoiceApi
- `AndroidManifest.xml` -- RECORD_AUDIO permission
- `strings.xml` -- Voice recording strings

## Notes for Android Dev

- Use the existing `OkHttpClient` from Hilt for the presigned PUT upload
- VoiceRecorder should use `Context` from Hilt `@ApplicationContext`
- Amplitude polling at ~100ms intervals for smooth waveform
- Temp files go in `context.cacheDir`
