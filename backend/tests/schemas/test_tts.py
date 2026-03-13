"""Schema validation tests for TTS Pydantic models."""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.schemas.tts import TTSRequest, TTSResponse  # noqa: E402


class TestTTSRequest:
    """Tests for TTSRequest schema validation."""

    def test_valid_request(self) -> None:
        """Valid request with all fields."""
        req = TTSRequest(
            text="Hello, how are you?",
            character_id="550e8400-e29b-41d4-a716-446655440000",
        )
        assert req.text == "Hello, how are you?"
        assert req.character_id == "550e8400-e29b-41d4-a716-446655440000"
        assert req.language == "en"
        assert req.voice_id is None

    def test_valid_request_with_all_fields(self) -> None:
        """Valid request with all optional fields."""
        req = TTSRequest(
            text="Merhaba!",
            character_id="some-uuid",
            voice_id="custom-voice",
            language="tr",
        )
        assert req.voice_id == "custom-voice"
        assert req.language == "tr"

    def test_strips_whitespace_from_text(self) -> None:
        """Text is stripped of leading/trailing whitespace."""
        req = TTSRequest(text="  Hello!  ", character_id="uuid")
        assert req.text == "Hello!"

    def test_empty_text_after_strip_raises_error(self) -> None:
        """Text that becomes empty after stripping raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            TTSRequest(text="   ", character_id="uuid")
        assert "empty" in str(exc_info.value).lower()

    def test_empty_text_raises_error(self) -> None:
        """Empty text raises ValidationError."""
        with pytest.raises(ValidationError):
            TTSRequest(text="", character_id="uuid")

    def test_missing_text_raises_error(self) -> None:
        """Missing text raises ValidationError."""
        with pytest.raises(ValidationError):
            TTSRequest(character_id="uuid")  # type: ignore[call-arg]

    def test_missing_character_id_raises_error(self) -> None:
        """Missing character_id raises ValidationError."""
        with pytest.raises(ValidationError):
            TTSRequest(text="Hello")  # type: ignore[call-arg]

    def test_empty_character_id_raises_error(self) -> None:
        """Empty character_id raises ValidationError."""
        with pytest.raises(ValidationError):
            TTSRequest(text="Hello", character_id="")

    def test_text_max_length(self) -> None:
        """Text exceeding 5000 chars raises ValidationError."""
        with pytest.raises(ValidationError):
            TTSRequest(text="a" * 5001, character_id="uuid")

    def test_text_at_max_length_succeeds(self) -> None:
        """Text at exactly 5000 chars is valid."""
        req = TTSRequest(text="a" * 5000, character_id="uuid")
        assert len(req.text) == 5000

    def test_language_normalized_to_lowercase(self) -> None:
        """Language code is lowercased."""
        req = TTSRequest(text="Hello", character_id="uuid", language="TR")
        assert req.language == "tr"

    def test_empty_language_raises_error(self) -> None:
        """Empty language after strip raises ValidationError."""
        with pytest.raises(ValidationError):
            TTSRequest(text="Hello", character_id="uuid", language="   ")


class TestTTSResponse:
    """Tests for TTSResponse schema."""

    def test_valid_response(self) -> None:
        """Valid response with audio_url and duration."""
        resp = TTSResponse(audio_url="https://s3.example.com/audio.mp3", duration_seconds=4.2)
        assert resp.audio_url == "https://s3.example.com/audio.mp3"
        assert resp.duration_seconds == 4.2

    def test_response_without_duration(self) -> None:
        """Response without duration is valid (duration is optional)."""
        resp = TTSResponse(audio_url="https://s3.example.com/audio.mp3")
        assert resp.duration_seconds is None

    def test_response_missing_audio_url_raises_error(self) -> None:
        """Missing audio_url raises ValidationError."""
        with pytest.raises(ValidationError):
            TTSResponse()  # type: ignore[call-arg]
