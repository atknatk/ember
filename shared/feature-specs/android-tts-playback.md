# Feature Spec: Android TTS Playback (P05-06)

**Feature ID**: P05-06
**Layer**: Android
**Dependencies**: P04-05 (android-chat), P04-07 (android-profile)
**Agent**: architect

---

## Overview

Add text-to-speech playback to the Android ChatScreen. AI message bubbles gain
a speaker icon button that, when tapped, calls POST /api/v1/tts to synthesize
audio, then plays it via ExoPlayer (Media3). A compact audio progress bar
appears inside the message bubble during playback. Users can control speed
(0.75x / 1x / 1.25x / 1.5x) via PlaybackParameters.

---

## API Contract

### POST /api/v1/tts

**Request:**
```json
{
  "text": "string (1-5000 chars)",
  "character_id": "string",
  "voice_id": "string | null",
  "language": "string (default: en)"
}
```

**Response:**
```json
{
  "audio_url": "string (S3 URL)",
  "duration_seconds": "float | null"
}
```

---

## Architecture

### AudioPlayerManager (@Singleton)

A Hilt singleton wrapping Media3 ExoPlayer. Only one audio plays at a time.

**State (exposed as StateFlows):**
- `playbackState: StateFlow<AudioPlaybackState>` — sealed class:
  - `Idle` — nothing playing
  - `Loading(messageId: String)` — TTS request in flight
  - `Playing(messageId: String, currentMs: Long, durationMs: Long, speed: Float)`
  - `Paused(messageId: String, currentMs: Long, durationMs: Long, speed: Float)`
  - `Error(messageId: String, message: String)`

**Methods:**
- `play(url: String, messageId: String)` — stops current, loads new URI, plays
- `pause()` — pauses current playback
- `resume()` — resumes paused playback
- `stop()` — stops and resets to Idle
- `setSpeed(speed: Float)` — updates PlaybackParameters
- `release()` — releases ExoPlayer resources

**Implementation notes:**
- Uses `Player.Listener` for state callbacks
- Polls current position every 200ms via a coroutine while playing
- Speed values: 0.75f, 1.0f, 1.25f, 1.5f

### VoiceApi additions

Add TTS endpoint:
```kotlin
@POST("api/v1/tts")
suspend fun synthesizeSpeech(@Body request: TTSRequest): Response<TTSResponse>
```

### ChatRepository additions

```kotlin
suspend fun requestTTS(text: String, characterId: String): Result<TTSResponse>
```

### ChatViewModel additions

- Inject `AudioPlayerManager`
- Expose `audioPlaybackState: StateFlow<AudioPlaybackState>` from manager
- `requestTTS(messageId: String)` — finds message content, calls repo, plays audio
- `pauseAudio()`, `resumeAudio()`, `stopAudio()`
- `setPlaybackSpeed(speed: Float)`

### UI Changes

#### MessageBubble.kt
- Add speaker icon button (Icons.Outlined.VolumeUp) on AI messages only
- When audio is playing/paused for this message, show AudioProgressBar instead of icon
- Haptic feedback on tap (CONTEXT_CLICK)

#### AudioProgressBar.kt (new)
- Compact horizontal layout inside message bubble
- Play/Pause toggle icon button
- Time labels: elapsed / total (e.g., "0:08 / 0:23")
- Linear progress indicator (Slider or LinearProgressIndicator)
- Speed toggle button cycling through 0.75x -> 1x -> 1.25x -> 1.5x

#### ChatScreen.kt
- Stop audio on DisposableEffect (screen leave)
- Pass audio state and callbacks to ChatContent -> MessageBubble

---

## String Resources

```xml
<string name="tts_listen">Listen</string>
<string name="tts_pause">Pause</string>
<string name="tts_resume">Resume</string>
<string name="tts_stop">Stop</string>
<string name="tts_speed_label">Playback speed %1$s</string>
<string name="tts_loading">Loading audio…</string>
<string name="tts_error">Could not play audio</string>
<string name="tts_time_format">%1$d:%02d</string>
<string name="tts_progress_a11y">Audio playback at %1$s of %2$s</string>
```

---

## Dependencies

Add to `android/app/build.gradle.kts`:
```kotlin
implementation("androidx.media3:media3-exoplayer:1.5.1")
```

Add to `android/gradle/libs.versions.toml`:
```toml
media3 = "1.5.1"
media3-exoplayer = { group = "androidx.media3", name = "media3-exoplayer", version.ref = "media3" }
```

---

## Edge Cases

1. **Double tap**: If user taps listen while already loading, ignore second tap
2. **Switch message**: If user taps listen on different message while one plays, stop current and start new
3. **Screen leave**: Stop playback on screen dispose
4. **Network error**: Show snackbar error, reset to idle
5. **Empty text**: Do not show listen button on empty AI messages
6. **Streaming**: Do not show listen button while message is still streaming
