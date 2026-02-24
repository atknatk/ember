# Feature Spec: P01-10 -- Media Upload (Presigned URL)

**Feature ID**: P01-10
**Phase**: 1
**Layer**: backend
**GitHub Issue**: #12
**Date**: 2026-02-24
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature adds a single REST endpoint that generates an AWS S3 presigned PUT URL for file uploads. Mobile clients call `POST /api/v1/media/upload-url` with a filename, content type, and media type. The backend validates the request, generates a time-limited presigned PUT URL pointing to a well-structured S3 key, and returns both the upload URL (for the client to PUT the file directly to S3) and the permanent file URL (for the client to reference in subsequent messages).

The upload flow is:
1. Client calls `POST /api/v1/media/upload-url` with metadata.
2. Backend validates content type, generates S3 key, creates presigned PUT URL.
3. Client PUTs the raw file bytes directly to S3 using the presigned URL.
4. Client uses the `file_url` when sending a message (`POST /characters/:id/messages` with `media_url` field).

### Why It Exists

Users need to attach photos (meal tracking, progress photos, screenshots) and audio recordings (voice messages) to their conversations with AI characters. The presigned URL pattern offloads file transfer from the backend to S3, keeping the backend stateless and avoiding large multipart request handling on ECS Fargate.

Per `docs/08-guvenlik-performans.md`, S3 access is private (presigned URLs only) and files are isolated per user in the S3 key path. This endpoint enforces both constraints.

### Dependencies

- **Requires**: P01-04 (auth-endpoints -- `get_current_user` dependency, Profile model with `id`)
- **Requires**: P01-01 (project-setup -- FastAPI scaffold, `config.py` with `s3_bucket_name` and `aws_region`)

### What This Feature Does NOT Do

- It does not upload the file itself. The client uploads directly to S3 via the presigned URL.
- It does not store file metadata in the database. The `file_url` is stored on the `messages.media_url` or `messages.tts_url` column when the client sends a message (handled by the chat flow, P01-06).
- It does not resize, compress, or transcode files. Image compression is the mobile client's responsibility (per `docs/08-guvenlik-performans.md`: max 1MB, HEIF to JPEG on iOS, WEBP on Android).
- It does not serve files. File retrieval uses the permanent S3 URL (or a CloudFront distribution in front of S3 in production).
- It does not delete files. File cleanup is a separate concern (GDPR account deletion, S3 lifecycle policies).

---

## 2. Data Models

### No New Tables

This feature does not create or alter any database tables.

### No New Columns

All required columns already exist:

| Table | Column | Usage in This Feature |
|-------|--------|----------------------|
| `profiles.id` | UUID PK | Used to construct the S3 key path: `{type}/{user_id}/...` |

### No Mem0 Operations

This feature does not interact with Mem0.

---

## 3. API Endpoints

All endpoints are under the `/api/v1` prefix. The single endpoint requires `Authorization: Bearer <jwt>`.

---

### POST /api/v1/media/upload-url

Generates a presigned S3 PUT URL for the client to upload a file directly to S3.

```
Auth: Bearer JWT required
Content-Type: application/json
```

**Request Body:**

```json
{
  "filename": "meal.jpg",
  "content_type": "image/jpeg",
  "type": "photo"
}
```

| Field | Type | Required | Constraints | Description |
|-------|------|----------|-------------|-------------|
| `filename` | string | yes | 1-255 chars, must contain only safe characters (alphanumeric, hyphens, underscores, dots) | Original filename. Used as a suffix in the S3 key for human-readability. |
| `content_type` | string | yes | Must be in the allowed whitelist (see below) | MIME type of the file to upload. |
| `type` | string | yes | One of: `"photo"`, `"audio"`, `"tts"` | Media category. Determines the S3 key prefix directory. |

**Content Type Whitelist:**

