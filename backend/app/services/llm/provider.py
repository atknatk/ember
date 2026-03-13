"""Abstract base class for LLM providers.

Defines the interface that all LLM providers must implement: `complete`
for non-streaming, `stream` for streaming, and `complete_fast` for
fast/cheap classification tasks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMProvider(ABC):
    """Abstract interface for all LLM providers."""

    @abstractmethod
    async def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.8,
    ) -> str:
        """Non-streaming completion. Returns the full response text."""

    @abstractmethod
    def stream(
        self,
        system: str,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.8,
    ) -> AsyncIterator[str]:
        """Streaming completion. Yields text chunks as they arrive."""

    @abstractmethod
    async def complete_fast(
        self,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> str:
        """Fast/cheap completion for classification tasks.

        Uses the provider's fast/cheap model automatically. Callers
        should NOT specify a model — the provider picks its own fast
        model from config.
        """
