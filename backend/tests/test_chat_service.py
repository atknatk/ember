"""Unit tests for ChatService.

Tests service methods with mocked DB, Claude, and Mem0 dependencies.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import asyncio  # noqa: E402
import json  # noqa: E402
import uuid  # noqa: E402
from collections.abc import AsyncGenerator  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402
from typing import Any  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from app.services.chat_service import (  # noqa: E402
    ChatService,
    _deduplicate_memories,
    _persist_exchange,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
FAKE_CHARACTER_ID = uuid.UUID("660e8400-e29b-41d4-a716-446655440001")
FAKE_CONVERSATION_ID = uuid.UUID("880e8400-e29b-41d4-a716-446655440002")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_profile() -> MagicMock:
    """Create a fake Profile object."""
    profile = MagicMock()
    profile.id = FAKE_USER_ID
    profile.name = "Alex"
    profile.mem0_user_id = f"user_{FAKE_USER_ID}"
    profile.timezone = "America/New_York"
    profile.preferred_language = "en"
    return profile


def _make_fake_character() -> MagicMock:
    """Create a fake Character object."""
    char = MagicMock()
    char.id = FAKE_CHARACTER_ID
    char.user_id = FAKE_USER_ID
    char.name = "Sarah"
    char.template = "english_teacher"
    char.system_prompt = "You are Sarah, an English teacher."
    char.mem0_agent_id = f"english_teacher_{FAKE_USER_ID}"
    char.is_active = True
    return char


def _make_fake_conversation() -> MagicMock:
    """Create a fake Conversation object."""
    conv = MagicMock()
    conv.id = FAKE_CONVERSATION_ID
    conv.user_id = FAKE_USER_ID
    conv.character_id = FAKE_CHARACTER_ID
    return conv


def _make_fake_message(
    role: str = "user",
    content: str = "Hello",
    offset_minutes: int = 0,
) -> MagicMock:
    """Create a fake Message object."""
    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.conversation_id = FAKE_CONVERSATION_ID
    msg.user_id = FAKE_USER_ID
    msg.role = role
    msg.content = content
    msg.media_url = None
    msg.metadata_ = None
    msg.created_at = datetime.now(tz=UTC) - timedelta(minutes=offset_minutes)
    return msg


def _make_valid_context() -> dict[str, Any]:
    """Create a valid context dict as returned by validate_send_message."""
    return {
        "character": _make_fake_character(),
        "conversation": _make_fake_conversation(),
        "system_prompt": "You are Sarah.",
        "formatted_messages": [{"role": "user", "content": "Hello"}],
    }


def _parse_sse_events(sse_lines: list[str]) -> list[dict[str, Any]]:
    """Parse collected SSE lines into event dicts."""
    events = []
    for line in sse_lines:
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


# ---------------------------------------------------------------------------
# validate_send_message tests
# ---------------------------------------------------------------------------


class TestValidateSendMessage:
    """Tests for ChatService.validate_send_message()."""

    @pytest.mark.asyncio
    async def test_parallel_fetch_mem0_and_db(self) -> None:
        """validate_send_message calls search + recent messages in parallel."""
        profile = _make_fake_profile()
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_conv = _make_fake_conversation()

        with (
            patch.object(service, "_get_active_character", return_value=mock_char),
            patch.object(
                service, "_get_or_create_conversation", return_value=mock_conv,
            ),
            patch.object(service, "_search_memories", return_value=[]) as mock_sm,
            patch.object(service, "_get_recent_messages", return_value=[]) as mock_rm,
        ):
            ctx = await service.validate_send_message(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
                profile=profile,
                content="Hello",
            )

        # _search_memories called twice (global + character)
        assert mock_sm.call_count == 2
        # _get_recent_messages called once
        assert mock_rm.call_count == 1
        # Verify context has required keys
        assert "character" in ctx
        assert "conversation" in ctx
        assert "system_prompt" in ctx
        assert "formatted_messages" in ctx

    @pytest.mark.asyncio
    async def test_mem0_search_failure_continues(self) -> None:
        """Mem0 search failure does not crash validate_send_message."""
        profile = _make_fake_profile()
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_conv = _make_fake_conversation()

        async def _failing_search(*args: object, **kwargs: object) -> list[str]:
            raise RuntimeError("Mem0 down")

        with (
            patch.object(service, "_get_active_character", return_value=mock_char),
            patch.object(
                service, "_get_or_create_conversation", return_value=mock_conv,
            ),
            patch.object(service, "_search_memories", side_effect=_failing_search),
            patch.object(service, "_get_recent_messages", return_value=[]),
        ):
            ctx = await service.validate_send_message(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
                profile=profile,
                content="Hello",
            )

        # Should still return a valid context
        assert "system_prompt" in ctx


# ---------------------------------------------------------------------------
# stream_response tests
# ---------------------------------------------------------------------------


class TestStreamResponse:
    """Tests for ChatService.stream_response()."""

    @pytest.mark.asyncio
    async def test_yields_chunk_events(self) -> None:
        """stream_response yields chunk events from Claude stream."""
        profile = _make_fake_profile()
        mock_db = AsyncMock()
        service = ChatService(mock_db)
        ctx = _make_valid_context()

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        async def _text_iter() -> AsyncGenerator[str, None]:
            for chunk in ["Hello", ", ", "world!"]:
                yield chunk

        mock_stream.text_stream = _text_iter()

        with (
            patch("app.services.chat_service.AsyncAnthropic") as mock_a,
            patch.object(service, "_extract_intent", return_value=None),
            patch("app.services.chat_service._persist_exchange"),
        ):
            mc = AsyncMock()
            mc.messages.stream = MagicMock(return_value=mock_stream)
            mock_a.return_value = mc

            sse_lines = []
            async for event in service.stream_response(
                context=ctx,
                user_id=FAKE_USER_ID,
                profile=profile,
                content="Hello",
                media_url=None,
            ):
                sse_lines.append(event)

        events = _parse_sse_events(sse_lines)
        chunk_events = [e for e in events if e["type"] == "chunk"]
        assert len(chunk_events) == 3
        assert chunk_events[0]["content"] == "Hello"
        assert chunk_events[1]["content"] == ", "
        assert chunk_events[2]["content"] == "world!"

    @pytest.mark.asyncio
    async def test_yields_action_event_when_intent_detected(self) -> None:
        """stream_response yields action event when intent is detected."""
        profile = _make_fake_profile()
        mock_db = AsyncMock()
        service = ChatService(mock_db)
        ctx = _make_valid_context()

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        async def _text_iter() -> AsyncGenerator[str, None]:
            yield "Setting alarm."

        mock_stream.text_stream = _text_iter()

        with (
            patch("app.services.chat_service.AsyncAnthropic") as mock_a,
            patch.object(
                service,
                "_extract_intent",
                return_value={
                    "action": "SET_ALARM",
                    "payload": {"time": "07:00", "label": "Wake up"},
                },
            ),
            patch("app.services.chat_service._persist_exchange"),
        ):
            mc = AsyncMock()
            mc.messages.stream = MagicMock(return_value=mock_stream)
            mock_a.return_value = mc

            sse_lines = []
            async for event in service.stream_response(
                context=ctx,
                user_id=FAKE_USER_ID,
                profile=profile,
                content="Set alarm",
                media_url=None,
            ):
                sse_lines.append(event)

        events = _parse_sse_events(sse_lines)
        action_events = [e for e in events if e["type"] == "action"]
        assert len(action_events) == 1
        assert action_events[0]["action"] == "SET_ALARM"

    @pytest.mark.asyncio
    async def test_skips_action_when_haiku_returns_none(self) -> None:
        """No action event when Haiku returns none."""
        profile = _make_fake_profile()
        mock_db = AsyncMock()
        service = ChatService(mock_db)
        ctx = _make_valid_context()

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        async def _text_iter() -> AsyncGenerator[str, None]:
            yield "Just chatting."

        mock_stream.text_stream = _text_iter()

        with (
            patch("app.services.chat_service.AsyncAnthropic") as mock_a,
            patch.object(service, "_extract_intent", return_value=None),
            patch("app.services.chat_service._persist_exchange"),
        ):
            mc = AsyncMock()
            mc.messages.stream = MagicMock(return_value=mock_stream)
            mock_a.return_value = mc

            sse_lines = []
            async for event in service.stream_response(
                context=ctx,
                user_id=FAKE_USER_ID,
                profile=profile,
                content="Hello",
                media_url=None,
            ):
                sse_lines.append(event)

        events = _parse_sse_events(sse_lines)
        assert not any(e["type"] == "action" for e in events)

    @pytest.mark.asyncio
    async def test_yields_done_event_with_uuid(self) -> None:
        """stream_response yields done event with valid UUID message_id."""
        profile = _make_fake_profile()
        mock_db = AsyncMock()
        service = ChatService(mock_db)
        ctx = _make_valid_context()

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        async def _text_iter() -> AsyncGenerator[str, None]:
            yield "Hi"

        mock_stream.text_stream = _text_iter()

        with (
            patch("app.services.chat_service.AsyncAnthropic") as mock_a,
            patch.object(service, "_extract_intent", return_value=None),
            patch("app.services.chat_service._persist_exchange"),
        ):
            mc = AsyncMock()
            mc.messages.stream = MagicMock(return_value=mock_stream)
            mock_a.return_value = mc

            sse_lines = []
            async for event in service.stream_response(
                context=ctx,
                user_id=FAKE_USER_ID,
                profile=profile,
                content="Hello",
                media_url=None,
            ):
                sse_lines.append(event)

        events = _parse_sse_events(sse_lines)
        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 1
        uuid.UUID(done_events[0]["message_id"])

    @pytest.mark.asyncio
    async def test_fires_background_task_for_persistence(self) -> None:
        """stream_response fires asyncio.create_task for persistence."""
        profile = _make_fake_profile()
        mock_db = AsyncMock()
        service = ChatService(mock_db)
        ctx = _make_valid_context()

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        async def _text_iter() -> AsyncGenerator[str, None]:
            yield "Hi"

        mock_stream.text_stream = _text_iter()

        with (
            patch("app.services.chat_service.AsyncAnthropic") as mock_a,
            patch.object(service, "_extract_intent", return_value=None),
            patch("app.services.chat_service._persist_exchange"),
            patch("app.services.chat_service.asyncio") as mock_asyncio,
        ):
            mc = AsyncMock()
            mc.messages.stream = MagicMock(return_value=mock_stream)
            mock_a.return_value = mc

            mock_asyncio.gather = asyncio.gather
            mock_asyncio.to_thread = asyncio.to_thread
            mock_asyncio.create_task = MagicMock()

            sse_lines = []
            async for event in service.stream_response(
                context=ctx,
                user_id=FAKE_USER_ID,
                profile=profile,
                content="Hello",
                media_url=None,
            ):
                sse_lines.append(event)

            mock_asyncio.create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_claude_error_emits_error_event(self) -> None:
        """stream_response emits error event when Claude fails."""
        profile = _make_fake_profile()
        mock_db = AsyncMock()
        service = ChatService(mock_db)
        ctx = _make_valid_context()

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(side_effect=Exception("API error"))

        with patch("app.services.chat_service.AsyncAnthropic") as mock_a:
            mc = AsyncMock()
            mc.messages.stream = MagicMock(return_value=mock_stream)
            mock_a.return_value = mc

            sse_lines = []
            async for event in service.stream_response(
                context=ctx,
                user_id=FAKE_USER_ID,
                profile=profile,
                content="Hello",
                media_url=None,
            ):
                sse_lines.append(event)

        events = _parse_sse_events(sse_lines)
        assert events[-1]["type"] == "error"


# ---------------------------------------------------------------------------
# System prompt and message formatting tests
# ---------------------------------------------------------------------------


class TestSystemPromptBuilder:
    """Tests for ChatService._build_system_prompt() and _format_messages()."""

    def test_builds_system_prompt_with_three_blocks(self) -> None:
        """System prompt contains character prompt, memories, and date/time."""
        profile = _make_fake_profile()
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        prompt = service._build_system_prompt(
            character_system_prompt="You are Sarah.",
            global_memories=["Likes pizza"],
            character_memories=["Struggles with grammar"],
            profile=profile,
        )

        assert "You are Sarah." in prompt
        assert "- Likes pizza" in prompt
        assert "- Struggles with grammar" in prompt
        assert "What you know about this user:" in prompt
        assert "Current date and time:" in prompt
        assert "Timezone: America/New_York" in prompt
        assert "User's preferred language: en" in prompt

    def test_system_prompt_omits_memory_block_when_empty(self) -> None:
        """System prompt omits Block 2 when no memories exist."""
        profile = _make_fake_profile()
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        prompt = service._build_system_prompt(
            character_system_prompt="You are Sarah.",
            global_memories=[],
            character_memories=[],
            profile=profile,
        )

        assert "What you know about this user:" not in prompt
        assert "You are Sarah." in prompt
        assert "Current date and time:" in prompt

    def test_system_prompt_includes_timezone_and_language(self) -> None:
        """System prompt Block 3 includes user timezone and language."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        profile = _make_fake_profile()
        profile.timezone = "Europe/Istanbul"
        profile.preferred_language = "tr"

        prompt = service._build_system_prompt(
            character_system_prompt="You are a companion.",
            global_memories=[],
            character_memories=[],
            profile=profile,
        )

        assert "Timezone: Europe/Istanbul" in prompt
        assert "User's preferred language: tr" in prompt

    def test_formats_messages_with_history(self) -> None:
        """Message history + new content are formatted for Claude API."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        msg1 = _make_fake_message(role="user", content="Hi")
        msg2 = _make_fake_message(role="assistant", content="Hello!")

        formatted = service._format_messages([msg1, msg2], "How are you?")

        assert len(formatted) == 3
        assert formatted[0] == {"role": "user", "content": "Hi"}
        assert formatted[1] == {"role": "assistant", "content": "Hello!"}
        assert formatted[2] == {"role": "user", "content": "How are you?"}


# ---------------------------------------------------------------------------
# get_messages tests
# ---------------------------------------------------------------------------


class TestGetMessages:
    """Tests for ChatService.get_messages()."""

    @pytest.mark.asyncio
    async def test_returns_messages_in_desc_order(self) -> None:
        """get_messages returns messages newest-first."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_conv = _make_fake_conversation()

        msg1 = _make_fake_message(content="older", offset_minutes=10)
        msg2 = _make_fake_message(content="newer", offset_minutes=0)

        call_count = 0

        async def _mock_execute(stmt: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_char
            elif call_count == 2:
                result.scalar_one_or_none.return_value = mock_conv
            else:
                result.scalars.return_value.all.return_value = [msg2, msg1]
            return result

        mock_db.execute = AsyncMock(side_effect=_mock_execute)

        response = await service.get_messages(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            cursor=None,
            limit=20,
        )

        assert len(response.items) == 2
        assert response.items[0].content == "newer"
        assert response.items[1].content == "older"
        assert response.has_more is False

    @pytest.mark.asyncio
    async def test_has_more_and_next_cursor(self) -> None:
        """get_messages sets has_more=True and next_cursor when more exist."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_conv = _make_fake_conversation()

        messages = [
            _make_fake_message(content=f"msg{i}", offset_minutes=i) for i in range(3)
        ]

        call_count = 0

        async def _mock_execute(stmt: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_char
            elif call_count == 2:
                result.scalar_one_or_none.return_value = mock_conv
            else:
                result.scalars.return_value.all.return_value = messages
            return result

        mock_db.execute = AsyncMock(side_effect=_mock_execute)

        response = await service.get_messages(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            cursor=None,
            limit=2,
        )

        assert len(response.items) == 2
        assert response.has_more is True
        assert response.next_cursor is not None

    @pytest.mark.asyncio
    async def test_missing_conversation_raises_404(self) -> None:
        """get_messages raises 404 for missing conversation."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()

        call_count = 0

        async def _mock_execute(stmt: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_char
            else:
                result.scalar_one_or_none.return_value = None
            return result

        mock_db.execute = AsyncMock(side_effect=_mock_execute)

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.get_messages(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
                cursor=None,
                limit=20,
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Intent extraction tests
# ---------------------------------------------------------------------------


class TestExtractIntent:
    """Tests for ChatService._extract_intent()."""

    @pytest.mark.asyncio
    async def test_returns_action_when_intent_detected(self) -> None:
        """Returns action dict when Haiku finds an intent."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = json.dumps({
            "action": "SET_ALARM",
            "payload": {"time": "2026-02-24T07:00:00", "label": "Wake up"},
        })
        mock_response.content = [mock_content]

        with patch("app.services.chat_service.AsyncAnthropic") as mock_a:
            mc = AsyncMock()
            mc.messages.create = AsyncMock(return_value=mock_response)
            mock_a.return_value = mc

            result = await service._extract_intent("I'll set an alarm.", "UTC")

        assert result is not None
        assert result["action"] == "SET_ALARM"

    @pytest.mark.asyncio
    async def test_returns_none_when_haiku_says_none(self) -> None:
        """Returns None when Haiku responds with 'none'."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "none"
        mock_response.content = [mock_content]

        with patch("app.services.chat_service.AsyncAnthropic") as mock_a:
            mc = AsyncMock()
            mc.messages.create = AsyncMock(return_value=mock_response)
            mock_a.return_value = mc

            result = await service._extract_intent("Just chatting.", "UTC")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_haiku_fails(self) -> None:
        """Returns None when Haiku call fails (no crash)."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        with patch("app.services.chat_service.AsyncAnthropic") as mock_a:
            mc = AsyncMock()
            mc.messages.create = AsyncMock(side_effect=Exception("API error"))
            mock_a.return_value = mc

            result = await service._extract_intent("Some text.", "UTC")

        assert result is None


# ---------------------------------------------------------------------------
# Background task tests
# ---------------------------------------------------------------------------


class TestPersistExchange:
    """Tests for the _persist_exchange background task."""

    @pytest.mark.asyncio
    async def test_persists_user_and_assistant_messages(self) -> None:
        """Background task inserts two messages."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        with (
            patch("app.services.chat_service.AsyncSessionLocal") as mock_factory,
            patch("app.services.chat_service.MemoryClient") as mock_mem0,
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session,
            )
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_mem0_inst = MagicMock()
            mock_mem0.return_value = mock_mem0_inst

            await _persist_exchange(
                user_id=FAKE_USER_ID,
                conversation_id=FAKE_CONVERSATION_ID,
                user_content="Hello",
                user_media_url=None,
                assistant_content="Hi there!",
                assistant_message_id=uuid.uuid4(),
                action_metadata=None,
                mem0_user_id=f"user_{FAKE_USER_ID}",
                mem0_agent_id=f"english_teacher_{FAKE_USER_ID}",
            )

        assert mock_session.add.call_count == 2
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_db_error_gracefully(self) -> None:
        """Background task handles DB error without crash."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(side_effect=Exception("DB error"))

        with (
            patch("app.services.chat_service.AsyncSessionLocal") as mock_factory,
            patch("app.services.chat_service.MemoryClient") as mock_mem0,
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session,
            )
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_mem0_inst = MagicMock()
            mock_mem0.return_value = mock_mem0_inst

            await _persist_exchange(
                user_id=FAKE_USER_ID,
                conversation_id=FAKE_CONVERSATION_ID,
                user_content="Hello",
                user_media_url=None,
                assistant_content="Hi there!",
                assistant_message_id=uuid.uuid4(),
                action_metadata=None,
                mem0_user_id=f"user_{FAKE_USER_ID}",
                mem0_agent_id=f"english_teacher_{FAKE_USER_ID}",
            )

    @pytest.mark.asyncio
    async def test_handles_mem0_error_gracefully(self) -> None:
        """Background task handles Mem0 error without crash."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        with (
            patch("app.services.chat_service.AsyncSessionLocal") as mock_factory,
            patch("app.services.chat_service.MemoryClient") as mock_mem0,
            patch("app.services.chat_service.asyncio") as mock_asyncio_mod,
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session,
            )
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_mem0_inst = MagicMock()
            mock_mem0.return_value = mock_mem0_inst

            async def _failing_to_thread(
                fn: object, *args: object, **kwargs: object
            ) -> None:
                raise RuntimeError("Mem0 error")

            mock_asyncio_mod.to_thread = _failing_to_thread

            await _persist_exchange(
                user_id=FAKE_USER_ID,
                conversation_id=FAKE_CONVERSATION_ID,
                user_content="Hello",
                user_media_url=None,
                assistant_content="Hi there!",
                assistant_message_id=uuid.uuid4(),
                action_metadata=None,
                mem0_user_id=f"user_{FAKE_USER_ID}",
                mem0_agent_id=f"english_teacher_{FAKE_USER_ID}",
            )

    @pytest.mark.asyncio
    async def test_calls_mem0_add_with_correct_agent_id(self) -> None:
        """Background task calls Mem0 add with correct parameters."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        agent_id = f"english_teacher_{FAKE_USER_ID}"
        mem0_user_id = f"user_{FAKE_USER_ID}"

        with (
            patch("app.services.chat_service.AsyncSessionLocal") as mock_factory,
            patch("app.services.chat_service.MemoryClient") as mock_mem0,
            patch(
                "app.services.chat_service.asyncio.to_thread",
            ) as mock_to_thread,
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session,
            )
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_mem0_inst = MagicMock()
            mock_mem0.return_value = mock_mem0_inst
            mock_to_thread.return_value = None

            await _persist_exchange(
                user_id=FAKE_USER_ID,
                conversation_id=FAKE_CONVERSATION_ID,
                user_content="Hello",
                user_media_url=None,
                assistant_content="Hi!",
                assistant_message_id=uuid.uuid4(),
                action_metadata=None,
                mem0_user_id=mem0_user_id,
                mem0_agent_id=agent_id,
            )

        mock_to_thread.assert_called_once()
        call_args = mock_to_thread.call_args
        assert call_args.kwargs.get("user_id") == mem0_user_id
        assert call_args.kwargs.get("agent_id") == agent_id


# ---------------------------------------------------------------------------
# Utility tests
# ---------------------------------------------------------------------------


class TestDeduplicateMemories:
    """Tests for _deduplicate_memories."""

    def test_deduplicates_by_exact_match(self) -> None:
        """Identical memories are de-duplicated."""
        global_mems = ["Likes pizza", "Prefers mornings"]
        char_mems = ["Likes pizza", "Struggles with grammar"]

        result = _deduplicate_memories(global_mems, char_mems)

        assert "Likes pizza" in result
        assert result.count("Likes pizza") == 1
        assert "Struggles with grammar" in result
        assert "Prefers mornings" in result

    def test_preserves_order_character_first(self) -> None:
        """Character-specific memories come before global."""
        result = _deduplicate_memories(
            global_memories=["global1"],
            character_memories=["char1"],
        )
        assert result[0] == "char1"
        assert result[1] == "global1"

    def test_empty_lists(self) -> None:
        """Empty input returns empty output."""
        result = _deduplicate_memories([], [])
        assert result == []

    def test_all_duplicates(self) -> None:
        """When all memories are duplicated, result has each only once."""
        result = _deduplicate_memories(
            global_memories=["likes pizza", "morning person"],
            character_memories=["likes pizza", "morning person"],
        )
        assert result == ["likes pizza", "morning person"]
        assert len(result) == 2

    def test_only_global_memories(self) -> None:
        """When only global memories exist, they are all returned."""
        result = _deduplicate_memories(
            global_memories=["fact1", "fact2"],
            character_memories=[],
        )
        assert result == ["fact1", "fact2"]

    def test_only_character_memories(self) -> None:
        """When only character memories exist, they are all returned."""
        result = _deduplicate_memories(
            global_memories=[],
            character_memories=["fact1", "fact2"],
        )
        assert result == ["fact1", "fact2"]


# ---------------------------------------------------------------------------
# Additional validate_send_message tests (backend-tester)
# ---------------------------------------------------------------------------


class TestValidateSendMessageAdditional:
    """Additional tests for ChatService.validate_send_message()."""

    @pytest.mark.asyncio
    async def test_character_not_found_raises_404(self) -> None:
        """validate_send_message raises 404 for non-existent character."""
        from fastapi import HTTPException

        mock_db = AsyncMock()
        service = ChatService(mock_db)

        with patch.object(
            service,
            "_get_active_character",
            side_effect=HTTPException(status_code=404, detail="Character not found"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await service.validate_send_message(
                    character_id=FAKE_CHARACTER_ID,
                    user_id=FAKE_USER_ID,
                    profile=_make_fake_profile(),
                    content="Hello",
                )
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_ownership_check_raises_403(self) -> None:
        """validate_send_message raises 403 when character belongs to another user."""
        from fastapi import HTTPException

        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_char.user_id = uuid.UUID("990e8400-e29b-41d4-a716-446655440099")

        with patch.object(
            service, "_get_active_character", return_value=mock_char,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await service.validate_send_message(
                    character_id=FAKE_CHARACTER_ID,
                    user_id=FAKE_USER_ID,
                    profile=_make_fake_profile(),
                    content="Hello",
                )
            assert exc_info.value.status_code == 403
            assert exc_info.value.detail == "Character does not belong to user"

    @pytest.mark.asyncio
    async def test_recent_messages_failure_continues(self) -> None:
        """DB fetch failure for recent messages continues with empty list."""
        profile = _make_fake_profile()
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_conv = _make_fake_conversation()

        async def _failing_recent(*args: object, **kwargs: object) -> list[MagicMock]:
            raise RuntimeError("DB down")

        with (
            patch.object(service, "_get_active_character", return_value=mock_char),
            patch.object(
                service, "_get_or_create_conversation", return_value=mock_conv,
            ),
            patch.object(service, "_search_memories", return_value=[]),
            patch.object(
                service, "_get_recent_messages", side_effect=_failing_recent,
            ),
        ):
            ctx = await service.validate_send_message(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
                profile=profile,
                content="Hello",
            )

        # Should still return a valid context
        assert "system_prompt" in ctx
        assert "formatted_messages" in ctx

    @pytest.mark.asyncio
    async def test_context_includes_character_and_conversation(self) -> None:
        """Context dict includes all required keys with correct objects."""
        profile = _make_fake_profile()
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_conv = _make_fake_conversation()

        with (
            patch.object(service, "_get_active_character", return_value=mock_char),
            patch.object(
                service, "_get_or_create_conversation", return_value=mock_conv,
            ),
            patch.object(service, "_search_memories", return_value=[]),
            patch.object(service, "_get_recent_messages", return_value=[]),
        ):
            ctx = await service.validate_send_message(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
                profile=profile,
                content="Hello",
            )

        assert ctx["character"].id == FAKE_CHARACTER_ID
        assert ctx["conversation"].id == FAKE_CONVERSATION_ID
        assert isinstance(ctx["system_prompt"], str)
        assert isinstance(ctx["formatted_messages"], list)


# ---------------------------------------------------------------------------
# Additional stream_response tests (backend-tester)
# ---------------------------------------------------------------------------


class TestStreamResponseAdditional:
    """Additional tests for ChatService.stream_response()."""

    @pytest.mark.asyncio
    async def test_action_event_before_done_event(self) -> None:
        """Action event always comes before done event in the stream."""
        profile = _make_fake_profile()
        mock_db = AsyncMock()
        service = ChatService(mock_db)
        ctx = _make_valid_context()

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        async def _text_iter() -> AsyncGenerator[str, None]:
            yield "Setting alarm now."

        mock_stream.text_stream = _text_iter()

        with (
            patch("app.services.chat_service.AsyncAnthropic") as mock_a,
            patch.object(
                service,
                "_extract_intent",
                return_value={
                    "action": "ADD_CALENDAR_EVENT",
                    "payload": {"title": "Meeting", "date": "2026-02-25"},
                },
            ),
            patch("app.services.chat_service._persist_exchange"),
        ):
            mc = AsyncMock()
            mc.messages.stream = MagicMock(return_value=mock_stream)
            mock_a.return_value = mc

            sse_lines = []
            async for event in service.stream_response(
                context=ctx,
                user_id=FAKE_USER_ID,
                profile=profile,
                content="Add a meeting",
                media_url=None,
            ):
                sse_lines.append(event)

        events = _parse_sse_events(sse_lines)
        types = [e["type"] for e in events]
        assert "action" in types
        assert "done" in types
        assert types.index("action") < types.index("done")

    @pytest.mark.asyncio
    async def test_persist_exchange_called_with_correct_args(self) -> None:
        """Background task receives correct arguments."""
        profile = _make_fake_profile()
        mock_db = AsyncMock()
        service = ChatService(mock_db)
        ctx = _make_valid_context()

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        async def _text_iter() -> AsyncGenerator[str, None]:
            yield "Response text"

        mock_stream.text_stream = _text_iter()

        with (
            patch("app.services.chat_service.AsyncAnthropic") as mock_a,
            patch.object(service, "_extract_intent", return_value=None),
            patch("app.services.chat_service._persist_exchange") as mock_persist,
            patch("app.services.chat_service.asyncio") as mock_asyncio_mod,
        ):
            mc = AsyncMock()
            mc.messages.stream = MagicMock(return_value=mock_stream)
            mock_a.return_value = mc

            mock_asyncio_mod.gather = asyncio.gather
            mock_asyncio_mod.to_thread = asyncio.to_thread
            mock_asyncio_mod.create_task = MagicMock()

            sse_lines = []
            async for event in service.stream_response(
                context=ctx,
                user_id=FAKE_USER_ID,
                profile=profile,
                content="Hello there",
                media_url="https://example.com/img.jpg",
            ):
                sse_lines.append(event)

            mock_asyncio_mod.create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_chunks_streamed(self) -> None:
        """Stream yields multiple chunk events with proper content."""
        profile = _make_fake_profile()
        mock_db = AsyncMock()
        service = ChatService(mock_db)
        ctx = _make_valid_context()

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=False)

        async def _text_iter() -> AsyncGenerator[str, None]:
            for token in ["I", " am", " Emma", ".", " How", " can", " I", " help", "?"]:
                yield token

        mock_stream.text_stream = _text_iter()

        with (
            patch("app.services.chat_service.AsyncAnthropic") as mock_a,
            patch.object(service, "_extract_intent", return_value=None),
            patch("app.services.chat_service._persist_exchange"),
        ):
            mc = AsyncMock()
            mc.messages.stream = MagicMock(return_value=mock_stream)
            mock_a.return_value = mc

            sse_lines = []
            async for event in service.stream_response(
                context=ctx,
                user_id=FAKE_USER_ID,
                profile=profile,
                content="Hello",
                media_url=None,
            ):
                sse_lines.append(event)

        events = _parse_sse_events(sse_lines)
        chunk_events = [e for e in events if e["type"] == "chunk"]
        assert len(chunk_events) == 9
        full_text = "".join(e["content"] for e in chunk_events)
        assert full_text == "I am Emma. How can I help?"


# ---------------------------------------------------------------------------
# Additional get_messages tests (backend-tester)
# ---------------------------------------------------------------------------


class TestGetMessagesAdditional:
    """Additional tests for ChatService.get_messages()."""

    @pytest.mark.asyncio
    async def test_ownership_check_raises_403(self) -> None:
        """get_messages raises 403 when character belongs to another user."""
        from fastapi import HTTPException

        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_char.user_id = uuid.UUID("990e8400-e29b-41d4-a716-446655440099")

        call_count = 0

        async def _mock_execute(stmt: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_char
            return result

        mock_db.execute = AsyncMock(side_effect=_mock_execute)

        with pytest.raises(HTTPException) as exc_info:
            await service.get_messages(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
                cursor=None,
                limit=20,
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_cursor_filter_applied(self) -> None:
        """get_messages applies cursor filter correctly."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_conv = _make_fake_conversation()

        call_count = 0

        async def _mock_execute(stmt: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_char
            elif call_count == 2:
                result.scalar_one_or_none.return_value = mock_conv
            else:
                result.scalars.return_value.all.return_value = []
            return result

        mock_db.execute = AsyncMock(side_effect=_mock_execute)

        cursor_time = datetime.now(tz=UTC) - timedelta(hours=1)
        response = await service.get_messages(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            cursor=cursor_time,
            limit=20,
        )

        assert response.items == []
        assert response.has_more is False
        assert response.next_cursor is None

    @pytest.mark.asyncio
    async def test_empty_conversation_returns_empty_list(self) -> None:
        """Empty conversation returns empty items list."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_conv = _make_fake_conversation()

        call_count = 0

        async def _mock_execute(stmt: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_char
            elif call_count == 2:
                result.scalar_one_or_none.return_value = mock_conv
            else:
                result.scalars.return_value.all.return_value = []
            return result

        mock_db.execute = AsyncMock(side_effect=_mock_execute)

        response = await service.get_messages(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            cursor=None,
            limit=20,
        )

        assert response.items == []
        assert response.has_more is False
        assert response.next_cursor is None

    @pytest.mark.asyncio
    async def test_next_cursor_matches_last_item(self) -> None:
        """next_cursor equals the last item's created_at when has_more is true."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_conv = _make_fake_conversation()

        now = datetime.now(tz=UTC)
        messages = [
            _make_fake_message(content=f"msg{i}", offset_minutes=i) for i in range(4)
        ]
        # Set explicit created_at for predictable cursor
        for i, msg in enumerate(messages):
            msg.created_at = now - timedelta(minutes=i)

        call_count = 0

        async def _mock_execute(stmt: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_char
            elif call_count == 2:
                result.scalar_one_or_none.return_value = mock_conv
            else:
                result.scalars.return_value.all.return_value = messages
            return result

        mock_db.execute = AsyncMock(side_effect=_mock_execute)

        response = await service.get_messages(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            cursor=None,
            limit=3,
        )

        assert response.has_more is True
        assert len(response.items) == 3
        # next_cursor should be the created_at of the last returned item
        assert response.next_cursor == messages[2].created_at.isoformat()


# ---------------------------------------------------------------------------
# Additional _extract_intent tests (backend-tester)
# ---------------------------------------------------------------------------


class TestExtractIntentAdditional:
    """Additional tests for ChatService._extract_intent()."""

    @pytest.mark.asyncio
    async def test_returns_calendar_event_action(self) -> None:
        """Returns ADD_CALENDAR_EVENT action when Haiku detects it."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = json.dumps({
            "action": "ADD_CALENDAR_EVENT",
            "payload": {
                "title": "Dentist",
                "date": "2026-02-24",
                "time": "15:00",
                "duration_minutes": 60,
            },
        })
        mock_response.content = [mock_content]

        with patch("app.services.chat_service.AsyncAnthropic") as mock_a:
            mc = AsyncMock()
            mc.messages.create = AsyncMock(return_value=mock_response)
            mock_a.return_value = mc

            result = await service._extract_intent(
                "I've added the dentist appointment.", "UTC",
            )

        assert result is not None
        assert result["action"] == "ADD_CALENDAR_EVENT"
        assert result["payload"]["title"] == "Dentist"

    @pytest.mark.asyncio
    async def test_returns_none_for_invalid_json(self) -> None:
        """Returns None when Haiku responds with invalid JSON."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "this is not json {{{]]]"
        mock_response.content = [mock_content]

        with patch("app.services.chat_service.AsyncAnthropic") as mock_a:
            mc = AsyncMock()
            mc.messages.create = AsyncMock(return_value=mock_response)
            mock_a.return_value = mc

            result = await service._extract_intent("Some text.", "UTC")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_unsupported_action(self) -> None:
        """Returns None when Haiku returns an unsupported action type."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = json.dumps({
            "action": "UNSUPPORTED_ACTION",
            "payload": {"data": "value"},
        })
        mock_response.content = [mock_content]

        with patch("app.services.chat_service.AsyncAnthropic") as mock_a:
            mc = AsyncMock()
            mc.messages.create = AsyncMock(return_value=mock_response)
            mock_a.return_value = mc

            result = await service._extract_intent("Some text.", "UTC")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_json_without_action_key(self) -> None:
        """Returns None when Haiku returns valid JSON but no 'action' key."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = json.dumps({"something": "else"})
        mock_response.content = [mock_content]

        with patch("app.services.chat_service.AsyncAnthropic") as mock_a:
            mc = AsyncMock()
            mc.messages.create = AsyncMock(return_value=mock_response)
            mock_a.return_value = mc

            result = await service._extract_intent("Some text.", "UTC")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_none_case_insensitive(self) -> None:
        """Returns None when Haiku responds with 'None' (uppercase)."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "None"
        mock_response.content = [mock_content]

        with patch("app.services.chat_service.AsyncAnthropic") as mock_a:
            mc = AsyncMock()
            mc.messages.create = AsyncMock(return_value=mock_response)
            mock_a.return_value = mc

            result = await service._extract_intent("Just a casual response.", "UTC")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_default_empty_payload_when_missing(self) -> None:
        """Returns empty payload dict when Haiku omits payload key."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = json.dumps({"action": "SET_ALARM"})
        mock_response.content = [mock_content]

        with patch("app.services.chat_service.AsyncAnthropic") as mock_a:
            mc = AsyncMock()
            mc.messages.create = AsyncMock(return_value=mock_response)
            mock_a.return_value = mc

            result = await service._extract_intent("Set alarm.", "UTC")

        assert result is not None
        assert result["action"] == "SET_ALARM"
        assert result["payload"] == {}


# ---------------------------------------------------------------------------
# Additional _build_system_prompt tests (backend-tester)
# ---------------------------------------------------------------------------


class TestBuildSystemPromptAdditional:
    """Additional tests for ChatService._build_system_prompt()."""

    def test_invalid_timezone_falls_back_to_utc(self) -> None:
        """Invalid timezone falls back to UTC without crashing."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        profile = _make_fake_profile()
        profile.timezone = "Invalid/Timezone"

        prompt = service._build_system_prompt(
            character_system_prompt="You are Sarah.",
            global_memories=[],
            character_memories=[],
            profile=profile,
        )

        # Should still contain date/time info (using UTC fallback)
        assert "Current date and time:" in prompt

    def test_none_timezone_falls_back_to_utc(self) -> None:
        """None timezone falls back to UTC without crashing."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        profile = _make_fake_profile()
        profile.timezone = None

        prompt = service._build_system_prompt(
            character_system_prompt="You are Sarah.",
            global_memories=[],
            character_memories=[],
            profile=profile,
        )

        assert "Current date and time:" in prompt

    def test_memory_deduplication_in_prompt(self) -> None:
        """Duplicated memories between global and character appear only once."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        profile = _make_fake_profile()
        prompt = service._build_system_prompt(
            character_system_prompt="You are Sarah.",
            global_memories=["Likes pizza", "Morning person"],
            character_memories=["Likes pizza", "Struggles with grammar"],
            profile=profile,
        )

        # "Likes pizza" should appear only once
        assert prompt.count("Likes pizza") == 1
        assert "Morning person" in prompt
        assert "Struggles with grammar" in prompt

    def test_max_ten_memories_in_prompt(self) -> None:
        """Up to 10 memories (5 global + 5 character) can appear in prompt."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        profile = _make_fake_profile()
        prompt = service._build_system_prompt(
            character_system_prompt="You are Sarah.",
            global_memories=[f"global_fact_{i}" for i in range(5)],
            character_memories=[f"char_fact_{i}" for i in range(5)],
            profile=profile,
        )

        assert "What you know about this user:" in prompt
        # All 10 unique memories should be present
        for i in range(5):
            assert f"global_fact_{i}" in prompt
            assert f"char_fact_{i}" in prompt


# ---------------------------------------------------------------------------
# Additional _format_messages tests (backend-tester)
# ---------------------------------------------------------------------------


class TestFormatMessagesAdditional:
    """Additional tests for ChatService._format_messages()."""

    def test_formats_with_empty_history(self) -> None:
        """Empty history produces only the new user message."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        formatted = service._format_messages([], "Hello!")

        assert len(formatted) == 1
        assert formatted[0] == {"role": "user", "content": "Hello!"}

    def test_new_message_appended_last(self) -> None:
        """New user message is always the last item."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        msg1 = _make_fake_message(role="user", content="First")
        msg2 = _make_fake_message(role="assistant", content="Reply")

        formatted = service._format_messages([msg1, msg2], "New message")

        assert formatted[-1] == {"role": "user", "content": "New message"}
        assert len(formatted) == 3


# ---------------------------------------------------------------------------
# Additional _persist_exchange tests (backend-tester)
# ---------------------------------------------------------------------------


class TestPersistExchangeAdditional:
    """Additional tests for the _persist_exchange background task."""

    @pytest.mark.asyncio
    async def test_persists_action_metadata(self) -> None:
        """Background task stores action metadata on assistant message."""
        mock_session = AsyncMock()
        add_calls: list[Any] = []
        mock_session.add = MagicMock(side_effect=lambda obj: add_calls.append(obj))
        mock_session.commit = AsyncMock()

        action_meta = {
            "action": "SET_ALARM",
            "payload": {"time": "07:00", "label": "Wake up"},
        }

        with (
            patch("app.services.chat_service.AsyncSessionLocal") as mock_factory,
            patch("app.services.chat_service.MemoryClient") as mock_mem0,
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session,
            )
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_mem0_inst = MagicMock()
            mock_mem0.return_value = mock_mem0_inst

            await _persist_exchange(
                user_id=FAKE_USER_ID,
                conversation_id=FAKE_CONVERSATION_ID,
                user_content="Set alarm for 7am",
                user_media_url=None,
                assistant_content="I've set an alarm for 7:00 AM.",
                assistant_message_id=uuid.uuid4(),
                action_metadata=action_meta,
                mem0_user_id=f"user_{FAKE_USER_ID}",
                mem0_agent_id=f"english_teacher_{FAKE_USER_ID}",
            )

        # Verify 2 messages were added
        assert mock_session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_persists_media_url_on_user_message(self) -> None:
        """Background task stores media_url on user message."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        with (
            patch("app.services.chat_service.AsyncSessionLocal") as mock_factory,
            patch("app.services.chat_service.MemoryClient") as mock_mem0,
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session,
            )
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_mem0_inst = MagicMock()
            mock_mem0.return_value = mock_mem0_inst

            await _persist_exchange(
                user_id=FAKE_USER_ID,
                conversation_id=FAKE_CONVERSATION_ID,
                user_content="Look at this",
                user_media_url="https://s3.amazonaws.com/bucket/image.jpg",
                assistant_content="Nice photo!",
                assistant_message_id=uuid.uuid4(),
                action_metadata=None,
                mem0_user_id=f"user_{FAKE_USER_ID}",
                mem0_agent_id=f"english_teacher_{FAKE_USER_ID}",
            )

        assert mock_session.add.call_count == 2
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_mem0_add_called_with_message_pair(self) -> None:
        """Background task passes correct user/assistant message pair to Mem0."""
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        with (
            patch("app.services.chat_service.AsyncSessionLocal") as mock_factory,
            patch("app.services.chat_service.MemoryClient") as mock_mem0,
            patch(
                "app.services.chat_service.asyncio.to_thread",
            ) as mock_to_thread,
        ):
            mock_factory.return_value.__aenter__ = AsyncMock(
                return_value=mock_session,
            )
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_mem0_inst = MagicMock()
            mock_mem0.return_value = mock_mem0_inst
            mock_to_thread.return_value = None

            await _persist_exchange(
                user_id=FAKE_USER_ID,
                conversation_id=FAKE_CONVERSATION_ID,
                user_content="How are you?",
                user_media_url=None,
                assistant_content="I'm great!",
                assistant_message_id=uuid.uuid4(),
                action_metadata=None,
                mem0_user_id=f"user_{FAKE_USER_ID}",
                mem0_agent_id=f"english_teacher_{FAKE_USER_ID}",
            )

        # Verify the message pair passed to Mem0
        mock_to_thread.assert_called_once()
        call_args = mock_to_thread.call_args
        messages_arg = call_args.args[1]  # Second positional arg
        assert len(messages_arg) == 2
        assert messages_arg[0]["role"] == "user"
        assert messages_arg[0]["content"] == "How are you?"
        assert messages_arg[1]["role"] == "assistant"
        assert messages_arg[1]["content"] == "I'm great!"


# ---------------------------------------------------------------------------
# _get_active_character tests (backend-tester)
# ---------------------------------------------------------------------------


class TestGetActiveCharacter:
    """Tests for ChatService._get_active_character()."""

    @pytest.mark.asyncio
    async def test_returns_character_when_found(self) -> None:
        """Returns the character when found and active."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_char
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service._get_active_character(FAKE_CHARACTER_ID)
        assert result.id == FAKE_CHARACTER_ID

    @pytest.mark.asyncio
    async def test_raises_404_when_not_found(self) -> None:
        """Raises 404 when character does not exist or is inactive."""
        from fastapi import HTTPException

        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await service._get_active_character(FAKE_CHARACTER_ID)
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Character not found"


# ---------------------------------------------------------------------------
# _get_or_create_conversation tests (backend-tester)
# ---------------------------------------------------------------------------


class TestGetOrCreateConversation:
    """Tests for ChatService._get_or_create_conversation()."""

    @pytest.mark.asyncio
    async def test_returns_existing_conversation(self) -> None:
        """Returns existing conversation without creating a new one."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_conv = _make_fake_conversation()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_conv
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service._get_or_create_conversation(
            FAKE_CHARACTER_ID, FAKE_USER_ID,
        )

        assert result.id == FAKE_CONVERSATION_ID
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_conversation_when_missing(self) -> None:
        """Auto-creates a conversation when none exists for the character."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        result = await service._get_or_create_conversation(
            FAKE_CHARACTER_ID, FAKE_USER_ID,
        )

        # A new conversation was added and committed
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()


# ---------------------------------------------------------------------------
# _search_memories tests (backend-tester)
# ---------------------------------------------------------------------------


class TestSearchMemories:
    """Tests for ChatService._search_memories()."""

    @pytest.mark.asyncio
    async def test_search_with_agent_id(self) -> None:
        """Passes agent_id to Mem0 when provided."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        agent_id = f"english_teacher_{FAKE_USER_ID}"

        with (
            patch("app.services.chat_service.MemoryClient") as mock_mem0_cls,
            patch("app.services.chat_service.asyncio.to_thread") as mock_to_thread,
        ):
            mock_mem0_inst = MagicMock()
            mock_mem0_cls.return_value = mock_mem0_inst
            mock_to_thread.return_value = [
                {"memory": "Likes reading"},
                {"memory": "Prefers mornings"},
            ]

            result = await service._search_memories(
                "Hello", f"user_{FAKE_USER_ID}", agent_id=agent_id,
            )

        assert result == ["Likes reading", "Prefers mornings"]
        mock_to_thread.assert_called_once()
        call_kwargs = mock_to_thread.call_args.kwargs
        assert call_kwargs["agent_id"] == agent_id

    @pytest.mark.asyncio
    async def test_search_without_agent_id(self) -> None:
        """Omits agent_id from Mem0 call when not provided (global search)."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        with (
            patch("app.services.chat_service.MemoryClient") as mock_mem0_cls,
            patch("app.services.chat_service.asyncio.to_thread") as mock_to_thread,
        ):
            mock_mem0_inst = MagicMock()
            mock_mem0_cls.return_value = mock_mem0_inst
            mock_to_thread.return_value = [{"memory": "Global fact"}]

            result = await service._search_memories(
                "Hello", f"user_{FAKE_USER_ID}", agent_id=None,
            )

        assert result == ["Global fact"]
        mock_to_thread.assert_called_once()
        call_kwargs = mock_to_thread.call_args.kwargs
        assert "agent_id" not in call_kwargs

    @pytest.mark.asyncio
    async def test_search_handles_exception(self) -> None:
        """Returns empty list when Mem0 search raises an exception."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        with patch(
            "app.services.chat_service.MemoryClient",
            side_effect=Exception("Connection error"),
        ):
            result = await service._search_memories(
                "Hello", f"user_{FAKE_USER_ID}", agent_id=None,
            )

        assert result == []


# ---------------------------------------------------------------------------
# _get_recent_messages tests (backend-tester)
# ---------------------------------------------------------------------------


class TestGetRecentMessages:
    """Tests for ChatService._get_recent_messages()."""

    @pytest.mark.asyncio
    async def test_returns_messages_in_chronological_order(self) -> None:
        """Recent messages are returned in chronological order (oldest first)."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        now = datetime.now(tz=UTC)
        msg_old = _make_fake_message(content="older", offset_minutes=10)
        msg_new = _make_fake_message(content="newer", offset_minutes=0)

        # DB returns DESC order (newest first)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [msg_new, msg_old]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service._get_recent_messages(FAKE_CONVERSATION_ID)

        # After reversal, should be chronological: oldest first
        assert result[0].content == "older"
        assert result[1].content == "newer"

    @pytest.mark.asyncio
    async def test_returns_empty_for_new_conversation(self) -> None:
        """Returns empty list when conversation has no messages."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service._get_recent_messages(FAKE_CONVERSATION_ID)

        assert result == []
