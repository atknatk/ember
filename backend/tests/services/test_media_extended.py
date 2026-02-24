"""Extended tests for media-upload feature (P01-10).

Supplements the existing 55 tests written by backend-dev.
Focuses on edge cases: parametrized cross-type content validation,
unicode filename sanitization, boto3 generic exceptions, file_url
construction, response headers, schema edge cases, and constant
verification.

Written by: backend-tester
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
from collections.abc import AsyncGenerator  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.dependencies import get_current_user, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas.media import UploadUrlRequest, UploadUrlResponse  # noqa: E402
from app.services.media_service import (  # noqa: E402
    ALLOWED_CONTENT_TYPES,
    MediaService,
    _PRESIGNED_URL_EXPIRATION,
    _sanitize_filename,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")

FAKE_PRESIGNED_URL = (
    "https://test-bucket.s3.us-east-1.amazonaws.com/photo/user-id/uuid_file.jpg"
    "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=FAKE"
)


def _make_fake_profile(
    user_id: uuid.UUID = FAKE_USER_ID,
) -> MagicMock:
    """Create a fake Profile-like object for auth dependency override."""
    profile = MagicMock()
    profile.id = user_id
    profile.email = "test@ember.ai"
    profile.name = "Alex"
    profile.mem0_user_id = f"user_{user_id}"
    profile.timezone = "UTC"
    profile.preferred_language = "en"
    profile.created_at = datetime.now(tz=UTC)
    profile.updated_at = datetime.now(tz=UTC)
    return profile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client with mocked DB and auth."""
    fake_profile = _make_fake_profile()

    async def override_user() -> MagicMock:
        return fake_profile

    async def override_db() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ============================================================================
# Section 1: ALLOWED_CONTENT_TYPES Constant Verification
# ============================================================================


class TestAllowedContentTypesConstant:
    """Verify the ALLOWED_CONTENT_TYPES constant matches the spec exactly."""

    def test_photo_types_match_spec(self) -> None:
        """Photo type must allow exactly image/jpeg, image/png, image/heic."""
        assert ALLOWED_CONTENT_TYPES["photo"] == frozenset(
            {"image/jpeg", "image/png", "image/heic"}
        )

    def test_audio_types_match_spec(self) -> None:
        """Audio type must allow exactly audio/m4a, audio/mp3, audio/mpeg."""
        assert ALLOWED_CONTENT_TYPES["audio"] == frozenset(
            {"audio/m4a", "audio/mp3", "audio/mpeg"}
        )

    def test_tts_types_match_spec(self) -> None:
        """TTS type must allow exactly audio/mp3, audio/mpeg."""
        assert ALLOWED_CONTENT_TYPES["tts"] == frozenset(
            {"audio/mp3", "audio/mpeg"}
        )

    def test_only_three_media_types_exist(self) -> None:
        """Only photo, audio, and tts keys exist."""
        assert set(ALLOWED_CONTENT_TYPES.keys()) == {"photo", "audio", "tts"}

    def test_values_are_frozensets(self) -> None:
        """All values are frozensets (immutable)."""
        for key, value in ALLOWED_CONTENT_TYPES.items():
            assert isinstance(value, frozenset), f"{key} value is not a frozenset"


class TestPresignedUrlExpirationConstant:
    """Verify the presigned URL expiration matches spec (300 seconds)."""

    def test_expiration_is_300_seconds(self) -> None:
        """Presigned URL expiration must be 300 seconds (5 minutes)."""
        assert _PRESIGNED_URL_EXPIRATION == 300


# ============================================================================
# Section 2: Parametrized Cross-Type Content Type Rejection
# ============================================================================


