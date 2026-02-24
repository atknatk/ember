"""Route-level integration tests for chat streaming endpoints.

Uses the FastAPI test client with mocked ChatService and dependencies
to test HTTP status codes, SSE stream format, and request validation.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import base64  # noqa: E402
import json  # noqa: E402
import uuid  # noqa: E402
from collections.abc import AsyncGenerator  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402
from typing import Any  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.dependencies import get_current_user, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.chat_service import _encode_cursor  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
OTHER_USER_ID = uuid.UUID("770e8400-e29b-41d4-a716-446655440099")
FAKE_CHARACTER_ID = uuid.UUID("660e8400-e29b-41d4-a716-446655440001")
FAKE_CONVERSATION_ID = uuid.UUID("880e8400-e29b-41d4-a716-446655440002")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_profile(user_id: uuid.UUID = FAKE_USER_ID) -> MagicMock:
    """Create a fake Profile-like object for auth dependency override."""
    profile = MagicMock()
    profile.id = user_id
    profile.email = "test@ember.ai"
    profile.name = "Alex"
    profile.mem0_user_id = f"user_{user_id}"
    profile.fcm_token = None
    profile.timezone = "UTC"
    profile.avatar_url = None
    profile.preferred_language = "en"
    profile.onboarding_completed = False
    profile.subscription_tier = "free"
    profile.subscription_expires_at = None
    profile.created_at = datetime.now(tz=UTC)
    profile.updated_at = datetime.now(tz=UTC)
    return profile


def _make_valid_context() -> dict[str, Any]:
    """Create a valid context dict as returned by validate_send_message."""
    mock_char = MagicMock()
    mock_char.id = FAKE_CHARACTER_ID
    mock_char.user_id = FAKE_USER_ID
    mock_char.mem0_agent_id = f"english_teacher_{FAKE_USER_ID}"

    mock_conv = MagicMock()
    mock_conv.id = FAKE_CONVERSATION_ID

    return {
        "character": mock_char,
        "conversation": mock_conv,
        "system_prompt": "You are Sarah.",
        "formatted_messages": [{"role": "user", "content": "Hello"}],
    }


def _parse_sse_events(text: str) -> list[dict[str, Any]]:
    """Parse SSE text into a list of JSON event dicts."""
    events = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


# ---------------------------------------------------------------------------
# Mock streaming generator
# ---------------------------------------------------------------------------


async def _mock_stream_chunks(
    chunks: list[str],
    action: dict[str, Any] | None = None,
) -> AsyncGenerator[str, None]:
    """Create a mock SSE streaming generator."""
    from app.schemas.chat import ActionEvent, ChunkEvent, DoneEvent

    for chunk in chunks:
        event = ChunkEvent(content=chunk)
        yield f"data: {event.model_dump_json()}\n\n"

    if action is not None:
        action_event = ActionEvent(
            action=action["action"],
            payload=action["payload"],
        )
        yield f"data: {action_event.model_dump_json()}\n\n"

    done_event = DoneEvent(message_id=str(uuid.uuid4()))
    yield f"data: {done_event.model_dump_json()}\n\n"


async def _mock_stream_error() -> AsyncGenerator[str, None]:
    """Create a mock SSE streaming generator that emits an error event."""
    from app.schemas.chat import ErrorEvent

    error_event = ErrorEvent(message="AI service temporarily unavailable")
    yield f"data: {error_event.model_dump_json()}\n\n"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client with mocked DB and auth."""
    fake_profile = _make_fake_profile()

    async def override_user() -> MagicMock:
        return fake_profile

    async def override_db() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unauthed_client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client without auth override (for 401/403 tests)."""
    async def override_db() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    app.dependency_overrides[get_db] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /api/v1/characters/:id/messages tests
# ---------------------------------------------------------------------------


class TestSendMessage:
    """Tests for POST /api/v1/characters/:id/messages (SSE streaming)."""

    @pytest.mark.asyncio
    async def test_valid_message_returns_sse_stream(self, client: AsyncClient) -> None:
        """Valid message returns 200 with SSE stream containing chunk and done events."""
        ctx = _make_valid_context()

        with (
            patch(
                "app.services.chat_service.ChatService.validate_send_message",
                return_value=ctx,
            ),
            patch(
                "app.services.chat_service.ChatService.stream_response",
                return_value=_mock_stream_chunks(["Hello", ", ", "world!"]),
            ),
        ):
            resp = await client.post(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
                json={"content": "Hello"},
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        events = _parse_sse_events(resp.text)
        assert len(events) >= 2

        chunk_events = [e for e in events if e["type"] == "chunk"]
        assert len(chunk_events) == 3

        assert events[-1]["type"] == "done"
        assert "message_id" in events[-1]

    @pytest.mark.asyncio
    async def test_message_to_other_users_character_returns_403(
        self,
        client: AsyncClient,
    ) -> None:
        """Message to another user's character returns 403."""
        from fastapi import HTTPException, status

        with patch(
            "app.services.chat_service.ChatService.validate_send_message",
            side_effect=HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Character does not belong to user",
            ),
        ):
            resp = await client.post(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
                json={"content": "Hello"},
            )

        assert resp.status_code == 403
        assert resp.json()["detail"] == "Character does not belong to user"

    @pytest.mark.asyncio
    async def test_message_to_nonexistent_character_returns_404(
        self,
        client: AsyncClient,
    ) -> None:
        """Message to non-existent character returns 404."""
        from fastapi import HTTPException, status

        with patch(
            "app.services.chat_service.ChatService.validate_send_message",
            side_effect=HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Character not found",
            ),
        ):
            resp = await client.post(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
                json={"content": "Hello"},
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Character not found"

    @pytest.mark.asyncio
    async def test_message_to_inactive_character_returns_404(
        self,
        client: AsyncClient,
    ) -> None:
        """Message to inactive character returns 404."""
        from fastapi import HTTPException, status

        with patch(
            "app.services.chat_service.ChatService.validate_send_message",
            side_effect=HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Character not found",
            ),
        ):
            resp = await client.post(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
                json={"content": "Hello"},
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_content_returns_422(self, client: AsyncClient) -> None:
        """Empty content (whitespace only) returns 422."""
        resp = await client.post(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
            json={"content": "   "},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_content_exceeds_max_length_returns_422(
        self,
        client: AsyncClient,
    ) -> None:
        """Content exceeding 4000 chars returns 422."""
        resp = await client.post(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
            json={"content": "a" * 4001},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_auth_returns_401_or_403(
        self,
        unauthed_client: AsyncClient,
    ) -> None:
        """Missing auth header returns 401 or 403."""
        resp = await unauthed_client.post(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
            json={"content": "Hello"},
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_sse_event_order_chunk_then_done(
        self,
        client: AsyncClient,
    ) -> None:
        """SSE stream has chunk events first, then done event last."""
        ctx = _make_valid_context()

        with (
            patch(
                "app.services.chat_service.ChatService.validate_send_message",
                return_value=ctx,
            ),
            patch(
                "app.services.chat_service.ChatService.stream_response",
                return_value=_mock_stream_chunks(["Hi", " there"]),
            ),
        ):
            resp = await client.post(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
                json={"content": "Hello"},
            )

        events = _parse_sse_events(resp.text)
        types = [e["type"] for e in events]

        assert all(t == "chunk" for t in types[:-1])
        assert types[-1] == "done"

    @pytest.mark.asyncio
    async def test_claude_failure_emits_error_event(
        self,
        client: AsyncClient,
    ) -> None:
        """Claude API failure during streaming emits error SSE event."""
        ctx = _make_valid_context()

        with (
            patch(
                "app.services.chat_service.ChatService.validate_send_message",
                return_value=ctx,
            ),
            patch(
                "app.services.chat_service.ChatService.stream_response",
                return_value=_mock_stream_error(),
            ),
        ):
            resp = await client.post(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
                json={"content": "Hello"},
            )

        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        assert any(e["type"] == "error" for e in events)

    @pytest.mark.asyncio
    async def test_intent_detected_emits_action_event(
        self,
        client: AsyncClient,
    ) -> None:
        """When intent is detected, an action event appears before done."""
        ctx = _make_valid_context()
        action = {
            "action": "SET_ALARM",
            "payload": {"time": "2026-02-24T07:00:00", "label": "Wake up"},
        }

        with (
            patch(
                "app.services.chat_service.ChatService.validate_send_message",
                return_value=ctx,
            ),
            patch(
                "app.services.chat_service.ChatService.stream_response",
                return_value=_mock_stream_chunks(
                    ["I'll set an alarm for 7 AM."],
                    action=action,
                ),
            ),
        ):
            resp = await client.post(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
                json={"content": "Set an alarm for 7 AM"},
            )

        events = _parse_sse_events(resp.text)
        types = [e["type"] for e in events]

        assert "action" in types
        assert types[-1] == "done"
        action_idx = types.index("action")
        done_idx = types.index("done")
        assert action_idx < done_idx

    @pytest.mark.asyncio
    async def test_no_intent_no_action_event(self, client: AsyncClient) -> None:
        """When no intent detected, no action event in stream."""
        ctx = _make_valid_context()

        with (
            patch(
                "app.services.chat_service.ChatService.validate_send_message",
                return_value=ctx,
            ),
            patch(
                "app.services.chat_service.ChatService.stream_response",
                return_value=_mock_stream_chunks(["Just a regular response."]),
            ),
        ):
            resp = await client.post(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
                json={"content": "Hello"},
            )

        events = _parse_sse_events(resp.text)
        types = [e["type"] for e in events]
        assert "action" not in types


# ---------------------------------------------------------------------------
# GET /api/v1/characters/:id/messages tests
# ---------------------------------------------------------------------------


class TestGetMessages:
    """Tests for GET /api/v1/characters/:id/messages (paginated)."""

    @pytest.mark.asyncio
    async def test_get_messages_first_page(self, client: AsyncClient) -> None:
        """Returns 200 with messages on first page (no cursor)."""
        from app.schemas.chat import MessageListResponse

        mock_response = MessageListResponse(
            items=[],
            next_cursor=None,
            has_more=False,
        )

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            return_value=mock_response,
        ):
            resp = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "next_cursor" in data
        assert "has_more" in data

    @pytest.mark.asyncio
    async def test_get_messages_with_cursor(self, client: AsyncClient) -> None:
        """Returns 200 with messages older than cursor (base64 composite cursor)."""
        from app.schemas.chat import MessageListResponse

        mock_response = MessageListResponse(
            items=[],
            next_cursor=None,
            has_more=False,
        )

        cursor_ts = datetime(2026, 2, 23, 14, 30, 0, tzinfo=UTC)
        cursor_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440088")
        encoded_cursor = _encode_cursor(cursor_ts, cursor_id)

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            return_value=mock_response,
        ):
            resp = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
                f"?cursor={encoded_cursor}",
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_messages_with_limit(self, client: AsyncClient) -> None:
        """Returns 200 respecting custom limit."""
        from app.schemas.chat import MessageListResponse

        mock_response = MessageListResponse(
            items=[],
            next_cursor=None,
            has_more=False,
        )

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            return_value=mock_response,
        ):
            resp = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages?limit=5",
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_messages_empty_conversation(
        self,
        client: AsyncClient,
    ) -> None:
        """Empty conversation returns 200 with empty items."""
        from app.schemas.chat import MessageListResponse

        mock_response = MessageListResponse(
            items=[],
            next_cursor=None,
            has_more=False,
        )

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            return_value=mock_response,
        ):
            resp = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["next_cursor"] is None
        assert data["has_more"] is False

    @pytest.mark.asyncio
    async def test_get_messages_other_users_character_returns_403(
        self,
        client: AsyncClient,
    ) -> None:
        """Get messages for another user's character returns 403."""
        from fastapi import HTTPException, status

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            side_effect=HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Character does not belong to user",
            ),
        ):
            resp = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
            )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_messages_nonexistent_character_returns_404(
        self,
        client: AsyncClient,
    ) -> None:
        """Get messages for non-existent character returns 404."""
        from fastapi import HTTPException, status

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            side_effect=HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Character not found",
            ),
        ):
            resp = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
            )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_messages_without_auth_returns_401(
        self,
        unauthed_client: AsyncClient,
    ) -> None:
        """Missing auth header returns 401 or 403."""
        resp = await unauthed_client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_get_messages_has_more_true(self, client: AsyncClient) -> None:
        """has_more is true when more messages exist."""
        from app.schemas.chat import MessageItem, MessageListResponse

        now = datetime.now(tz=UTC)
        last_item_id = uuid.uuid4()
        items = [
            MessageItem(
                id=str(uuid.uuid4()),
                role="user",
                content=f"msg {i}",
                media_url=None,
                metadata=None,
                created_at=now - timedelta(minutes=i),
            )
            for i in range(4)
        ]
        items.append(
            MessageItem(
                id=str(last_item_id),
                role="user",
                content="msg 4",
                media_url=None,
                metadata=None,
                created_at=now - timedelta(minutes=4),
            ),
        )
        mock_response = MessageListResponse(
            items=items,
            next_cursor=_encode_cursor(now - timedelta(minutes=4), last_item_id),
            has_more=True,
        )

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            return_value=mock_response,
        ):
            resp = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages?limit=5",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["has_more"] is True
        assert data["next_cursor"] is not None

    @pytest.mark.asyncio
    async def test_get_messages_has_more_false_on_last_page(
        self,
        client: AsyncClient,
    ) -> None:
        """has_more is false when all messages fit in one page."""
        from app.schemas.chat import MessageItem, MessageListResponse

        now = datetime.now(tz=UTC)
        items = [
            MessageItem(
                id=str(uuid.uuid4()),
                role="user",
                content="hello",
                media_url=None,
                metadata=None,
                created_at=now,
            ),
        ]
        mock_response = MessageListResponse(
            items=items,
            next_cursor=None,
            has_more=False,
        )

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            return_value=mock_response,
        ):
            resp = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages?limit=20",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["has_more"] is False
        assert data["next_cursor"] is None


