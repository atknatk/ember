# Feature Spec: Voice TTS Backend (P05-01)

## Overview

Backend TTS (Text-to-Speech) service using ElevenLabs Flash v2.5 as primary provider and AWS Polly as fallback, with audio caching in S3.

## Endpoint

**POST /api/v1/tts**

### Request
```json
{
  "text": "That's great progress! Your vocabulary is improving.",
  "character_id": "uuid",
  "voice_id": "optional-elevenlabs-voice-id",
  "language": "en"
}
```

### Response (200)
```json
{
  "audio_url": "https://s3.amazonaws.com/.../tts/uuid/hash.mp3",
  "duration_seconds": null
}
```

## Provider Strategy

### Hybrid Routing
- **Short texts (< 150 chars):** Routed directly to AWS Polly (faster, cheaper)
- **Long texts (>= 150 chars):** Routed to ElevenLabs Flash v2.5 (higher quality)
- **Fallback:** If ElevenLabs fails, Polly is used as fallback for all text lengths

### ElevenLabs Flash v2.5
- Model: `eleven_flash_v2_5` (multilingual, 135ms TTFA)
- Output: MP3 (audio/mpeg)
- Language hint sent for non-English text

### AWS Polly (Fallback)
- Engine: Neural
- Voice mapping: `tr` -> Burcu, `en` -> Joanna, `de` -> Vicki, `fr` -> Lea, `es` -> Lucia
- Output: MP3

## Circuit Breaker

Dedicated `ElevenLabsCircuitBreaker` (separate from Mem0 circuit breaker):
- 3-state: CLOSED, OPEN, HALF_OPEN
- Failure threshold: 3 consecutive failures
- Recovery timeout: 60 seconds
- When open, all requests go directly to Polly

## Audio Caching

- Hash-based S3 keys: `tts/{user_id}/{sha256(text|voice_id|language)[:32]}.mp3`
- Before synthesis, checks S3 for existing audio via `HEAD` request
- Identical text+voice+language combinations are served from cache

## Character Validation

- Character must exist and be active
- Character must belong to the authenticated user
- user_id extracted from JWT (never from request body)

## Error Handling

| Code | Condition |
|------|-----------|
| 200 | Audio generated or cached URL returned |
| 401 | Missing or invalid JWT |
| 403 | Character belongs to another user |
| 404 | Character not found |
| 422 | Validation error (empty text, missing fields) |
| 503 | Both TTS providers unavailable |

## Files

- `backend/app/routes/tts.py` -- 1 endpoint
- `backend/app/services/tts_service.py` -- TTSService + ElevenLabsCircuitBreaker
- `backend/app/schemas/tts.py` -- TTSRequest, TTSResponse
- `shared/api-contracts/paths/tts.yaml` -- OpenAPI path
- `shared/api-contracts/schemas/tts.yaml` -- OpenAPI schemas
