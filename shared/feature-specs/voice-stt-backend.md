# Feature Spec: Voice STT Backend (P05-02)

**Feature ID**: P05-02
**Layer**: backend
**Status**: SPEC COMPLETE
**Date**: 2026-03-13

## Overview

Speech-to-text endpoint that accepts an S3 audio URL, downloads the audio,
sends it to OpenAI Whisper API for transcription, and returns the transcript
with detected language and confidence score.

## Endpoint

### POST /api/v1/stt

**Auth**: Bearer JWT (required)

**Request Body**:
```json
{
  "audio_url": "https://s3.amazonaws.com/ember-media/audio/user_id/recording.m4a"
}
```

**Response (200)**:
```json
{
  "transcript": "I want to practice speaking today",
  "language": "en",
  "confidence": 0.97,
  "duration_seconds": 4.2
}
```

**Error Responses**:
- `400` — Unsupported audio format (not M4A/MP3/WAV/OGG)
- `401` — Missing or invalid JWT
- `413` — Audio file exceeds 25MB
- `422` — Validation error (missing/invalid audio_url)
- `429` — Rate limit exceeded
- `503` — Whisper API unavailable

## Constraints

- **Supported formats**: M4A, MP3, WAV, OGG
- **Max file size**: 25MB (Whisper API limit)
- **Audio source**: Must be an S3 URL from the configured bucket
- **Blocking calls**: OpenAI Whisper SDK is synchronous; wrap in `asyncio.to_thread`
- **No new DB tables**: This is a stateless transcription endpoint

## Flow

1. Validate JWT, extract user from token
2. Validate `audio_url` format and extension
3. Download audio from S3 using boto3 (via `asyncio.to_thread`)
4. Validate file size (reject if > 25MB)
5. Send audio bytes to OpenAI Whisper API (`asyncio.to_thread`)
6. Return transcript, detected language, confidence, and duration

## Acceptance Criteria

- [ ] POST /api/v1/stt returns 200 with transcript for valid audio
- [ ] Returns 400 for unsupported audio formats
- [ ] Returns 413 for files exceeding 25MB
- [ ] Returns 422 for missing/invalid audio_url
- [ ] Returns 401 without valid JWT
- [ ] Returns 503 when Whisper API is unavailable
- [ ] All external calls (S3 download, Whisper) use asyncio.to_thread
- [ ] No hardcoded API keys
- [ ] Tests pass with mocked S3 and Whisper