# ---------------------------------------------------------------------------
# Additional POST tests (backend-tester)
# ---------------------------------------------------------------------------


class TestSendMessageAdditional:
    """Additional tests for POST /api/v1/characters/:id/messages."""

    @pytest.mark.asyncio
    async def test_sse_response_headers(self, client: AsyncClient) -> None:
        """SSE response includes Cache-Control and X-Accel-Buffering headers."""
        ctx = _make_valid_context()

        with (
            patch(
                "app.services.chat_service.ChatService.validate_send_message",
                return_value=ctx,
            ),
            patch(
                "app.services.chat_service.ChatService.stream_response",
                return_value=_mock_stream_chunks(["Hi"]),
            ),
        ):
            resp = await client.post(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
                json={"content": "Hello"},
            )

        assert resp.headers.get("cache-control") == "no-cache"
        assert resp.headers.get("x-accel-buffering") == "no"

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_422(self, client: AsyncClient) -> None:
        """Invalid UUID in path parameter returns 422."""
        resp = await client.post(
            "/api/v1/characters/not-a-uuid/messages",
            json={"content": "Hello"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_content_field_returns_422(self, client: AsyncClient) -> None:
        """Missing 'content' field in request body returns 422."""
        resp = await client.post(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
            json={},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_valid_media_url_accepted(self, client: AsyncClient) -> None:
        """Valid media_url is accepted along with content."""
        ctx = _make_valid_context()

        with (
            patch(
                "app.services.chat_service.ChatService.validate_send_message",
                return_value=ctx,
            ),
            patch(
                "app.services.chat_service.ChatService.stream_response",
                return_value=_mock_stream_chunks(["Hello!"]),
            ),
        ):
            resp = await client.post(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
                json={
                    "content": "Look at this image",
                    "media_url": "https://s3.amazonaws.com/bucket/photo.jpg",
                },
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_action_event_payload_structure(self, client: AsyncClient) -> None:
        """Action event has correct action and payload structure."""
        ctx = _make_valid_context()
        action = {
            "action": "ADD_CALENDAR_EVENT",
            "payload": {
                "title": "Dentist",
                "date": "2026-02-24",
                "time": "15:00",
                "duration_minutes": 60,
            },
        }

        with (
            patch(
                "app.services.chat_service.ChatService.validate_send_message",
                return_value=ctx,
            ),
            patch(
                "app.services.chat_service.ChatService.stream_response",
                return_value=_mock_stream_chunks(
                    ["I've added the event."],
                    action=action,
                ),
            ),
        ):
            resp = await client.post(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
                json={"content": "Add a dentist appointment at 3pm"},
            )

        events = _parse_sse_events(resp.text)
        action_events = [e for e in events if e["type"] == "action"]
        assert len(action_events) == 1
        assert action_events[0]["action"] == "ADD_CALENDAR_EVENT"
        assert action_events[0]["payload"]["title"] == "Dentist"
        assert action_events[0]["payload"]["duration_minutes"] == 60

    @pytest.mark.asyncio
    async def test_sse_chunk_content_accumulated(self, client: AsyncClient) -> None:
        """Accumulated chunk content forms the full response text."""
        ctx = _make_valid_context()

        with (
            patch(
                "app.services.chat_service.ChatService.validate_send_message",
                return_value=ctx,
            ),
            patch(
                "app.services.chat_service.ChatService.stream_response",
                return_value=_mock_stream_chunks(["Hello", " ", "world", "!"]),
            ),
        ):
            resp = await client.post(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
                json={"content": "Hi"},
            )

        events = _parse_sse_events(resp.text)
        chunks = [e["content"] for e in events if e["type"] == "chunk"]
        full_text = "".join(chunks)
        assert full_text == "Hello world!"

    @pytest.mark.asyncio
    async def test_error_event_contains_message(self, client: AsyncClient) -> None:
        """Error SSE event contains a user-friendly message."""
        ctx = _make_valid_context()

        with (
            patch(
                "app.services.chat_service.ChatService.validate_send_message",
                return_value=ctx,
            ),
            patch(
                "app.services.chat_service.ChatService.stream_response",
                return_value=_mock_stream_error(),
            ),
        ):
            resp = await client.post(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
                json={"content": "Hello"},
            )

        events = _parse_sse_events(resp.text)
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "message" in error_events[0]
        assert error_events[0]["message"] == "AI service temporarily unavailable"

    @pytest.mark.asyncio
    async def test_error_event_no_done_event(self, client: AsyncClient) -> None:
        """When error event is emitted, no done event follows."""
        ctx = _make_valid_context()

        with (
            patch(
                "app.services.chat_service.ChatService.validate_send_message",
                return_value=ctx,
            ),
            patch(
                "app.services.chat_service.ChatService.stream_response",
                return_value=_mock_stream_error(),
            ),
        ):
            resp = await client.post(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
                json={"content": "Hello"},
            )

        events = _parse_sse_events(resp.text)
        types = [e["type"] for e in events]
        assert "done" not in types


# ---------------------------------------------------------------------------
# Additional GET tests (backend-tester)
# ---------------------------------------------------------------------------


class TestGetMessagesAdditional:
    """Additional tests for GET /api/v1/characters/:id/messages."""

    @pytest.mark.asyncio
    async def test_limit_below_min_returns_422(self, client: AsyncClient) -> None:
        """limit=0 returns 422 (minimum is 1)."""
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages?limit=0",
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_limit_above_max_returns_422(self, client: AsyncClient) -> None:
        """limit=101 returns 422 (maximum is 100)."""
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages?limit=101",
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_messages_invalid_uuid_returns_422(
        self,
        client: AsyncClient,
    ) -> None:
        """Invalid UUID in path parameter returns 422."""
        resp = await client.get("/api/v1/characters/not-a-uuid/messages")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_messages_response_items_structure(
        self,
        client: AsyncClient,
    ) -> None:
        """Each message item in the response has the required fields."""
        from app.schemas.chat import MessageItem, MessageListResponse

        now = datetime.now(tz=UTC)
        msg_id = str(uuid.uuid4())
        items = [
            MessageItem(
                id=msg_id,
                role="user",
                content="Hello",
                media_url=None,
                metadata=None,
                created_at=now,
            ),
        ]
        mock_response = MessageListResponse(
            items=items,
            next_cursor=None,
            has_more=False,
        )

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            return_value=mock_response,
        ):
            resp = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
            )

        assert resp.status_code == 200
        data = resp.json()
        msg = data["items"][0]
        assert "id" in msg
        assert "role" in msg
        assert "content" in msg
        assert "media_url" in msg
        assert "metadata" in msg
        assert "created_at" in msg
        assert msg["id"] == msg_id
        assert msg["role"] == "user"

    @pytest.mark.asyncio
    async def test_get_messages_next_cursor_format(
        self,
        client: AsyncClient,
    ) -> None:
        """next_cursor is a valid base64 JSON string with ts and id when has_more is true."""
        from app.schemas.chat import MessageItem, MessageListResponse

        now = datetime.now(tz=UTC)
        last_id = uuid.uuid4()
        cursor_value = _encode_cursor(now - timedelta(minutes=10), last_id)
        items = [
            MessageItem(
                id=str(uuid.uuid4()),
                role="user",
                content="Hello",
                media_url=None,
                metadata=None,
                created_at=now,
            ),
        ]
        mock_response = MessageListResponse(
            items=items,
            next_cursor=cursor_value,
            has_more=True,
        )

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            return_value=mock_response,
        ):
            resp = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages?limit=1",
            )

        data = resp.json()
        # Verify next_cursor is a valid base64 JSON with ts and id
        raw_cursor = data["next_cursor"]
        padded = raw_cursor + "=" * (-len(raw_cursor) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded))
        assert "ts" in decoded
        assert "id" in decoded
        datetime.fromisoformat(decoded["ts"])
        uuid.UUID(decoded["id"])

    @pytest.mark.asyncio
    async def test_get_messages_conversation_not_found_returns_404(
        self,
        client: AsyncClient,
    ) -> None:
        """Conversation not found returns 404."""
        from fastapi import HTTPException, status

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            side_effect=HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            ),
        ):
            resp = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Conversation not found"

    # --- R1: Invalid cursor (not base64) returns 400 ---

    @pytest.mark.asyncio
    async def test_invalid_cursor_not_base64_returns_400(
        self,
        client: AsyncClient,
    ) -> None:
        """Cursor that is not valid base64 returns 400."""
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
            "?cursor=!!!not-base64!!!",
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid cursor format"

    # --- R2: Invalid cursor (valid base64, invalid JSON) returns 400 ---

    @pytest.mark.asyncio
    async def test_invalid_cursor_base64_not_json_returns_400(
        self,
        client: AsyncClient,
    ) -> None:
        """Cursor with valid base64 but not valid JSON returns 400."""
        encoded = base64.urlsafe_b64encode(b"not json at all").decode()
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
            f"?cursor={encoded}",
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid cursor format"

    # --- R3: Invalid cursor (valid JSON, missing ts) returns 400 ---

    @pytest.mark.asyncio
    async def test_invalid_cursor_missing_ts_returns_400(
        self,
        client: AsyncClient,
    ) -> None:
        """Cursor JSON missing 'ts' field returns 400."""
        payload = json.dumps({"id": str(uuid.uuid4())}).encode()
        encoded = base64.urlsafe_b64encode(payload).decode()
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
            f"?cursor={encoded}",
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid cursor format"

    # --- R4: Invalid cursor (valid JSON, missing id) returns 400 ---

    @pytest.mark.asyncio
    async def test_invalid_cursor_missing_id_returns_400(
        self,
        client: AsyncClient,
    ) -> None:
        """Cursor JSON missing 'id' field returns 400."""
        payload = json.dumps({"ts": "2026-02-23T14:30:00+00:00"}).encode()
        encoded = base64.urlsafe_b64encode(payload).decode()
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
            f"?cursor={encoded}",
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid cursor format"

    # --- R5: Invalid cursor (valid JSON, ts not ISO 8601) returns 400 ---

    @pytest.mark.asyncio
    async def test_invalid_cursor_bad_ts_returns_400(
        self,
        client: AsyncClient,
    ) -> None:
        """Cursor JSON with non-ISO 'ts' field returns 400."""
        payload = json.dumps(
            {"ts": "not-a-timestamp", "id": str(uuid.uuid4())},
        ).encode()
        encoded = base64.urlsafe_b64encode(payload).decode()
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
            f"?cursor={encoded}",
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid cursor format"

    # --- R6: Invalid cursor (valid JSON, id not UUID) returns 400 ---

    @pytest.mark.asyncio
    async def test_invalid_cursor_bad_id_returns_400(
        self,
        client: AsyncClient,
    ) -> None:
        """Cursor JSON with non-UUID 'id' field returns 400."""
        payload = json.dumps(
            {"ts": "2026-02-23T14:30:00+00:00", "id": "not-a-uuid"},
        ).encode()
        encoded = base64.urlsafe_b64encode(payload).decode()
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
            f"?cursor={encoded}",
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid cursor format"

    # --- R7: Valid base64 cursor is accepted ---

    @pytest.mark.asyncio
    async def test_valid_base64_cursor_accepted(
        self,
        client: AsyncClient,
    ) -> None:
        """Valid base64 composite cursor is accepted and returns 200."""
        from app.schemas.chat import MessageListResponse

        mock_response = MessageListResponse(
            items=[],
            next_cursor=None,
            has_more=False,
        )

        cursor_ts = datetime(2026, 2, 23, 14, 30, 0, tzinfo=UTC)
        cursor_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440088")
        encoded_cursor = _encode_cursor(cursor_ts, cursor_id)

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            return_value=mock_response,
        ):
            resp = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
                f"?cursor={encoded_cursor}",
            )

        assert resp.status_code == 200

    # --- R8: next_cursor decodes to JSON with ts and id ---

    @pytest.mark.asyncio
    async def test_next_cursor_decodes_to_ts_and_id(
        self,
        client: AsyncClient,
    ) -> None:
        """next_cursor in response decodes to JSON with valid ts and id fields."""
        from app.schemas.chat import MessageItem, MessageListResponse

        now = datetime.now(tz=UTC)
        last_id = uuid.uuid4()
        items = [
            MessageItem(
                id=str(last_id),
                role="user",
                content="Hello",
                media_url=None,
                metadata=None,
                created_at=now,
            ),
        ]
        mock_response = MessageListResponse(
            items=items,
            next_cursor=_encode_cursor(now, last_id),
            has_more=True,
        )

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            return_value=mock_response,
        ):
            resp = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages?limit=1",
            )

        data = resp.json()
        raw_cursor = data["next_cursor"]
        padded = raw_cursor + "=" * (-len(raw_cursor) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded))
        assert "ts" in decoded
        assert "id" in decoded
        # ts is valid ISO 8601
        datetime.fromisoformat(decoded["ts"])
        # id is valid UUID
        uuid.UUID(decoded["id"])

    # --- R9: Empty cursor string returns 400 ---

    @pytest.mark.asyncio
    async def test_empty_cursor_string_returns_400(
        self,
        client: AsyncClient,
    ) -> None:
        """Empty cursor string returns 400."""
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
            "?cursor=",
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid cursor format"

    # --- Old format cursor (plain ISO timestamp) returns 400 ---

    @pytest.mark.asyncio
    async def test_old_format_cursor_returns_400(
        self,
        client: AsyncClient,
    ) -> None:
        """Plain ISO 8601 timestamp cursor (old format) returns 400."""
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
            "?cursor=2026-02-23T14:30:00%2B00:00",
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid cursor format"


