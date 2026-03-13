"""Provider interface contract tests and additional edge case coverage.

Covers:
- LLMProvider ABC cannot be instantiated directly
- LLMProviderError attributes (all codes, retryable semantics)
- OpenAIProvider error paths: RateLimitError, APIConnectionError in complete/stream
- OpenAIProvider ImportError path (package not installed)
- OpenAIProvider response with None content (returns empty string)
- OpenAIProvider stream with chunk that has None delta content (skipped)
- LLMRouter singleton lazy-creation path (creates instance when None)
- ChatService stream_response generic Exception path emits error event
- ChatService _extract_intent uses complete_fast (not complete)
- ChatService _extract_intent with unsupported action returns None
- ChatService _extract_intent with JSON parse error returns None
- ChatService uses injected router on every stream call
- ChatService _llm_router property: override vs lazy get_llm_router
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import pytest  # noqa: E402

from app.services.llm.exceptions import LLMProviderError  # noqa: E402
from app.services.llm.provider import LLMProvider  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers shared across classes
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
FAKE_CHARACTER_ID = uuid.UUID("660e8400-e29b-41d4-a716-446655440001")
FAKE_CONVERSATION_ID = uuid.UUID("880e8400-e29b-41d4-a716-446655440002")


def _make_fake_profile() -> MagicMock:
    profile = MagicMock()
    profile.id = FAKE_USER_ID
    profile.name = "Alex"
    profile.mem0_user_id = f"user_{FAKE_USER_ID}"
    profile.timezone = "America/New_York"
    profile.preferred_language = "en"
    return profile


def _make_fake_character() -> MagicMock:
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
    conv = MagicMock()
    conv.id = FAKE_CONVERSATION_ID
    conv.user_id = FAKE_USER_ID
    conv.character_id = FAKE_CHARACTER_ID
    return conv


def _make_mock_llm_router(
    stream_chunks: list[str] | None = None,
    complete_fast_result: str = "none",
    stream_error: Exception | None = None,
    complete_fast_error: Exception | None = None,
) -> MagicMock:
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
    return {
        "character": _make_fake_character(),
        "conversation": _make_fake_conversation(),
        "system_prompt": "You are Sarah.",
        "formatted_messages": [{"role": "user", "content": "Hello"}],
    }


def _parse_sse_events(sse_lines: list[str]) -> list[dict[str, Any]]:
    events = []
    for line in sse_lines:
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


# ---------------------------------------------------------------------------
# LLMProvider ABC contract tests
# ---------------------------------------------------------------------------


class TestLLMProviderABC:
    """Verify the LLMProvider ABC cannot be used directly."""

    def test_abstract_class_cannot_be_instantiated(self) -> None:
        """LLMProvider is abstract and must not be directly instantiated."""
        with pytest.raises(TypeError):
            LLMProvider()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_all_methods(self) -> None:
        """A class that only implements 'complete' cannot be instantiated."""

        class PartialProvider(LLMProvider):
            async def complete(self, system, messages, model=None, max_tokens=1024, temperature=0.8):
                return ""

            # Missing stream() and complete_fast()

        with pytest.raises(TypeError):
            PartialProvider()  # type: ignore[abstract]

    def test_concrete_subclass_can_be_instantiated_when_all_methods_implemented(self) -> None:
        """A fully implemented subclass can be instantiated."""

        class FullProvider(LLMProvider):
            async def complete(self, system, messages, model=None, max_tokens=1024, temperature=0.8):
                return "ok"

            async def stream(self, system, messages, model=None, max_tokens=1024, temperature=0.8):  # type: ignore[override]
                yield "ok"

            async def complete_fast(self, system, messages, max_tokens=256, temperature=0.0):
                return "fast"

        p = FullProvider()
        assert p is not None


# ---------------------------------------------------------------------------
# LLMProviderError attribute tests
# ---------------------------------------------------------------------------


class TestLLMProviderError:
    """Verify LLMProviderError carries all expected attributes."""

    def test_retryable_defaults_to_false(self) -> None:
        """LLMProviderError.retryable defaults to False."""
        err = LLMProviderError(message="something broke", code="provider_error")
        assert err.retryable is False

    def test_provider_defaults_to_empty_string(self) -> None:
        """LLMProviderError.provider defaults to empty string."""
        err = LLMProviderError(message="something broke", code="provider_error")
        assert err.provider == ""

    def test_rate_limit_is_retryable(self) -> None:
        """rate_limit_exceeded errors must be retryable."""
        err = LLMProviderError(
            message="rate limited",
            code="rate_limit_exceeded",
            provider="claude",
            retryable=True,
        )
        assert err.retryable is True
        assert err.code == "rate_limit_exceeded"

    def test_connection_error_is_retryable(self) -> None:
        """connection_error errors must be retryable."""
        err = LLMProviderError(
            message="cannot reach",
            code="connection_error",
            provider="openai",
            retryable=True,
        )
        assert err.retryable is True

    def test_authentication_error_is_not_retryable(self) -> None:
        """authentication_error must not be retryable."""
        err = LLMProviderError(
            message="invalid key",
            code="authentication_error",
            provider="claude",
            retryable=False,
        )
        assert err.retryable is False

    def test_all_error_codes_are_strings(self) -> None:
        """Verify all spec-defined error codes can be stored without exception."""
        codes = [
            "provider_not_configured",
            "authentication_error",
            "rate_limit_exceeded",
            "model_not_available",
            "context_length_exceeded",
            "connection_error",
            "provider_error",
        ]
        for code in codes:
            err = LLMProviderError(message="test", code=code)
            assert err.code == code

    def test_inherits_from_exception(self) -> None:
        """LLMProviderError must be catchable as a plain Exception."""
        err = LLMProviderError(message="boom", code="provider_error")
        assert isinstance(err, Exception)
        assert str(err) == "boom"


# ---------------------------------------------------------------------------
# OpenAIProvider error path tests (rate limit and connection in complete/stream)
# ---------------------------------------------------------------------------


class TestOpenAIProviderErrorPaths:
    """Additional error path coverage for OpenAIProvider."""

    def _make_provider(self) -> Any:
        """Create an OpenAIProvider bypassing real __init__."""
        with patch(
            "app.services.llm.openai_provider.OpenAIProvider.__init__",
            return_value=None,
        ):
            from app.services.llm.openai_provider import OpenAIProvider

            provider = OpenAIProvider.__new__(OpenAIProvider)
            mock_client = AsyncMock()
            provider._client = mock_client
            provider._conversation_model = "gpt-4o"
            provider._fast_model = "gpt-4o-mini"
            return provider, mock_client

    @pytest.mark.asyncio
    async def test_complete_rate_limit_raises_retryable_error(self) -> None:
        """complete() wraps OpenAI RateLimitError as retryable LLMProviderError."""
        from openai import RateLimitError

        provider, mock_client = self._make_provider()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RateLimitError(
                message="rate limited",
                response=MagicMock(status_code=429, headers={}),
                body=None,
            ),
        )

        with pytest.raises(LLMProviderError) as exc_info:
            await provider.complete(
                system="Test",
                messages=[{"role": "user", "content": "Hi"}],
            )

        assert exc_info.value.code == "rate_limit_exceeded"
        assert exc_info.value.retryable is True
        assert exc_info.value.provider == "openai"

    @pytest.mark.asyncio
    async def test_complete_connection_error_raises_retryable_error(self) -> None:
        """complete() wraps OpenAI APIConnectionError as retryable LLMProviderError."""
        from openai import APIConnectionError

        provider, mock_client = self._make_provider()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=APIConnectionError(request=MagicMock()),
        )

        with pytest.raises(LLMProviderError) as exc_info:
            await provider.complete(
                system="Test",
                messages=[{"role": "user", "content": "Hi"}],
            )

        assert exc_info.value.code == "connection_error"
        assert exc_info.value.retryable is True
        assert exc_info.value.provider == "openai"

    @pytest.mark.asyncio
    async def test_complete_returns_empty_string_when_content_is_none(self) -> None:
        """complete() returns empty string when choices[0].message.content is None."""
        provider, mock_client = self._make_provider()

        choice = MagicMock()
        choice.message.content = None
        response = MagicMock()
        response.choices = [choice]
        mock_client.chat.completions.create = AsyncMock(return_value=response)

        result = await provider.complete(
            system="Test",
            messages=[{"role": "user", "content": "Hi"}],
        )

        assert result == ""

    @pytest.mark.asyncio
    async def test_stream_rate_limit_raises_retryable_error(self) -> None:
        """stream() wraps OpenAI RateLimitError as retryable LLMProviderError."""
        from openai import RateLimitError

        provider, mock_client = self._make_provider()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RateLimitError(
                message="rate limited",
                response=MagicMock(status_code=429, headers={}),
                body=None,
            ),
        )

        with pytest.raises(LLMProviderError) as exc_info:
            async for _ in provider.stream(
                system="Test",
                messages=[{"role": "user", "content": "Hi"}],
            ):
                pass

        assert exc_info.value.code == "rate_limit_exceeded"
        assert exc_info.value.retryable is True
        assert exc_info.value.provider == "openai"

    @pytest.mark.asyncio
    async def test_stream_connection_error_raises_retryable_error(self) -> None:
        """stream() wraps OpenAI APIConnectionError as retryable LLMProviderError."""
        from openai import APIConnectionError

        provider, mock_client = self._make_provider()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=APIConnectionError(request=MagicMock()),
        )

        with pytest.raises(LLMProviderError) as exc_info:
            async for _ in provider.stream(
                system="Test",
                messages=[{"role": "user", "content": "Hi"}],
            ):
                pass

        assert exc_info.value.code == "connection_error"
        assert exc_info.value.retryable is True

    @pytest.mark.asyncio
    async def test_stream_api_error_raises_non_retryable_error(self) -> None:
        """stream() wraps generic OpenAI APIError as non-retryable LLMProviderError."""
        from openai import APIError

        provider, mock_client = self._make_provider()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=APIError(
                message="server error",
                request=MagicMock(),
                body=None,
            ),
        )

        with pytest.raises(LLMProviderError) as exc_info:
            async for _ in provider.stream(
                system="Test",
                messages=[{"role": "user", "content": "Hi"}],
            ):
                pass

        assert exc_info.value.code == "provider_error"
        assert exc_info.value.retryable is False

    @pytest.mark.asyncio
    async def test_stream_skips_chunks_with_none_delta_content(self) -> None:
        """stream() skips chunks where delta.content is None or empty."""

        async def _stream_iter() -> AsyncGenerator[MagicMock, None]:
            # First chunk: real content
            chunk1 = MagicMock()
            chunk1.choices = [MagicMock()]
            chunk1.choices[0].delta.content = "Hello"
            yield chunk1
            # Second chunk: None content (common for stop tokens)
            chunk2 = MagicMock()
            chunk2.choices = [MagicMock()]
            chunk2.choices[0].delta.content = None
            yield chunk2
            # Third chunk: empty choices (should be skipped)
            chunk3 = MagicMock()
            chunk3.choices = []
            yield chunk3

        provider, mock_client = self._make_provider()
        mock_client.chat.completions.create = AsyncMock(return_value=_stream_iter())

        collected: list[str] = []
        async for text in provider.stream(
            system="",
            messages=[{"role": "user", "content": "Hi"}],
        ):
            collected.append(text)

        assert collected == ["Hello"]

    def test_openai_provider_import_error_raises_llm_error(self) -> None:
        """OpenAIProvider __init__ raises LLMProviderError when openai is not installed."""
        import builtins

        real_import = builtins.__import__

        def _mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "openai":
                raise ImportError("No module named 'openai'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_mock_import):
            from app.services.llm.openai_provider import OpenAIProvider

            settings = MagicMock()
            settings.openai_api_key = "test-key"
            settings.openai_model = "gpt-4o"
            settings.openai_fast_model = "gpt-4o-mini"

            with pytest.raises(LLMProviderError) as exc_info:
                OpenAIProvider(settings)

        assert exc_info.value.code == "provider_not_configured"
        assert exc_info.value.provider == "openai"
        assert exc_info.value.retryable is False

    def test_openai_provider_init_stores_models_from_settings(self) -> None:
        """OpenAIProvider.__init__ stores conversation and fast models from settings.

        Exercises lines 40-42 (client construction and attribute assignment).
        """
        import openai

        settings = MagicMock()
        settings.openai_api_key = "sk-test-key"
        settings.openai_model = "gpt-4o"
        settings.openai_fast_model = "gpt-4o-mini"

        from app.services.llm.openai_provider import OpenAIProvider

        mock_client = MagicMock()
        with patch.object(openai, "AsyncOpenAI", return_value=mock_client) as mock_cls:
            provider = OpenAIProvider(settings)

        # Verify the client was constructed with the API key
        mock_cls.assert_called_once_with(api_key="sk-test-key")
        # Verify model attributes were stored
        assert provider._conversation_model == "gpt-4o"
        assert provider._fast_model == "gpt-4o-mini"
        assert provider._client is mock_client


# ---------------------------------------------------------------------------
# LLMRouter singleton lazy creation path
# ---------------------------------------------------------------------------


class TestLLMRouterSingleton:
    """Verify the get_llm_router() lazy-creation path."""

    def test_get_llm_router_creates_instance_when_none(self) -> None:
        """get_llm_router() creates a new LLMRouter when _router_instance is None."""
        import app.services.llm.router as router_module

        original = router_module._router_instance
        try:
            router_module._router_instance = None

            mock_settings = MagicMock()
            mock_settings.llm_provider = "claude"
            mock_settings.anthropic_api_key = "test-key"
            mock_settings.openai_api_key = ""
            mock_settings.claude_model = "claude-sonnet-4-6"
            mock_settings.claude_haiku_model = "claude-haiku-4-5"
            mock_settings.openai_model = "gpt-4o"
            mock_settings.openai_fast_model = "gpt-4o-mini"

            # settings is imported lazily inside get_llm_router() from app.config
            with (
                patch("app.services.llm.anthropic_provider.AsyncAnthropic"),
                patch("app.config.settings", mock_settings),
            ):
                instance = router_module.get_llm_router()
                assert instance is not None
                assert isinstance(instance, router_module.LLMRouter)
                # Second call must return same instance (caching)
                instance2 = router_module.get_llm_router()
                assert instance is instance2
        finally:
            router_module._router_instance = original

    def test_get_llm_router_reuses_existing_instance(self) -> None:
        """get_llm_router() does NOT create a new router when one already exists."""
        import app.services.llm.router as router_module

        original = router_module._router_instance
        try:
            sentinel = MagicMock(spec=router_module.LLMRouter)
            router_module._router_instance = sentinel

            result = router_module.get_llm_router()
            assert result is sentinel
        finally:
            router_module._router_instance = original


# ---------------------------------------------------------------------------
# ChatService integration with injected router
# ---------------------------------------------------------------------------


class TestChatServiceRouterIntegration:
    """Tests for ChatService integration with the LLM router."""

    @pytest.mark.asyncio
    async def test_stream_response_uses_injected_router(self) -> None:
        """stream_response calls self._llm_router.get() — not AsyncAnthropic directly."""
        from app.services.chat_service import ChatService

        mock_db = AsyncMock()
        mock_router = _make_mock_llm_router(stream_chunks=["Test"])
        service = ChatService(mock_db, llm_router=mock_router)
        ctx = _make_valid_context()

        with (
            patch.object(service, "_extract_intent", return_value=None),
            patch("app.services.chat_service._persist_exchange"),
        ):
            async for _ in service.stream_response(
                context=ctx,
                user_id=FAKE_USER_ID,
                profile=_make_fake_profile(),
                content="Hello",
                media_url=None,
            ):
                pass

        mock_router.get.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_stream_response_generic_exception_emits_error_event(self) -> None:
        """Generic (non-LLMProviderError) exception during stream emits error event."""
        from app.services.chat_service import ChatService

        mock_db = AsyncMock()
        # Raise a plain RuntimeError (not LLMProviderError) to exercise the
        # second except branch in stream_response
        mock_router = _make_mock_llm_router(
            stream_error=RuntimeError("Unexpected failure"),
        )
        service = ChatService(mock_db, llm_router=mock_router)
        ctx = _make_valid_context()

        sse_lines: list[str] = []
        async for event in service.stream_response(
            context=ctx,
            user_id=FAKE_USER_ID,
            profile=_make_fake_profile(),
            content="Hello",
            media_url=None,
        ):
            sse_lines.append(event)

        events = _parse_sse_events(sse_lines)
        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert "unavailable" in events[0]["message"].lower()

    @pytest.mark.asyncio
    async def test_stream_response_error_event_message_is_user_safe(self) -> None:
        """Error event message must not expose internal error details."""
        from app.services.chat_service import ChatService

        from app.services.llm.exceptions import LLMProviderError

        mock_db = AsyncMock()
        mock_router = _make_mock_llm_router(
            stream_error=LLMProviderError(
                "SECRET_API_KEY=abc123 exposed",
                code="provider_error",
                provider="claude",
            ),
        )
        service = ChatService(mock_db, llm_router=mock_router)
        ctx = _make_valid_context()

        sse_lines: list[str] = []
        async for event in service.stream_response(
            context=ctx,
            user_id=FAKE_USER_ID,
            profile=_make_fake_profile(),
            content="Hello",
            media_url=None,
        ):
            sse_lines.append(event)

        events = _parse_sse_events(sse_lines)
        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        # Must NOT leak the raw exception message
        assert "SECRET_API_KEY" not in error_events[0]["message"]
        assert "abc123" not in error_events[0]["message"]

    @pytest.mark.asyncio
    async def test_extract_intent_uses_complete_fast_not_complete(self) -> None:
        """_extract_intent calls complete_fast(), never complete()."""
        from app.services.chat_service import ChatService

        mock_db = AsyncMock()
        mock_router = _make_mock_llm_router(complete_fast_result="none")
        mock_provider = mock_router.get.return_value
        # Track whether complete() was called
        mock_provider.complete = AsyncMock(return_value="should not be called")

        service = ChatService(mock_db, llm_router=mock_router)
        result = await service._extract_intent("Just a response.", "UTC")

        assert result is None
        # complete() must never be called for intent extraction
        mock_provider.complete.assert_not_called()
        mock_provider.complete_fast.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_intent_with_unsupported_action_returns_none(self) -> None:
        """_extract_intent returns None when action is not in SUPPORTED_ACTIONS."""
        from app.services.chat_service import ChatService

        unsupported_action = json.dumps(
            {"action": "SEND_EMAIL", "payload": {"to": "user@example.com"}}
        )
        mock_db = AsyncMock()
        mock_router = _make_mock_llm_router(complete_fast_result=unsupported_action)
        service = ChatService(mock_db, llm_router=mock_router)

        result = await service._extract_intent("I'll email you.", "UTC")

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_intent_with_malformed_json_returns_none(self) -> None:
        """_extract_intent returns None when Haiku returns invalid JSON."""
        from app.services.chat_service import ChatService

        mock_db = AsyncMock()
        mock_router = _make_mock_llm_router(
            complete_fast_result='{"action": "SET_ALARM", "payload": {broken json',
        )
        service = ChatService(mock_db, llm_router=mock_router)

        result = await service._extract_intent("Set alarm for 7.", "UTC")

        assert result is None

    @pytest.mark.asyncio
    async def test_extract_intent_with_add_calendar_event(self) -> None:
        """_extract_intent recognizes ADD_CALENDAR_EVENT action."""
        from app.services.chat_service import ChatService

        calendar_json = json.dumps({
            "action": "ADD_CALENDAR_EVENT",
            "payload": {
                "title": "Team meeting",
                "date": "2026-03-14",
                "time": "10:00",
                "duration": 60,
            },
        })
        mock_db = AsyncMock()
        mock_router = _make_mock_llm_router(complete_fast_result=calendar_json)
        service = ChatService(mock_db, llm_router=mock_router)

        result = await service._extract_intent(
            "I'll add your team meeting to the calendar.", "UTC"
        )

        assert result is not None
        assert result["action"] == "ADD_CALENDAR_EVENT"
        assert result["payload"]["title"] == "Team meeting"

    @pytest.mark.asyncio
    async def test_stream_response_done_event_always_last(self) -> None:
        """done event is always the final SSE event in a successful stream."""
        from app.services.chat_service import ChatService

        mock_db = AsyncMock()
        mock_router = _make_mock_llm_router(
            stream_chunks=["Hello", " world"],
            complete_fast_result=json.dumps({
                "action": "SET_ALARM",
                "payload": {"time": "07:00"},
            }),
        )
        service = ChatService(mock_db, llm_router=mock_router)
        ctx = _make_valid_context()

        with patch("app.services.chat_service._persist_exchange"):
            sse_lines: list[str] = []
            async for event in service.stream_response(
                context=ctx,
                user_id=FAKE_USER_ID,
                profile=_make_fake_profile(),
                content="Set an alarm for 7am",
                media_url=None,
            ):
                sse_lines.append(event)

        events = _parse_sse_events(sse_lines)
        assert events[-1]["type"] == "done"

    @pytest.mark.asyncio
    async def test_stream_response_event_sequence_chunk_action_done(self) -> None:
        """SSE stream must produce: chunk(s) → action → done (when action detected)."""
        from app.services.chat_service import ChatService

        mock_db = AsyncMock()
        mock_router = _make_mock_llm_router(
            stream_chunks=["I'll set that alarm."],
        )
        service = ChatService(mock_db, llm_router=mock_router)
        ctx = _make_valid_context()

        with (
            patch.object(
                service,
                "_extract_intent",
                return_value={"action": "SET_ALARM", "payload": {"time": "07:00"}},
            ),
            patch("app.services.chat_service._persist_exchange"),
        ):
            sse_lines: list[str] = []
            async for event in service.stream_response(
                context=ctx,
                user_id=FAKE_USER_ID,
                profile=_make_fake_profile(),
                content="Set alarm for 7",
                media_url=None,
            ):
                sse_lines.append(event)

        events = _parse_sse_events(sse_lines)
        types = [e["type"] for e in events]

        # All chunks come before action/done
        last_chunk_idx = max(
            (i for i, e in enumerate(events) if e["type"] == "chunk"),
            default=-1,
        )
        action_indices = [i for i, e in enumerate(events) if e["type"] == "action"]
        done_indices = [i for i, e in enumerate(events) if e["type"] == "done"]

        assert len(action_indices) == 1
        assert len(done_indices) == 1
        assert action_indices[0] > last_chunk_idx
        assert done_indices[0] > action_indices[0]
        assert types[-1] == "done"

    def test_chat_service_uses_override_router_not_singleton(self) -> None:
        """ChatService with injected llm_router never calls get_llm_router()."""
        from app.services.chat_service import ChatService

        mock_db = AsyncMock()
        mock_router = MagicMock()
        service = ChatService(mock_db, llm_router=mock_router)

        with patch("app.services.chat_service.get_llm_router") as mock_singleton:
            # Access the property
            router = service._llm_router
            # Should have used the override, not the singleton
            assert router is mock_router
            mock_singleton.assert_not_called()

    def test_chat_service_uses_singleton_when_no_router_provided(self) -> None:
        """ChatService without injected router calls get_llm_router() on access."""
        from app.services.chat_service import ChatService

        mock_db = AsyncMock()
        service = ChatService(mock_db)  # No llm_router

        mock_singleton_router = MagicMock()
        with patch(
            "app.services.chat_service.get_llm_router",
            return_value=mock_singleton_router,
        ) as mock_singleton:
            router = service._llm_router
            assert router is mock_singleton_router
            mock_singleton.assert_called_once()
