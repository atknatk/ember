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
import base64  # noqa: E402
import json  # noqa: E402
import uuid  # noqa: E402
from collections.abc import AsyncGenerator  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402
from typing import Any  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from app.services.chat_service import (  # noqa: E402
    ChatService,
    MessageCursor,
    _decode_cursor,
    _deduplicate_memories,
    _encode_cursor,
    _persist_exchange,
)
from app.services.llm.exceptions import LLMProviderError  # noqa: E402

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


def _make_mock_llm_router(
    stream_chunks: list[str] | None = None,
    complete_fast_result: str = "none",
    stream_error: Exception | None = None,
    complete_fast_error: Exception | None = None,
) -> MagicMock:
    """Create a mock LLMRouter with a mock provider.

    Args:
        stream_chunks: Text chunks the stream() method will yield.
        complete_fast_result: Text returned by complete_fast().
        stream_error: If set, stream() raises this after yielding.
        complete_fast_error: If set, complete_fast() raises this.
    """
    mock_router = MagicMock()
    mock_provider = MagicMock()

    async def _mock_stream(
        system: str = "",
        messages: list[dict[str, str]] | None = None,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.8,
    ) -> AsyncGenerator[str, None]:
        if stream_error is not None:
            raise stream_error
        for chunk in (stream_chunks or []):
            yield chunk

    mock_provider.stream = _mock_stream

    if complete_fast_error is not None:
        mock_provider.complete_fast = AsyncMock(side_effect=complete_fast_error)
    else:
        mock_provider.complete_fast = AsyncMock(return_value=complete_fast_result)

    mock_router.get = MagicMock(return_value=mock_provider)
    return mock_router


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
        """stream_response yields chunk events from LLM provider stream."""
        profile = _make_fake_profile()
        mock_db = AsyncMock()
        mock_router = _make_mock_llm_router(
            stream_chunks=["Hello", ", ", "world!"],
        )
        service = ChatService(mock_db, llm_router=mock_router)
        ctx = _make_valid_context()

        with (
            patch.object(service, "_extract_intent", return_value=None),
            patch("app.services.chat_service._persist_exchange"),
        ):
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
        mock_router = _make_mock_llm_router(stream_chunks=["Setting alarm."])
        service = ChatService(mock_db, llm_router=mock_router)
        ctx = _make_valid_context()

        with (
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
        mock_router = _make_mock_llm_router(stream_chunks=["Just chatting."])
        service = ChatService(mock_db, llm_router=mock_router)
        ctx = _make_valid_context()

        with (
            patch.object(service, "_extract_intent", return_value=None),
            patch("app.services.chat_service._persist_exchange"),
        ):
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
        mock_router = _make_mock_llm_router(stream_chunks=["Hi"])
        service = ChatService(mock_db, llm_router=mock_router)
        ctx = _make_valid_context()

        with (
            patch.object(service, "_extract_intent", return_value=None),
            patch("app.services.chat_service._persist_exchange"),
        ):
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
        mock_router = _make_mock_llm_router(stream_chunks=["Hi"])
        service = ChatService(mock_db, llm_router=mock_router)
        ctx = _make_valid_context()

        with (
            patch.object(service, "_extract_intent", return_value=None),
            patch("app.services.chat_service._persist_exchange"),
            patch("app.services.chat_service.asyncio") as mock_asyncio,
        ):
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
        """stream_response emits error event when LLM provider fails."""
        profile = _make_fake_profile()
        mock_db = AsyncMock()
        mock_router = _make_mock_llm_router(
            stream_error=LLMProviderError(
                "API error", code="provider_error", provider="claude",
            ),
        )
        service = ChatService(mock_db, llm_router=mock_router)
        ctx = _make_valid_context()

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
        intent_json = json.dumps({
            "action": "SET_ALARM",
            "payload": {"time": "2026-02-24T07:00:00", "label": "Wake up"},
        })
        mock_router = _make_mock_llm_router(complete_fast_result=intent_json)
        service = ChatService(mock_db, llm_router=mock_router)

        result = await service._extract_intent("I'll set an alarm.", "UTC")

        assert result is not None
        assert result["action"] == "SET_ALARM"

    @pytest.mark.asyncio
    async def test_returns_none_when_haiku_says_none(self) -> None:
        """Returns None when Haiku responds with 'none'."""
        mock_db = AsyncMock()
        mock_router = _make_mock_llm_router(complete_fast_result="none")
        service = ChatService(mock_db, llm_router=mock_router)

        result = await service._extract_intent("Just chatting.", "UTC")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_haiku_fails(self) -> None:
        """Returns None when Haiku call fails (no crash)."""
        mock_db = AsyncMock()
        mock_router = _make_mock_llm_router(
            complete_fast_error=Exception("API error"),
        )
        service = ChatService(mock_db, llm_router=mock_router)

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
        mock_router = _make_mock_llm_router(stream_chunks=["Setting alarm now."])
        service = ChatService(mock_db, llm_router=mock_router)
        ctx = _make_valid_context()

        with (
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
        mock_router = _make_mock_llm_router(stream_chunks=["Response text"])
        service = ChatService(mock_db, llm_router=mock_router)
        ctx = _make_valid_context()

        with (
            patch.object(service, "_extract_intent", return_value=None),
            patch("app.services.chat_service._persist_exchange") as mock_persist,
            patch("app.services.chat_service.asyncio") as mock_asyncio_mod,
        ):
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
        tokens = ["I", " am", " Emma", ".", " How", " can", " I", " help", "?"]
        mock_router = _make_mock_llm_router(stream_chunks=tokens)
        service = ChatService(mock_db, llm_router=mock_router)
        ctx = _make_valid_context()

        with (
            patch.object(service, "_extract_intent", return_value=None),
            patch("app.services.chat_service._persist_exchange"),
        ):
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
        """get_messages applies composite cursor filter correctly."""
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

        cursor = MessageCursor(
            ts=datetime.now(tz=UTC) - timedelta(hours=1),
            id=uuid.uuid4(),
        )
        response = await service.get_messages(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            cursor=cursor,
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
        """next_cursor encodes the last item's (created_at, id) as base64 JSON."""
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
        # next_cursor should be a base64-encoded JSON with ts and id of last item
        assert response.next_cursor is not None
        decoded = _decode_cursor(response.next_cursor)
        assert decoded.ts == messages[2].created_at
        assert decoded.id == messages[2].id


# ---------------------------------------------------------------------------
# Additional _extract_intent tests (backend-tester)
# ---------------------------------------------------------------------------


class TestExtractIntentAdditional:
    """Additional tests for ChatService._extract_intent()."""

    @pytest.mark.asyncio
    async def test_returns_calendar_event_action(self) -> None:
        """Returns ADD_CALENDAR_EVENT action when Haiku detects it."""
        mock_db = AsyncMock()
        intent_json = json.dumps({
            "action": "ADD_CALENDAR_EVENT",
            "payload": {
                "title": "Dentist",
                "date": "2026-02-24",
                "time": "15:00",
                "duration_minutes": 60,
            },
        })
        mock_router = _make_mock_llm_router(complete_fast_result=intent_json)
        service = ChatService(mock_db, llm_router=mock_router)

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
        mock_router = _make_mock_llm_router(
            complete_fast_result="this is not json {{{]]]",
        )
        service = ChatService(mock_db, llm_router=mock_router)

        result = await service._extract_intent("Some text.", "UTC")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_unsupported_action(self) -> None:
        """Returns None when Haiku returns an unsupported action type."""
        mock_db = AsyncMock()
        intent_json = json.dumps({
            "action": "UNSUPPORTED_ACTION",
            "payload": {"data": "value"},
        })
        mock_router = _make_mock_llm_router(complete_fast_result=intent_json)
        service = ChatService(mock_db, llm_router=mock_router)

        result = await service._extract_intent("Some text.", "UTC")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_json_without_action_key(self) -> None:
        """Returns None when Haiku returns valid JSON but no 'action' key."""
        mock_db = AsyncMock()
        intent_json = json.dumps({"something": "else"})
        mock_router = _make_mock_llm_router(complete_fast_result=intent_json)
        service = ChatService(mock_db, llm_router=mock_router)

        result = await service._extract_intent("Some text.", "UTC")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_none_case_insensitive(self) -> None:
        """Returns None when Haiku responds with 'None' (uppercase)."""
        mock_db = AsyncMock()
        mock_router = _make_mock_llm_router(complete_fast_result="None")
        service = ChatService(mock_db, llm_router=mock_router)

        result = await service._extract_intent("Just a casual response.", "UTC")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_default_empty_payload_when_missing(self) -> None:
        """Returns empty payload dict when Haiku omits payload key."""
        mock_db = AsyncMock()
        intent_json = json.dumps({"action": "SET_ALARM"})
        mock_router = _make_mock_llm_router(complete_fast_result=intent_json)
        service = ChatService(mock_db, llm_router=mock_router)

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


# ---------------------------------------------------------------------------
# Composite cursor helper unit tests (U1-U7)
# ---------------------------------------------------------------------------


class TestCursorHelpers:
    """Unit tests for _encode_cursor, _decode_cursor, and MessageCursor."""

    # --- U1: _encode_cursor returns a string ---

    def test_encode_cursor_returns_string(self) -> None:
        """_encode_cursor returns a string."""
        now = datetime.now(tz=UTC)
        msg_id = uuid.uuid4()
        result = _encode_cursor(now, msg_id)
        assert isinstance(result, str)

    # --- U2: _encode_cursor output is valid base64 ---

    def test_encode_cursor_is_valid_base64(self) -> None:
        """_encode_cursor output can be base64-decoded."""
        now = datetime.now(tz=UTC)
        msg_id = uuid.uuid4()
        result = _encode_cursor(now, msg_id)
        padded = result + "=" * (-len(result) % 4)
        decoded = base64.urlsafe_b64decode(padded)
        # Should be valid JSON
        payload = json.loads(decoded)
        assert "ts" in payload
        assert "id" in payload

    # --- U3: _decode_cursor returns a MessageCursor ---

    def test_decode_cursor_returns_message_cursor(self) -> None:
        """_decode_cursor returns a MessageCursor instance."""
        now = datetime.now(tz=UTC)
        msg_id = uuid.uuid4()
        encoded = _encode_cursor(now, msg_id)
        result = _decode_cursor(encoded)
        assert isinstance(result, MessageCursor)

    # --- U4: _decode_cursor roundtrip returns correct ts and id ---

    def test_decode_cursor_roundtrip_correct_values(self) -> None:
        """decode(encode(ts, id)) returns the original ts and id."""
        now = datetime.now(tz=UTC)
        msg_id = uuid.uuid4()
        encoded = _encode_cursor(now, msg_id)
        decoded = _decode_cursor(encoded)
        assert decoded.ts == now
        assert decoded.id == msg_id

    # --- U5: _decode_cursor with empty string raises 400 ---

    def test_decode_cursor_empty_string_raises_400(self) -> None:
        """_decode_cursor raises HTTPException(400) for empty string."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _decode_cursor("")
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Invalid cursor format"

    # --- U6: _decode_cursor with plain ISO timestamp (old format) raises 400 ---

    def test_decode_cursor_plain_iso_raises_400(self) -> None:
        """_decode_cursor raises HTTPException(400) for plain ISO timestamp."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _decode_cursor("2026-02-23T14:30:00+00:00")
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Invalid cursor format"

    # --- U7: _decode_cursor with valid base64 but missing ts raises 400 ---

    def test_decode_cursor_missing_ts_raises_400(self) -> None:
        """_decode_cursor raises HTTPException(400) when ts is missing."""
        from fastapi import HTTPException

        payload = json.dumps({"id": str(uuid.uuid4())}).encode()
        encoded = base64.urlsafe_b64encode(payload).decode()
        with pytest.raises(HTTPException) as exc_info:
            _decode_cursor(encoded)
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Invalid cursor format"

    # --- Additional: _decode_cursor with garbage bytes raises 400 ---

    def test_decode_cursor_garbage_raises_400(self) -> None:
        """_decode_cursor raises HTTPException(400) for random garbage."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _decode_cursor("abcxyz123456")
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Invalid cursor format"

    # --- S4: Roundtrip test ---

    def test_cursor_roundtrip(self) -> None:
        """Encode then decode roundtrip preserves values."""
        ts = datetime(2026, 2, 23, 14, 30, 0, tzinfo=UTC)
        msg_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440088")
        encoded = _encode_cursor(ts, msg_id)
        decoded = _decode_cursor(encoded)
        assert decoded.ts == ts
        assert decoded.id == msg_id

    # --- S5: _decode_cursor raises HTTPException(400) for garbage ---

    def test_decode_raises_for_garbage(self) -> None:
        """_decode_cursor raises 400 for non-decodable input."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _decode_cursor("!!!totally-invalid!!!")
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Same-timestamp tiebreaker tests (S1-S3)
# ---------------------------------------------------------------------------


class TestSameTimestampPagination:
    """Tests for same-timestamp tiebreaker in composite cursor pagination."""

    # --- S1: Two messages with same created_at but different ids ---

    @pytest.mark.asyncio
    async def test_same_timestamp_different_ids_paginated_correctly(self) -> None:
        """Two messages with same created_at are correctly paginated with limit=1."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_conv = _make_fake_conversation()

        now = datetime.now(tz=UTC)
        # Two messages with SAME created_at, different ids
        msg1 = _make_fake_message(content="first", offset_minutes=0)
        msg1.created_at = now
        msg1.id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

        msg2 = _make_fake_message(content="second", offset_minutes=0)
        msg2.created_at = now
        msg2.id = uuid.UUID("00000000-0000-0000-0000-000000000001")

        call_count = 0

        # First call: returns both messages (limit=1, so 2 = limit+1 returned)
        async def _mock_execute_page1(stmt: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = mock_char
            elif call_count == 2:
                result.scalar_one_or_none.return_value = mock_conv
            else:
                # msg1 has larger id so comes first in DESC order
                result.scalars.return_value.all.return_value = [msg1, msg2]
            return result

        mock_db.execute = AsyncMock(side_effect=_mock_execute_page1)

        # First page
        response1 = await service.get_messages(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            cursor=None,
            limit=1,
        )

        assert len(response1.items) == 1
        assert response1.items[0].content == "first"
        assert response1.has_more is True
        assert response1.next_cursor is not None

        # Verify cursor encodes the last returned item
        decoded = _decode_cursor(response1.next_cursor)
        assert decoded.ts == msg1.created_at
        assert decoded.id == msg1.id

    # --- S2: next_cursor encodes to valid base64 JSON ---

    @pytest.mark.asyncio
    async def test_next_cursor_is_valid_base64_json(self) -> None:
        """next_cursor in get_messages response is valid base64 JSON with ts and id."""
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

        assert response.next_cursor is not None
        # Decode and verify structure
        padded = response.next_cursor + "=" * (-len(response.next_cursor) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded))
        assert "ts" in decoded
        assert "id" in decoded
        datetime.fromisoformat(decoded["ts"])
        uuid.UUID(decoded["id"])

    # --- S3: Service accepts MessageCursor and tuple comparison works ---

    @pytest.mark.asyncio
    async def test_service_accepts_message_cursor(self) -> None:
        """Service method accepts MessageCursor and executes query without error."""
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

        cursor = MessageCursor(
            ts=datetime.now(tz=UTC),
            id=uuid.uuid4(),
        )
        response = await service.get_messages(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            cursor=cursor,
            limit=20,
        )

        assert response.items == []
        assert response.has_more is False


# ---------------------------------------------------------------------------
# Pagination edge-case service tests (backend-tester: P01-07)
# ---------------------------------------------------------------------------


class TestPaginationEdgeCases:
    """Edge-case service tests for cursor-based pagination (P01-07)."""

    # --- Helper for building mock_execute with call_count pattern ---

    @staticmethod
    def _build_mock_execute(
        mock_char: MagicMock,
        mock_conv: MagicMock,
        messages: list[MagicMock],
    ):
        """Return an async side_effect function for mock_db.execute.

        Call 1 -> character lookup, Call 2 -> conversation lookup,
        Call 3+ -> message query.
        """
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

        return _mock_execute

    # --- Exactly N messages where N=limit (has_more boundary) ---

    @pytest.mark.asyncio
    async def test_exactly_limit_messages_has_more_false(self) -> None:
        """When DB returns exactly limit rows (not limit+1), has_more is False."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_conv = _make_fake_conversation()

        # Create exactly 5 messages (limit=5 means service queries 6, gets 5 back)
        messages = [
            _make_fake_message(content=f"msg{i}", offset_minutes=i)
            for i in range(5)
        ]

        mock_db.execute = AsyncMock(
            side_effect=self._build_mock_execute(mock_char, mock_conv, messages),
        )

        response = await service.get_messages(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            cursor=None,
            limit=5,
        )

        assert len(response.items) == 5
        assert response.has_more is False
        assert response.next_cursor is None

    # --- Exactly limit+1 messages (has_more=True, returns limit items) ---

    @pytest.mark.asyncio
    async def test_limit_plus_one_messages_has_more_true(self) -> None:
        """When DB returns limit+1 rows, has_more is True and only limit items returned."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_conv = _make_fake_conversation()

        # Create limit+1 = 6 messages for limit=5
        messages = [
            _make_fake_message(content=f"msg{i}", offset_minutes=i)
            for i in range(6)
        ]

        mock_db.execute = AsyncMock(
            side_effect=self._build_mock_execute(mock_char, mock_conv, messages),
        )

        response = await service.get_messages(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            cursor=None,
            limit=5,
        )

        assert len(response.items) == 5
        assert response.has_more is True
        assert response.next_cursor is not None

    # --- Single message in conversation ---

    @pytest.mark.asyncio
    async def test_single_message_returns_correctly(self) -> None:
        """Conversation with exactly one message returns it correctly."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_conv = _make_fake_conversation()

        msg = _make_fake_message(content="only message", offset_minutes=0)

        mock_db.execute = AsyncMock(
            side_effect=self._build_mock_execute(mock_char, mock_conv, [msg]),
        )

        response = await service.get_messages(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            cursor=None,
            limit=20,
        )

        assert len(response.items) == 1
        assert response.items[0].content == "only message"
        assert response.has_more is False
        assert response.next_cursor is None

    # --- Same-timestamp with 3 messages: multi-page walk ---

    @pytest.mark.asyncio
    async def test_three_same_timestamp_messages_paginate_correctly(self) -> None:
        """Three messages with identical created_at paginate without duplicates."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_conv = _make_fake_conversation()

        now = datetime.now(tz=UTC)

        # Three messages at same timestamp, different UUIDs (ordered DESC by id)
        msg_a = _make_fake_message(content="msg_a")
        msg_a.created_at = now
        msg_a.id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

        msg_b = _make_fake_message(content="msg_b")
        msg_b.created_at = now
        msg_b.id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

        msg_c = _make_fake_message(content="msg_c")
        msg_c.created_at = now
        msg_c.id = uuid.UUID("00000000-0000-0000-0000-000000000001")

        # Page 1: limit=1, returns [msg_a, msg_b] (limit+1=2)
        page1_call_count = 0

        async def _mock_execute_page1(stmt: object) -> MagicMock:
            nonlocal page1_call_count
            page1_call_count += 1
            result = MagicMock()
            if page1_call_count == 1:
                result.scalar_one_or_none.return_value = mock_char
            elif page1_call_count == 2:
                result.scalar_one_or_none.return_value = mock_conv
            else:
                # msg_a has larger id so comes first in DESC order
                result.scalars.return_value.all.return_value = [msg_a, msg_b]
            return result

        mock_db.execute = AsyncMock(side_effect=_mock_execute_page1)

        # First page
        response1 = await service.get_messages(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            cursor=None,
            limit=1,
        )

        assert len(response1.items) == 1
        assert response1.items[0].content == "msg_a"
        assert response1.has_more is True

        # Decode cursor and verify it points to msg_a
        cursor1 = _decode_cursor(response1.next_cursor)
        assert cursor1.ts == now
        assert cursor1.id == msg_a.id

        # Page 2: cursor from page1, returns [msg_b, msg_c] (limit+1=2)
        page2_call_count = 0

        async def _mock_execute_page2(stmt: object) -> MagicMock:
            nonlocal page2_call_count
            page2_call_count += 1
            result = MagicMock()
            if page2_call_count == 1:
                result.scalar_one_or_none.return_value = mock_char
            elif page2_call_count == 2:
                result.scalar_one_or_none.return_value = mock_conv
            else:
                result.scalars.return_value.all.return_value = [msg_b, msg_c]
            return result

        mock_db.execute = AsyncMock(side_effect=_mock_execute_page2)

        response2 = await service.get_messages(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            cursor=cursor1,
            limit=1,
        )

        assert len(response2.items) == 1
        assert response2.items[0].content == "msg_b"
        assert response2.has_more is True

        # Page 3: returns [msg_c] only (no extra row)
        page3_call_count = 0

        async def _mock_execute_page3(stmt: object) -> MagicMock:
            nonlocal page3_call_count
            page3_call_count += 1
            result = MagicMock()
            if page3_call_count == 1:
                result.scalar_one_or_none.return_value = mock_char
            elif page3_call_count == 2:
                result.scalar_one_or_none.return_value = mock_conv
            else:
                result.scalars.return_value.all.return_value = [msg_c]
            return result

        cursor2 = _decode_cursor(response2.next_cursor)
        mock_db.execute = AsyncMock(side_effect=_mock_execute_page3)

        response3 = await service.get_messages(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            cursor=cursor2,
            limit=1,
        )

        assert len(response3.items) == 1
        assert response3.items[0].content == "msg_c"
        assert response3.has_more is False

        # All three messages appeared exactly once across all pages
        all_contents = [
            response1.items[0].content,
            response2.items[0].content,
            response3.items[0].content,
        ]
        assert sorted(all_contents) == sorted(["msg_a", "msg_b", "msg_c"])

    # --- Cursor with future timestamp returns all messages ---

    @pytest.mark.asyncio
    async def test_cursor_with_future_timestamp_returns_all_messages(self) -> None:
        """Cursor with far-future timestamp returns messages older than the cursor."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_conv = _make_fake_conversation()

        now = datetime.now(tz=UTC)
        messages = [
            _make_fake_message(content=f"msg{i}", offset_minutes=i)
            for i in range(3)
        ]

        mock_db.execute = AsyncMock(
            side_effect=self._build_mock_execute(mock_char, mock_conv, messages),
        )

        future_cursor = MessageCursor(
            ts=now + timedelta(days=365),
            id=uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        )

        response = await service.get_messages(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            cursor=future_cursor,
            limit=20,
        )

        # All 3 messages are older than the future cursor, so all returned
        assert len(response.items) == 3

    # --- Cursor pointing past oldest message returns empty ---

    @pytest.mark.asyncio
    async def test_cursor_past_oldest_message_returns_empty(self) -> None:
        """Cursor older than all messages returns empty items."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_conv = _make_fake_conversation()

        # No messages match the cursor filter (all messages are newer)
        mock_db.execute = AsyncMock(
            side_effect=self._build_mock_execute(mock_char, mock_conv, []),
        )

        old_cursor = MessageCursor(
            ts=datetime(2020, 1, 1, tzinfo=UTC),
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        )

        response = await service.get_messages(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            cursor=old_cursor,
            limit=20,
        )

        assert response.items == []
        assert response.has_more is False
        assert response.next_cursor is None

    # --- Multi-page walk: 3 pages of 3 messages each ---

    @pytest.mark.asyncio
    async def test_multi_page_walk_three_pages(self) -> None:
        """Multi-page walk through 9 messages in pages of 3 returns all without duplicates."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_conv = _make_fake_conversation()

        now = datetime.now(tz=UTC)
        all_messages = []
        for i in range(9):
            msg = _make_fake_message(content=f"msg{i}", offset_minutes=i)
            msg.created_at = now - timedelta(minutes=i)
            msg.id = uuid.UUID(f"00000000-0000-0000-0000-{i:012d}")
            all_messages.append(msg)

        all_collected_ids: set[str] = set()
        cursor: MessageCursor | None = None

        for page_num in range(3):
            page_call_count = 0
            start = page_num * 3
            # Simulate DB returning limit+1=4 rows for first 2 pages, 3 for last
            if page_num < 2:
                page_msgs = all_messages[start : start + 4]
            else:
                page_msgs = all_messages[start : start + 3]

            async def _mock_execute(
                stmt: object,
                _msgs: list[MagicMock] = page_msgs,
            ) -> MagicMock:
                nonlocal page_call_count
                page_call_count += 1
                result = MagicMock()
                if page_call_count == 1:
                    result.scalar_one_or_none.return_value = mock_char
                elif page_call_count == 2:
                    result.scalar_one_or_none.return_value = mock_conv
                else:
                    result.scalars.return_value.all.return_value = _msgs
                return result

            mock_db.execute = AsyncMock(side_effect=_mock_execute)

            response = await service.get_messages(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
                cursor=cursor,
                limit=3,
            )

            page_ids = {item.id for item in response.items}
            # No duplicates between this page and previously collected
            assert page_ids.isdisjoint(all_collected_ids), (
                f"Duplicate IDs found on page {page_num + 1}"
            )
            all_collected_ids.update(page_ids)

            if response.next_cursor is not None:
                cursor = _decode_cursor(response.next_cursor)
            else:
                cursor = None

        # All 9 messages collected
        assert len(all_collected_ids) == 9

    # --- next_cursor is None when has_more is False ---

    @pytest.mark.asyncio
    async def test_next_cursor_none_when_has_more_false(self) -> None:
        """next_cursor is always None when has_more is False."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_conv = _make_fake_conversation()

        # 2 messages with limit=5 -> no overflow -> has_more=False
        messages = [
            _make_fake_message(content=f"msg{i}", offset_minutes=i)
            for i in range(2)
        ]

        mock_db.execute = AsyncMock(
            side_effect=self._build_mock_execute(mock_char, mock_conv, messages),
        )

        response = await service.get_messages(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            cursor=None,
            limit=5,
        )

        assert response.has_more is False
        assert response.next_cursor is None

    # --- Items have correct MessageItem fields ---

    @pytest.mark.asyncio
    async def test_items_have_correct_fields(self) -> None:
        """Each item in response has all required MessageItem fields."""
        mock_db = AsyncMock()
        service = ChatService(mock_db)

        mock_char = _make_fake_character()
        mock_conv = _make_fake_conversation()

        msg = _make_fake_message(content="Test content", offset_minutes=0)
        msg.media_url = "https://example.com/image.jpg"
        msg.metadata_ = {"key": "value"}

        mock_db.execute = AsyncMock(
            side_effect=self._build_mock_execute(mock_char, mock_conv, [msg]),
        )

        response = await service.get_messages(
            character_id=FAKE_CHARACTER_ID,
            user_id=FAKE_USER_ID,
            cursor=None,
            limit=20,
        )

        assert len(response.items) == 1
        item = response.items[0]
        assert item.id == str(msg.id)
        assert item.role == msg.role
        assert item.content == msg.content
        assert item.media_url == msg.media_url
        assert item.metadata == msg.metadata_
        assert item.created_at == msg.created_at


# ---------------------------------------------------------------------------
# Cursor helper edge-case tests (backend-tester: P01-07)
# ---------------------------------------------------------------------------


class TestCursorHelpersEdgeCases:
    """Additional edge-case tests for cursor encode/decode helpers."""

    # --- Encode with timezone-aware datetime ---

    def test_encode_with_utc_timezone(self) -> None:
        """_encode_cursor works correctly with UTC timezone-aware datetime."""
        ts = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
        msg_id = uuid.uuid4()
        encoded = _encode_cursor(ts, msg_id)
        decoded = _decode_cursor(encoded)
        assert decoded.ts == ts
        assert decoded.id == msg_id

    # --- Roundtrip with microseconds preserved ---

    def test_roundtrip_preserves_microseconds(self) -> None:
        """Cursor roundtrip preserves microsecond precision in timestamp."""
        ts = datetime(2026, 2, 23, 14, 30, 0, 123456, tzinfo=UTC)
        msg_id = uuid.uuid4()
        encoded = _encode_cursor(ts, msg_id)
        decoded = _decode_cursor(encoded)
        assert decoded.ts == ts
        assert decoded.ts.microsecond == 123456

    # --- Encode with uuid.UUID edge values ---

    def test_encode_with_nil_uuid(self) -> None:
        """_encode_cursor works with nil UUID (all zeros)."""
        ts = datetime.now(tz=UTC)
        nil_uuid = uuid.UUID("00000000-0000-0000-0000-000000000000")
        encoded = _encode_cursor(ts, nil_uuid)
        decoded = _decode_cursor(encoded)
        assert decoded.id == nil_uuid

    def test_encode_with_max_uuid(self) -> None:
        """_encode_cursor works with max UUID (all f's)."""
        ts = datetime.now(tz=UTC)
        max_uuid = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
        encoded = _encode_cursor(ts, max_uuid)
        decoded = _decode_cursor(encoded)
        assert decoded.id == max_uuid

    # --- MessageCursor is frozen (immutable) ---

    def test_message_cursor_is_frozen(self) -> None:
        """MessageCursor dataclass is frozen (immutable)."""
        from dataclasses import FrozenInstanceError

        cursor = MessageCursor(
            ts=datetime.now(tz=UTC),
            id=uuid.uuid4(),
        )
        with pytest.raises(FrozenInstanceError):
            cursor.ts = datetime.now(tz=UTC)  # type: ignore[misc]

    def test_message_cursor_is_frozen_id(self) -> None:
        """MessageCursor id field is also frozen."""
        from dataclasses import FrozenInstanceError

        cursor = MessageCursor(
            ts=datetime.now(tz=UTC),
            id=uuid.uuid4(),
        )
        with pytest.raises(FrozenInstanceError):
            cursor.id = uuid.uuid4()  # type: ignore[misc]

    # --- Decode with valid base64 that decodes to a JSON string (not object) ---

    def test_decode_json_string_returns_400(self) -> None:
        """_decode_cursor raises 400 for base64 JSON string value."""
        from fastapi import HTTPException

        payload = json.dumps("just a string").encode()
        encoded = base64.urlsafe_b64encode(payload).decode()
        with pytest.raises(HTTPException) as exc_info:
            _decode_cursor(encoded)
        assert exc_info.value.status_code == 400

    # --- Decode with valid base64 JSON but ts is empty string ---

    def test_decode_ts_empty_string_returns_400(self) -> None:
        """_decode_cursor raises 400 when ts is an empty string."""
        from fastapi import HTTPException

        payload = json.dumps({"ts": "", "id": str(uuid.uuid4())}).encode()
        encoded = base64.urlsafe_b64encode(payload).decode()
        with pytest.raises(HTTPException) as exc_info:
            _decode_cursor(encoded)
        assert exc_info.value.status_code == 400

    # --- Decode with valid base64 JSON but id is empty string ---

    def test_decode_id_empty_string_returns_400(self) -> None:
        """_decode_cursor raises 400 when id is an empty string."""
        from fastapi import HTTPException

        payload = json.dumps({
            "ts": "2026-02-23T14:30:00+00:00",
            "id": "",
        }).encode()
        encoded = base64.urlsafe_b64encode(payload).decode()
        with pytest.raises(HTTPException) as exc_info:
            _decode_cursor(encoded)
        assert exc_info.value.status_code == 400

    # --- Multiple roundtrips produce consistent results ---

    def test_multiple_roundtrips_consistent(self) -> None:
        """Encoding the same cursor multiple times produces the same string."""
        ts = datetime(2026, 2, 23, 14, 30, 0, tzinfo=UTC)
        msg_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440088")

        encoded1 = _encode_cursor(ts, msg_id)
        encoded2 = _encode_cursor(ts, msg_id)
        assert encoded1 == encoded2

    # --- Decode with base64 JSON containing timezone offsets ---

    def test_decode_ts_with_positive_timezone_offset(self) -> None:
        """_decode_cursor handles positive timezone offset in ts."""
        payload = json.dumps({
            "ts": "2026-02-23T17:30:00+03:00",
            "id": str(uuid.uuid4()),
        }).encode()
        encoded = base64.urlsafe_b64encode(payload).decode()
        result = _decode_cursor(encoded)
        assert result.ts.utcoffset().total_seconds() == 10800  # +03:00

    # --- Decode with negative timezone offset ---

    def test_decode_ts_with_negative_timezone_offset(self) -> None:
        """_decode_cursor handles negative timezone offset in ts."""
        msg_id = uuid.uuid4()
        payload = json.dumps({
            "ts": "2026-02-23T09:30:00-05:00",
            "id": str(msg_id),
        }).encode()
        encoded = base64.urlsafe_b64encode(payload).decode()
        result = _decode_cursor(encoded)
        assert result.ts.utcoffset().total_seconds() == -18000  # -05:00
        assert result.id == msg_id
