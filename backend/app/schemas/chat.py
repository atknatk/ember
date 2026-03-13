"""Pydantic request/response schemas for chat streaming endpoints.

Covers sending messages (SSE streaming), message history pagination,
and SSE event serialization models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class SendMessageRequest(BaseModel):
    """Request body for POST /api/v1/characters/:id/messages."""

    content: str = Field(..., min_length=1, max_length=4000)
    media_url: str | None = Field(default=None, max_length=2048)

    @field_validator("content")
    @classmethod
    def strip_content(cls, v: str) -> str:
        """Remove leading/trailing whitespace; reject if empty after trim."""
        stripped = v.strip()
        if not stripped:
            msg = "Message content must not be empty after trimming whitespace"
            raise ValueError(msg)
        return stripped

    @field_validator("media_url")
    @classmethod
    def validate_media_url(cls, v: str | None) -> str | None:
        """Validate that media_url is a valid HTTP or HTTPS URL if provided."""
        if v is None:
            return v
        v = v.strip()
        if not v.startswith(("http://", "https://")):
            msg = "media_url must be a valid HTTP or HTTPS URL"
            raise ValueError(msg)
        return v


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class MessageItem(BaseModel):
    """A single message in the paginated message list response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    media_url: str | None
    metadata: dict[str, Any] | None
    created_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id_to_str(cls, v: object) -> str:
        """Convert UUID or other types to string for API output."""
        return str(v)

    @field_validator("metadata", mode="before")
    @classmethod
    def coerce_metadata(cls, v: object) -> dict[str, Any] | None:
        """Handle the ORM column name metadata_ -> metadata."""
        if v is None:
            return None
        if isinstance(v, dict):
            return v  # type: ignore[return-value]
        return None


class MessageListResponse(BaseModel):
    """Response for GET /api/v1/characters/:id/messages."""

    items: list[MessageItem]
    next_cursor: str | None
    has_more: bool


# ---------------------------------------------------------------------------
# SSE event models (used for serialization, NOT as response_model)
# ---------------------------------------------------------------------------


class ChunkEvent(BaseModel):
    """SSE chunk event — a text fragment of the streaming AI response."""

    type: str = "chunk"
    content: str


class ActionEvent(BaseModel):
    """SSE action event — a device action intent detected in the response."""

    type: str = "action"
    action: str
    payload: dict[str, Any]


class DoneEvent(BaseModel):
    """SSE done event — signals the stream is complete."""

    type: str = "done"
    message_id: str


class ErrorEvent(BaseModel):
    """SSE error event — signals an error occurred mid-stream."""

    type: str = "error"
    message: str


class ModerationSSEEvent(BaseModel):
    """SSE moderation event — signals crisis augmentation was applied (therapist only)."""

    type: str = "moderation"
    message: str
