# Architect Handoff: iOS Voice Recording (P05-03)

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## Summary

Designed the voice recording feature for the iOS ChatView. Users hold a mic button to record audio (M4A, 44100Hz, 2min max), upload to S3 via presigned URL, transcribe via POST /stt, and display the transcript in the message input field.

## Spec Location

- `shared/feature-specs/ios-voice-recording.md`

## Key Decisions

1. **Hold-to-record UX**: Long press (0.3s min) starts recording, release stops. More natural than tap-to-toggle.
2. **M4A format**: AAC encoding in M4A container -- good quality/size ratio, native iOS support.
3. **Waveform visualization**: 24 bars updated at ~15Hz from AVAudioRecorder metering data.
4. **Swipe up to cancel**: Drag gesture with 60pt threshold, matches common messaging app patterns.
5. **Transcript-to-input**: Transcript goes to the text input (not auto-sent), allowing user to review/edit.
6. **2-minute limit**: Auto-stop timer prevents excessively large uploads.

## Handoff to iOS Dev

- Feature spec is complete at `shared/feature-specs/ios-voice-recording.md`
- All API endpoints are already implemented on the backend
- Existing `UploadURLRequest`/`UploadURLResponse` models in `ProfileModels.swift` can be reused
- New `STTRequest`/`STTResponse` models needed in `Core/Models/STTModels.swift`
- New `.transcribeAudio` case needed in `APIEndpoint.swift`