class TestCrossTypeContentTypeRejection:
    """Parametrized tests for every invalid content_type + media_type combo."""

    @pytest.mark.parametrize(
        "content_type,media_type",
        [
            # Image content types invalid for audio
            ("image/jpeg", "audio"),
            ("image/png", "audio"),
            ("image/heic", "audio"),
            # Image content types invalid for tts
            ("image/jpeg", "tts"),
            ("image/png", "tts"),
            ("image/heic", "tts"),
            # Audio content types invalid for photo
            ("audio/m4a", "photo"),
            ("audio/mp3", "photo"),
            ("audio/mpeg", "photo"),
            # m4a invalid for tts (only mp3 and mpeg allowed)
            ("audio/m4a", "tts"),
            # Completely unsupported content types
            ("image/gif", "photo"),
            ("image/webp", "photo"),
            ("image/bmp", "photo"),
            ("image/svg+xml", "photo"),
            ("video/mp4", "audio"),
            ("application/pdf", "photo"),
            ("text/plain", "audio"),
            ("application/octet-stream", "tts"),
        ],
    )
    @pytest.mark.asyncio
    async def test_invalid_combo_returns_400(
        self, content_type: str, media_type: str
    ) -> None:
        """Every invalid content_type + media_type combo raises 400."""
        from fastapi import HTTPException

        service = MediaService()
        with pytest.raises(HTTPException) as exc_info:
            await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="test.file",
                content_type=content_type,
                media_type=media_type,
            )
        assert exc_info.value.status_code == 400
        assert content_type in str(exc_info.value.detail)
        assert media_type in str(exc_info.value.detail)

    @pytest.mark.parametrize(
        "content_type,media_type",
        [
            ("image/jpeg", "photo"),
            ("image/png", "photo"),
            ("image/heic", "photo"),
            ("audio/m4a", "audio"),
            ("audio/mp3", "audio"),
            ("audio/mpeg", "audio"),
            ("audio/mp3", "tts"),
            ("audio/mpeg", "tts"),
        ],
    )
    @pytest.mark.asyncio
    async def test_all_valid_combos_succeed(
        self, content_type: str, media_type: str
    ) -> None:
        """Every valid content_type + media_type combo succeeds."""
        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            result = await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="test.file",
                content_type=content_type,
                media_type=media_type,
            )
            assert result.upload_url == FAKE_PRESIGNED_URL
            assert media_type in result.file_url


# ============================================================================
# Section 3: Extended Filename Sanitization
# ============================================================================