| Type | Allowed content_type values |
|------|----------------------------|
| `photo` | `image/jpeg`, `image/png`, `image/heic` |
| `audio` | `audio/m4a`, `audio/mp3`, `audio/mpeg` |
| `tts` | `audio/mp3`, `audio/mpeg` |

Notes on the whitelist:
- `audio/mpeg` is the official IANA MIME type for MP3 files. Some clients send `audio/mp3` (non-standard but widely used). Both are accepted.
- `audio/m4a` covers AAC/M4A recordings from iOS.
- `image/heic` covers HEIF photos from iOS (before client-side conversion).
- The whitelist is validated based on the `type` field: a `photo` type cannot have an `audio/*` content type, and vice versa.

**Response 200 OK:**

```json
{
  "upload_url": "https://ai-companion-media-123456.s3.us-east-1.amazonaws.com/photo/550e8400-e29b-41d4-a716-446655440000/a1b2c3d4-e5f6-7890-abcd-ef1234567890_meal.jpg?X-Amz-Algorithm=AWS4-HMAC-SHA256&...",
  "file_url": "https://ai-companion-media-123456.s3.us-east-1.amazonaws.com/photo/550e8400-e29b-41d4-a716-446655440000/a1b2c3d4-e5f6-7890-abcd-ef1234567890_meal.jpg"
}
```

| Response Field | Type | Description |
|----------------|------|-------------|
| `upload_url` | string | Time-limited presigned S3 PUT URL. Client must PUT the raw file bytes to this URL within the expiration window. Includes `Content-Type` and `Content-Length` conditions. |
| `file_url` | string | Permanent S3 object URL (without query string). This is what the client stores and sends in the `media_url` field of messages. |

**S3 Key Format:**

```
{type}/{user_id}/{uuid}_{filename}
```

Where:
- `{type}` is `photo`, `audio`, or `tts` (from the request `type` field).
- `{user_id}` is the authenticated user's profile UUID (from JWT).
- `{uuid}` is a newly generated UUID4 (ensures uniqueness, prevents overwrites).
- `{filename}` is the sanitized original filename from the request.

Example: `photo/550e8400-e29b-41d4-a716-446655440000/a1b2c3d4_meal.jpg`

**Presigned URL Parameters:**

| Parameter | Value |
|-----------|-------|
| HTTP Method | PUT |
| Expiration | 300 seconds (5 minutes) |
| ContentType condition | Must match the `content_type` from the request |
| ContentLengthRange | 1 byte to 10,485,760 bytes (10 MB) |

The `ContentLengthRange` condition is enforced by S3 itself. If the client attempts to upload a file larger than 10 MB, S3 rejects the PUT with a 403 error. The backend does not need to verify file size.

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 401 | Missing or invalid JWT | `{"detail": "Invalid or expired token"}` |
| 400 | `content_type` not in the allowed whitelist for the given `type` | `{"detail": "Content type '{content_type}' is not allowed for type '{type}'"}` |
| 400 | `type` not one of photo/audio/tts | Pydantic validation error (422 from FastAPI, but the Literal type annotation handles this) |
| 422 | Missing required fields or invalid field types | Pydantic validation error (FastAPI auto-generates) |
| 503 | AWS S3 presigned URL generation fails | `{"detail": "Storage service unavailable"}` |

---

## 4. Backend Logic

### MediaService Class

A new `MediaService` class in `backend/app/services/media_service.py` encapsulates presigned URL generation. Route handlers delegate to this service.

```
class MediaService:
    async def generate_upload_url(
        self,
        user_id: uuid.UUID,
        filename: str,
        content_type: str,
        media_type: str,
    ) -> UploadUrlResponse:
        """Generate a presigned S3 PUT URL for file upload."""
```

### Generate Upload URL Flow

