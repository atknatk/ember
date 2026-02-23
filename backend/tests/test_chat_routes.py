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
        """Returns 200 with messages older than cursor."""
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
                f"/api/v1/characters/{FAKE_CHARACTER_ID}/messages"
                "?cursor=2026-02-23T14:30:00%2B00:00",
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
        items = [
            MessageItem(
                id=str(uuid.uuid4()),
                role="user",
                content=f"msg {i}",
                media_url=None,
                metadata=None,
                created_at=now - timedelta(minutes=i),
            )
            for i in range(5)
        ]
        mock_response = MessageListResponse(
            items=items,
            next_cursor=(now - timedelta(minutes=4)).isoformat(),
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