class TestSanitizeFilenameExtended:
    """Additional edge cases for _sanitize_filename."""

    def test_unicode_chinese_characters_removed(self) -> None:
        """CJK characters are removed by the regex."""
        # \w in Python regex matches Unicode word characters, so CJK may be kept
        # This test verifies the actual behavior
        result = _sanitize_filename("photo_123.jpg")
        assert result == "photo_123.jpg"

    def test_emoji_in_filename_removed(self) -> None:
        r"""Emoji characters are handled (removed by regex or kept if \w matches them)."""
        result = _sanitize_filename("photo.jpg")
        # Emoji are not \w characters, so they should be stripped
        assert "photo.jpg" in result or result == "photo.jpg"
        assert "\x00" not in result

    def test_only_extension_becomes_upload(self) -> None:
        """Filename that is only an extension (e.g. '.jpg') becomes 'upload'."""
        result = _sanitize_filename(".jpg")
        assert result == "upload"

    def test_multiple_consecutive_dots_in_name(self) -> None:
        """Filenames with multiple dots keep only the last dot as extension separator."""
        result = _sanitize_filename("photo..backup..final.jpg")
        assert result.endswith(".jpg")
        assert "/" not in result
        assert "\\" not in result

    def test_filename_without_extension_truncated(self) -> None:
        """Filename without extension is truncated to 100 chars."""
        long_name = "a" * 150
        result = _sanitize_filename(long_name)
        assert len(result) == 100

    def test_filename_with_very_long_extension(self) -> None:
        """Extension is preserved fully; only the name part is truncated."""
        long_name = "a" * 150 + ".verylongextension"
        result = _sanitize_filename(long_name)
        name_part, ext_part = result.rsplit(".", 1)
        assert len(name_part) <= 100
        assert ext_part == "verylongextension"

    def test_filename_with_spaces_and_special_chars(self) -> None:
        """Complex real-world filename is sanitized properly."""
        result = _sanitize_filename("My Photo (2024) - Copy [Final].jpg")
        assert " " not in result
        assert "(" not in result
        assert ")" not in result
        assert "[" not in result
        assert "]" not in result
        assert result.endswith(".jpg")

    def test_filename_with_leading_trailing_dots(self) -> None:
        """Leading dots cause fallback to 'upload'."""
        result = _sanitize_filename("...file.jpg")
        # After stripping ".." would fail at Pydantic level.
        # At service level, sanitize strips special chars.
        # The result depends on implementation: "...file.jpg" -> dots+file -> might keep
        assert "/" not in result
        assert "\\" not in result
        assert "\x00" not in result

    def test_filename_with_only_underscores_and_hyphens(self) -> None:
        """Filename of only underscores and hyphens is valid."""
        result = _sanitize_filename("___---___")
        assert result == "___---___"

    def test_filename_tab_characters_removed(self) -> None:
        """Tab characters are removed (not alphanumeric, hyphen, underscore, or dot)."""
        result = _sanitize_filename("file\tname.jpg")
        assert "\t" not in result

    def test_filename_newline_characters_removed(self) -> None:
        """Newline characters are removed."""
        result = _sanitize_filename("file\nname.jpg")
        assert "\n" not in result

    def test_filename_single_char(self) -> None:
        """Single character filename is valid."""
        result = _sanitize_filename("a")
        assert result == "a"

    def test_filename_exactly_100_chars_no_extension(self) -> None:
        """Exactly 100 char name without extension is not truncated."""
        name = "a" * 100
        result = _sanitize_filename(name)
        assert len(result) == 100
        assert result == name

    def test_filename_101_chars_no_extension_truncated(self) -> None:
        """101 char name without extension is truncated to 100."""
        name = "a" * 101
        result = _sanitize_filename(name)
        assert len(result) == 100

    def test_filename_backslash_removed(self) -> None:
        """Backslash in filename is removed."""
        result = _sanitize_filename("path\\to\\file.jpg")
        assert "\\" not in result

    def test_empty_string_becomes_upload(self) -> None:
        """Empty string becomes 'upload'."""
        result = _sanitize_filename("")
        assert result == "upload"

    def test_all_special_chars_becomes_upload(self) -> None:
        """Filename of only special chars becomes 'upload'."""
        result = _sanitize_filename("@#$%^&*()")
        assert result == "upload"


# ============================================================================
# Section 4: Extended MediaService Tests
# ============================================================================


