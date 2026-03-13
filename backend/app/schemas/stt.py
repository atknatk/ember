"""Pydantic request/response schemas for STT (speech-to-text) endpoints.

Covers the POST /api/v1/stt endpoint for transcribing audio to text.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

# Supported audio extensions for Whisper transcription
_SUPPORTED_EXTENSIONS = (".m4a", ".mp3", ".wav", ".ogg")


class STTRequest(BaseModel):
    """Request body for POST /api/v1/stt."""

    audio_url: str = Field(..., min_length=1, max_length=2048)

    @field_validator("audio_url")
    @classmethod
    def validate_audio_url(cls, v: str) -> str:
        """Validate audio URL format and extension."""
        stripped = v.strip()
        if not stripped:
            msg = "audio_url must not be empty after trimming whitespace"
            raise ValueError(msg)

        lower = stripped.lower()
        # Remove query parameters for extension check
        path_part = lower.split("?")[0]
        if not path_part.endswith(_SUPPORTED_EXTENSIONS):
            msg = (
                f"Unsupported audio format. Supported formats: "
                f"{', '.join(ext.lstrip('.').upper() for ext in _SUPPORTED_EXTENSIONS)}"
            )
            raise ValueError(msg)
        return stripped


class STTResponse(BaseModel):
    """Response for POST /api/v1/stt."""

    transcript: str
    language: str
    confidence: float
    duration_seconds: float | None = None
