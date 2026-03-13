"""Service-level unit tests for TTSService.

Tests ElevenLabs/Polly synthesis, S3 caching, circuit breaker,
and character ownership validation. All external services are mocked.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import uuid  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402
from fastapi import HTTPException  # noqa: E402

import app.services.tts_service as tts_module  # noqa: E402
from app.services.tts_service import (  # noqa: E402
    TTSService,
    _compute_audio_hash,
    get_elevenlabs_circuit_breaker,
)

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
FAKE_CHARACTER_ID = uuid.UUID("660e8400-e29b-41d4-a716-446655440001")
FAKE_AUDIO_DATA = b"\xff\xfb\x90\x00" * 100  # Fake MP3 bytes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_character(
    char_id: uuid.UUID = FAKE_CHARACTER_ID,
    user_id: uuid.UUID = FAKE_USER_ID,
    template: str = "companion",
) -> MagicMock:
    """Create a fake Character ORM object."""
    char = MagicMock()
    char.id = char_id
    char.user_id = user_id
    char.template = template
    char.name = "Luna"
    char.mem0_agent_id = f"{template}_{user_id}"
    char.is_active = True
    return char


def _mock_db_with_character(character: MagicMock | None = None) -> AsyncMock:
    """Create a mock db session that returns a character on execute."""
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = character
    db.execute.return_value = result_mock
    return db


# ---------------------------------------------------------------------------
# Audio Hash Tests
# ---------------------------------------------------------------------------


class TestComputeAudioHash:
    """Tests for the _compute_audio_hash helper."""

    def test_same_inputs_produce_same_hash(self) -> None:
        """Identical inputs produce the same hash."""
        h1 = _compute_audio_hash("hello", "voice-1", "en")
        h2 = _compute_audio_hash("hello", "voice-1", "en")
        assert h1 == h2

    def test_different_text_produces_different_hash(self) -> None:
        """Different text produces a different hash."""
        h1 = _compute_audio_hash("hello", "voice-1", "en")
        h2 = _compute_audio_hash("goodbye", "voice-1", "en")
        assert h1 != h2

    def test_different_voice_produces_different_hash(self) -> None:
        """Different voice_id produces a different hash."""
        h1 = _compute_audio_hash("hello", "voice-1", "en")
        h2 = _compute_audio_hash("hello", "voice-2", "en")
        assert h1 != h2

    def test_different_language_produces_different_hash(self) -> None:
        """Different language produces a different hash."""
        h1 = _compute_audio_hash("hello", "voice-1", "en")
        h2 = _compute_audio_hash("hello", "voice-1", "tr")
        assert h1 != h2

    def test_hash_length_is_32(self) -> None:
        """Hash is truncated to 32 characters."""
        h = _compute_audio_hash("text", "voice", "en")
        assert len(h) == 32


# ---------------------------------------------------------------------------
# Circuit Breaker Tests
# ---------------------------------------------------------------------------


class TestElevenLabsCircuitBreaker:
    """Tests for the ElevenLabs circuit breaker."""

    @pytest.fixture(autouse=True)
    def _reset_breaker(self) -> None:
        """Reset the circuit breaker singleton before each test."""
        tts_module._elevenlabs_breaker = None

    def test_initially_closed(self) -> None:
        """Circuit starts in CLOSED state."""
        breaker = get_elevenlabs_circuit_breaker()
        assert breaker.is_available()
        assert breaker.state.value == "closed"

    def test_opens_after_threshold_failures(self) -> None:
        """Circuit opens after reaching failure threshold."""
        breaker = get_elevenlabs_circuit_breaker()
        for _ in range(breaker.failure_threshold):
            breaker.record_failure()
        assert not breaker.is_available()
        assert breaker.state.value == "open"

    def test_success_resets_failure_count(self) -> None:
        """A success resets the failure counter."""
        breaker = get_elevenlabs_circuit_breaker()
        breaker.record_failure()
        breaker.record_failure()
        breaker.record_success()
        assert breaker.failure_count == 0

    def test_get_status_returns_dict(self) -> None:
        """get_status returns state and failure_count."""
        breaker = get_elevenlabs_circuit_breaker()
        status = breaker.get_status()
        assert "state" in status
        assert "failure_count" in status


# ---------------------------------------------------------------------------
# TTSService Tests
# ---------------------------------------------------------------------------


class TestTTSServiceCharacterValidation:
    """Tests for character ownership validation."""

    @pytest.mark.asyncio
    async def test_invalid_character_id_raises_404(self) -> None:
        """Invalid UUID for character_id raises 404."""
        db = AsyncMock()
        service = TTSService(db)

        with pytest.raises(HTTPException) as exc_info:
            await service.synthesize(
                user_id=FAKE_USER_ID,
                character_id="not-a-uuid",
                text="Hello",
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_character_not_found_raises_404(self) -> None:
        """Character not in DB raises 404."""
        db = _mock_db_with_character(None)
        service = TTSService(db)

        with pytest.raises(HTTPException) as exc_info:
            await service.synthesize(
                user_id=FAKE_USER_ID,
                character_id=str(FAKE_CHARACTER_ID),
                text="Hello",
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_character_wrong_owner_raises_403(self) -> None:
        """Character belonging to another user raises 403."""
        other_user = uuid.UUID("770e8400-e29b-41d4-a716-446655440002")
        character = _make_fake_character(user_id=other_user)
        db = _mock_db_with_character(character)
        service = TTSService(db)

        with pytest.raises(HTTPException) as exc_info:
            await service.synthesize(
                user_id=FAKE_USER_ID,
                character_id=str(FAKE_CHARACTER_ID),
                text="Hello",
            )
        assert exc_info.value.status_code == 403


class TestTTSServiceSynthesis:
    """Tests for the main synthesize method."""

    @pytest.fixture(autouse=True)
    def _reset_breaker(self) -> None:
        """Reset the circuit breaker singleton before each test."""
        tts_module._elevenlabs_breaker = None

    @pytest.mark.asyncio
    async def test_returns_cached_audio_url(self) -> None:
        """Returns cached URL when audio exists in S3."""
        character = _make_fake_character()
        db = _mock_db_with_character(character)
        service = TTSService(db)

        with patch("app.services.tts_service._s3_client") as mock_s3:
            # head_object succeeds = cache hit
            mock_s3.head_object.return_value = {}

            result = await service.synthesize(
                user_id=FAKE_USER_ID,
                character_id=str(FAKE_CHARACTER_ID),
                text="Hello",
            )

        assert "tts/" in result.audio_url
        assert str(FAKE_USER_ID) in result.audio_url
        assert result.audio_url.endswith(".mp3")

    @pytest.mark.asyncio
    async def test_short_text_uses_polly(self) -> None:
        """Short text (< 150 chars) routes directly to Polly."""
        character = _make_fake_character()
        db = _mock_db_with_character(character)
        service = TTSService(db)

        # Polly response mock
        audio_stream_mock = MagicMock()
        audio_stream_mock.read.return_value = FAKE_AUDIO_DATA
        polly_response = {"AudioStream": audio_stream_mock}

        with (
            patch("app.services.tts_service._s3_client") as mock_s3,
            patch("app.services.tts_service._polly_client") as mock_polly,
        ):
            # S3 cache miss
            mock_s3.head_object.side_effect = ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )
            mock_s3.put_object.return_value = {}
            mock_polly.synthesize_speech.return_value = polly_response

            result = await service.synthesize(
                user_id=FAKE_USER_ID,
                character_id=str(FAKE_CHARACTER_ID),
                text="Short text",  # < 150 chars
            )

        assert result.audio_url.endswith(".mp3")
        mock_polly.synthesize_speech.assert_called_once()

    @pytest.mark.asyncio
    async def test_long_text_uses_elevenlabs(self) -> None:
        """Long text (>= 150 chars) routes to ElevenLabs."""
        character = _make_fake_character()
        db = _mock_db_with_character(character)
        service = TTSService(db)

        long_text = "a" * 200

        with (
            patch("app.services.tts_service._s3_client") as mock_s3,
            patch("app.services.tts_service.settings") as mock_settings,
            patch("app.services.tts_service.httpx.AsyncClient") as mock_http_cls,
        ):
            mock_settings.elevenlabs_api_key = "test-key"
            mock_settings.s3_bucket_name = "test-bucket"
            mock_settings.aws_region = "us-east-1"

            # S3 cache miss
            mock_s3.head_object.side_effect = ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )
            mock_s3.put_object.return_value = {}

            # Mock httpx response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = FAKE_AUDIO_DATA

            mock_client_instance = AsyncMock()
            mock_client_instance.post.return_value = mock_response
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_http_cls.return_value = mock_client_instance

            result = await service.synthesize(
                user_id=FAKE_USER_ID,
                character_id=str(FAKE_CHARACTER_ID),
                text=long_text,
            )

        assert result.audio_url.endswith(".mp3")
        mock_client_instance.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_elevenlabs_failure_falls_back_to_polly(self) -> None:
        """When ElevenLabs fails, Polly is used as fallback."""
        character = _make_fake_character()
        db = _mock_db_with_character(character)
        service = TTSService(db)

        long_text = "a" * 200
        audio_stream_mock = MagicMock()
        audio_stream_mock.read.return_value = FAKE_AUDIO_DATA
        polly_response = {"AudioStream": audio_stream_mock}

        with (
            patch("app.services.tts_service._s3_client") as mock_s3,
            patch("app.services.tts_service._polly_client") as mock_polly,
            patch("app.services.tts_service.settings") as mock_settings,
            patch("app.services.tts_service.httpx.AsyncClient") as mock_http_cls,
        ):
            mock_settings.elevenlabs_api_key = "test-key"
            mock_settings.s3_bucket_name = "test-bucket"
            mock_settings.aws_region = "us-east-1"

            # S3 cache miss
            mock_s3.head_object.side_effect = ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )
            mock_s3.put_object.return_value = {}

            # ElevenLabs fails
            mock_client_instance = AsyncMock()
            mock_client_instance.post.side_effect = Exception("ElevenLabs down")
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            mock_http_cls.return_value = mock_client_instance

            # Polly succeeds
            mock_polly.synthesize_speech.return_value = polly_response

            result = await service.synthesize(
                user_id=FAKE_USER_ID,
                character_id=str(FAKE_CHARACTER_ID),
                text=long_text,
            )

        assert result.audio_url.endswith(".mp3")
        mock_polly.synthesize_speech.assert_called_once()

    @pytest.mark.asyncio
    async def test_both_providers_fail_raises_503(self) -> None:
        """When both ElevenLabs and Polly fail, 503 is raised."""
        character = _make_fake_character()
        db = _mock_db_with_character(character)
        service = TTSService(db)

        with (
            patch("app.services.tts_service._s3_client") as mock_s3,
            patch("app.services.tts_service._polly_client") as mock_polly,
        ):
            # S3 cache miss
            mock_s3.head_object.side_effect = ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )

            # Polly fails too (short text goes straight to Polly)
            mock_polly.synthesize_speech.side_effect = ClientError(
                {"Error": {"Code": "InternalError", "Message": "Polly down"}},
                "SynthesizeSpeech",
            )

            with pytest.raises(HTTPException) as exc_info:
                await service.synthesize(
                    user_id=FAKE_USER_ID,
                    character_id=str(FAKE_CHARACTER_ID),
                    text="Short",
                )
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_s3_upload_failure_raises_503(self) -> None:
        """S3 upload failure raises 503."""
        character = _make_fake_character()
        db = _mock_db_with_character(character)
        service = TTSService(db)

        audio_stream_mock = MagicMock()
        audio_stream_mock.read.return_value = FAKE_AUDIO_DATA
        polly_response = {"AudioStream": audio_stream_mock}

        with (
            patch("app.services.tts_service._s3_client") as mock_s3,
            patch("app.services.tts_service._polly_client") as mock_polly,
        ):
            # S3 cache miss
            mock_s3.head_object.side_effect = ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )
            # S3 upload fails
            mock_s3.put_object.side_effect = ClientError(
                {"Error": {"Code": "InternalError", "Message": "S3 unavailable"}},
                "PutObject",
            )
            mock_polly.synthesize_speech.return_value = polly_response

            with pytest.raises(HTTPException) as exc_info:
                await service.synthesize(
                    user_id=FAKE_USER_ID,
                    character_id=str(FAKE_CHARACTER_ID),
                    text="Short",
                )
            assert exc_info.value.status_code == 503
            assert "Storage" in str(exc_info.value.detail)