# ---------------------------------------------------------------------------
# Pagination edge-case route tests (backend-tester: P01-07)
# ---------------------------------------------------------------------------


class TestGetMessagesPaginationEdgeCases:
    """Edge-case route tests for cursor-based pagination (P01-07)."""

    # --- Cursor with extra fields still works (forward-compatible) ---

    @pytest.mark.asyncio
    async def test_cursor_with_extra_fields_accepted(
        self,
        client: AsyncClient,
    ) -> None:
        """Cursor JSON with extra fields beyond ts and id is still accepted."""
        from app.schemas.chat import MessageListResponse

        mock_response = MessageListResponse(
            items=[],
            next_cursor=None,
            has_more=False,
        )

        payload = json.dumps({
            "ts": "2026-02-23T14:30:00+00:00",
            "id": str(uuid.uuid4()),
            "extra_field": "should_be_ignored",
        }).encode()
        encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            return_value=mock_response,
        ):
            resp = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
                f"?cursor={encoded}",
            )

        assert resp.status_code == 200

    # --- Cursor with valid base64 but empty JSON object ---

    @pytest.mark.asyncio
    async def test_cursor_empty_json_object_returns_400(
        self,
        client: AsyncClient,
    ) -> None:
        """Cursor with valid base64 encoding of empty JSON object returns 400."""
        payload = json.dumps({}).encode()
        encoded = base64.urlsafe_b64encode(payload).decode()
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
            f"?cursor={encoded}",
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid cursor format"

    # --- Cursor with valid base64 but JSON array instead of object ---

    @pytest.mark.asyncio
    async def test_cursor_json_array_returns_400(
        self,
        client: AsyncClient,
    ) -> None:
        """Cursor with valid base64 encoding of JSON array returns 400."""
        payload = json.dumps(["2026-02-23T14:30:00+00:00", str(uuid.uuid4())]).encode()
        encoded = base64.urlsafe_b64encode(payload).decode()
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
            f"?cursor={encoded}",
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid cursor format"

    # --- Cursor with ts as integer (wrong type) ---

    @pytest.mark.asyncio
    async def test_cursor_ts_as_integer_returns_400(
        self,
        client: AsyncClient,
    ) -> None:
        """Cursor JSON with ts as integer instead of ISO string returns 400."""
        payload = json.dumps({
            "ts": 1234567890,
            "id": str(uuid.uuid4()),
        }).encode()
        encoded = base64.urlsafe_b64encode(payload).decode()
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
            f"?cursor={encoded}",
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid cursor format"

    # --- Cursor with id as integer (wrong type) ---

    @pytest.mark.asyncio
    async def test_cursor_id_as_integer_returns_400(
        self,
        client: AsyncClient,
    ) -> None:
        """Cursor JSON with id as integer instead of UUID string returns 400."""
        payload = json.dumps({
            "ts": "2026-02-23T14:30:00+00:00",
            "id": 12345,
        }).encode()
        encoded = base64.urlsafe_b64encode(payload).decode()
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
            f"?cursor={encoded}",
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid cursor format"

    # --- limit=1 boundary ---

    @pytest.mark.asyncio
    async def test_limit_equals_one_accepted(
        self,
        client: AsyncClient,
    ) -> None:
        """limit=1 is accepted and returns at most 1 item."""
        from app.schemas.chat import MessageItem, MessageListResponse

        now = datetime.now(tz=UTC)
        item = MessageItem(
            id=str(uuid.uuid4()),
            role="user",
            content="Hello",
            media_url=None,
            metadata=None,
            created_at=now,
        )
        mock_response = MessageListResponse(
            items=[item],
            next_cursor=_encode_cursor(now, uuid.uuid4()),
            has_more=True,
        )

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            return_value=mock_response,
        ):
            resp = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages?limit=1",
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1

    # --- limit=100 boundary ---

    @pytest.mark.asyncio
    async def test_limit_equals_100_accepted(
        self,
        client: AsyncClient,
    ) -> None:
        """limit=100 is accepted (maximum allowed)."""
        from app.schemas.chat import MessageListResponse

        mock_response = MessageListResponse(
            items=[],
            next_cursor=None,
            has_more=False,
        )

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            return_value=mock_response,
        ):
            resp = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages?limit=100",
            )

        assert resp.status_code == 200

    # --- Negative limit returns 422 ---

    @pytest.mark.asyncio
    async def test_negative_limit_returns_422(
        self,
        client: AsyncClient,
    ) -> None:
        """Negative limit returns 422."""
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages?limit=-1",
        )
        assert resp.status_code == 422

    # --- Non-integer limit returns 422 ---

    @pytest.mark.asyncio
    async def test_non_integer_limit_returns_422(
        self,
        client: AsyncClient,
    ) -> None:
        """Non-integer limit value returns 422."""
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages?limit=abc",
        )
        assert resp.status_code == 422

    # --- Cursor with null bytes in base64 ---

    @pytest.mark.asyncio
    async def test_cursor_with_null_bytes_returns_400(
        self,
        client: AsyncClient,
    ) -> None:
        """Cursor containing null bytes encoded in base64 returns 400."""
        encoded = base64.urlsafe_b64encode(b"\x00\x00\x00").decode()
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
            f"?cursor={encoded}",
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid cursor format"

    # --- Cursor with extremely long string returns 400 ---

    @pytest.mark.asyncio
    async def test_cursor_very_long_string_returns_400(
        self,
        client: AsyncClient,
    ) -> None:
        """Very long cursor string returns 400 (not a valid cursor)."""
        long_cursor = base64.urlsafe_b64encode(b"x" * 10000).decode()
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
            f"?cursor={long_cursor}",
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid cursor format"

    # --- Multi-page sequential walk via route ---

    @pytest.mark.asyncio
    async def test_multi_page_walk_returns_no_duplicates(
        self,
        client: AsyncClient,
    ) -> None:
        """Sequential page walk using next_cursor returns no duplicate IDs."""
        from app.schemas.chat import MessageItem, MessageListResponse

        now = datetime.now(tz=UTC)
        all_ids = [uuid.uuid4() for _ in range(6)]

        # Page 1: items 0-2, has_more=True
        page1_items = [
            MessageItem(
                id=str(all_ids[i]),
                role="user",
                content=f"msg{i}",
                media_url=None,
                metadata=None,
                created_at=now - timedelta(minutes=i),
            )
            for i in range(3)
        ]
        page1_cursor = _encode_cursor(
            now - timedelta(minutes=2), all_ids[2],
        )
        page1_response = MessageListResponse(
            items=page1_items,
            next_cursor=page1_cursor,
            has_more=True,
        )

        # Page 2: items 3-5, has_more=False
        page2_items = [
            MessageItem(
                id=str(all_ids[i]),
                role="user",
                content=f"msg{i}",
                media_url=None,
                metadata=None,
                created_at=now - timedelta(minutes=i),
            )
            for i in range(3, 6)
        ]
        page2_response = MessageListResponse(
            items=page2_items,
            next_cursor=None,
            has_more=False,
        )

        call_count = 0

        def _mock_get_messages(*args: object, **kwargs: object) -> MessageListResponse:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return page1_response
            return page2_response

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            side_effect=_mock_get_messages,
        ):
            # First page
            resp1 = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages?limit=3",
            )
            data1 = resp1.json()
            assert resp1.status_code == 200
            assert len(data1["items"]) == 3
            assert data1["has_more"] is True
            cursor = data1["next_cursor"]

            # Second page
            resp2 = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
                f"?limit=3&cursor={cursor}",
            )
            data2 = resp2.json()
            assert resp2.status_code == 200
            assert len(data2["items"]) == 3
            assert data2["has_more"] is False

        # No duplicate IDs across pages
        ids1 = {m["id"] for m in data1["items"]}
        ids2 = {m["id"] for m in data2["items"]}
        assert ids1.isdisjoint(ids2)
        assert len(ids1 | ids2) == 6

    # --- next_cursor in response matches last item exactly ---

    @pytest.mark.asyncio
    async def test_next_cursor_matches_last_item_in_response(
        self,
        client: AsyncClient,
    ) -> None:
        """next_cursor ts and id match the last item in the response items array."""
        from app.schemas.chat import MessageItem, MessageListResponse

        now = datetime.now(tz=UTC)
        last_id = uuid.uuid4()
        last_ts = now - timedelta(minutes=5)

        items = [
            MessageItem(
                id=str(uuid.uuid4()),
                role="user",
                content="first",
                media_url=None,
                metadata=None,
                created_at=now,
            ),
            MessageItem(
                id=str(last_id),
                role="assistant",
                content="second",
                media_url=None,
                metadata=None,
                created_at=last_ts,
            ),
        ]
        mock_response = MessageListResponse(
            items=items,
            next_cursor=_encode_cursor(last_ts, last_id),
            has_more=True,
        )

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            return_value=mock_response,
        ):
            resp = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages?limit=2",
            )

        data = resp.json()
        raw_cursor = data["next_cursor"]
        padded = raw_cursor + "=" * (-len(raw_cursor) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded))

        # ts and id must match last item
        last_item = data["items"][-1]
        assert decoded["id"] == last_item["id"]

    # --- Cursor with padding characters is still decodable ---

    @pytest.mark.asyncio
    async def test_cursor_with_base64_padding_accepted(
        self,
        client: AsyncClient,
    ) -> None:
        """Cursor that includes trailing = padding is accepted."""
        from app.schemas.chat import MessageListResponse

        mock_response = MessageListResponse(
            items=[],
            next_cursor=None,
            has_more=False,
        )

        payload = json.dumps({
            "ts": "2026-02-23T14:30:00+00:00",
            "id": str(uuid.uuid4()),
        }).encode()
        # Keep padding (do not strip =)
        encoded_with_padding = base64.urlsafe_b64encode(payload).decode()

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            return_value=mock_response,
        ):
            resp = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
                f"?cursor={encoded_with_padding}",
            )

        assert resp.status_code == 200

    # --- Cursor with whitespace-only base64 decoded content ---

    @pytest.mark.asyncio
    async def test_cursor_whitespace_base64_returns_400(
        self,
        client: AsyncClient,
    ) -> None:
        """Cursor that decodes to whitespace-only bytes returns 400."""
        encoded = base64.urlsafe_b64encode(b"   ").decode()
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
            f"?cursor={encoded}",
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid cursor format"

    # --- Default limit (no limit param) returns 200 ---

    @pytest.mark.asyncio
    async def test_default_limit_returns_200(
        self,
        client: AsyncClient,
    ) -> None:
        """Omitting limit param uses default (20) and returns 200."""
        from app.schemas.chat import MessageListResponse

        mock_response = MessageListResponse(
            items=[],
            next_cursor=None,
            has_more=False,
        )

        with patch(
            "app.services.chat_service.ChatService.get_messages",
            return_value=mock_response,
        ) as mock_get:
            resp = await client.get(
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages",
            )

        assert resp.status_code == 200
        # Verify the service was called with limit=20
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        assert call_kwargs.kwargs.get("limit") == 20 or call_kwargs[1].get("limit") == 20

    # --- Cursor with ts as null ---

    @pytest.mark.asyncio
    async def test_cursor_ts_null_returns_400(
        self,
        client: AsyncClient,
    ) -> None:
        """Cursor JSON with ts=null returns 400."""
        payload = json.dumps({
            "ts": None,
            "id": str(uuid.uuid4()),
        }).encode()
        encoded = base64.urlsafe_b64encode(payload).decode()
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
            f"?cursor={encoded}",
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid cursor format"

    # --- Cursor with id as null ---

    @pytest.mark.asyncio
    async def test_cursor_id_null_returns_400(
        self,
        client: AsyncClient,
    ) -> None:
        """Cursor JSON with id=null returns 400."""
        payload = json.dumps({
            "ts": "2026-02-23T14:30:00+00:00",
            "id": None,
        }).encode()
        encoded = base64.urlsafe_b64encode(payload).decode()
        resp = await client.get(
            f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
            f"?cursor={encoded}",
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid cursor format"
