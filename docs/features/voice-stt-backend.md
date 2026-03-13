# Voice STT Backend

> Transcribes audio recordings to text by downloading audio from S3, validating the file, and sending it to OpenAI Whisper for multilingual transcription with confidence scoring.

**Status**: Released
**Added in**: Phase 5 (P05-02)
**Platforms**: Backend

---

## Overview

Ember's speech-to-text endpoint gives mobile clients a way to convert audio recordings into text they can send as chat messages. Rather than streaming audio in real time, the endpoint works asynchronously: the client first uploads an audio file to S3 via the media upload endpoint (P01-10), then calls this endpoint with the resulting S3 URL.

The backend downloads the audio, validates its format and size, and forwards the bytes to OpenAI Whisper using the `whisper-1` model with `verbose_json` response format. Whisper detects the language automatically — no client-side language hint is required. The response includes the transcript, the detected language code, a confidence score derived from Whisper's per-segment log-probabilities, and the audio duration in seconds.

This endpoint is intentionally stateless. It reads no database tables and writes nothing to the database or Mem0. The mobile client is responsible for taking the returned transcript and sending it as a chat message via the standard chat endpoint (P01-06). The separation of concerns keeps the STT endpoint simple and independently testable.

---

## Architecture

### How It Works (Data Flow)

1. The mobile client records audio and uploads it to S3 via `POST /api/v1/media/upload-url` (P01-10), receiving a permanent `file_url`.
2. The client calls `POST /api/v1/stt` with `Authorization: Bearer <jwt>` and the S3 `file_url` as `audio_url` in the JSON body.
3. The route handler resolves the authenticated user via the `get_current_user` dependency. The user identity is used only for authentication — no user-specific logic is applied to the transcription itself.
4. The route instantiates `STTService` and calls `transcribe(audio_url=body.audio_url)`.
5. `STTService._parse_s3_url()` parses the URL and extracts the S3 bucket name and object key. Both virtual-hosted style (`bucket.s3.region.amazonaws.com/key`) and path-style (`s3.region.amazonaws.com/bucket/key`) URLs are supported.
6. `STTService._get_extension()` extracts the file extension from the S3 key (ignoring any query parameters). If the extension is not one of `.m4a`, `.mp3`, `.wav`, `.ogg`, a 400 error is raised.
7. Note: unsupported formats are also caught earlier at the Pydantic schema layer (returning 422), so the service-level check is a defense-in-depth safeguard.
8. `STTService._download_from_s3()` calls `boto3.client.get_object()` via `asyncio.to_thread()` to keep the async event loop unblocked. If the key does not exist (`NoSuchKey`), a 400 error is returned; other S3 errors return 503.
9. The downloaded byte length is checked against the 25 MB limit (26,214,400 bytes). Files that exceed this raise 413.
10. `STTService._call_whisper()` checks that `settings.openai_api_key` is non-empty (503 if missing), then calls `STTService._whisper_transcribe()` via `asyncio.to_thread()` because the OpenAI Python SDK is synchronous.
11. `_whisper_transcribe()` creates an `OpenAI` client, wraps the audio bytes in a `BytesIO` object with the filename set (so Whisper infers MIME type from the name), and calls `client.audio.transcriptions.create()` with `response_format="verbose_json"`.
12. `_compute_average_confidence()` derives a 0–1 confidence score by averaging `math.exp(segment.avg_logprob)` across all returned segments and clamping to `[0.0, 1.0]`. If no segment data is present, confidence is `0.0`.
13. The route handler maps the result dict to an `STTResponse` Pydantic model and returns HTTP 200.

### Confidence Score Derivation

Whisper's `verbose_json` format does not include a single top-level confidence value. Each segment carries `avg_logprob`, the average log-probability over tokens in that segment. The service converts this to a linear scale with `exp(avg_logprob)` and averages across all segments. Because `avg_logprob` is typically a negative value close to zero for high-quality transcriptions (e.g., `-0.1` yields `~0.905`), the result is a natural 0–1 float. The value is clamped to `[0.0, 1.0]` and rounded to 4 decimal places. When Whisper returns no segment data, the confidence is reported as `0.0` rather than omitted.

### S3 URL Parsing

The service handles both S3 URL styles in production:

| Style | Format | Example |
|-------|--------|---------|
| Virtual-hosted | `https://{bucket}.s3.{region}.amazonaws.com/{key}` | `https://ember-media.s3.us-east-1.amazonaws.com/audio/usr123/rec.m4a` |
| Path-style | `https://s3.{region}.amazonaws.com/{bucket}/{key}` | `https://s3.us-east-1.amazonaws.com/ember-media/audio/usr123/rec.m4a` |

The URL must be an `amazonaws.com` URL; any other domain returns 400. This prevents callers from directing the backend to download audio from arbitrary external URLs.

### Threading Model

Both external calls — S3 download and Whisper transcription — use `asyncio.to_thread()`. The boto3 S3 client and the OpenAI Python SDK are both synchronous. Running them directly in the async route handler would block the FastAPI event loop. `asyncio.to_thread()` moves each call to the default thread pool, keeping the server responsive during the download and transcription wait.

