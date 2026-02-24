"""Service-level unit tests for MediaService.

Tests content type validation, filename sanitization, S3 key construction,
and presigned URL generation. boto3 is mocked at the module level.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import re  # noqa: E402
import uuid  # noqa: E402
from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402

from app.services.media_service import (  # noqa: E402
    ALLOWED_CONTENT_TYPES,
    MediaService,
    _sanitize_filename,
)

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
FAKE_PRESIGNED_URL = (
    "https://test-bucket.s3.us-east-1.amazonaws.com/photo/user-id/uuid_file.jpg"
    "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=FAKE"
)


# ---------------------------------------------------------------------------
# Filename Sanitization Unit Tests
# ---------------------------------------------------------------------------


class TestSanitizeFilename:
    """Tests for the _sanitize_filename helper function."""

    def test_replaces_spaces_with_underscores(self) -> None:
        """S5: Spaces are replaced with underscores."""
        result = _sanitize_filename("my photo file.jpg")
        assert " " not in result
        assert "my_photo_file.jpg" == result

    def test_strips_path_separators(self) -> None:
        """S6: Path separators are removed."""
        result = _sanitize_filename("path/to/file.jpg")
        assert "/" not in result
        assert "\\" not in result

    def test_truncates_long_filenames(self) -> None:
        """S7: Filename portion (excluding extension) is truncated to 100 chars."""
        long_name = "a" * 150 + ".jpg"
        result = _sanitize_filename(long_name)
        name_part = result.rsplit(".", 1)[0]
        assert len(name_part) <= 100

    def test_empty_after_sanitization_becomes_upload(self) -> None:
        """S8: Filename that becomes empty after sanitization uses 'upload'."""
        result = _sanitize_filename("...")
        assert result == "upload"

    def test_only_dots_becomes_upload(self) -> None:
        """S8b: Filename starting with dot after sanitization uses 'upload'."""
        result = _sanitize_filename(".hidden")
        assert result == "upload"

    def test_normal_filename_unchanged(self) -> None:
        """Normal filenames pass through with no changes."""
        result = _sanitize_filename("meal.jpg")
        assert result == "meal.jpg"

    def test_strips_null_bytes(self) -> None:
        """Null bytes are removed."""
        result = _sanitize_filename("file\x00name.jpg")
        assert "\x00" not in result

    def test_removes_special_characters(self) -> None:
        """Special characters (except alphanumeric, hyphens, underscores, dots) are removed."""
        result = _sanitize_filename("file@#$%^&name.jpg")
        assert result == "filename.jpg"

    def test_preserves_hyphens_and_underscores(self) -> None:
        """Hyphens and underscores are preserved."""
        result = _sanitize_filename("my-photo_2024.jpg")
        assert result == "my-photo_2024.jpg"


# ---------------------------------------------------------------------------
# MediaService Unit Tests
# ---------------------------------------------------------------------------


class TestMediaServiceGenerateUploadUrl:
    """Tests for MediaService.generate_upload_url()."""

    @pytest.mark.asyncio
    async def test_calls_boto3_with_correct_params(self) -> None:
        """S1: boto3 generate_presigned_url is called with correct bucket, key, content_type."""
        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            result = await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="meal.jpg",
                content_type="image/jpeg",
                media_type="photo",
            )

            mock_client.generate_presigned_url.assert_called_once()
            call_args = mock_client.generate_presigned_url.call_args
            assert call_args[0][0] == "put_object"
            params = call_args[1]["Params"]
            assert params["ContentType"] == "image/jpeg"
            assert params["Key"].startswith("photo/")
            assert str(FAKE_USER_ID) in params["Key"]
            assert call_args[1]["ExpiresIn"] == 300
            assert result.upload_url == FAKE_PRESIGNED_URL

    @pytest.mark.asyncio
    async def test_s3_key_format(self) -> None:
        """S2: S3 key matches {type}/{user_id}/{uuid}_{filename} pattern."""
        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            result = await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="meal.jpg",
                content_type="image/jpeg",
                media_type="photo",
            )

            # Extract the S3 key from the file_url
            file_url = result.file_url
            # Pattern: photo/{user_id}/{uuid}_{filename}
            key_pattern = (
                rf"photo/{FAKE_USER_ID}/"
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
                r"_meal\.jpg"
            )
            assert re.search(key_pattern, file_url), f"file_url doesn't match pattern: {file_url}"

    @pytest.mark.asyncio
    async def test_file_url_is_permanent(self) -> None:
        """S3: file_url has no query parameters (permanent URL)."""
        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            result = await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="meal.jpg",
                content_type="image/jpeg",
                media_type="photo",
            )

            assert "?" not in result.file_url
            assert result.file_url.startswith("https://")

    @pytest.mark.asyncio
    async def test_invalid_content_type_raises_400(self) -> None:
        """S4: Content type not in whitelist raises HTTPException(400)."""
        from fastapi import HTTPException

        service = MediaService()
        with pytest.raises(HTTPException) as exc_info:
            await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="file.gif",
                content_type="image/gif",
                media_type="photo",
            )
        assert exc_info.value.status_code == 400
        assert "image/gif" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_sanitizes_filename_spaces(self) -> None:
        """S5: Filename spaces become underscores in S3 key."""
        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            result = await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="my photo.jpg",
                content_type="image/jpeg",
                media_type="photo",
            )

            assert "my_photo.jpg" in result.file_url
            assert "my photo" not in result.file_url

    @pytest.mark.asyncio
    async def test_boto3_error_raises_503(self) -> None:
        """S9: boto3 ClientError raises HTTPException(503)."""
        from botocore.exceptions import ClientError
        from fastapi import HTTPException

        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.side_effect = ClientError(
                {"Error": {"Code": "InternalError", "Message": "S3 unavailable"}},
                "PutObject",
            )

            service = MediaService()
            with pytest.raises(HTTPException) as exc_info:
                await service.generate_upload_url(
                    user_id=FAKE_USER_ID,
                    filename="meal.jpg",
                    content_type="image/jpeg",
                    media_type="photo",
                )
            assert exc_info.value.status_code == 503
            assert exc_info.value.detail == "Storage service unavailable"

    @pytest.mark.asyncio
    async def test_unique_uuids_per_call(self) -> None:
        """S10: Two sequential calls produce different S3 keys."""
        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            result1 = await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="meal.jpg",
                content_type="image/jpeg",
                media_type="photo",
            )
            result2 = await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="meal.jpg",
                content_type="image/jpeg",
                media_type="photo",
            )

            assert result1.file_url != result2.file_url

    @pytest.mark.asyncio
    async def test_tts_with_mp3_succeeds(self) -> None:
        """S11: type=tts with content_type=audio/mp3 succeeds."""
        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            result = await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="response.mp3",
                content_type="audio/mp3",
                media_type="tts",
            )

            assert "tts/" in result.file_url
            assert result.upload_url == FAKE_PRESIGNED_URL

    @pytest.mark.asyncio
    async def test_tts_with_m4a_raises_400(self) -> None:
        """S12: type=tts with content_type=audio/m4a raises 400."""
        from fastapi import HTTPException

        service = MediaService()
        with pytest.raises(HTTPException) as exc_info:
            await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="response.m4a",
                content_type="audio/m4a",
                media_type="tts",
            )
        assert exc_info.value.status_code == 400
        assert "audio/m4a" in str(exc_info.value.detail)
        assert "tts" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_audio_with_m4a_succeeds(self) -> None:
        """Audio type with audio/m4a content type succeeds."""
        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            result = await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="recording.m4a",
                content_type="audio/m4a",
                media_type="audio",
            )

            assert "audio/" in result.file_url

    @pytest.mark.asyncio
    async def test_all_valid_content_types(self) -> None:
        """All valid content_type + type combinations succeed."""
        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            for media_type, content_types in ALLOWED_CONTENT_TYPES.items():
                for content_type in content_types:
                    result = await service.generate_upload_url(
                        user_id=FAKE_USER_ID,
                        filename="test.file",
                        content_type=content_type,
                        media_type=media_type,
                    )
                    assert result.upload_url == FAKE_PRESIGNED_URL
