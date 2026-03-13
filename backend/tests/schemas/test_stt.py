"""Schema validation tests for STT Pydantic models."""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.schemas.stt import STTRequest, STTResponse  # noqa: E402


class TestSTTRequest:
    """Tests for STTRequest schema validation."""

    def test_valid_m4a_url(self) -> None:
        """Valid M4A URL is accepted."""
        req = STTRequest(
            audio_url="https://bucket.s3.us-east-1.amazonaws.com/audio/recording.m4a",
        )
        assert req.audio_url.endswith(".m4a")

    def test_valid_mp3_url(self) -> None:
        """Valid MP3 URL is accepted."""
        req = STTRequest(
            audio_url="https://bucket.s3.us-east-1.amazonaws.com/audio/recording.mp3",
        )
        assert req.audio_url.endswith(".mp3")

    def test_valid_wav_url(self) -> None:
        """Valid WAV URL is accepted."""
        req = STTRequest(
            audio_url="https://bucket.s3.us-east-1.amazonaws.com/audio/recording.wav",
        )
        assert req.audio_url.endswith(".wav")

    def test_valid_ogg_url(self) -> None:
        """Valid OGG URL is accepted."""
        req = STTRequest(
            audio_url="https://bucket.s3.us-east-1.amazonaws.com/audio/recording.ogg",
        )
        assert req.audio_url.endswith(".ogg")

    def test_url_with_query_params_accepted(self) -> None:
        """URL with query parameters is accepted if extension is valid."""
        req = STTRequest(
            audio_url="https://bucket.s3.us-east-1.amazonaws.com/audio/recording.mp3?X-Amz-Signature=abc",
        )
        assert "recording.mp3" in req.audio_url

    def test_strips_whitespace(self) -> None:
        """Leading/trailing whitespace is stripped."""
        req = STTRequest(
            audio_url="  https://bucket.s3.us-east-1.amazonaws.com/audio/recording.mp3  ",
        )
        assert not req.audio_url.startswith(" ")
        assert not req.audio_url.endswith(" ")

    def test_empty_url_raises_error(self) -> None:
        """Empty audio_url raises ValidationError."""
        with pytest.raises(ValidationError):
            STTRequest(audio_url="")

    def test_whitespace_only_raises_error(self) -> None:
        """Whitespace-only audio_url raises ValidationError."""
        with pytest.raises(ValidationError):
            STTRequest(audio_url="   ")

    def test_missing_audio_url_raises_error(self) -> None:
        """Missing audio_url raises ValidationError."""
        with pytest.raises(ValidationError):
            STTRequest()  # type: ignore[call-arg]

    def test_unsupported_format_raises_error(self) -> None:
        """Unsupported format (e.g., .txt) raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            STTRequest(
                audio_url="https://bucket.s3.us-east-1.amazonaws.com/audio/file.txt",
            )
        assert "unsupported" in str(exc_info.value).lower()

    def test_pdf_format_raises_error(self) -> None:
        """PDF format raises ValidationError."""
        with pytest.raises(ValidationError):
            STTRequest(
                audio_url="https://bucket.s3.us-east-1.amazonaws.com/audio/file.pdf",
            )

    def test_no_extension_raises_error(self) -> None:
        """URL without extension raises ValidationError."""
        with pytest.raises(ValidationError):
            STTRequest(
                audio_url="https://bucket.s3.us-east-1.amazonaws.com/audio/noextension",
            )

    def test_url_max_length(self) -> None:
        """URL exceeding 2048 chars raises ValidationError."""
        long_url = "https://bucket.s3.us-east-1.amazonaws.com/" + "a" * 2010 + ".mp3"
        with pytest.raises(ValidationError):
            STTRequest(audio_url=long_url)

    def test_case_insensitive_extension(self) -> None:
        """Extension matching is case-insensitive."""
        req = STTRequest(
            audio_url="https://bucket.s3.us-east-1.amazonaws.com/audio/recording.MP3",
        )
        assert "recording.MP3" in req.audio_url


class TestSTTResponse:
    """Tests for STTResponse schema."""

    def test_valid_response(self) -> None:
        """Valid response with all fields."""
        resp = STTResponse(
            transcript="Hello world",
            language="en",
            confidence=0.95,
            duration_seconds=3.5,
        )
        assert resp.transcript == "Hello world"
        assert resp.language == "en"
        assert resp.confidence == 0.95
        assert resp.duration_seconds == 3.5

    def test_response_without_duration(self) -> None:
        """Response without duration is valid (optional field)."""
        resp = STTResponse(
            transcript="Hello",
            language="en",
            confidence=0.9,
        )
        assert resp.duration_seconds is None

    def test_missing_transcript_raises_error(self) -> None:
        """Missing transcript raises ValidationError."""
        with pytest.raises(ValidationError):
            STTResponse(language="en", confidence=0.9)  # type: ignore[call-arg]

    def test_missing_language_raises_error(self) -> None:
        """Missing language raises ValidationError."""
        with pytest.raises(ValidationError):
            STTResponse(transcript="Hello", confidence=0.9)  # type: ignore[call-arg]

    def test_missing_confidence_raises_error(self) -> None:
        """Missing confidence raises ValidationError."""
        with pytest.raises(ValidationError):
            STTResponse(transcript="Hello", language="en")  # type: ignore[call-arg]
