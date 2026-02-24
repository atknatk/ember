# Media Upload (Presigned URL)

> Generates S3 presigned PUT URLs so mobile clients can upload photos and audio files directly to S3 without routing file bytes through the backend.

**Status**: Released
**Added in**: Phase 1 (P01-10)
**Platforms**: Backend
**GitHub Issue**: #12

---

## Overview

Ember users need to attach photos (meal tracking, progress photos, screenshots) and audio recordings (voice messages) to their conversations with AI characters. Rather than accepting multipart file uploads on the backend -- which would add latency, memory pressure, and complexity on ECS Fargate -- this feature implements the presigned URL pattern: the backend generates a time-limited S3 PUT URL, and the mobile client uploads the file directly to S3.

The flow is straightforward. The client calls `POST /api/v1/media/upload-url` with a filename, MIME content type, and media category (photo, audio, or tts). The backend validates the content type against a per-category whitelist, sanitizes the filename, constructs an S3 key that isolates files by user, generates a 5-minute presigned PUT URL via boto3, and returns both the upload URL (for the client to PUT file bytes to S3) and a permanent file URL (for the client to reference in subsequent messages via `media_url` or `tts_url`).

This endpoint does not store file metadata in the database. The permanent `file_url` is associated with a message when the user sends it through the chat flow (P01-06), stored in the `messages.media_url` or `messages.tts_url` column. It does not resize, compress, or transcode files -- image compression is the mobile client's responsibility (per `docs/08-guvenlik-performans.md`: max 1 MB, HEIF to JPEG on iOS, WEBP on Android). It does not serve or delete files; file retrieval uses the permanent S3 URL (or CloudFront in production), and cleanup is handled by S3 lifecycle policies.

---

## Architecture

### How It Works (Data Flow)

1. The mobile client selects a photo from the camera roll or records an audio message.
2. The client sends `POST /api/v1/media/upload-url` with `Authorization: Bearer <jwt>` and a JSON body containing `filename`, `content_type`, and `type`.
3. The route handler resolves the authenticated user via the `get_current_user` dependency, providing the `Profile` with `id`.
4. The route handler delegates to `MediaService.generate_upload_url()`.
5. The service validates the `content_type` against the `ALLOWED_CONTENT_TYPES` whitelist for the given `type`. Mismatches produce a 400 error.
6. The service sanitizes the filename: strips path separators and null bytes, replaces spaces with underscores, removes unsafe characters, truncates the name portion to 100 characters, and falls back to `"upload"` if the result is empty or starts with a dot.
7. The service constructs the S3 key: `{type}/{user_id}/{uuid4}_{sanitized_filename}`.
8. The service calls `boto3.generate_presigned_url("put_object", ...)` via `asyncio.to_thread()`, specifying the bucket, key, content type, 5-minute expiration, and PUT method. Any boto3 error is caught and returned as 503.
9. The service constructs the permanent `file_url` from the bucket name, region, and S3 key (no query parameters).
10. The endpoint returns 200 with `upload_url` and `file_url`.
11. The client PUTs the raw file bytes to the `upload_url` with the matching `Content-Type` header.
12. When sending a message, the client includes `file_url` in the message request body's `media_url` or `tts_url` field. The chat flow (P01-06) stores it in the database.

### S3 Key Format

```
{type}/{user_id}/{uuid}_{filename}
```

| Segment | Source | Example |
|---------|--------|---------|
| `{type}` | Request `type` field | `photo`, `audio`, or `tts` |
| `{user_id}` | Authenticated user's profile UUID (from JWT) | `550e8400-e29b-41d4-a716-446655440000` |
| `{uuid}` | Newly generated UUID4 per request | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| `{filename}` | Sanitized original filename | `meal.jpg` |

Full example: `photo/550e8400-e29b-41d4-a716-446655440000/a1b2c3d4-e5f6-7890-abcd-ef1234567890_meal.jpg`

The UUID4 guarantees uniqueness without the risk of timestamp collisions and prevents sequential enumeration of a user's files. The S3 key path provides per-user file isolation as required by `docs/08-guvenlik-performans.md`.

### Content Type Whitelist

The backend validates that the `content_type` matches the declared `type`. A photo type cannot have an audio MIME type and vice versa.

| `type` | Allowed `content_type` values |
|--------|-------------------------------|
| `photo` | `image/jpeg`, `image/png`, `image/heic` |
| `audio` | `audio/m4a`, `audio/mp3`, `audio/mpeg` |
| `tts` | `audio/mp3`, `audio/mpeg` |