```
Client sends: POST /api/v1/media/upload-url
Authorization: Bearer <jwt>
Body: { "filename": "meal.jpg", "content_type": "image/jpeg", "type": "photo" }
    |
    v
1. get_current_user extracts user_id from JWT/Profile
    |
    v
2. Validate content_type against the whitelist for the given type:
   ALLOWED_CONTENT_TYPES = {
       "photo": {"image/jpeg", "image/png", "image/heic"},
       "audio": {"audio/m4a", "audio/mp3", "audio/mpeg"},
       "tts":   {"audio/mp3", "audio/mpeg"},
   }
   If content_type not in ALLOWED_CONTENT_TYPES[type]:
       --> 400 "Content type '...' is not allowed for type '...'"
    |
    v
3. Sanitize filename:
   - Strip path separators (/, \) and null bytes
   - Replace spaces with underscores
   - Truncate to 100 characters (excluding extension)
   - If filename becomes empty after sanitization, use "upload" as default
    |
    v
4. Construct S3 key:
   file_uuid = uuid.uuid4()
   s3_key = f"{type}/{user_id}/{file_uuid}_{sanitized_filename}"
    |
    v
5. Generate presigned PUT URL via boto3:
   s3_client = boto3.client("s3", region_name=settings.aws_region)
   upload_url = s3_client.generate_presigned_url(
       "put_object",
       Params={
           "Bucket": settings.s3_bucket_name,
           "Key": s3_key,
           "ContentType": content_type,
       },
       ExpiresIn=300,
       HttpMethod="PUT",
   )
    |
    +--> boto3 error (ClientError, etc.) --> 503 "Storage service unavailable"
    |
    v
6. Construct file_url:
   file_url = f"https://{settings.s3_bucket_name}.s3.{settings.aws_region}.amazonaws.com/{s3_key}"
    |
    v
7. Return 200 { "upload_url": upload_url, "file_url": file_url }
```

### boto3 Client Usage

The boto3 S3 client is synchronous. The `generate_presigned_url` method is a local computation (it does not make a network call to AWS -- it signs the URL using local credentials). Therefore it completes in microseconds and does not need `asyncio.to_thread()`. However, if the boto3 client initialization involves credential fetching (e.g., from IAM role metadata), that may block briefly. To be safe, the presigned URL generation should be wrapped in `asyncio.to_thread()`.

The S3 client should be instantiated once at the module level or as a class attribute (not per-request), since it maintains an internal connection pool and credential cache.

### ContentLengthRange Enforcement

The presigned URL includes a `Content-Length` condition that limits uploads to 10 MB. This is enforced by S3 at upload time. The backend does not need any middleware or request-size checking.

To enforce ContentLengthRange on a presigned PUT URL, the service must use `generate_presigned_post` (not `generate_presigned_url`) or add conditions via a presigned POST policy. However, for a PUT-based presigned URL, S3 does not natively support ContentLengthRange conditions in the signature.

**Important implementation note**: There are two approaches to enforce file size:

1. **Presigned POST** (S3 POST policy): Supports `["content-length-range", 1, 10485760]` as a condition. Returns a form-based upload URL. Mobile clients must use multipart form POST.

2. **Presigned PUT** with server-side trust: The presigned PUT URL does not enforce file size at the S3 level. The 10 MB limit is documented and enforced client-side. The backend trusts that clients respect the limit. S3 bucket lifecycle or Lambda@Edge can enforce hard limits.

**Decision**: Use **presigned PUT** (simpler client integration -- a single PUT request with raw bytes) and enforce the 10 MB limit via an S3 bucket policy or Lambda@Edge in production. The presigned URL itself includes the ContentType condition. The 10 MB limit is a documented contract that clients must respect, and can be enforced server-side via S3 bucket policy:

```json
{
  "Condition": {
    "NumericLessThanEquals": {
      "s3:content-length-range": 10485760
    }
  }
}
```

