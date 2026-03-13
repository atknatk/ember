"""LLM router — selects the active provider based on configuration.

Provides a singleton LLMRouter that holds configured provider instances
and routes requests to the active provider. Follows the same lazy-singleton
pattern as get_mem0_circuit_breaker() in app/core/circuit_breaker.py.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.llm.anthropic_provider import AnthropicProvider
from app.services.llm.exceptions import LLMProviderError
from app.services.llm.openai_provider import OpenAIProvider
from app.services.llm.provider import LLMProvider

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger("ember")


class LLMRouter:
    """Routes LLM requests to the configured provider."""

    def __init__(self, settings: Settings) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._default: str = settings.llm_provider

        # Register providers that have valid API keys
        if settings.anthropic_api_key:
            self._providers["claude"] = AnthropicProvider(settings)
        if settings.openai_api_key:
            self._providers["openai"] = OpenAIProvider(settings)

        if self._default not in self._providers:
            msg = (
                f"Default LLM provider '{self._default}' is not configured. "
                f"Set {self._default.upper()}_API_KEY or change LLM_PROVIDER."
            )
            raise ValueError(msg)

    def get(self, provider: str | None = None) -> LLMProvider:
        """Get a provider instance. None means default."""
        name = provider or self._default
        if name not in self._providers:
            raise LLMProviderError(
                message=f"Provider '{name}' not configured",
                code="provider_not_configured",
                provider=name,
            )
        return self._providers[name]

    @property
    def default_provider_name(self) -> str:
        """Return the name of the default provider."""
        return self._default


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_router_instance: LLMRouter | None = None


def get_llm_router() -> LLMRouter:
    """Return the module-level LLMRouter singleton.

    Creates the router on first call using the global settings.
    """
    global _router_instance  # noqa: PLW0603
    if _router_instance is None:
        from app.config import settings

        _router_instance = LLMRouter(settings)
    return _router_instance