Notes:
- `audio/mpeg` is the official IANA MIME type for MP3 files. `audio/mp3` (non-standard but widely used) is also accepted.
- `audio/m4a` covers AAC/M4A recordings from iOS.
- `image/heic` covers HEIF photos from iOS before client-side conversion.
- `audio/m4a` is valid for `audio` but NOT for `tts`. The TTS category only accepts MP3/MPEG because ElevenLabs outputs in MP3 format.

The whitelist is defined as the module-level constant `ALLOWED_CONTENT_TYPES` in `media_service.py` using `frozenset` values for immutability.

### Presigned URL Parameters

| Parameter | Value |
|-----------|-------|
| HTTP Method | PUT |
| Expiration | 300 seconds (5 minutes) |
| ContentType condition | Must match the `content_type` from the request |
| Bucket | `settings.s3_bucket_name` (from `config.py`) |

The presigned PUT URL does not natively support `ContentLengthRange` conditions. The 10 MB file size limit is enforced via S3 bucket policy (an infrastructure concern outside this feature's scope). Mobile clients are expected to compress images to max 1 MB before upload.

### Filename Sanitization

The `_sanitize_filename()` function in `media_service.py` applies these transformations in order:

1. Strip path separators (`/`, `\`) and null bytes
2. Replace spaces with underscores
3. Remove characters not matching `[a-zA-Z0-9_\-.]` (alphanumeric, hyphens, underscores, dots)
4. Split at the last dot to separate name from extension; truncate the name portion to 100 characters
5. If the result is empty or starts with a dot, fall back to `"upload"`

The Pydantic schema also rejects filenames containing `..` (path traversal), `/` or `\` (path separators), and null bytes at the validation layer before the service is called.

### Database Tables Involved

This feature does not read from or write to any database table. The only data dependency is the authenticated user's `Profile.id` (UUID), which is extracted from the JWT by `get_current_user`.

| Table | Operation | Notes |
|-------|-----------|-------|
| `profiles` | (none -- read via JWT) | `user_id` is extracted from the JWT, not queried from DB by this endpoint |

### No Mem0 Operations

This feature does not interact with Mem0.

---

## API Reference

### POST /api/v1/media/upload-url

Generates a presigned S3 PUT URL for the client to upload a file directly to S3.

**Auth**: Bearer JWT required
**Content-Type**: `application/json`

**Request Body**:

```json
{
  "filename": "meal.jpg",
  "content_type": "image/jpeg",
  "type": "photo"
}
```

**Request Fields**:

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `filename` | string | yes | 1-255 chars; no `..`, `/`, `\`, or null bytes; whitespace-trimmed | Original filename. Sanitized and used as a suffix in the S3 key. |
| `content_type` | string | yes | Non-empty; must be in the allowed whitelist for the given `type` | MIME type of the file to upload. |
| `type` | string | yes | One of: `"photo"`, `"audio"`, `"tts"` | Media category. Determines the S3 key prefix directory. |

**Response 200 OK**:

```json
{
  "upload_url": "https://bucket.s3.us-east-1.amazonaws.com/photo/user-uuid/file-uuid_meal.jpg?X-Amz-Algorithm=AWS4-HMAC-SHA256&...",
  "file_url": "https://bucket.s3.us-east-1.amazonaws.com/photo/user-uuid/file-uuid_meal.jpg"
}
```

| Response Field | Type | Description |
|----------------|------|-------------|
| `upload_url` | string | Time-limited presigned S3 PUT URL. Client must PUT raw file bytes to this URL within 5 minutes. The `Content-Type` header on the PUT request must match the `content_type` from the original request. |
| `file_url` | string | Permanent S3 object URL (no query string). This is the URL the client stores and sends in the `media_url` field of messages. |

**Error Responses**:

| Status | Detail | When |
|--------|--------|------|
| 400 | `"Content type '{content_type}' is not allowed for type '{type}'"` | `content_type` not in the allowed whitelist for the given `type` |
| 401 | `"Invalid or expired token"` | Missing or invalid JWT |
| 422 | Standard FastAPI validation error | Missing required fields, invalid `type` value (not photo/audio/tts), empty filename, path traversal in filename, filename > 255 chars |
| 503 | `"Storage service unavailable"` | boto3 S3 presigned URL generation failed (ClientError or other exception) |

---

## Configuration

No new configuration values were introduced for this feature. All required settings already exist from prior features (P01-01).

| Setting | Source | Description |
|---------|--------|-------------|
| `s3_bucket_name` | `app/config.py` | S3 bucket name for media uploads. |
| `aws_region` | `app/config.py` | AWS region for S3 URL construction and boto3 client initialization. |

No new packages were added. `boto3` and `botocore` were already dependencies.

### Infrastructure Prerequisites

These are outside this feature's scope but are required for the feature to work correctly:

- The S3 bucket (`s3_bucket_name`) must exist with "Block Public Access" enabled.
- The ECS task role must have `s3:PutObject` and `s3:GetObject` permissions on the bucket.
- A 10 MB file size limit should be enforced via S3 bucket policy (not enforced by the presigned URL itself).
- The boto3 credential chain (IAM role on ECS Fargate, or environment variables in local dev) must be configured.

---

## Files

| File | Role |
|------|------|
| `backend/app/routes/media.py` | Route handler. Single router with one endpoint (`POST /upload-url`). Delegates all logic to `MediaService`. |
| `backend/app/services/media_service.py` | `MediaService` class with `generate_upload_url()` method, plus `_sanitize_filename()` helper function. Contains the `ALLOWED_CONTENT_TYPES` constant, the module-level boto3 S3 client, and the presigned URL expiration constant. |
| `backend/app/schemas/media.py` | `UploadUrlRequest` and `UploadUrlResponse` Pydantic models. Request schema includes a `field_validator` for filename safety checks. |
| `backend/app/main.py` | Modified to import `media` module and register the router at `/api/v1/media`. |

### Router Registration

```python
# In main.py:
from app.routes import auth, characters, chat, health, media, memories, onboarding

app.include_router(media.router, prefix="/api/v1/media", tags=["media"])
```

---

## Testing

### Coverage Summary

| File | Tests (original + extended) | Line Coverage | Branch Coverage |
|------|----------------------------|---------------|-----------------|
| `test_media_schemas.py` + `test_media_extended.py` | 15 + 9 schema tests | 100% | 100% |
| `test_media_service.py` + `test_media_extended.py` | 21 + 15 service tests | 100% | 100% |
| `test_media_routes.py` + `test_media_extended.py` | 20 + 10 route tests | 100% | 100% |
| **Total** | **137 passed, 0 failed** | **100%** | **100%** |

Full backend suite after this feature: 1330 passed, 0 failed.

### Key Test Scenarios

**Route tests** cover the full HTTP integration: all 8 valid content type + type combinations, several invalid combinations (image/jpeg for audio, audio/mp3 for photo, image/gif for photo, audio/m4a for tts), invalid type (422), missing auth (401), missing required fields (422), empty filename (422), path traversal in filename (400/422), boto3 failure (503), S3 key format verification in `file_url`, and response structure validation.

**Service tests** verify business logic in isolation: boto3 called with correct bucket/key/content-type/expiration parameters, S3 key matches `{type}/{user_id}/{uuid}_{filename}` pattern, `file_url` is permanent (no query params), content type whitelist enforcement, filename sanitization (spaces to underscores, path separator stripping, long name truncation, empty-after-sanitize fallback to "upload"), boto3 `ClientError` and generic `Exception` both produce 503, and unique UUID per call (no overwrites).

**Schema tests** verify Pydantic validation: all required fields, invalid type enum value, empty filename rejection, path traversal rejection (`..`), path separator rejection, null byte rejection, max length boundary (255 chars), whitespace trimming, and response serialization.

**Extended tests** add depth beyond the original test suite: `ALLOWED_CONTENT_TYPES` constant membership verification, presigned URL expiration constant check, exhaustive parametrized cross-type content type rejection (18 invalid combos + 8 valid combos), 18 additional filename sanitization edge cases (Unicode, emoji, extension-only, consecutive dots, leading dots, boundary lengths), user isolation verification, response Content-Type header check, and extra request fields ignored.

### Running Tests

Media tests only:

```bash
cd backend && python -m pytest tests/test_media_schemas.py tests/test_media_service.py tests/test_media_routes.py tests/test_media_extended.py -v
```

Full backend suite:

```bash
cd backend && python -m pytest tests/ -v --ignore=tests/test_migration.py
```

---

## Known Limitations

- **No file size enforcement in presigned URL**: The presigned PUT URL does not enforce a `ContentLengthRange` condition (PUT-based presigned URLs do not support this). The documented 10 MB limit must be enforced via S3 bucket policy (infrastructure concern) and client-side validation.
- **No file deletion endpoint**: There is no API to delete uploaded files. Orphaned files (uploaded but never attached to a message) are cleaned up by S3 lifecycle policies. Account deletion (GDPR) file cleanup is a separate future concern.
- **No file metadata in the database**: File records are not stored in a dedicated table. The only reference is the `file_url` stored in `messages.media_url` or `messages.tts_url` when a message is sent. This means there is no server-side inventory of uploaded files.
- **No image/audio processing**: The backend does not resize, compress, or transcode files. Image compression (HEIF to JPEG, max 1 MB) is the mobile client's responsibility.
- **CloudFront URL rewriting not implemented**: The `file_url` uses the direct S3 URL format (`https://{bucket}.s3.{region}.amazonaws.com/{key}`). If CloudFront is deployed in front of S3, a URL rewrite or migration will be needed.
- **S3 key format differs from docs/09-dagitim.md**: The deployment doc shows `{timestamp}_{filename}` as the S3 key pattern, but this feature uses `{uuid}_{filename}` per the issue description. The issue description took precedence. This is a documented deviation, not a bug.

---

## Design Decisions

### Why presigned PUT (not presigned POST or multipart upload to backend)

Presigned PUT is the simplest integration for mobile clients: a single HTTP PUT with raw file bytes. Presigned POST requires multipart form encoding with specific field ordering, which is more complex on mobile. Uploading to the backend (multipart to FastAPI) would require the backend to receive, buffer, and forward large files -- adding latency, memory pressure, and complexity on ECS Fargate.

### Why UUID in S3 key (not timestamp)

UUID4 guarantees uniqueness without the risk of timestamp collisions (two rapid uploads in the same millisecond). It also prevents sequential enumeration of a user's files.

### Why 5-minute presigned URL expiration

Five minutes is sufficient for the mobile client to receive the URL and start the upload, even on slow connections. A longer expiration increases the window for URL leakage. A shorter expiration risks timing out on slow networks where the client compresses the file before uploading.

### Why module-level boto3 client

Unlike the Mem0 client (instantiated per-call in other services), the boto3 S3 client is designed for reuse. It manages an internal connection pool and credential cache. Creating it per-request would be wasteful.

### Why asyncio.to_thread() wraps generate_presigned_url

The `generate_presigned_url` method is a local HMAC signing computation that completes in microseconds and does not make network calls. Wrapping it in `asyncio.to_thread()` is not strictly necessary but provides safety in case boto3 client initialization involves credential fetching that could block briefly.

### Why no database writes

The `file_url` is associated with a message when the user sends it via the chat endpoint (P01-06). Creating a separate `media` or `uploads` table would add complexity without value -- `messages.media_url` and `messages.tts_url` already serve as the file reference.

### Why content type is validated per media type

A photo endpoint that accepts `audio/mp3` would confuse downstream processing and UI rendering. The per-type whitelist ensures the S3 key prefix accurately reflects the file content.

### Why filename sanitization (not rejection)

Rejecting filenames with spaces, special characters, or long names would create a poor user experience on mobile (filenames from camera rolls often contain spaces and non-ASCII characters). Sanitizing for S3 key safety while preserving readability is more user-friendly. Path traversal sequences (`..`) are still rejected outright at the Pydantic validation layer.

---

## Extending This Feature

**Adding a new media type** (e.g., `"video"`): Add the type to the `Literal` annotation in `UploadUrlRequest.type` in `backend/app/schemas/media.py`. Add a corresponding entry to the `ALLOWED_CONTENT_TYPES` dict in `backend/app/services/media_service.py` with the allowed MIME types. No other changes are needed -- the S3 key construction and presigned URL generation handle any type string.

**Adding a new content type to an existing media type** (e.g., `image/webp` for photos): Add the MIME type string to the relevant `frozenset` in `ALLOWED_CONTENT_TYPES`. No schema changes are needed since `content_type` is a free-form string validated in the service layer.

**Enforcing file size at the S3 level**: Add a bucket policy with `NumericLessThanEquals` on `s3:content-length-range`. See the feature spec (`shared/feature-specs/media-upload.md`, section 4) for the exact policy JSON.

**Adding file metadata tracking**: Create a `media_uploads` table with columns for `id`, `user_id`, `s3_key`, `content_type`, `type`, `created_at`. Insert a row in `MediaService.generate_upload_url()` before returning. This would enable server-side file inventory, orphan cleanup, and usage analytics.

**Switching to CloudFront URLs**: Replace the `file_url` construction in `MediaService.generate_upload_url()` to use the CloudFront distribution domain instead of the direct S3 URL. Add a `cloudfront_domain` setting to `config.py`.

---

## Related Documentation

- [Database Schema and API Endpoints](../04-veri-api.md) -- S3 key patterns and API contract
- [Security and Performance](../08-guvenlik-performans.md) -- S3 isolation, presigned URL policy, client-side compression requirements
- [Deployment](../09-dagitim.md) -- S3 bucket configuration, IAM permissions
- [Chat Streaming](./chat-streaming.md) -- P01-06, where `media_url` and `tts_url` are stored with messages
