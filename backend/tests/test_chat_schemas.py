"""Unit tests for chat Pydantic schemas.

Tests request validation (SendMessageRequest), response serialization
(MessageItem, MessageListResponse), and SSE event models.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import uuid  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.schemas.chat import (  # noqa: E402
    ActionEvent,
    ChunkEvent,
    DoneEvent,
    ErrorEvent,
    MessageItem,
    MessageListResponse,
    SendMessageRequest,
)

# ---------------------------------------------------------------------------
# SendMessageRequest tests
# ---------------------------------------------------------------------------


class TestSendMessageRequest:
    """Tests for the SendMessageRequest schema."""

    def test_valid_content(self) -> None:
        """Accept valid content string."""
        req = SendMessageRequest(content="Hello, world!")
        assert req.content == "Hello, world!"
        assert req.media_url is None

    def test_strips_whitespace_from_content(self) -> None:
        """Content is whitespace-trimmed."""
        req = SendMessageRequest(content="  Hello  ")
        assert req.content == "Hello"

    def test_rejects_empty_content_after_strip(self) -> None:
        """Content that becomes empty after stripping raises ValidationError."""
        with pytest.raises(ValidationError):
            SendMessageRequest(content="   ")

    def test_rejects_content_exceeding_max_length(self) -> None:
        """Content exceeding 4000 chars raises ValidationError."""
        with pytest.raises(ValidationError):
            SendMessageRequest(content="a" * 4001)

    def test_accepts_null_media_url(self) -> None:
        """Null media_url is accepted."""
        req = SendMessageRequest(content="Hello", media_url=None)
        assert req.media_url is None

    def test_accepts_valid_https_url(self) -> None:
        """Valid HTTPS media_url is accepted."""
        req = SendMessageRequest(
            content="Hello",
            media_url="https://s3.amazonaws.com/bucket/image.jpg",
        )
        assert req.media_url == "https://s3.amazonaws.com/bucket/image.jpg"

    def test_accepts_valid_http_url(self) -> None:
        """Valid HTTP media_url is accepted."""
        req = SendMessageRequest(
            content="Hello",
            media_url="http://example.com/image.jpg",
        )
        assert req.media_url == "http://example.com/image.jpg"

    def test_rejects_invalid_media_url(self) -> None:
        """media_url without HTTP/HTTPS scheme raises ValidationError."""
        with pytest.raises(ValidationError):
            SendMessageRequest(content="Hello", media_url="ftp://invalid.com/file")

    def test_media_url_strips_whitespace(self) -> None:
        """media_url is whitespace-trimmed."""
        req = SendMessageRequest(
            content="Hello",
            media_url="  https://example.com/image.jpg  ",
        )
        assert req.media_url == "https://example.com/image.jpg"


# ---------------------------------------------------------------------------
# MessageItem tests
# ---------------------------------------------------------------------------


class TestMessageItem:
    """Tests for the MessageItem response schema."""

    def test_coerces_uuid_id_to_string(self) -> None:
        """UUID id is coerced to string."""
        msg_id = uuid.uuid4()
        item = MessageItem(
            id=msg_id,  # type: ignore[arg-type]
            role="user",
            content="Hello",
            media_url=None,
            metadata=None,
            created_at=datetime.now(tz=UTC),
        )
        assert item.id == str(msg_id)

    def test_string_id_passed_through(self) -> None:
        """String id is kept as-is."""
        item = MessageItem(
            id="some-string-id",
            role="assistant",
            content="Hi there",
            media_url=None,
            metadata=None,
            created_at=datetime.now(tz=UTC),
        )
        assert item.id == "some-string-id"

    def test_metadata_dict_accepted(self) -> None:
        """dict metadata is passed through."""
        meta = {"action": "SET_ALARM", "payload": {"time": "07:00"}}
        item = MessageItem(
            id="id1",
            role="assistant",
            content="OK",
            media_url=None,
            metadata=meta,
            created_at=datetime.now(tz=UTC),
        )
        assert item.metadata == meta

    def test_metadata_none_accepted(self) -> None:
        """None metadata is accepted."""
        item = MessageItem(
            id="id1",
            role="user",
            content="Hello",
            media_url=None,
            metadata=None,
            created_at=datetime.now(tz=UTC),
        )
        assert item.metadata is None


# ---------------------------------------------------------------------------
# MessageListResponse tests
# ---------------------------------------------------------------------------


class TestMessageListResponse:
    """Tests for the MessageListResponse schema."""

    def test_includes_pagination_fields(self) -> None:
        """Response includes items, next_cursor, and has_more."""
        resp = MessageListResponse(
            items=[],
            next_cursor=None,
            has_more=False,
        )
        assert resp.items == []
        assert resp.next_cursor is None
        assert resp.has_more is False

    def test_with_items_and_cursor(self) -> None:
        """Response with items and cursor is serialized correctly."""
        item = MessageItem(
            id="id1",
            role="user",
            content="Hello",
            media_url=None,
            metadata=None,
            created_at=datetime.now(tz=UTC),
        )
        resp = MessageListResponse(
            items=[item],
            next_cursor="2026-02-23T14:30:00+00:00",
            has_more=True,
        )
        assert len(resp.items) == 1
        assert resp.next_cursor == "2026-02-23T14:30:00+00:00"
        assert resp.has_more is True


# ---------------------------------------------------------------------------
# SSE Event models tests
# ---------------------------------------------------------------------------


class TestSSEEventModels:
    """Tests for SSE event serialization models."""

    def test_chunk_event(self) -> None:
        """ChunkEvent serializes correctly."""
        event = ChunkEvent(content="Hello")
        data = event.model_dump()
        assert data == {"type": "chunk", "content": "Hello"}

    def test_action_event(self) -> None:
        """ActionEvent serializes correctly."""
        event = ActionEvent(
            action="SET_ALARM",
            payload={"time": "2026-02-24T07:00:00", "label": "Wake up"},
        )
        data = event.model_dump()
        assert data["type"] == "action"
        assert data["action"] == "SET_ALARM"
        assert data["payload"]["time"] == "2026-02-24T07:00:00"

    def test_done_event(self) -> None:
        """DoneEvent serializes correctly."""
        msg_id = str(uuid.uuid4())
        event = DoneEvent(message_id=msg_id)
        data = event.model_dump()
        assert data == {"type": "done", "message_id": msg_id}

    def test_error_event(self) -> None:
        """ErrorEvent serializes correctly."""
        event = ErrorEvent(message="AI service temporarily unavailable")
        data = event.model_dump()
        assert data == {
            "type": "error",
            "message": "AI service temporarily unavailable",
        }