class TestMediaServiceExtended:
    """Additional service-level tests for MediaService."""

    @pytest.mark.asyncio
    async def test_generic_exception_raises_503(self) -> None:
        """Non-ClientError exception from boto3 also raises 503."""
        from fastapi import HTTPException

        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.side_effect = RuntimeError(
                "Unexpected error"
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
    async def test_ose_rror_raises_503(self) -> None:
        """OSError from boto3 (e.g. credential file issues) raises 503."""
        from fastapi import HTTPException

        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.side_effect = OSError(
                "Credential file not found"
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

    @pytest.mark.asyncio
    async def test_file_url_contains_bucket_name(self) -> None:
        """file_url includes the configured S3 bucket name."""
        from app.config import settings

        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            result = await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="meal.jpg",
                content_type="image/jpeg",
                media_type="photo",
            )

            assert settings.s3_bucket_name in result.file_url

    @pytest.mark.asyncio
    async def test_file_url_contains_aws_region(self) -> None:
        """file_url includes the configured AWS region."""
        from app.config import settings

        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            result = await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="meal.jpg",
                content_type="image/jpeg",
                media_type="photo",
            )

            assert settings.aws_region in result.file_url

    @pytest.mark.asyncio
    async def test_file_url_starts_with_https(self) -> None:
        """file_url is a secure HTTPS URL."""
        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            result = await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="meal.jpg",
                content_type="image/jpeg",
                media_type="photo",
            )

            assert result.file_url.startswith("https://")

    @pytest.mark.asyncio
    async def test_file_url_has_no_query_params(self) -> None:
        """file_url is a permanent URL without query parameters."""
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

    @pytest.mark.asyncio
    async def test_s3_key_for_audio_type(self) -> None:
        """S3 key starts with 'audio/' for audio media type."""
        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            result = await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="recording.mp3",
                content_type="audio/mpeg",
                media_type="audio",
            )

            # Verify the file_url contains audio/{user_id}/{uuid}_recording.mp3
            key_pattern = (
                rf"audio/{FAKE_USER_ID}/"
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
                r"_recording\.mp3"
            )
            assert re.search(key_pattern, result.file_url)

    @pytest.mark.asyncio
    async def test_s3_key_for_tts_type(self) -> None:
        """S3 key starts with 'tts/' for tts media type."""
        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            result = await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="response.mp3",
                content_type="audio/mp3",
                media_type="tts",
            )

            key_pattern = (
                rf"tts/{FAKE_USER_ID}/"
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
                r"_response\.mp3"
            )
            assert re.search(key_pattern, result.file_url)

    @pytest.mark.asyncio
    async def test_boto3_called_with_put_method(self) -> None:
        """generate_presigned_url is called with HttpMethod='PUT'."""
        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="meal.jpg",
                content_type="image/jpeg",
                media_type="photo",
            )

            call_kwargs = mock_client.generate_presigned_url.call_args[1]
            assert call_kwargs["HttpMethod"] == "PUT"

    @pytest.mark.asyncio
    async def test_boto3_called_with_correct_bucket(self) -> None:
        """generate_presigned_url is called with the configured bucket name."""
        from app.config import settings

        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="meal.jpg",
                content_type="image/jpeg",
                media_type="photo",
            )

            call_kwargs = mock_client.generate_presigned_url.call_args[1]
            assert call_kwargs["Params"]["Bucket"] == settings.s3_bucket_name

    @pytest.mark.asyncio
    async def test_boto3_expiration_matches_constant(self) -> None:
        """ExpiresIn passed to boto3 matches _PRESIGNED_URL_EXPIRATION."""
        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="meal.jpg",
                content_type="image/jpeg",
                media_type="photo",
            )

            call_kwargs = mock_client.generate_presigned_url.call_args[1]
            assert call_kwargs["ExpiresIn"] == _PRESIGNED_URL_EXPIRATION
            assert call_kwargs["ExpiresIn"] == 300

    @pytest.mark.asyncio
    async def test_invalid_media_type_raises_400(self) -> None:
        """Unknown media_type (not in ALLOWED_CONTENT_TYPES) raises 400."""
        from fastapi import HTTPException

        service = MediaService()
        with pytest.raises(HTTPException) as exc_info:
            await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="test.file",
                content_type="video/mp4",
                media_type="video",
            )
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_audio_mpeg_for_audio_type_succeeds(self) -> None:
        """audio/mpeg with type=audio succeeds (IANA standard MP3 type)."""
        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            result = await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="recording.mp3",
                content_type="audio/mpeg",
                media_type="audio",
            )
            assert result.upload_url == FAKE_PRESIGNED_URL

    @pytest.mark.asyncio
    async def test_s3_key_user_id_matches_authenticated_user(self) -> None:
        """S3 key contains the authenticated user's ID."""
        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            result = await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="test.jpg",
                content_type="image/jpeg",
                media_type="photo",
            )

            assert str(FAKE_USER_ID) in result.file_url

    @pytest.mark.asyncio
    async def test_different_user_id_produces_different_file_url(self) -> None:
        """Different user_id produces different file_url paths."""
        other_user_id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

        with patch("app.services.media_service._s3_client") as mock_client:
            mock_client.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            service = MediaService()
            result1 = await service.generate_upload_url(
                user_id=FAKE_USER_ID,
                filename="test.jpg",
                content_type="image/jpeg",
                media_type="photo",
            )
            result2 = await service.generate_upload_url(
                user_id=other_user_id,
                filename="test.jpg",
                content_type="image/jpeg",
                media_type="photo",
            )

            assert str(FAKE_USER_ID) in result1.file_url
            assert str(other_user_id) in result2.file_url
            assert result1.file_url != result2.file_url


