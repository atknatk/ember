# Backend Dev Handoff: Media Upload (Presigned URL)

**Date**: 2026-02-24
**Agent**: backend-dev
**Status**: COMPLETE

## Implemented Files

- `backend/app/schemas/media.py` -- 2 schemas (UploadUrlRequest, UploadUrlResponse)
- `backend/app/services/media_service.py` -- 1 service class (MediaService) with 1 public method + 1 helper function
- `backend/app/routes/media.py` -- 1 endpoint (POST /upload-url)
- `backend/app/main.py` -- MODIFIED (added media router registration)
- `backend/tests/test_media_schemas.py` -- 15 schema validation tests
- `backend/tests/test_media_service.py` -- 9 sanitization + 12 service unit tests = 21 tests
- `backend/tests/test_media_routes.py` -- 20 route integration tests

## Endpoints Implemented

- `POST /api/v1/media/upload-url` -- Generates presigned S3 PUT URL for file upload. Returns `upload_url` and `file_url`.

## Test Results

- pytest: 55 passed, 0 failed (media tests); 1248 passed total suite
- ruff: clean (all checks passed)
- No hardcoded secrets

## Test Command

```bash
cd backend && python -m pytest tests/test_media_schemas.py tests/test_media_service.py tests/test_media_routes.py -v
```

## Known Issues / Deviations from Spec

- None. Implementation follows the spec exactly.

## Notes for Backend Tester

### Mocking Strategy

- **boto3**: Mock `app.services.media_service._s3_client` (module-level boto3 S3 client). Set `generate_presigned_url.return_value` to a fake URL string.
- **Auth**: Override `get_current_user` dependency to return a fake Profile with a known UUID. No database is needed for this feature.
- **No DB mocking needed**: Override `get_db` with a no-op async generator (the endpoint does not access the database).

### Edge Cases to Verify

1. **Content type whitelist**: All 8 valid combinations are tested, plus several invalid ones. Key edge case: `audio/m4a` is valid for `audio` but NOT for `tts`.
2. **Filename sanitization**: Spaces become underscores, path traversal chars are rejected by Pydantic validator (`..`, `/`, `\`, null bytes), special characters are stripped, long names are truncated to 100 chars (name portion only).
3. **S3 key uniqueness**: Each call generates a new UUID4 in the key, preventing overwrites even for identical filenames.
4. **503 on boto3 failure**: `botocore.exceptions.ClientError` is caught and returned as 503.
5. **file_url is permanent**: No query parameters in `file_url` (unlike `upload_url` which contains presigned signature).

### Architecture Notes

- `MediaService` does NOT take a `db` parameter (unlike other services). It has no database interaction.
- The boto3 S3 client is instantiated at module level (`_s3_client`) and reused across requests.
- `generate_presigned_url` is wrapped in `asyncio.to_thread()` for safety, even though it is a local HMAC computation.
- The `ALLOWED_CONTENT_TYPES` dict is a module-level constant in `media_service.py`.
- The presigned URL has a 5-minute (300 second) expiration.
