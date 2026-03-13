# Android TTS Playback (P05-06)

## Overview

Adds text-to-speech playback to AI message bubbles in Android ChatScreen. Users tap "Listen" to hear AI responses read aloud via the backend TTS service with ExoPlayer (Media3).

## Features

- **Listen button**: Speaker icon on AI message bubbles
- **ExoPlayer playback**: Media3 ExoPlayer with buffering indicator
- **Progress bar**: Play/pause, time labels, linear progress indicator
- **Speed control**: Cycles through 0.75x / 1.0x / 1.25x / 1.5x
- **Single playback**: Only one audio plays at a time
- **Auto-cleanup**: Stops playback when leaving chat

## Architecture

### New Files
- `AudioPlaybackState.kt` — Sealed interface with Idle/Loading/Playing/Paused/Error
- `AudioPlayerManager.kt` — @Singleton ExoPlayer wrapper with StateFlow
- `AudioProgressBar.kt` — Compact progress composable with speed toggle

### Modified Files
- `VoiceApi.kt` — TTS endpoint + TTSRequest/TTSResponse data classes
- `ChatRepository.kt` — requestTTS method
- `ChatViewModel.kt` — TTS request flow, play/pause/stop, speed cycling
- `MessageBubble.kt` — Listen button and AudioProgressBar on AI messages
- `ChatScreen.kt` — Audio state collection and cleanup on dispose
- `build.gradle.kts` — Media3 ExoPlayer dependency
- `strings.xml` — TTS string resources
