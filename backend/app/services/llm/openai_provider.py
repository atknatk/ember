"""OpenAI LLM provider implementation (stub).

Minimal implementation that proves the LLMProvider interface with a second
provider. Will be fully implemented when OpenAI fallback is activated.
The openai package must be available in requirements.txt.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from app.services.llm.exceptions import LLMProviderError

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger("ember")


class OpenAIProvider:
    """Concrete LLM provider backed by OpenAI.

    The AsyncOpenAI client is constructed once in __init__ and reused
    across all calls.
    """

    def __init__(self, settings: Settings) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise LLMProviderError(
                message="openai package is not installed",
                code="provider_not_configured",
                provider="openai",
                retryable=False,
            ) from exc

        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._conversation_model = settings.openai_model
        self._fast_model = settings.openai_fast_model

    async def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.8,
    ) -> str:
        """Non-streaming completion via OpenAI."""
        from openai import APIConnectionError, APIError, RateLimitError

        resolved_model = model or self._conversation_model
        all_messages: list[dict[str, str]] = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        try:
            response = await self._client.chat.completions.create(
                model=resolved_model,
                messages=all_messages,  # type: ignore[arg-type]
                max_tokens=max_tokens,
                temperature=temperature,
            )
            content = response.choices[0].message.content
            return content or ""
        except RateLimitError as exc:
            raise LLMProviderError(
                message=f"OpenAI rate limit exceeded: {exc}",
                code="rate_limit_exceeded",
                provider="openai",
                retryable=True,
            ) from exc
        except APIConnectionError as exc:
            raise LLMProviderError(
                message=f"Cannot reach OpenAI API: {exc}",
                code="connection_error",
                provider="openai",
                retryable=True,
            ) from exc
        except APIError as exc:
            raise LLMProviderError(
                message=f"OpenAI API error: {exc}",
                code="provider_error",
                provider="openai",
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
        """Streaming completion via OpenAI. Yields text chunks."""
        from openai import APIConnectionError, APIError, RateLimitError

        resolved_model = model or self._conversation_model
        all_messages: list[dict[str, str]] = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)

        try:
            stream = await self._client.chat.completions.create(
                model=resolved_model,
                messages=all_messages,  # type: ignore[arg-type]
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except RateLimitError as exc:
            raise LLMProviderError(
                message=f"OpenAI rate limit exceeded: {exc}",
                code="rate_limit_exceeded",
                provider="openai",
                retryable=True,
            ) from exc
        except APIConnectionError as exc:
            raise LLMProviderError(
                message=f"Cannot reach OpenAI API: {exc}",
                code="connection_error",
                provider="openai",
                retryable=True,
            ) from exc
        except APIError as exc:
            raise LLMProviderError(
                message=f"OpenAI API error: {exc}",
                code="provider_error",
                provider="openai",
                retryable=False,
            ) from exc

    async def complete_fast(
        self,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> str:
        """Fast/cheap completion using gpt-4o-mini."""
        return await self.complete(
            system=system,
            messages=messages,
            model=self._fast_model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
