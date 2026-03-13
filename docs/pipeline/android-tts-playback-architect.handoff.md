# Architect Handoff: Android TTS Playback

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## Feature
P05-06 — android-tts-playback

## Spec Location
`shared/feature-specs/android-tts-playback.md`

## Summary
TTS playback in Android ChatScreen. Speaker icon on AI messages -> POST /api/v1/tts -> ExoPlayer (Media3) playback. Compact progress bar composable inside message bubble. Speed control 0.75x/1x/1.25x/1.5x.

## Key Decisions
- AudioPlayerManager as @Singleton Hilt class (one player at a time)
- Sealed AudioPlaybackState for type-safe state management
- 200ms position polling via coroutine (not seekbar listener)
- Speed cycling button instead of dropdown menu (more compact)
- No auto-play — user must tap speaker icon

## Dependencies
- Media3 ExoPlayer 1.5.1 (new dependency)
- Backend POST /api/v1/tts endpoint (already implemented)

## Notes for Android Dev
- Match existing ChatRepository pattern for TTS API call
- Match existing VoiceApi pattern for Retrofit interface addition
- AudioPlayerManager must handle lifecycle (release on app destroy)
- MessageBubble already has context menu — listen button goes above timestamp
