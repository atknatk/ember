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

    def test_metadata_non_dict_coerced_to_none(self) -> None:
        """Non-dict, non-None metadata is coerced to None."""
        item = MessageItem(
            id="id1",
            role="user",
            content="Hello",
            media_url=None,
            metadata="invalid_string",  # type: ignore[arg-type]
            created_at=datetime.now(tz=UTC),
        )
        assert item.metadata is None

    def test_metadata_list_coerced_to_none(self) -> None:
        """List metadata is coerced to None (not a dict)."""
        item = MessageItem(
            id="id1",
            role="user",
            content="Hello",
            media_url=None,
            metadata=["item1"],  # type: ignore[arg-type]
            created_at=datetime.now(tz=UTC),
        )
        assert item.metadata is None

    def test_integer_id_coerced_to_string(self) -> None:
        """Integer id is coerced to string."""
        item = MessageItem(
            id=12345,  # type: ignore[arg-type]
            role="user",
            content="Hello",
            media_url=None,
            metadata=None,
            created_at=datetime.now(tz=UTC),
        )
        assert item.id == "12345"

    def test_media_url_preserved(self) -> None:
        """media_url is preserved in the response item."""
        item = MessageItem(
            id="id1",
            role="user",
            content="Hello",
            media_url="https://s3.amazonaws.com/bucket/image.jpg",
            metadata=None,
            created_at=datetime.now(tz=UTC),
        )
        assert item.media_url == "https://s3.amazonaws.com/bucket/image.jpg"


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

    def test_chunk_event_model_dump_json(self) -> None:
        """ChunkEvent serializes to valid JSON string."""
        import json as json_mod

        event = ChunkEvent(content="token")
        raw = event.model_dump_json()
        parsed = json_mod.loads(raw)
        assert parsed["type"] == "chunk"
        assert parsed["content"] == "token"

    def test_action_event_calendar(self) -> None:
        """ActionEvent for ADD_CALENDAR_EVENT serializes correctly."""
        event = ActionEvent(
            action="ADD_CALENDAR_EVENT",
            payload={
                "title": "Dentist",
                "date": "2026-02-24",
                "time": "15:00",
                "duration_minutes": 60,
            },
        )
        data = event.model_dump()
        assert data["action"] == "ADD_CALENDAR_EVENT"
        assert data["payload"]["title"] == "Dentist"
        assert data["payload"]["duration_minutes"] == 60

    def test_done_event_model_dump_json(self) -> None:
        """DoneEvent serializes to valid JSON string."""
        import json as json_mod

        msg_id = str(uuid.uuid4())
        event = DoneEvent(message_id=msg_id)
        raw = event.model_dump_json()
        parsed = json_mod.loads(raw)
        assert parsed["type"] == "done"
        assert parsed["message_id"] == msg_id


# ---------------------------------------------------------------------------
# SendMessageRequest edge cases
# ---------------------------------------------------------------------------


class TestSendMessageRequestEdgeCases:
    """Additional edge case tests for SendMessageRequest."""

    def test_content_at_max_length_accepted(self) -> None:
        """Content exactly at 4000 chars is accepted."""
        req = SendMessageRequest(content="a" * 4000)
        assert len(req.content) == 4000

    def test_content_at_min_length_accepted(self) -> None:
        """Content exactly at 1 char is accepted."""
        req = SendMessageRequest(content="x")
        assert req.content == "x"

    def test_content_with_newlines_accepted(self) -> None:
        """Content containing newlines is accepted."""
        req = SendMessageRequest(content="line1\nline2\nline3")
        assert "line1\nline2\nline3" == req.content

    def test_content_with_unicode_accepted(self) -> None:
        """Content with unicode characters is accepted."""
        req = SendMessageRequest(content="Merhaba, nasilsiniz? Gunaydin!")
        assert req.content == "Merhaba, nasilsiniz? Gunaydin!"

    def test_media_url_at_max_length_accepted(self) -> None:
        """media_url exactly at 2048 chars is accepted."""
        url = "https://example.com/" + "a" * (2048 - len("https://example.com/"))
        req = SendMessageRequest(content="Hello", media_url=url)
        assert len(req.media_url) == 2048  # type: ignore[arg-type]

    def test_media_url_exceeds_max_length_rejected(self) -> None:
        """media_url over 2048 chars raises ValidationError."""
        url = "https://example.com/" + "a" * 2050
        with pytest.raises(ValidationError):
            SendMessageRequest(content="Hello", media_url=url)

    def test_missing_content_rejected(self) -> None:
        """Missing content field raises ValidationError."""
        with pytest.raises(ValidationError):
            SendMessageRequest()  # type: ignore[call-arg]
