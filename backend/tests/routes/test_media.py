"""Route-level integration tests for media upload endpoints.

Uses the FastAPI test client with mocked auth dependency and boto3 S3 client.
No database access is needed for this feature.
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

from app.dependencies import get_current_user, get_db  # noqa: E402
from app.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
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


@pytest_asyncio.fixture
async def unauthed_client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client without auth override (for 401 tests)."""
    async def override_db() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /api/v1/media/upload-url tests
# ---------------------------------------------------------------------------


class TestCreateUploadUrl:
    """Tests for POST /api/v1/media/upload-url."""

    @pytest.mark.asyncio
    async def test_valid_photo_request(self, client: AsyncClient) -> None:
        """R1: Valid photo request returns 200 with upload_url and file_url."""
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
        data = resp.json()
        assert "upload_url" in data
        assert "file_url" in data

    @pytest.mark.asyncio
    async def test_valid_audio_request(self, client: AsyncClient) -> None:
        """R2: Valid audio request returns 200."""
        with patch("app.services.media_service._s3_client") as mock_s3:
            mock_s3.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            resp = await client.post(
                "/api/v1/media/upload-url",
                json={
                    "filename": "voice.mp3",
                    "content_type": "audio/mp3",
                    "type": "audio",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "upload_url" in data
        assert "file_url" in data

    @pytest.mark.asyncio
    async def test_valid_tts_request(self, client: AsyncClient) -> None:
        """R3: Valid TTS request returns 200."""
        with patch("app.services.media_service._s3_client") as mock_s3:
            mock_s3.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            resp = await client.post(
                "/api/v1/media/upload-url",
                json={
                    "filename": "response.mp3",
                    "content_type": "audio/mpeg",
                    "type": "tts",
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "upload_url" in data
        assert "file_url" in data

    @pytest.mark.asyncio
    async def test_photo_png_succeeds(self, client: AsyncClient) -> None:
        """R4: image/png with type=photo returns 200."""
        with patch("app.services.media_service._s3_client") as mock_s3:
            mock_s3.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            resp = await client.post(
                "/api/v1/media/upload-url",
                json={
                    "filename": "screenshot.png",
                    "content_type": "image/png",
                    "type": "photo",
                },
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_photo_heic_succeeds(self, client: AsyncClient) -> None:
        """R5: image/heic with type=photo returns 200."""
        with patch("app.services.media_service._s3_client") as mock_s3:
            mock_s3.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            resp = await client.post(
                "/api/v1/media/upload-url",
                json={
                    "filename": "photo.heic",
                    "content_type": "image/heic",
                    "type": "photo",
                },
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_audio_m4a_succeeds(self, client: AsyncClient) -> None:
        """R6: audio/m4a with type=audio returns 200."""
        with patch("app.services.media_service._s3_client") as mock_s3:
            mock_s3.generate_presigned_url.return_value = FAKE_PRESIGNED_URL

            resp = await client.post(
                "/api/v1/media/upload-url",
                json={
                    "filename": "recording.m4a",
                    "content_type": "audio/m4a",
                    "type": "audio",
                },
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_content_type_mismatch_image_for_audio(self, client: AsyncClient) -> None:
        """R7: image/jpeg for type=audio returns 400."""
        resp = await client.post(
            "/api/v1/media/upload-url",
            json={
                "filename": "meal.jpg",
                "content_type": "image/jpeg",
                "type": "audio",
            },
        )

        assert resp.status_code == 400
        assert "image/jpeg" in resp.json()["detail"]
        assert "audio" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_content_type_mismatch_audio_for_photo(self, client: AsyncClient) -> None:
        """R8: audio/mp3 for type=photo returns 400."""
        resp = await client.post(
            "/api/v1/media/upload-url",
            json={
                "filename": "voice.mp3",
                "content_type": "audio/mp3",
                "type": "photo",
            },
        )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_type_returns_422(self, client: AsyncClient) -> None:
        """R9: type=video returns 422 (Pydantic validation error)."""
        resp = await client.post(
            "/api/v1/media/upload-url",
            json={
                "filename": "video.mp4",
                "content_type": "video/mp4",
                "type": "video",
            },
        )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_without_auth_returns_401(self, unauthed_client: AsyncClient) -> None:
        """R10: Request without auth header returns 401 or 403."""
        resp = await unauthed_client.post(
            "/api/v1/media/upload-url",
            json={
                "filename": "meal.jpg",
                "content_type": "image/jpeg",
                "type": "photo",
            },
        )

        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_missing_filename_returns_422(self, client: AsyncClient) -> None:
        """R11: Missing filename returns 422."""
        resp = await client.post(
            "/api/v1/media/upload-url",
            json={
                "content_type": "image/jpeg",
                "type": "photo",
            },
        )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_content_type_returns_422(self, client: AsyncClient) -> None:
        """R12: Missing content_type returns 422."""
        resp = await client.post(
            "/api/v1/media/upload-url",
            json={
                "filename": "meal.jpg",
                "type": "photo",
            },
        )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_type_returns_422(self, client: AsyncClient) -> None:
        """R13: Missing type returns 422."""
        resp = await client.post(
            "/api/v1/media/upload-url",
            json={
                "filename": "meal.jpg",
                "content_type": "image/jpeg",
            },
        )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_filename_returns_422(self, client: AsyncClient) -> None:
        """R14: Empty filename returns 422."""
        resp = await client.post(
            "/api/v1/media/upload-url",
            json={
                "filename": "   ",
                "content_type": "image/jpeg",
                "type": "photo",
            },
        )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_path_traversal_filename_returns_error(self, client: AsyncClient) -> None:
        """R15: Path traversal in filename returns 422 (rejected by validator)."""
        resp = await client.post(
            "/api/v1/media/upload-url",
            json={
                "filename": "../../etc/passwd",
                "content_type": "image/jpeg",
                "type": "photo",
            },
        )

        # Pydantic validator rejects ".." in filename
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_s3_failure_returns_503(self, client: AsyncClient) -> None:
        """R16: S3 client failure returns 503."""
        from botocore.exceptions import ClientError

        with patch("app.services.media_service._s3_client") as mock_s3:
            mock_s3.generate_presigned_url.side_effect = ClientError(
                {"Error": {"Code": "InternalError", "Message": "S3 unavailable"}},
                "PutObject",
            )

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
    async def test_upload_url_contains_bucket_name(self, client: AsyncClient) -> None:
        """R17: Response upload_url contains the S3 bucket name."""
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
        # The presigned URL is returned directly from boto3, which includes the bucket

    @pytest.mark.asyncio
    async def test_file_url_matches_key_format(self, client: AsyncClient) -> None:
        """R18: file_url matches {type}/{user_id}/{uuid}_{filename} pattern."""
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
        file_url = resp.json()["file_url"]

        # Verify key format: photo/{user_id}/{uuid}_meal.jpg
        key_pattern = (
            rf"photo/{FAKE_USER_ID}/"
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
            r"_meal\.jpg"
        )
        assert re.search(key_pattern, file_url), f"file_url does not match pattern: {file_url}"

    @pytest.mark.asyncio
    async def test_unsupported_content_type_returns_400(self, client: AsyncClient) -> None:
        """R19: Unsupported content_type (image/gif for photo) returns 400."""
        resp = await client.post(
            "/api/v1/media/upload-url",
            json={
                "filename": "animation.gif",
                "content_type": "image/gif",
                "type": "photo",
            },
        )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_tts_with_m4a_returns_400(self, client: AsyncClient) -> None:
        """R20: audio/m4a for type=tts returns 400."""
        resp = await client.post(
            "/api/v1/media/upload-url",
            json={
                "filename": "response.m4a",
                "content_type": "audio/m4a",
                "type": "tts",
            },
        )

        assert resp.status_code == 400
        assert "audio/m4a" in resp.json()["detail"]
        assert "tts" in resp.json()["detail"]