The module-level `_s3_client` is created once at import time and reused across requests. boto3 clients manage their own connection pool and credential cache; per-request instantiation would be wasteful.

### Database Tables Involved

This feature does not read from or write to any database table. The `get_current_user` dependency validates the JWT and provides the `Profile` object, but no database query is issued by the STT endpoint itself.

| Table | Operation | Notes |
|-------|-----------|-------|
| (none) | — | Stateless endpoint; all data comes from S3 and Whisper |

### No Mem0 Operations

This feature does not interact with Mem0. Memory storage is the responsibility of the chat endpoint (P01-06) when the client sends the transcript as a message.

---

## API Reference

### `POST /api/v1/stt`

Transcribes audio from an S3 URL to text using OpenAI Whisper.

**Auth**: Bearer JWT required
**Content-Type**: `application/json`

**Request Body**:

```json
{
  "audio_url": "https://ember-media.s3.us-east-1.amazonaws.com/audio/user_id/recording.m4a"
}
```

**Request Fields**:

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `audio_url` | string | yes | 1–2048 chars; must end with `.m4a`, `.mp3`, `.wav`, or `.ogg` (case-insensitive, query params ignored); must be an `amazonaws.com` URL |

**Response 200 OK**:

```json
{
  "transcript": "I want to practice speaking today",
  "language": "en",
  "confidence": 0.9048,
  "duration_seconds": 4.2
}
```

**Response Fields**:

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `transcript` | string | no | Full transcribed text from Whisper |
| `language` | string | no | ISO 639-1 language code detected by Whisper (e.g., `"en"`, `"tr"`). Returns `"unknown"` when Whisper cannot detect. |
| `confidence` | float | no | Average confidence derived from segment log-probabilities, clamped to `[0.0, 1.0]`. Returns `0.0` when Whisper provides no segment data. |
| `duration_seconds` | float | yes | Audio duration in seconds as reported by Whisper. `null` when Whisper does not return duration. |

**Error Responses**:

| Status | When |
|--------|------|
| 400 | `audio_url` is not an `amazonaws.com` URL |
| 400 | Unsupported audio format at the service layer (defense-in-depth, normally caught at 422) |
| 400 | S3 object does not exist (`NoSuchKey`) |
| 401 | Missing or invalid JWT |
| 413 | Audio file exceeds 25 MB after download |
| 422 | Missing `audio_url`, empty string, or extension not in `.m4a/.mp3/.wav/.ogg` (Pydantic validation) |
| 429 | Rate limit exceeded (per-user rate limiting from P1.5-01) |
| 503 | S3 is unreachable or returns an unexpected error |
| 503 | `openai_api_key` is not configured |
| 503 | OpenAI Whisper API call failed |

---

## Configuration

No new configuration sections were introduced. The only new setting consumed is `openai_api_key`.

| Setting | Source | Description |
|---------|--------|-------------|
| `openai_api_key` | `app/config.py` (`settings.openai_api_key`) | OpenAI API key. Required for Whisper. If empty, the endpoint returns 503 immediately without attempting S3 download. |
| `aws_region` | `app/config.py` (`settings.aws_region`) | AWS region used when constructing the module-level boto3 S3 client. |

The `openai` Python package must be present in `backend/requirements.txt`. No new infrastructure dependencies are required beyond the existing S3 permissions already granted by the ECS task role for the media upload feature (P01-10).

---

## Files

| File | Role |
|------|------|
| `backend/app/routes/stt.py` | Route handler. Single async endpoint `POST /stt` registered under the `/api/v1` prefix. Delegates all logic to `STTService`. |
| `backend/app/services/stt_service.py` | `STTService` class with `transcribe()`, `_parse_s3_url()`, `_get_extension()`, `_download_from_s3()`, `_call_whisper()`, and `_whisper_transcribe()` methods. Module-level `_s3_client` and `_compute_average_confidence()` helper function. |
| `backend/app/schemas/stt.py` | `STTRequest` and `STTResponse` Pydantic models. `STTRequest.audio_url` has a `field_validator` that checks for the supported extensions before the service is reached. |
| `backend/app/main.py` | Imports `stt` router and registers it at `prefix="/api/v1"`, `tags=["stt"]`. |
| `shared/api-contracts/paths/stt.yaml` | OpenAPI path specification for `POST /api/v1/stt`. |
| `shared/api-contracts/schemas/stt.yaml` | OpenAPI schema definitions for `STTRequest` and `STTResponse`. |
| `shared/api-contracts/ember-api.yaml` | Top-level OpenAPI document; includes the STT path reference and `stt` tag. |

### Router Registration

```python
# In main.py:
from app.routes import ..., stt

app.include_router(stt.router, prefix="/api/v1", tags=["stt"])
```

---

## Testing

### Coverage Summary

