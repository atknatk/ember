"""Pydantic request/response schemas for TTS (text-to-speech) endpoints.

Covers the POST /api/v1/tts endpoint for converting text to audio.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class TTSRequest(BaseModel):
    """Request body for POST /api/v1/tts."""

    text: str = Field(..., min_length=1, max_length=5000)
    character_id: str = Field(..., min_length=1)
    voice_id: str | None = Field(default=None, max_length=100)
    language: str = Field(default="en", max_length=10)

    @field_validator("text")
    @classmethod
    def strip_text(cls, v: str) -> str:
        """Strip whitespace and reject empty text."""
        stripped = v.strip()
        if not stripped:
            msg = "Text must not be empty after trimming whitespace"
            raise ValueError(msg)
        return stripped

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        """Validate language code."""
        stripped = v.strip().lower()
        if not stripped:
            msg = "Language code must not be empty"
            raise ValueError(msg)
        return stripped


class TTSResponse(BaseModel):
    """Response for POST /api/v1/tts."""

    audio_url: str
    duration_seconds: float | None = None
