"""Service-level unit tests for STTService.

Tests S3 download, format validation, size validation, Whisper API calls,
and error handling. All external services are mocked.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.services.stt_service import (  # noqa: E402
    STTService,
    _compute_average_confidence,
)

FAKE_AUDIO_DATA = b"\xff\xfb\x90\x00" * 100  # Fake audio bytes
SMALL_AUDIO_URL = "https://test-bucket.s3.us-east-1.amazonaws.com/audio/user123/recording.mp3"
M4A_AUDIO_URL = "https://test-bucket.s3.us-east-1.amazonaws.com/audio/user123/recording.m4a"
WAV_AUDIO_URL = "https://test-bucket.s3.us-east-1.amazonaws.com/audio/user123/recording.wav"
OGG_AUDIO_URL = "https://test-bucket.s3.us-east-1.amazonaws.com/audio/user123/recording.ogg"


# ---------------------------------------------------------------------------
# S3 URL Parsing Tests
# ---------------------------------------------------------------------------


class TestParseS3URL:
    """Tests for _parse_s3_url."""

    def test_virtual_hosted_style(self) -> None:
        """Parse virtual-hosted style S3 URL."""
        service = STTService()
        bucket, key = service._parse_s3_url(
            "https://my-bucket.s3.us-east-1.amazonaws.com/audio/file.mp3",
        )
        assert bucket == "my-bucket"
        assert key == "audio/file.mp3"

    def test_path_style(self) -> None:
        """Parse path-style S3 URL."""
        service = STTService()
        bucket, key = service._parse_s3_url(
            "https://s3.us-east-1.amazonaws.com/my-bucket/audio/file.mp3",
        )
        assert bucket == "my-bucket"
        assert key == "audio/file.mp3"

    def test_invalid_non_s3_url_raises_400(self) -> None:
        """Non-S3 URL raises 400."""
        service = STTService()
        with pytest.raises(HTTPException) as exc_info:
            service._parse_s3_url("https://example.com/audio/file.mp3")
        assert exc_info.value.status_code == 400

    def test_path_style_missing_key_raises_400(self) -> None:
        """Path-style URL without key raises 400."""
        service = STTService()
        with pytest.raises(HTTPException) as exc_info:
            service._parse_s3_url("https://s3.us-east-1.amazonaws.com/bucket-only")
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Extension Validation Tests
# ---------------------------------------------------------------------------


class TestGetExtension:
    """Tests for _get_extension."""

    def test_mp3(self) -> None:
        """Extract .mp3 extension."""
        assert STTService._get_extension("audio/file.mp3") == ".mp3"

    def test_m4a(self) -> None:
        """Extract .m4a extension."""
        assert STTService._get_extension("audio/file.m4a") == ".m4a"

    def test_wav(self) -> None:
        """Extract .wav extension."""
        assert STTService._get_extension("audio/file.wav") == ".wav"

    def test_ogg(self) -> None:
        """Extract .ogg extension."""
        assert STTService._get_extension("audio/file.ogg") == ".ogg"

    def test_uppercase_normalized(self) -> None:
        """Extension is lowercased."""
        assert STTService._get_extension("audio/file.MP3") == ".mp3"

    def test_no_extension(self) -> None:
        """Returns empty string for no extension."""
        assert STTService._get_extension("audio/noext") == ""

    def test_query_params_stripped(self) -> None:
        """Query parameters are ignored."""
        assert STTService._get_extension("audio/file.mp3?token=abc") == ".mp3"


# ---------------------------------------------------------------------------
# Confidence Computation Tests
# ---------------------------------------------------------------------------


class TestComputeAverageConfidence:
    """Tests for _compute_average_confidence."""

    def test_no_segments_returns_zero(self) -> None:
        """Returns 0.0 when no segments."""
        mock_transcription = MagicMock()
        mock_transcription.segments = None
        assert _compute_average_confidence(mock_transcription) == 0.0

    def test_empty_segments_returns_zero(self) -> None:
        """Returns 0.0 for empty segment list."""
        mock_transcription = MagicMock()
        mock_transcription.segments = []
        assert _compute_average_confidence(mock_transcription) == 0.0

    def test_single_segment(self) -> None:
        """Computes confidence from a single segment."""
        import math

        segment = MagicMock()
        segment.avg_logprob = -0.1  # exp(-0.1) ~ 0.9048
        mock_transcription = MagicMock()
        mock_transcription.segments = [segment]

        confidence = _compute_average_confidence(mock_transcription)
        expected = round(math.exp(-0.1), 4)
        assert confidence == expected

    def test_multiple_segments_averaged(self) -> None:
        """Averages confidence across multiple segments."""
        import math

        seg1 = MagicMock()
        seg1.avg_logprob = -0.1
        seg2 = MagicMock()
        seg2.avg_logprob = -0.2
        mock_transcription = MagicMock()
        mock_transcription.segments = [seg1, seg2]

        confidence = _compute_average_confidence(mock_transcription)
        expected = round((math.exp(-0.1) + math.exp(-0.2)) / 2, 4)
        assert confidence == expected

    def test_confidence_clamped_to_1(self) -> None:
        """Confidence is clamped to max 1.0."""
        segment = MagicMock()
        segment.avg_logprob = 1.0  # exp(1) > 1, should be clamped
        mock_transcription = MagicMock()
        mock_transcription.segments = [segment]

        confidence = _compute_average_confidence(mock_transcription)
        assert confidence <= 1.0


# ---------------------------------------------------------------------------
# STTService.transcribe Tests
# ---------------------------------------------------------------------------


class TestSTTServiceTranscribe:
    """Tests for STTService.transcribe."""

    @pytest.mark.asyncio
    async def test_successful_transcription(self) -> None:
        """Successful transcription returns transcript, language, confidence."""
        service = STTService()

        # Mock S3 download
        body_mock = MagicMock()
        body_mock.read.return_value = FAKE_AUDIO_DATA
        s3_response = {"Body": body_mock}

        # Mock Whisper response
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

            result = await service.transcribe(SMALL_AUDIO_URL)

        assert result["transcript"] == "Hello world"
        assert result["language"] == "en"
        assert result["duration_seconds"] == 3.5
        assert isinstance(result["confidence"], float)

    @pytest.mark.asyncio
    async def test_unsupported_format_raises_400(self) -> None:
        """Unsupported audio format raises 400."""
        service = STTService()
        url = "https://test-bucket.s3.us-east-1.amazonaws.com/audio/file.txt"

        with pytest.raises(HTTPException) as exc_info:
            await service.transcribe(url)
        assert exc_info.value.status_code == 400
        assert "Unsupported" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_file_too_large_raises_413(self) -> None:
        """File exceeding 25MB raises 413."""
        service = STTService()

        # Create data > 25MB
        large_data = b"\x00" * (26 * 1024 * 1024)
        body_mock = MagicMock()
        body_mock.read.return_value = large_data
        s3_response = {"Body": body_mock}

        with patch("app.services.stt_service._s3_client") as mock_s3:
            mock_s3.get_object.return_value = s3_response

            with pytest.raises(HTTPException) as exc_info:
                await service.transcribe(SMALL_AUDIO_URL)
            assert exc_info.value.status_code == 413
            assert "25MB" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_s3_not_found_raises_400(self) -> None:
        """S3 file not found raises 400."""
        service = STTService()

        with patch("app.services.stt_service._s3_client") as mock_s3:
            mock_s3.get_object.side_effect = ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}},
                "GetObject",
            )

            with pytest.raises(HTTPException) as exc_info:
                await service.transcribe(SMALL_AUDIO_URL)
            assert exc_info.value.status_code == 400
            assert "not found" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_s3_server_error_raises_503(self) -> None:
        """S3 internal error raises 503."""
        service = STTService()

        with patch("app.services.stt_service._s3_client") as mock_s3:
            mock_s3.get_object.side_effect = ClientError(
                {"Error": {"Code": "InternalError", "Message": "S3 down"}},
                "GetObject",
            )

            with pytest.raises(HTTPException) as exc_info:
                await service.transcribe(SMALL_AUDIO_URL)
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_whisper_api_failure_raises_503(self) -> None:
        """Whisper API failure raises 503."""
        service = STTService()

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
            mock_client.audio.transcriptions.create.side_effect = Exception("Whisper down")
            mock_openai_cls.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                await service.transcribe(SMALL_AUDIO_URL)
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_no_openai_key_raises_503(self) -> None:
        """Missing OpenAI API key raises 503."""
        service = STTService()

        body_mock = MagicMock()
        body_mock.read.return_value = FAKE_AUDIO_DATA
        s3_response = {"Body": body_mock}

        with (
            patch("app.services.stt_service._s3_client") as mock_s3,
            patch("app.services.stt_service.settings") as mock_settings,
        ):
            mock_settings.openai_api_key = ""
            mock_s3.get_object.return_value = s3_response

            with pytest.raises(HTTPException) as exc_info:
                await service.transcribe(SMALL_AUDIO_URL)
            assert exc_info.value.status_code == 503
            assert "not configured" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_m4a_format_accepted(self) -> None:
        """M4A format is accepted and transcribed."""
        service = STTService()

        body_mock = MagicMock()
        body_mock.read.return_value = FAKE_AUDIO_DATA
        s3_response = {"Body": body_mock}

        whisper_response = MagicMock()
        whisper_response.text = "Merhaba"
        whisper_response.language = "tr"
        whisper_response.duration = 2.0
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

            result = await service.transcribe(M4A_AUDIO_URL)

        assert result["transcript"] == "Merhaba"
        assert result["language"] == "tr"