| File | Tests | Notes |
|------|-------|-------|
| `backend/tests/schemas/test_stt.py` | 19 schema tests | Pydantic validation, field constraints, extension whitelist |
| `backend/tests/services/test_stt.py` | 24 service tests | S3 URL parsing, extension extraction, confidence math, transcribe flow, all error paths |
| `backend/tests/routes/test_stt.py` | 10 route tests | Full HTTP integration with mocked S3 and Whisper |
| **Total** | **53 passed, 0 failed** | |

Full backend suite at time of implementation: 2185 passed, 0 failed.

### Key Test Scenarios

**Schema tests** validate the `field_validator` on `audio_url`: whitespace trimming, case-insensitive extension matching (`.MP3` accepted), query-parameter stripping before extension check, all four accepted formats, rejection of unsupported extensions (`.txt`, `.flac`, `.mp4`), empty string rejection, max length (2048 chars), and response model serialization including nullable `duration_seconds`.

**Service tests** cover `_parse_s3_url` for both virtual-hosted and path-style URLs, non-S3 URL rejection (400), path-style URL missing key (400), `_get_extension` for all four formats plus uppercase normalization and query-param stripping, `_compute_average_confidence` for no segments (0.0), empty segments (0.0), single segment, multi-segment averaging, and logprob clamping to 1.0. The `STTService.transcribe` tests cover: successful full flow, unsupported format at service layer (400), file exceeding 25 MB (413), S3 `NoSuchKey` (400), S3 internal error (503), Whisper API failure (503), missing OpenAI API key (503), and M4A format acceptance.

**Route tests** cover: valid request returns 200 with all response fields, missing auth returns 401/403, missing `audio_url` returns 422, empty `audio_url` returns 422, unsupported format returns 422, file too large returns 413, S3 not found returns 400, Whisper failure returns 503, response shape validation, and M4A URL acceptance.

### Running Tests

STT tests only:

```bash
cd backend && python -m pytest tests/schemas/test_stt.py tests/services/test_stt.py tests/routes/test_stt.py -v
```

Full backend suite:

```bash
cd backend && python -m pytest tests/ -v
```

---

## Known Limitations

- **No real-time streaming**: Whisper transcription is batch-only. The entire audio file is downloaded before transcription begins. For short voice messages (under 30 seconds), this is acceptable latency. Long recordings will have proportionally longer wait times.
- **Confidence is `0.0` for short utterances**: When Whisper returns no segment-level data (e.g., for very short or silent clips), the `confidence` field is `0.0`, which is indistinguishable from a low-confidence transcription. Callers should not treat a `0.0` confidence score as an error.
- **No direct upload**: The endpoint only accepts S3 URLs. It does not accept direct audio byte uploads. Callers must use the media upload endpoint (P01-10) first.
- **S3 URL must be `amazonaws.com`**: Presigned URLs with custom domains (e.g., CloudFront) are not accepted by the URL parser. If CloudFront is placed in front of S3 in future, the URL validation logic in `_parse_s3_url` will need to be updated.
- **No language hint**: The Whisper call does not pass a `language` parameter; Whisper auto-detects. This is intentional for multilingual users but may reduce accuracy for short phrases in minority languages.
- **Rate limiting applies**: The STT endpoint is subject to the standard write-group rate limit (P1.5-01). Rapid successive calls from the same user will be rejected with 429.

---

## Extending This Feature

**Adding a new audio format**: Add the extension to the `_SUPPORTED_EXTENSIONS` set in `stt_service.py` and to the `_SUPPORTED_EXTENSIONS` tuple in `stt.py` (schemas). Also add an extension-to-MIME mapping entry to `_EXTENSION_MIME_MAP` in `stt_service.py`. Whisper supports a wider range of formats than the four currently allowed; check the Whisper API docs before adding new entries.

**Passing a language hint**: If the mobile UI has a known locale (e.g., the user's `preferred_language` from their profile), it can be added to the request body as an optional `language` field. Pass it through to `client.audio.transcriptions.create(language=language)` in `_whisper_transcribe()`. This can improve accuracy for short phrases in specific languages.

**Storing transcription results**: If you need audit logging or usage analytics, add an optional database write after a successful transcription. A lightweight `stt_logs` table with `user_id`, `duration_seconds`, `language`, and `created_at` would suffice. Insert it via a background task to avoid adding latency to the response.

**Supporting direct byte upload**: To allow clients to POST audio bytes directly (avoiding the two-step upload-then-transcribe flow), add a new endpoint that accepts `multipart/form-data`. The service's `_call_whisper()` method already accepts raw bytes, so only the route handler and the S3 download step would differ.

---

## Related Documentation

- [Voice and Audio Architecture](../12-ses-voice.md) — TTS/STT design decisions, ElevenLabs and Whisper overview
- [Database Schema and API Endpoints](../04-veri-api.md) — full API contract reference
- [Media Upload](./media-upload.md) — P01-10, the two-step upload flow that produces the S3 URL consumed by this endpoint
- [Chat Streaming](./chat-streaming.md) — P01-06, where the client sends the transcript as a chat message after transcription
- [Security and Performance](../08-guvenlik-performans.md) — S3 isolation, IAM permissions
