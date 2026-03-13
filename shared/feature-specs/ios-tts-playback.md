# Feature Spec: iOS TTS Playback (P05-04)

## Overview

Add text-to-speech (TTS) playback to iOS ChatView. Users can tap a "Listen" button on AI message bubbles to hear the message read aloud. Audio is synthesized via the backend `POST /api/v1/tts` endpoint (ElevenLabs Flash v2.5 / AWS Polly fallback) and played back with AVPlayer.

## User Flow

1. AI sends a text response (SSE stream completes)
2. User taps "Listen" (speaker.wave.2 icon) below the AI message text
3. App sends `POST /api/v1/tts` with `{ text, character_id }`
4. Backend returns `{ audio_url, duration_seconds }`
5. App plays audio via AVPlayer with `.playback` audio session
6. Message bubble shows inline progress bar: play/pause, time slider, speed control
7. Tapping another message's "Listen" stops the current audio and starts the new one

## API Contract

### Request: `POST /api/v1/tts`

```json
{
  "text": "Bugün harika bir antrenman yaptın!",
  "character_id": "char_abc123"
}
```

### Response: `200 OK`

```json
{
  "audio_url": "https://s3.amazonaws.com/ember-audio/tts/abc123.mp3",
  "duration_seconds": 4.2
}
```

## UI Components

### Listen Button (compact, default state)
- SF Symbol: `speaker.wave.2`
- Text: "Listen"
- Color: `emberTextSecondary`
- Position: Below message text, inside the bubble
- Shows loading spinner when TTS request is in flight

### Audio Progress Bar (expanded, when playing)
- Play/Pause button (play.fill / pause.fill)
- Current time label (M:SS)
- Scrubber slider with draggable thumb
- Duration label (M:SS)
- Speed toggle button: cycles 0.75x -> 1x -> 1.25x -> 1.5x

## Technical Requirements

### Audio Session
- Category: `.playback` (audio continues when screen locks)
- Mode: `.default`
- Configured before each playback start

### One Audio at a Time
- Starting playback on a new message stops the previous one
- AudioPlayerManager is shared across all message bubbles via ChatViewModel

### Playback Speed
- Default: 1.0x
- Options: 0.75x, 1.0x, 1.25x, 1.5x
- Persists within session (resets when leaving chat)
- Haptic feedback on speed change (selection)

### Progress Tracking
- CMTime periodic observer at 0.1s intervals
- Duration read from AVPlayerItem when available
- Fallback to server-provided `duration_seconds`
- Reset to start when playback completes

## Dependencies

- P03-07: iOS ChatView (done)
- P05-02: TTS backend endpoint (done)

## Layer

iOS only.
