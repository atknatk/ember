"""Route-level integration tests for STT endpoints.

Uses the FastAPI test client with mocked auth dependency and external services.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import uuid  # noqa: E402
from collections.abc import AsyncGenerator  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.dependencies import get_current_user, get_db  # noqa: E402
from app.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
FAKE_AUDIO_DATA = b"\xff\xfb\x90\x00" * 100
VALID_AUDIO_URL = "https://test-bucket.s3.us-east-1.amazonaws.com/audio/user123/recording.mp3"


def _make_fake_profile(
    user_id: uuid.UUID = FAKE_USER_ID,
) -> MagicMock:
    """Create a fake Profile for auth dependency override."""
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
    """Provide an async HTTP client without auth override."""

    async def override_db() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /api/v1/stt tests
# ---------------------------------------------------------------------------


class TestSTTEndpoint:
    """Tests for POST /api/v1/stt."""

    @pytest.mark.asyncio
    async def test_valid_request_returns_200(self, client: AsyncClient) -> None:
        """Valid STT request returns 200 with transcript."""
        body_mock = MagicMock()
        body_mock.read.return_value = FAKE_AUDIO_DATA
        s3_response = {"Body": body_mock}

        whisper_response = MagicMock()
        whisper_response.text = "Hello world"
        whisper_response.language = "en"
        whisper_response.duration = 3.5
        segment = MagicMock()
        segment.avg_logprob = -0.1
        whisper_response.segments = [segment]

        with (
            patch("app.services.stt_service._s3_client") as mock_s3,
            patch("app.services.stt_service.OpenAI") as mock_openai_cls,
            patch("app.services.stt_service.settings") as mock_settings,
        ):
            mock_settings.openai_api_key = "test-key"
            mock_s3.get_object.return_value = s3_response

            mock_client = MagicMock()
            mock_client.audio.transcriptions.create.return_value = whisper_response
            mock_openai_cls.return_value = mock_client

            resp = await client.post(
                "/api/v1/stt",
                json={"audio_url": VALID_AUDIO_URL},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["transcript"] == "Hello world"
        assert data["language"] == "en"
        assert data["confidence"] > 0
        assert data["duration_seconds"] == 3.5

    @pytest.mark.asyncio
    async def test_without_auth_returns_401_or_403(self, unauthed_client: AsyncClient) -> None:
        """Request without auth header returns 401 or 403."""
        resp = await unauthed_client.post(
            "/api/v1/stt",
            json={"audio_url": VALID_AUDIO_URL},
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_missing_audio_url_returns_422(self, client: AsyncClient) -> None:
        """Missing audio_url returns 422."""
        resp = await client.post("/api/v1/stt", json={})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_audio_url_returns_422(self, client: AsyncClient) -> None:
        """Empty audio_url returns 422."""
        resp = await client.post("/api/v1/stt", json={"audio_url": ""})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_unsupported_format_returns_422(self, client: AsyncClient) -> None:
        """Unsupported audio format returns 422 (caught by schema validator)."""
        resp = await client.post(
            "/api/v1/stt",
            json={
                "audio_url": "https://bucket.s3.us-east-1.amazonaws.com/audio/file.txt",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_file_too_large_returns_413(self, client: AsyncClient) -> None:
        """File exceeding 25MB returns 413."""
        large_data = b"\x00" * (26 * 1024 * 1024)
        body_mock = MagicMock()
        body_mock.read.return_value = large_data
        s3_response = {"Body": body_mock}

        with patch("app.services.stt_service._s3_client") as mock_s3:
            mock_s3.get_object.return_value = s3_response

            resp = await client.post(
                "/api/v1/stt",
                json={"audio_url": VALID_AUDIO_URL},
            )

        assert resp.status_code == 413

    @pytest.mark.asyncio
    async def test_s3_not_found_returns_400(self, client: AsyncClient) -> None:
        """S3 file not found returns 400."""
        with patch("app.services.stt_service._s3_client") as mock_s3:
            mock_s3.get_object.side_effect = ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}},
                "GetObject",
            )

            resp = await client.post(
                "/api/v1/stt",
                json={"audio_url": VALID_AUDIO_URL},
            )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_whisper_failure_returns_503(self, client: AsyncClient) -> None:
        """Whisper API failure returns 503."""
        body_mock = MagicMock()
        body_mock.read.return_value = FAKE_AUDIO_DATA
        s3_response = {"Body": body_mock}

        with (
            patch("app.services.stt_service._s3_client") as mock_s3,
            patch("app.services.stt_service.OpenAI") as mock_openai_cls,
            patch("app.services.stt_service.settings") as mock_settings,
        ):
            mock_settings.openai_api_key = "test-key"
            mock_s3.get_object.return_value = s3_response

            mock_client = MagicMock()
            mock_client.audio.transcriptions.create.side_effect = Exception("Whisper error")
            mock_openai_cls.return_value = mock_client

            resp = await client.post(
                "/api/v1/stt",
                json={"audio_url": VALID_AUDIO_URL},
            )

        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_response_shape(self, client: AsyncClient) -> None:
        """Response has correct shape: transcript, language, confidence, duration_seconds."""
        body_mock = MagicMock()
        body_mock.read.return_value = FAKE_AUDIO_DATA
        s3_response = {"Body": body_mock}

        whisper_response = MagicMock()
        whisper_response.text = "Test"
        whisper_response.language = "en"
        whisper_response.duration = 1.0
        whisper_response.segments = []

        with (
            patch("app.services.stt_service._s3_client") as mock_s3,
            patch("app.services.stt_service.OpenAI") as mock_openai_cls,
            patch("app.services.stt_service.settings") as mock_settings,
        ):
            mock_settings.openai_api_key = "test-key"
            mock_s3.get_object.return_value = s3_response

            mock_client = MagicMock()
            mock_client.audio.transcriptions.create.return_value = whisper_response
            mock_openai_cls.return_value = mock_client

            resp = await client.post(
                "/api/v1/stt",
                json={"audio_url": VALID_AUDIO_URL},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "transcript" in data
        assert "language" in data
        assert "confidence" in data
        assert "duration_seconds" in data

    @pytest.mark.asyncio
    async def test_m4a_url_accepted(self, client: AsyncClient) -> None:
        """M4A URL is accepted."""
        body_mock = MagicMock()
        body_mock.read.return_value = FAKE_AUDIO_DATA
        s3_response = {"Body": body_mock}

        whisper_response = MagicMock()
        whisper_response.text = "Hello"
        whisper_response.language = "en"
        whisper_response.duration = 1.0
        whisper_response.segments = []

        with (
            patch("app.services.stt_service._s3_client") as mock_s3,
            patch("app.services.stt_service.OpenAI") as mock_openai_cls,
            patch("app.services.stt_service.settings") as mock_settings,
        ):
            mock_settings.openai_api_key = "test-key"
            mock_s3.get_object.return_value = s3_response

            mock_client = MagicMock()
            mock_client.audio.transcriptions.create.return_value = whisper_response
            mock_openai_cls.return_value = mock_client

            m4a_url = "https://test-bucket.s3.us-east-1.amazonaws.com/audio/recording.m4a"
            resp = await client.post(
                "/api/v1/stt",
                json={"audio_url": m4a_url},
            )

        assert resp.status_code == 200
