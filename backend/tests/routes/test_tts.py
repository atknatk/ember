"""Route-level integration tests for TTS endpoints.

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

import app.services.tts_service as tts_module  # noqa: E402
from app.dependencies import get_current_user, get_db  # noqa: E402
from app.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
FAKE_CHARACTER_ID = uuid.UUID("660e8400-e29b-41d4-a716-446655440001")
FAKE_AUDIO_DATA = b"\xff\xfb\x90\x00" * 100


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


def _make_fake_character(
    char_id: uuid.UUID = FAKE_CHARACTER_ID,
    user_id: uuid.UUID = FAKE_USER_ID,
) -> MagicMock:
    """Create a fake Character ORM object."""
    char = MagicMock()
    char.id = char_id
    char.user_id = user_id
    char.template = "companion"
    char.name = "Luna"
    char.mem0_agent_id = f"companion_{user_id}"
    char.is_active = True
    return char


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_breaker() -> None:
    """Reset the ElevenLabs circuit breaker before each test."""
    tts_module._elevenlabs_breaker = None


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client with mocked DB and auth."""
    fake_profile = _make_fake_profile()
    fake_character = _make_fake_character()

    async def override_user() -> MagicMock:
        return fake_profile

    async def override_db() -> AsyncGenerator[AsyncMock, None]:
        mock_db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = fake_character
        mock_db.execute.return_value = result_mock
        yield mock_db

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
# POST /api/v1/tts tests
# ---------------------------------------------------------------------------


class TestTTSEndpoint:
    """Tests for POST /api/v1/tts."""

    @pytest.mark.asyncio
    async def test_valid_request_returns_200(self, client: AsyncClient) -> None:
        """Valid TTS request returns 200 with audio_url."""
        with patch("app.services.tts_service._s3_client") as mock_s3:
            # S3 cache hit
            mock_s3.head_object.return_value = {}

            resp = await client.post(
                "/api/v1/tts",
                json={
                    "text": "Hello, how are you?",
                    "character_id": str(FAKE_CHARACTER_ID),
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "audio_url" in data
        assert data["audio_url"].endswith(".mp3")

    @pytest.mark.asyncio
    async def test_synthesizes_with_polly_for_short_text(self, client: AsyncClient) -> None:
        """Short text synthesized via Polly."""
        audio_stream_mock = MagicMock()
        audio_stream_mock.read.return_value = FAKE_AUDIO_DATA
        polly_response = {"AudioStream": audio_stream_mock}

        with (
            patch("app.services.tts_service._s3_client") as mock_s3,
            patch("app.services.tts_service._polly_client") as mock_polly,
        ):
            mock_s3.head_object.side_effect = ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )
            mock_s3.put_object.return_value = {}
            mock_polly.synthesize_speech.return_value = polly_response

            resp = await client.post(
                "/api/v1/tts",
                json={
                    "text": "Hello!",
                    "character_id": str(FAKE_CHARACTER_ID),
                },
            )

        assert resp.status_code == 200
        assert resp.json()["audio_url"].endswith(".mp3")

    @pytest.mark.asyncio
    async def test_without_auth_returns_401_or_403(self, unauthed_client: AsyncClient) -> None:
        """Request without auth header returns 401 or 403."""
        resp = await unauthed_client.post(
            "/api/v1/tts",
            json={
                "text": "Hello",
                "character_id": str(FAKE_CHARACTER_ID),
            },
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_empty_text_returns_422(self, client: AsyncClient) -> None:
        """Empty text returns 422."""
        resp = await client.post(
            "/api/v1/tts",
            json={
                "text": "",
                "character_id": str(FAKE_CHARACTER_ID),
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_text_returns_422(self, client: AsyncClient) -> None:
        """Missing text returns 422."""
        resp = await client.post(
            "/api/v1/tts",
            json={
                "character_id": str(FAKE_CHARACTER_ID),
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_character_id_returns_422(self, client: AsyncClient) -> None:
        """Missing character_id returns 422."""
        resp = await client.post(
            "/api/v1/tts",
            json={
                "text": "Hello",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_whitespace_only_text_returns_422(self, client: AsyncClient) -> None:
        """Whitespace-only text returns 422."""
        resp = await client.post(
            "/api/v1/tts",
            json={
                "text": "   ",
                "character_id": str(FAKE_CHARACTER_ID),
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_custom_language_accepted(self, client: AsyncClient) -> None:
        """Custom language code is accepted."""
        audio_stream_mock = MagicMock()
        audio_stream_mock.read.return_value = FAKE_AUDIO_DATA
        polly_response = {"AudioStream": audio_stream_mock}

        with (
            patch("app.services.tts_service._s3_client") as mock_s3,
            patch("app.services.tts_service._polly_client") as mock_polly,
        ):
            mock_s3.head_object.side_effect = ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )
            mock_s3.put_object.return_value = {}
            mock_polly.synthesize_speech.return_value = polly_response

            resp = await client.post(
                "/api/v1/tts",
                json={
                    "text": "Merhaba!",
                    "character_id": str(FAKE_CHARACTER_ID),
                    "language": "tr",
                },
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_response_shape(self, client: AsyncClient) -> None:
        """Response has correct shape: audio_url and duration_seconds."""
        with patch("app.services.tts_service._s3_client") as mock_s3:
            mock_s3.head_object.return_value = {}

            resp = await client.post(
                "/api/v1/tts",
                json={
                    "text": "Hello!",
                    "character_id": str(FAKE_CHARACTER_ID),
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "audio_url" in data
        assert "duration_seconds" in data
