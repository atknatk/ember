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
