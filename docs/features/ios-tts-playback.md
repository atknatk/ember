# iOS TTS Playback (P05-04)

## Overview

Adds text-to-speech playback to AI message bubbles in iOS ChatView. Users tap "Listen" to hear AI responses read aloud via the backend TTS service.

## Features

- **Listen button**: Speaker icon on AI message bubbles
- **Audio progress**: Play/pause, time labels, draggable scrubber
- **Speed control**: Cycles through 0.75x / 1.0x / 1.25x / 1.5x
- **Single playback**: Only one audio plays at a time
- **Auto-cleanup**: Stops playback when leaving chat

## User Flow

1. AI message bubble shows speaker.wave.2 icon
2. Tap → POST /tts with message text + character_id
3. Backend returns audio_url
4. AVPlayer plays audio, progress bar appears in bubble
5. User can pause, scrub, or change speed
6. Tapping Listen on another message stops current playback

## Architecture

### New Files
- `AudioPlayerManager.swift` — @Observable AVPlayer wrapper with CMTime progress tracking
- `AudioProgressView.swift` — Compact progress bar with scrubber and speed toggle
- `TTSModels.swift` — TTS request/response Codable models

### Modified Files
- `MessageBubbleView.swift` — Listen button and AudioProgressView on AI messages
- `ChatViewModel.swift` — TTS request flow and AudioPlayerManager instance
- `ChatService.swift` — synthesizeSpeech protocol method
- `APIEndpoint.swift` — .synthesizeSpeech case
- `MockChatService.swift` — TTS stub
