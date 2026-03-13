# Voice STT Backend (P05-02)

## Overview

Speech-to-Text backend service that transcribes audio files using OpenAI Whisper API. Accepts S3 audio URLs, validates format and size, and returns transcripts with language detection and confidence scores.

## API Reference

### POST /api/v1/stt

Transcribe an audio file to text.

**Auth**: JWT Bearer token required

**Request Body**:
```json
{
  "audio_url": "https://s3.amazonaws.com/bucket/audio/file.m4a"
}
```

**Response** (200):
```json
{
  "transcript": "Hello, how are you today?",
  "language": "en",
  "confidence": 0.95,
  "duration_seconds": 3.5
}
```

**Errors**:
- `400` — Unsupported audio format
- `413` — File exceeds 25MB limit
- `422` — Invalid request (missing/malformed audio_url)
- `503` — Whisper API unavailable

### Supported Formats
- M4A, MP3, WAV, OGG

### Size Limit
- Maximum 25MB per audio file

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key for Whisper | Required |
| `AWS_S3_BUCKET` | S3 bucket for audio files | Required |

## Architecture

1. Client sends `audio_url` (S3 presigned URL from P01-10)
2. Service downloads audio from S3
3. Validates format (extension check) and size (Content-Length header)
4. Sends to OpenAI Whisper API via `asyncio.to_thread`
5. Computes confidence from segment log probabilities
6. Returns transcript, detected language, confidence, and duration

## Known Limitations

- Batch transcription only (not real-time streaming)
- Maximum 25MB file size (Whisper API limit)
- Confidence score is derived from average segment logprobs
- No caching of transcription results (each request re-transcribes)
