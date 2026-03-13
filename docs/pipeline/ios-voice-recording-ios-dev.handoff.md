# iOS Dev Handoff: iOS Voice Recording (P05-03)

**Date**: 2026-03-13
**Agent**: ios-dev
**Status**: COMPLETE

## Implemented Files

### New Files
- `ios/Ember/Features/Chat/VoiceRecorder.swift` -- @Observable class wrapping AVAudioRecorder with metering
- `ios/Ember/Features/Chat/VoiceRecordingOverlay.swift` -- Recording overlay UI with waveform, timer, cancel gesture
- `ios/Ember/Features/Chat/WaveformView.swift` -- Animated waveform bar visualization
- `ios/Ember/Core/Models/STTModels.swift` -- STTRequest and STTResponse Codable models

### Modified Files
- `ios/Ember/Features/Chat/ChatInputBar.swift` -- Added mic button (shown when text field empty), long-press gesture to start/stop recording
- `ios/Ember/Features/Chat/ChatViewModel.swift` -- Added VoiceRecorder instance, startRecording/stopRecording/cancelRecording methods, processVoiceRecording (upload + STT) flow
- `ios/Ember/Features/Chat/ChatService.swift` -- Added getUploadURL, uploadFile, transcribeAudio methods to protocol and implementation
- `ios/Ember/Features/Chat/ChatView.swift` -- Added VoiceRecordingOverlay, mic permission alert, background-cancel observer
- `ios/Ember/Core/Network/APIEndpoint.swift` -- Added `.transcribeAudio` case for POST /api/v1/stt
- `ios/Ember/Core/Extensions/EmberSymbol.swift` -- Added microphoneSlash, waveform, stopCircle symbols
- `ios/Ember.xcodeproj/project.pbxproj` -- Added NSMicrophoneUsageDescription in both Debug and Release build configs

## Screens Implemented
- **ChatInputBar**: Mic button appears when text input is empty. Long press starts recording, release stops.
- **VoiceRecordingOverlay**: Replaces input bar during recording. Shows pulsing red dot, waveform, timer, "Slide up to cancel" hint.
- **Mic Permission Alert**: Shown when microphone access is denied, with "Open Settings" button.

## Deviations from Spec
- None

## Notes for iOS Tester
- `ChatServiceProtocol` now has three new methods: `getUploadURL`, `uploadFile`, `transcribeAudio` -- create mocks for all three
- `VoiceRecorder` uses AVAudioRecorder which requires a real device -- mock the recorder for unit tests
- Test the 2-minute auto-stop by setting `maxDuration` to a smaller value in tests
- Test the cancel gesture by simulating a drag offset beyond 60pt
- Test app backgrounding during recording -- should cancel and clean up
- Test permission denied flow -- should show alert with Settings button
- `VoiceRecordingError` has three cases: `invalidUploadURL`, `emptyTranscript`, `recordingFailed`
- The processVoiceRecording flow has three network calls in sequence -- test each failure point
