"""Unit tests for OpenAIProvider.

Tests complete, stream, and complete_fast methods with mocked AsyncOpenAI,
including system message prepending and error wrapping.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

from collections.abc import AsyncGenerator  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from app.services.llm.exceptions import LLMProviderError  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings() -> MagicMock:
    """Create a mock Settings object with OpenAI config."""
    s = MagicMock()
    s.openai_api_key = "test-openai-key"
    s.openai_model = "gpt-4o"
    s.openai_fast_model = "gpt-4o-mini"
    return s


def _make_completion_response(text: str = "Hello!") -> MagicMock:
    """Create a mock OpenAI completion response."""
    choice = MagicMock()
    choice.message.content = text
    response = MagicMock()
    response.choices = [choice]
    return response


# ---------------------------------------------------------------------------
# complete tests
# ---------------------------------------------------------------------------


class TestOpenAIComplete:
    """Tests for OpenAIProvider.complete()."""

    @pytest.mark.asyncio
    async def test_complete_happy_path(self) -> None:
        """complete() returns the full response text."""
        settings = _make_settings()
        with patch(
            "app.services.llm.openai_provider.OpenAIProvider.__init__",
            return_value=None,
        ):
            from app.services.llm.openai_provider import OpenAIProvider

            provider = OpenAIProvider.__new__(OpenAIProvider)
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=_make_completion_response("Hello!"),
            )
            provider._client = mock_client
            provider._conversation_model = "gpt-4o"
            provider._fast_model = "gpt-4o-mini"

            result = await provider.complete(
                system="You are helpful.",
                messages=[{"role": "user", "content": "Hi"}],
            )

        assert result == "Hello!"

    @pytest.mark.asyncio
    async def test_complete_prepends_system_message(self) -> None:
        """complete() prepends system as a system message."""
        settings = _make_settings()
        with patch(
            "app.services.llm.openai_provider.OpenAIProvider.__init__",
            return_value=None,
        ):
            from app.services.llm.openai_provider import OpenAIProvider

            provider = OpenAIProvider.__new__(OpenAIProvider)
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=_make_completion_response("OK"),
            )
            provider._client = mock_client
            provider._conversation_model = "gpt-4o"
            provider._fast_model = "gpt-4o-mini"

            await provider.complete(
                system="Be helpful",
                messages=[{"role": "user", "content": "Hi"}],
            )

        call_args = mock_client.chat.completions.create.call_args
        passed_messages = call_args.kwargs["messages"]
        assert passed_messages[0] == {"role": "system", "content": "Be helpful"}
        assert passed_messages[1] == {"role": "user", "content": "Hi"}

    @pytest.mark.asyncio
    async def test_complete_empty_system_skips_prepend(self) -> None:
        """complete() does not prepend system message when system is empty."""
        with patch(
            "app.services.llm.openai_provider.OpenAIProvider.__init__",
            return_value=None,
        ):
            from app.services.llm.openai_provider import OpenAIProvider

            provider = OpenAIProvider.__new__(OpenAIProvider)
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=_make_completion_response("OK"),
            )
            provider._client = mock_client
            provider._conversation_model = "gpt-4o"
            provider._fast_model = "gpt-4o-mini"

            await provider.complete(
                system="",
                messages=[{"role": "user", "content": "Hi"}],
            )

        call_args = mock_client.chat.completions.create.call_args
        passed_messages = call_args.kwargs["messages"]
        assert len(passed_messages) == 1
        assert passed_messages[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_complete_error_wrapping(self) -> None:
        """complete() wraps OpenAI errors in LLMProviderError."""
        from openai import APIError

        with patch(
            "app.services.llm.openai_provider.OpenAIProvider.__init__",
            return_value=None,
        ):
            from app.services.llm.openai_provider import OpenAIProvider

            provider = OpenAIProvider.__new__(OpenAIProvider)
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                side_effect=APIError(
                    message="Server error",
                    request=MagicMock(),
                    body=None,
                ),
            )
            provider._client = mock_client
            provider._conversation_model = "gpt-4o"
            provider._fast_model = "gpt-4o-mini"

            with pytest.raises(LLMProviderError) as exc_info:
                await provider.complete(
                    system="Test",
                    messages=[{"role": "user", "content": "Hi"}],
                )

        assert exc_info.value.code == "provider_error"
        assert exc_info.value.provider == "openai"


# ---------------------------------------------------------------------------
# stream tests
# ---------------------------------------------------------------------------


class TestOpenAIStream:
    """Tests for OpenAIProvider.stream()."""

    @pytest.mark.asyncio
    async def test_stream_happy_path(self) -> None:
        """stream() yields text chunks."""
        with patch(
            "app.services.llm.openai_provider.OpenAIProvider.__init__",
            return_value=None,
        ):
            from app.services.llm.openai_provider import OpenAIProvider

            provider = OpenAIProvider.__new__(OpenAIProvider)
            mock_client = AsyncMock()

            chunks_data = ["Hello", ", ", "world!"]

            async def _stream_iter() -> AsyncGenerator[MagicMock, None]:
                for text in chunks_data:
                    chunk = MagicMock()
                    choice = MagicMock()
                    choice.delta.content = text
                    chunk.choices = [choice]
                    yield chunk

            mock_client.chat.completions.create = AsyncMock(
                return_value=_stream_iter(),
            )
            provider._client = mock_client
            provider._conversation_model = "gpt-4o"
            provider._fast_model = "gpt-4o-mini"

            collected: list[str] = []
            async for text in provider.stream(
                system="Test",
                messages=[{"role": "user", "content": "Hi"}],
            ):
                collected.append(text)

        assert collected == ["Hello", ", ", "world!"]


# ---------------------------------------------------------------------------
# complete_fast tests
# ---------------------------------------------------------------------------


class TestOpenAICompleteFast:
    """Tests for OpenAIProvider.complete_fast()."""

    @pytest.mark.asyncio
    async def test_complete_fast_uses_mini_model(self) -> None:
        """complete_fast() uses gpt-4o-mini."""
        with patch(
            "app.services.llm.openai_provider.OpenAIProvider.__init__",
            return_value=None,
        ):
            from app.services.llm.openai_provider import OpenAIProvider

            provider = OpenAIProvider.__new__(OpenAIProvider)
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(
                return_value=_make_completion_response("classified"),
            )
            provider._client = mock_client
            provider._conversation_model = "gpt-4o"
            provider._fast_model = "gpt-4o-mini"

            result = await provider.complete_fast(
                system="",
                messages=[{"role": "user", "content": "classify"}],
            )

        assert result == "classified"
        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4o-mini"
