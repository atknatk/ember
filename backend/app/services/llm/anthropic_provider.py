"""Anthropic Claude LLM provider implementation.

Wraps AsyncAnthropic with Ember's conventions: model pinning from config,
structured error handling via LLMProviderError, and observability via
log_external_call.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from anthropic import APIConnectionError, APIError, AsyncAnthropic, RateLimitError

from app.services.llm.exceptions import LLMProviderError
from app.utils.timing import log_external_call

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger("ember")


class AnthropicProvider:
    """Concrete LLM provider backed by Anthropic Claude.

    The AsyncAnthropic client is constructed once in __init__ and reused
    across all calls (it manages its own httpx connection pool).
    """

    def __init__(self, settings: Settings) -> None:
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._conversation_model = settings.claude_model
        self._fast_model = settings.claude_haiku_model

    async def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.8,
    ) -> str:
        """Non-streaming completion via Claude."""
        resolved_model = model or self._conversation_model
        try:
            async with log_external_call("claude", "create"):
                response = await self._client.messages.create(
                    model=resolved_model,
                    system=system,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            return response.content[0].text
        except RateLimitError as exc:
            raise LLMProviderError(
                message=f"Claude rate limit exceeded: {exc}",
                code="rate_limit_exceeded",
                provider="claude",
                retryable=True,
            ) from exc
        except APIConnectionError as exc:
            raise LLMProviderError(
                message=f"Cannot reach Claude API: {exc}",
                code="connection_error",
                provider="claude",
                retryable=True,
            ) from exc
        except APIError as exc:
            raise LLMProviderError(
                message=f"Claude API error: {exc}",
                code="provider_error",
                provider="claude",
                retryable=False,
            ) from exc

    async def stream(  # type: ignore[override]
        self,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.8,
    ) -> AsyncIterator[str]:
        """Streaming completion via Claude. Yields text chunks."""
        resolved_model = model or self._conversation_model
        try:
            async with log_external_call("claude", "stream"):
                async with self._client.messages.stream(
                    model=resolved_model,
                    system=system,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                ) as stream:
                    async for text in stream.text_stream:
                        yield text
        except RateLimitError as exc:
            raise LLMProviderError(
                message=f"Claude rate limit exceeded: {exc}",
                code="rate_limit_exceeded",
                provider="claude",
                retryable=True,
            ) from exc
        except APIConnectionError as exc:
            raise LLMProviderError(
                message=f"Cannot reach Claude API: {exc}",
                code="connection_error",
                provider="claude",
                retryable=True,
            ) from exc
        except APIError as exc:
            raise LLMProviderError(
                message=f"Claude API error: {exc}",
                code="provider_error",
                provider="claude",
                retryable=False,
            ) from exc

    async def complete_fast(
        self,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> str:
        """Fast/cheap completion using Claude Haiku."""
        return await self.complete(
            system=system,
            messages=messages,
            model=self._fast_model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