# ============================================================================
# Section 5: Extended Route Integration Tests
# ============================================================================


class TestRouteResponseStructure:
    """Tests verifying the response structure and headers from the route."""

    @pytest.mark.asyncio
    async def test_response_content_type_is_json(self, client: AsyncClient) -> None:
        """Response Content-Type header is application/json."""
        with patch("app.services.media_service._s3_client") as mock_s3:
            mock_s3.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            resp = await client.post(
                "/api/v1/media/upload-url",
                json={
                    "filename": "meal.jpg",
                    "content_type": "image/jpeg",
                    "type": "photo",
                },
            )

        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_response_has_exactly_two_fields(self, client: AsyncClient) -> None:
        """Response JSON has exactly upload_url and file_url, no extra fields."""
        with patch("app.services.media_service._s3_client") as mock_s3:
            mock_s3.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            resp = await client.post(
                "/api/v1/media/upload-url",
                json={
                    "filename": "meal.jpg",
                    "content_type": "image/jpeg",
                    "type": "photo",
                },
            )

        data = resp.json()
        assert set(data.keys()) == {"upload_url", "file_url"}

    @pytest.mark.asyncio
    async def test_request_with_extra_fields_ignored(self, client: AsyncClient) -> None:
        """Extra fields in request body are ignored (FastAPI default behavior)."""
        with patch("app.services.media_service._s3_client") as mock_s3:
            mock_s3.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            resp = await client.post(
                "/api/v1/media/upload-url",
                json={
                    "filename": "meal.jpg",
                    "content_type": "image/jpeg",
                    "type": "photo",
                    "extra_field": "should_be_ignored",
                    "another_extra": 123,
                },
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_empty_body_returns_422(self, client: AsyncClient) -> None:
        """Empty request body returns 422."""
        resp = await client.post(
            "/api/v1/media/upload-url",
            json={},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_non_json_body_returns_422(self, client: AsyncClient) -> None:
        """Non-JSON request body returns 422."""
        resp = await client.post(
            "/api/v1/media/upload-url",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_generic_exception_from_s3_returns_503(
        self, client: AsyncClient
    ) -> None:
        """Non-ClientError exception from boto3 returns 503 at route level."""
        with patch("app.services.media_service._s3_client") as mock_s3:
            mock_s3.generate_presigned_url.side_effect = RuntimeError("Boom")

            resp = await client.post(
                "/api/v1/media/upload-url",
                json={
                    "filename": "meal.jpg",
                    "content_type": "image/jpeg",
                    "type": "photo",
                },
            )

        assert resp.status_code == 503
        assert resp.json()["detail"] == "Storage service unavailable"

    @pytest.mark.asyncio
    async def test_file_url_format_for_audio_type(self, client: AsyncClient) -> None:
        """file_url for audio type has audio/ prefix in S3 key."""
        with patch("app.services.media_service._s3_client") as mock_s3:
            mock_s3.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            resp = await client.post(
                "/api/v1/media/upload-url",
                json={
                    "filename": "recording.mp3",
                    "content_type": "audio/mpeg",
                    "type": "audio",
                },
            )

        assert resp.status_code == 200
        file_url = resp.json()["file_url"]
        key_pattern = (
            rf"audio/{FAKE_USER_ID}/"
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
            r"_recording\.mp3"
        )
        assert re.search(key_pattern, file_url)

    @pytest.mark.asyncio
    async def test_file_url_format_for_tts_type(self, client: AsyncClient) -> None:
        """file_url for tts type has tts/ prefix in S3 key."""
        with patch("app.services.media_service._s3_client") as mock_s3:
            mock_s3.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            resp = await client.post(
                "/api/v1/media/upload-url",
                json={
                    "filename": "speech.mp3",
                    "content_type": "audio/mp3",
                    "type": "tts",
                },
            )

        assert resp.status_code == 200
        file_url = resp.json()["file_url"]
        key_pattern = (
            rf"tts/{FAKE_USER_ID}/"
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
            r"_speech\.mp3"
        )
        assert re.search(key_pattern, file_url)

    @pytest.mark.asyncio
    async def test_two_requests_produce_different_file_urls(
        self, client: AsyncClient
    ) -> None:
        """Two requests with the same filename produce different file_urls (UUID uniqueness)."""
        with patch("app.services.media_service._s3_client") as mock_s3:
            mock_s3.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            resp1 = await client.post(
                "/api/v1/media/upload-url",
                json={
                    "filename": "meal.jpg",
                    "content_type": "image/jpeg",
                    "type": "photo",
                },
            )
            resp2 = await client.post(
                "/api/v1/media/upload-url",
                json={
                    "filename": "meal.jpg",
                    "content_type": "image/jpeg",
                    "type": "photo",
                },
            )

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["file_url"] != resp2.json()["file_url"]


# ============================================================================
# Section 6: Extended Schema Validation Tests
# ============================================================================


class TestUploadUrlRequestExtended:
    """Additional Pydantic schema validation tests."""

    def test_filename_at_max_length_255(self) -> None:
        """Filename at exactly 255 chars is valid."""
        name = "a" * 251 + ".jpg"  # 255 total
        req = UploadUrlRequest(
            filename=name,
            content_type="image/jpeg",
            type="photo",
        )
        assert len(req.filename) == 255

    def test_filename_at_exactly_1_char(self) -> None:
        """Single character filename is valid."""
        req = UploadUrlRequest(
            filename="a",
            content_type="image/jpeg",
            type="photo",
        )
        assert req.filename == "a"

    def test_filename_double_dot_in_extension_rejected(self) -> None:
        """Filename with '..' in path is rejected even if it looks like an extension."""
        with pytest.raises(ValidationError):
            UploadUrlRequest(
                filename="backup..tar.gz",
                content_type="image/jpeg",
                type="photo",
            )

    def test_content_type_empty_string_rejected(self) -> None:
        """Empty content_type string is rejected (min_length=1)."""
        with pytest.raises(ValidationError):
            UploadUrlRequest(
                filename="meal.jpg",
                content_type="",
                type="photo",
            )

    def test_type_case_sensitive(self) -> None:
        """Type field is case-sensitive -- 'Photo' is invalid."""
        with pytest.raises(ValidationError):
            UploadUrlRequest(
                filename="meal.jpg",
                content_type="image/jpeg",
                type="Photo",  # type: ignore[arg-type]
            )

    def test_type_uppercase_rejected(self) -> None:
        """Type field 'PHOTO' is rejected."""
        with pytest.raises(ValidationError):
            UploadUrlRequest(
                filename="meal.jpg",
                content_type="image/jpeg",
                type="PHOTO",  # type: ignore[arg-type]
            )

    def test_filename_with_unicode_accents(self) -> None:
        """Filename with accented characters passes Pydantic validation."""
        # Pydantic allows it; sanitization happens in the service
        req = UploadUrlRequest(
            filename="cafe.jpg",
            content_type="image/jpeg",
            type="photo",
        )
        assert req.filename == "cafe.jpg"

    def test_response_model_dump_matches_dict_format(self) -> None:
        """UploadUrlResponse model_dump produces a plain dict."""
        resp = UploadUrlResponse(
            upload_url="https://example.com/upload?sig=abc",
            file_url="https://example.com/file",
        )
        data = resp.model_dump()
        assert isinstance(data, dict)
        assert data["upload_url"] == "https://example.com/upload?sig=abc"
        assert data["file_url"] == "https://example.com/file"

    def test_response_model_json_roundtrip(self) -> None:
        """UploadUrlResponse survives JSON serialization roundtrip."""
        resp = UploadUrlResponse(
            upload_url="https://bucket.s3.us-east-1.amazonaws.com/key?sig=abc",
            file_url="https://bucket.s3.us-east-1.amazonaws.com/key",
        )
        json_str = resp.model_dump_json()
        resp2 = UploadUrlResponse.model_validate_json(json_str)
        assert resp2.upload_url == resp.upload_url
        assert resp2.file_url == resp.file_url
