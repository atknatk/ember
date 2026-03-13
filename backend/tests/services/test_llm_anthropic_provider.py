"""Unit tests for AnthropicProvider.

Tests complete, stream, and complete_fast methods with mocked AsyncAnthropic,
including error wrapping for API errors, rate limits, and connection errors.
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
from anthropic import APIConnectionError, APIError, RateLimitError  # noqa: E402

from app.services.llm.anthropic_provider import AnthropicProvider  # noqa: E402
from app.services.llm.exceptions import LLMProviderError  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings() -> MagicMock:
    """Create a mock Settings object with Anthropic config."""
    s = MagicMock()
    s.anthropic_api_key = "test-key"
    s.claude_model = "claude-sonnet-4-6"
    s.claude_haiku_model = "claude-haiku-4-5"
    return s


def _make_response(text: str = "Hello!") -> MagicMock:
    """Create a mock Anthropic API response."""
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


# ---------------------------------------------------------------------------
# complete tests
# ---------------------------------------------------------------------------


class TestAnthropicComplete:
    """Tests for AnthropicProvider.complete()."""

    @pytest.mark.asyncio
    async def test_complete_happy_path(self) -> None:
        """complete() returns the full response text."""
        settings = _make_settings()
        with patch(
            "app.services.llm.anthropic_provider.AsyncAnthropic",
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                return_value=_make_response("Hello!"),
            )
            mock_cls.return_value = mock_client

            provider = AnthropicProvider(settings)
            result = await provider.complete(
                system="You are helpful.",
                messages=[{"role": "user", "content": "Hi"}],
            )

        assert result == "Hello!"
        mock_client.messages.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_with_explicit_model(self) -> None:
        """complete() uses the overridden model string."""
        settings = _make_settings()
        with patch(
            "app.services.llm.anthropic_provider.AsyncAnthropic",
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                return_value=_make_response("OK"),
            )
            mock_cls.return_value = mock_client

            provider = AnthropicProvider(settings)
            await provider.complete(
                system="Test",
                messages=[{"role": "user", "content": "Hi"}],
                model="claude-opus-4-6",
            )

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "claude-opus-4-6"

    @pytest.mark.asyncio
    async def test_complete_api_error(self) -> None:
        """complete() wraps APIError in LLMProviderError."""
        settings = _make_settings()
        with patch(
            "app.services.llm.anthropic_provider.AsyncAnthropic",
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=APIError(
                    message="Server error",
                    request=MagicMock(),
                    body=None,
                ),
            )
            mock_cls.return_value = mock_client

            provider = AnthropicProvider(settings)
            with pytest.raises(LLMProviderError) as exc_info:
                await provider.complete(
                    system="Test",
                    messages=[{"role": "user", "content": "Hi"}],
                )

        assert exc_info.value.code == "provider_error"
        assert exc_info.value.provider == "claude"

    @pytest.mark.asyncio
    async def test_complete_rate_limit(self) -> None:
        """complete() wraps RateLimitError in LLMProviderError with retryable=True."""
        settings = _make_settings()
        with patch(
            "app.services.llm.anthropic_provider.AsyncAnthropic",
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=RateLimitError(
                    message="Rate limited",
                    response=MagicMock(status_code=429, headers={}),
                    body=None,
                ),
            )
            mock_cls.return_value = mock_client

            provider = AnthropicProvider(settings)
            with pytest.raises(LLMProviderError) as exc_info:
                await provider.complete(
                    system="Test",
                    messages=[{"role": "user", "content": "Hi"}],
                )

        assert exc_info.value.code == "rate_limit_exceeded"
        assert exc_info.value.retryable is True

    @pytest.mark.asyncio
    async def test_complete_connection_error(self) -> None:
        """complete() wraps APIConnectionError in LLMProviderError with retryable=True."""
        settings = _make_settings()
        with patch(
            "app.services.llm.anthropic_provider.AsyncAnthropic",
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=APIConnectionError(request=MagicMock()),
            )
            mock_cls.return_value = mock_client

            provider = AnthropicProvider(settings)
            with pytest.raises(LLMProviderError) as exc_info:
                await provider.complete(
                    system="Test",
                    messages=[{"role": "user", "content": "Hi"}],
                )

        assert exc_info.value.code == "connection_error"
        assert exc_info.value.retryable is True


# ---------------------------------------------------------------------------
# stream tests
# ---------------------------------------------------------------------------


class TestAnthropicStream:
    """Tests for AnthropicProvider.stream()."""

    @pytest.mark.asyncio
    async def test_stream_happy_path(self) -> None:
        """stream() yields all text chunks from the underlying stream."""
        settings = _make_settings()

        mock_stream_ctx = AsyncMock()
        mock_stream_obj = AsyncMock()

        async def _text_iter() -> AsyncGenerator[str, None]:
            for chunk in ["Hello", ", ", "world!"]:
                yield chunk

        mock_stream_obj.text_stream = _text_iter()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_obj)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.llm.anthropic_provider.AsyncAnthropic",
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.stream = MagicMock(
                return_value=mock_stream_ctx,
            )
            mock_cls.return_value = mock_client

            provider = AnthropicProvider(settings)
            chunks: list[str] = []
            async for text in provider.stream(
                system="Test",
                messages=[{"role": "user", "content": "Hi"}],
            ):
                chunks.append(text)

        assert chunks == ["Hello", ", ", "world!"]

    @pytest.mark.asyncio
    async def test_stream_with_explicit_model(self) -> None:
        """stream() passes the overridden model to the client."""
        settings = _make_settings()

        mock_stream_ctx = AsyncMock()
        mock_stream_obj = AsyncMock()

        async def _text_iter() -> AsyncGenerator[str, None]:
            yield "OK"

        mock_stream_obj.text_stream = _text_iter()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_obj)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.services.llm.anthropic_provider.AsyncAnthropic",
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.stream = MagicMock(
                return_value=mock_stream_ctx,
            )
            mock_cls.return_value = mock_client

            provider = AnthropicProvider(settings)
            async for _ in provider.stream(
                system="Test",
                messages=[{"role": "user", "content": "Hi"}],
                model="claude-opus-4-6",
            ):
                pass

        call_kwargs = mock_client.messages.stream.call_args
        assert call_kwargs.kwargs["model"] == "claude-opus-4-6"

    @pytest.mark.asyncio
    async def test_stream_api_error(self) -> None:
        """stream() wraps APIError in LLMProviderError."""
        settings = _make_settings()

        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(
            side_effect=APIError(
                message="Server error",
                request=MagicMock(),
                body=None,
            ),
        )

        with patch(
            "app.services.llm.anthropic_provider.AsyncAnthropic",
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.stream = MagicMock(
                return_value=mock_stream_ctx,
            )
            mock_cls.return_value = mock_client

            provider = AnthropicProvider(settings)
            with pytest.raises(LLMProviderError) as exc_info:
                async for _ in provider.stream(
                    system="Test",
                    messages=[{"role": "user", "content": "Hi"}],
                ):
                    pass

        assert exc_info.value.code == "provider_error"

    @pytest.mark.asyncio
    async def test_stream_rate_limit(self) -> None:
        """stream() wraps RateLimitError with retryable=True."""
        settings = _make_settings()

        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(
            side_effect=RateLimitError(
                message="Rate limited",
                response=MagicMock(status_code=429, headers={}),
                body=None,
            ),
        )

        with patch(
            "app.services.llm.anthropic_provider.AsyncAnthropic",
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.stream = MagicMock(
                return_value=mock_stream_ctx,
            )
            mock_cls.return_value = mock_client

            provider = AnthropicProvider(settings)
            with pytest.raises(LLMProviderError) as exc_info:
                async for _ in provider.stream(
                    system="Test",
                    messages=[{"role": "user", "content": "Hi"}],
                ):
                    pass

        assert exc_info.value.code == "rate_limit_exceeded"
        assert exc_info.value.retryable is True

    @pytest.mark.asyncio
    async def test_stream_connection_error(self) -> None:
        """stream() wraps APIConnectionError with retryable=True."""
        settings = _make_settings()

        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(
            side_effect=APIConnectionError(request=MagicMock()),
        )

        with patch(
            "app.services.llm.anthropic_provider.AsyncAnthropic",
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.stream = MagicMock(
                return_value=mock_stream_ctx,
            )
            mock_cls.return_value = mock_client

            provider = AnthropicProvider(settings)
            with pytest.raises(LLMProviderError) as exc_info:
                async for _ in provider.stream(
                    system="Test",
                    messages=[{"role": "user", "content": "Hi"}],
                ):
                    pass

        assert exc_info.value.code == "connection_error"
        assert exc_info.value.retryable is True


# ---------------------------------------------------------------------------
# complete_fast tests
# ---------------------------------------------------------------------------


class TestAnthropicCompleteFast:
    """Tests for AnthropicProvider.complete_fast()."""

    @pytest.mark.asyncio
    async def test_complete_fast_uses_haiku_model(self) -> None:
        """complete_fast() uses the configured Haiku model."""
        settings = _make_settings()
        with patch(
            "app.services.llm.anthropic_provider.AsyncAnthropic",
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                return_value=_make_response("classified"),
            )
            mock_cls.return_value = mock_client

            provider = AnthropicProvider(settings)
            result = await provider.complete_fast(
                system="",
                messages=[{"role": "user", "content": "classify this"}],
            )

        assert result == "classified"
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "claude-haiku-4-5"
        assert call_kwargs.kwargs["temperature"] == 0.0

    @pytest.mark.asyncio
    async def test_complete_fast_not_conversation_model(self) -> None:
        """complete_fast() uses fast model, NOT the conversation model."""
        settings = _make_settings()
        with patch(
            "app.services.llm.anthropic_provider.AsyncAnthropic",
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                return_value=_make_response("ok"),
            )
            mock_cls.return_value = mock_client

            provider = AnthropicProvider(settings)
            await provider.complete_fast(
                system="",
                messages=[{"role": "user", "content": "test"}],
            )

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["model"] != settings.claude_model


# ---------------------------------------------------------------------------
# Client reuse test
# ---------------------------------------------------------------------------


class TestClientReuse:
    """Verify the AsyncAnthropic client is constructed once."""

    def test_client_constructed_once(self) -> None:
        """AsyncAnthropic is constructed in __init__, not per call."""
        settings = _make_settings()
        with patch(
            "app.services.llm.anthropic_provider.AsyncAnthropic",
        ) as mock_cls:
            mock_cls.return_value = MagicMock()
            _provider = AnthropicProvider(settings)

        mock_cls.assert_called_once_with(api_key="test-key")
