"""Pydantic request/response schemas for media upload endpoints.

Covers presigned S3 URL generation for file uploads (photos, audio, TTS).
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class UploadUrlRequest(BaseModel):
    """Request body for POST /api/v1/media/upload-url."""

    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., min_length=1)
    type: Literal["photo", "audio", "tts"]

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Strip whitespace and reject filenames with path traversal."""
        stripped = v.strip()
        if not stripped:
            msg = "Filename must not be empty after trimming whitespace"
            raise ValueError(msg)
        if ".." in stripped:
            msg = "Filename must not contain path traversal sequences (..)"
            raise ValueError(msg)
        if re.search(r"[/\\]", stripped):
            msg = "Filename must not contain path separators (/ or \\)"
            raise ValueError(msg)
        if "\x00" in stripped:
            msg = "Filename must not contain null bytes"
            raise ValueError(msg)
        return stripped


class UploadUrlResponse(BaseModel):
    """Response for POST /api/v1/media/upload-url."""

    upload_url: str
    file_url: str