This bucket policy enforcement is an infrastructure concern (outside this feature's scope) but should be documented for the DevOps team.

### Error Handling

All boto3 calls are wrapped in try/except. On any `botocore.exceptions.ClientError` or other exception:
- Log the error at ERROR level with user_id and s3_key (but NOT the presigned URL which contains credentials in the query string -- no secrets in logs).
- Raise `HTTPException(status_code=503, detail="Storage service unavailable")`.

### No Database Writes

This feature only reads user identity from the JWT (via `get_current_user`). There are no INSERT, UPDATE, or DELETE operations on any PostgreSQL table.

### No Background Tasks

URL generation is synchronous and fast. No background tasks are needed.

### No Third-Party API Calls

The presigned URL is generated locally by the boto3 SDK using AWS credentials. No network calls to external services.

---

## 5. Pydantic Schemas

All schemas are defined in `backend/app/schemas/media.py`.

### Request Schema

```
class UploadUrlRequest(BaseModel):
    """Request body for POST /api/v1/media/upload-url."""

    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., min_length=1)
    type: Literal["photo", "audio", "tts"]
```

| Field | Type | Validation |
|-------|------|------------|
| `filename` | string | 1-255 chars, required |
| `content_type` | string | Non-empty, required. Whitelist check is in the service layer (not Pydantic) for better error messages. |
| `type` | Literal["photo", "audio", "tts"] | Pydantic enforces the enum at parse time. |

**Filename Validator:**

A Pydantic `field_validator` on `filename` should:
- Strip leading/trailing whitespace
- Reject filenames that are empty after stripping
- Reject filenames containing path traversal characters (`..`, `/`, `\`, null bytes)

The deeper sanitization (replacing spaces, truncating) is done in the service layer because it transforms the value for S3 key construction, not for validation rejection.

### Response Schema

```
class UploadUrlResponse(BaseModel):
    """Response for POST /api/v1/media/upload-url."""

    upload_url: str
    file_url: str
```

| Field | Type | Description |
|-------|------|-------------|
| `upload_url` | string | Presigned S3 PUT URL |
| `file_url` | string | Permanent S3 object URL |

---

## 6. Router Registration

A new `media` router module with a single router.

In `backend/app/routes/media.py`:

```python
router = APIRouter()

@router.post("/upload-url", response_model=UploadUrlResponse)
async def create_upload_url(
    body: UploadUrlRequest,
    profile: Profile = Depends(get_current_user),
) -> UploadUrlResponse:
    ...
```

In `backend/app/main.py`, add:

```python
from app.routes import auth, characters, chat, health, media, memories, onboarding

app.include_router(media.router, prefix="/api/v1/media", tags=["media"])
```

---

## 7. Test Requirements

### Route Tests (`backend/tests/test_media_routes.py`)

These tests use the FastAPI test client. The `get_current_user` dependency is overridden to return a fake Profile. boto3 calls are mocked.

| # | Scenario | Expected |
|---|----------|----------|
| R1 | POST /media/upload-url with valid photo request (image/jpeg, type=photo) | 200, response has `upload_url` and `file_url` |
| R2 | POST /media/upload-url with valid audio request (audio/mp3, type=audio) | 200, response has `upload_url` and `file_url` |
| R3 | POST /media/upload-url with valid tts request (audio/mpeg, type=tts) | 200, response has `upload_url` and `file_url` |
| R4 | POST /media/upload-url with image/png, type=photo | 200, success |
| R5 | POST /media/upload-url with image/heic, type=photo | 200, success |
| R6 | POST /media/upload-url with audio/m4a, type=audio | 200, success |
| R7 | POST /media/upload-url with content_type mismatch (image/jpeg for type=audio) | 400, `"Content type 'image/jpeg' is not allowed for type 'audio'"` |
| R8 | POST /media/upload-url with content_type mismatch (audio/mp3 for type=photo) | 400, content type not allowed |
| R9 | POST /media/upload-url with invalid type (type=video) | 422, Pydantic validation error |
| R10 | POST /media/upload-url without auth header | 401 |
| R11 | POST /media/upload-url with missing filename | 422, Pydantic validation error |
| R12 | POST /media/upload-url with missing content_type | 422, Pydantic validation error |
| R13 | POST /media/upload-url with missing type | 422, Pydantic validation error |
| R14 | POST /media/upload-url with empty filename (whitespace only) | 422 or 400, validation error |
| R15 | POST /media/upload-url with path traversal in filename (`../../etc/passwd`) | 400 or sanitized successfully (no path traversal in S3 key) |
| R16 | POST /media/upload-url when S3 client fails | 503, `"Storage service unavailable"` |
| R17 | Response upload_url contains the S3 bucket name | Verified via string inspection |
| R18 | Response file_url matches the expected S3 key format: `{type}/{user_id}/{uuid}_{filename}` | Verified via regex or string parsing |
| R19 | POST /media/upload-url with unsupported content_type (image/gif for type=photo) | 400, content type not allowed |
| R20 | POST /media/upload-url with content_type=audio/m4a for type=tts | 400, content type not allowed (tts only allows mp3/mpeg) |

### Service Tests (`backend/tests/test_media_service.py`)

These tests unit-test the `MediaService` class directly. boto3 is mocked.

| # | Scenario | Expected |
|---|----------|----------|
| S1 | `generate_upload_url()` calls boto3 `generate_presigned_url` with correct bucket, key, content_type, expiration | boto3 called with exact parameters |
| S2 | `generate_upload_url()` constructs S3 key in format `{type}/{user_id}/{uuid}_{filename}` | Key matches expected pattern |
| S3 | `generate_upload_url()` returns file_url that matches the S3 key (no query params) | file_url is permanent URL |
| S4 | `generate_upload_url()` with content_type not in whitelist raises 400 | HTTPException(400) |
| S5 | `generate_upload_url()` sanitizes filename: replaces spaces with underscores | S3 key has underscores instead of spaces |
| S6 | `generate_upload_url()` sanitizes filename: strips path separators | No `/` or `\` in the filename portion of the key |
| S7 | `generate_upload_url()` sanitizes filename: truncates long filenames | Filename portion does not exceed 100 characters |
| S8 | `generate_upload_url()` uses "upload" as default when filename becomes empty after sanitization | S3 key contains "upload" |
| S9 | `generate_upload_url()` raises 503 when boto3 throws ClientError | HTTPException(503) |
| S10 | `generate_upload_url()` generates unique UUIDs for each call (no collisions) | Two sequential calls produce different S3 keys |
| S11 | `generate_upload_url()` with type=tts and content_type=audio/mp3 succeeds | No error raised |
| S12 | `generate_upload_url()` with type=tts and content_type=audio/m4a raises 400 | HTTPException(400) |

### Schema Tests (`backend/tests/test_media_schemas.py`)

| # | Scenario | Expected |
|---|----------|----------|
| T1 | `UploadUrlRequest` with all valid fields | Parses successfully |
| T2 | `UploadUrlRequest` with missing filename | ValidationError |
| T3 | `UploadUrlRequest` with missing content_type | ValidationError |
| T4 | `UploadUrlRequest` with missing type | ValidationError |
| T5 | `UploadUrlRequest` with type="video" (invalid) | ValidationError |
| T6 | `UploadUrlRequest` with empty filename | ValidationError |
| T7 | `UploadUrlRequest` with filename containing `..` | ValidationError (rejected by validator) |
| T8 | `UploadUrlResponse` serializes correctly | Both fields present as strings |
| T9 | `UploadUrlRequest` with filename exceeding 255 chars | ValidationError |
| T10 | `UploadUrlRequest` strips whitespace from filename | Trimmed correctly |

### How to Mock boto3

```python
from unittest.mock import patch, MagicMock

mock_s3_client = MagicMock()
mock_s3_client.generate_presigned_url.return_value = (
    "https://bucket.s3.us-east-1.amazonaws.com/photo/user-id/uuid_file.jpg"
    "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=..."
)

with patch("app.services.media_service.boto3") as mock_boto3:
    mock_boto3.client.return_value = mock_s3_client
    # ... run test
```

For the S3 client failure case:

```python
from botocore.exceptions import ClientError

mock_s3_client.generate_presigned_url.side_effect = ClientError(
    {"Error": {"Code": "InternalError", "Message": "S3 unavailable"}},
    "PutObject",
)
```

### How to Mock the Auth Dependency

Follow the same pattern as all existing route tests. Override `get_current_user` to return a fake Profile with a known UUID.

---

## 8. File Manifest

Every file to be created or modified, grouped by purpose.

### Route Handlers

```
Backend:
  CREATE  backend/app/routes/media.py
```

Contains a single router with one POST endpoint. Delegates to `MediaService`.

### Service Layer

```
Backend:
  CREATE  backend/app/services/media_service.py
```

Contains the `MediaService` class with `generate_upload_url()`, content type validation, filename sanitization, S3 key construction, and presigned URL generation.

### Pydantic Schemas

```
Backend:
  CREATE  backend/app/schemas/media.py
```

Contains `UploadUrlRequest` and `UploadUrlResponse`.

### Application Wiring

```
Backend:
  MODIFY  backend/app/main.py
```

Add `media` to the import line and register the router:

```python
from app.routes import auth, characters, chat, health, media, memories, onboarding

app.include_router(media.router, prefix="/api/v1/media", tags=["media"])
```

### Tests

```
Backend:
  CREATE  backend/tests/test_media_routes.py
  CREATE  backend/tests/test_media_service.py
  CREATE  backend/tests/test_media_schemas.py
```

### Documentation (Pipeline)

```
Shared:
  CREATE  shared/feature-specs/media-upload.md          (this file)
  CREATE  docs/pipeline/media-upload-architect.handoff.md
```

### Summary

| Action | Count |
|--------|-------|
| CREATE | 5 backend + 2 shared = 7 |
| MODIFY | 1 |
| DELETE | 0 |
| **Total** | **8** |

### Files NOT Modified

- `backend/app/dependencies.py` -- Uses the existing `get_current_user`. No changes needed.
- `backend/app/config.py` -- `s3_bucket_name` and `aws_region` already exist. No new config values needed.
- `backend/app/models/` -- No model changes. No new tables.
- `backend/app/schemas/__init__.py` -- Not modified (follow direct import pattern).
- `backend/app/services/__init__.py` -- Not modified (follow direct import pattern).
- `backend/requirements.txt` -- `boto3` is already a dependency.
- `backend/app/routes/chat.py` -- Not modified. The chat flow already accepts `media_url` in the message request body.

---

## 9. Acceptance Criteria

1. Given an authenticated user, when the client sends `POST /api/v1/media/upload-url` with `{"filename": "meal.jpg", "content_type": "image/jpeg", "type": "photo"}`, then the response is HTTP 200 with `upload_url` (a presigned S3 PUT URL) and `file_url` (a permanent S3 object URL).

2. Given the response `file_url`, when the URL is parsed, then the S3 key matches the pattern `photo/{user_id}/{uuid}_meal.jpg` where `{user_id}` is the authenticated user's UUID and `{uuid}` is a valid UUID4.

3. Given the response `upload_url`, when the client PUTs a JPEG file (under 10 MB) to that URL with `Content-Type: image/jpeg`, then S3 accepts the upload (HTTP 200).

4. Given a request with `content_type` of `image/gif` and `type` of `photo`, when the client sends the request, then the response is HTTP 400 with a detail message indicating the content type is not allowed.

5. Given a request with `content_type` of `image/jpeg` and `type` of `audio`, when the client sends the request, then the response is HTTP 400 with a detail message indicating the content type is not allowed for that type.

6. Given a request with `type` of `video` (not in the allowed set), when the client sends the request, then the response is HTTP 422 (Pydantic validation error).

7. Given a request without an `Authorization` header, when the client sends `POST /api/v1/media/upload-url`, then the response is HTTP 401.

8. Given a request with a filename containing path traversal characters (`../../secret.txt`), when the request is processed, then the filename is either rejected (400) or sanitized such that no path traversal characters appear in the S3 key.

9. Given a request with `type` of `audio` and `content_type` of `audio/m4a`, when the client sends the request, then the response is HTTP 200 with a valid presigned URL.

10. Given a request with `type` of `tts` and `content_type` of `audio/m4a`, when the client sends the request, then the response is HTTP 400 (tts only allows `audio/mp3` and `audio/mpeg`).

11. Given the presigned upload URL, when the client PUTs a file larger than 10 MB, then S3 rejects the upload (this is enforced by S3 bucket policy, not the backend endpoint itself).

12. Given that AWS S3 is unavailable, when the client sends `POST /api/v1/media/upload-url`, then the response is HTTP 503 with detail "Storage service unavailable".

13. Given the route handler code, when a developer inspects it, then all business logic (validation, sanitization, URL generation) is in `MediaService` and the route handler only calls the service method and returns the response.

14. Given the backend test suite, when a developer runs `pytest` on the new test files, then all tests pass with exit code 0.

15. Given two sequential requests with the same filename and type, when the responses are compared, then the `file_url` values are different (unique UUID in each key prevents overwrites).

---

## 10. Design Decisions and Rationale

### Why presigned PUT (not presigned POST or multipart upload to backend)

Presigned PUT is the simplest integration for mobile clients: a single HTTP PUT with raw file bytes. Presigned POST requires multipart form encoding with specific field ordering, which is more complex on mobile. Uploading to the backend (multipart to FastAPI) would require the backend to receive, buffer, and forward large files -- adding latency, memory pressure, and complexity on ECS Fargate.

### Why 10 MB limit

Per `docs/08-guvenlik-performans.md`, mobile clients compress images to max 1 MB before upload. The 10 MB limit provides headroom for uncompressed photos (up to 10 MB is reasonable for a high-res JPEG) and audio files (a 5-minute voice message at 128kbps MP3 is ~4.7 MB). 10 MB prevents abuse without being restrictive for legitimate use cases.

### Why UUID in S3 key (not timestamp)

The issue description specifies `{type}/{user_id}/{uuid}_{filename}`. A UUID4 guarantees uniqueness without the risk of timestamp collisions (two rapid uploads in the same millisecond). It also prevents sequential enumeration of a user's files.

Note: `docs/09-dagitim.md` shows `{timestamp}_{filename}` as the S3 key pattern, while the issue description specifies `{uuid}_{filename}`. The issue description takes precedence as it is the feature-specific requirement.

### Why content type is validated per media type

A photo endpoint that accepts `audio/mp3` would confuse downstream processing and UI rendering. The per-type whitelist ensures that the S3 key prefix (photo/audio/tts) accurately reflects the file content.

### Why filename sanitization (not rejection)

Rejecting filenames with spaces, special characters, or long names would create a poor user experience on mobile (filenames from camera rolls often have spaces and non-ASCII characters). Sanitizing the filename for S3 key safety while preserving readability is more user-friendly.

### Why no database write

The S3 key (via `file_url`) is associated with a message when the user sends it via `POST /characters/:id/messages`. Creating a separate `media` or `uploads` table would add complexity without value -- the `messages.media_url` and `messages.tts_url` columns already serve as the file reference. Orphaned files (uploaded but never attached to a message) are cleaned up by S3 lifecycle policies.

### Why the presigned URL expiration is 5 minutes

5 minutes is sufficient for the mobile client to receive the URL and start the upload, even on slow connections. A longer expiration (e.g., 1 hour) increases the window for URL leakage. A shorter expiration (e.g., 1 minute) risks timing out on slow networks where the client needs to compress the file before uploading.

### Why boto3 S3 client is instantiated at module level

Unlike the Mem0 client (instantiated per-call in other services), the boto3 S3 client is designed to be reused. It manages an internal connection pool and credential cache. Creating it per-request would be wasteful. The module-level or class-level client is the standard boto3 pattern.

---

## 11. Notes for Developers

### For backend-dev

1. **No new config values needed.** `s3_bucket_name` and `aws_region` already exist in `config.py`.

2. **boto3 client instantiation**: Create the S3 client at the module level in `media_service.py`:
   ```python
   import boto3
   from app.config import settings

   _s3_client = boto3.client("s3", region_name=settings.aws_region)
   ```
   This is safe because `generate_presigned_url` is thread-safe and does not mutate client state.

3. **Presigned URL generation**: Use `generate_presigned_url("put_object", ...)` with `Params` including `Bucket`, `Key`, and `ContentType`. The `ExpiresIn` is 300 seconds. Do NOT include `ContentLengthRange` in the presigned URL params -- that is not supported for PUT-based presigned URLs. File size enforcement is via S3 bucket policy (infrastructure concern).

4. **Filename sanitization order**: Strip path separators and null bytes first, then replace spaces with underscores, then truncate. Use a regex like `r'[^\w\-\.]'` to remove unsafe characters, keeping only alphanumeric, hyphens, underscores, and dots.

5. **file_url construction**: Build the permanent URL from the bucket name, region, and S3 key. Do NOT parse it out of the presigned URL (which contains query params). Use the format: `https://{bucket}.s3.{region}.amazonaws.com/{key}`.

6. **Content type validation**: Implement the `ALLOWED_CONTENT_TYPES` dict as a module-level constant in `media_service.py`. Check `content_type in ALLOWED_CONTENT_TYPES[media_type]` and raise `HTTPException(400)` with a descriptive message on mismatch.

7. **main.py change**: Add `media` to the existing import line: `from app.routes import auth, characters, chat, health, media, memories, onboarding`. Register with prefix `/api/v1/media` and tag `["media"]`.

8. **No async wrapping needed for `generate_presigned_url`**: This boto3 method performs local computation (HMAC signing) and does not make network calls. It completes in microseconds. Wrapping in `asyncio.to_thread()` is unnecessary but harmless. If you choose to wrap it for consistency, that is acceptable.

9. **Error handling**: Catch `botocore.exceptions.ClientError` and any other `Exception` from boto3. Log the error with `user_id` and `s3_key`. Do NOT log the presigned URL (it contains AWS credentials in query params). Raise `HTTPException(503, detail="Storage service unavailable")`.

10. **Route handler should not import boto3**: All S3 interaction is in `MediaService`. The route handler only calls `service.generate_upload_url()`.

### For backend-tester

1. **Mock boto3 at the module level**: Patch `app.services.media_service.boto3` or `app.services.media_service._s3_client` depending on how the developer implements client instantiation. Set `generate_presigned_url.return_value` to a fake URL string.

2. **Verify S3 key format in tests**: Extract the `file_url` from the response, parse the S3 key, and verify it matches `{type}/{user_id}/{uuid}_{sanitized_filename}` using regex.

3. **Test all content_type + type combinations**: Create parametrized tests covering every valid combination and several invalid combinations.

4. **Test filename edge cases**: Filenames with spaces, Unicode characters, path traversal (`../`), very long names, empty-after-trim names, names with only dots (`.`, `..`).

5. **503 test**: Make the mocked boto3 raise `ClientError` and verify the endpoint returns 503 with the correct detail message.

6. **No database setup needed**: This feature does not read from or write to the database. The only dependency is `get_current_user`, which should be overridden to return a fake Profile with a known UUID.
