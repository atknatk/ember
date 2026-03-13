"""Unit tests for LLMRouter.

Tests provider registration, default provider selection, missing provider
handling, invalid defaults, and the singleton pattern.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from app.services.llm.exceptions import LLMProviderError  # noqa: E402
from app.services.llm.router import LLMRouter  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(
    llm_provider: str = "claude",
    anthropic_api_key: str = "test-anthropic-key",
    openai_api_key: str = "",
    claude_model: str = "claude-sonnet-4-6",
    claude_haiku_model: str = "claude-haiku-4-5",
    openai_model: str = "gpt-4o",
    openai_fast_model: str = "gpt-4o-mini",
) -> MagicMock:
    """Create a mock Settings object."""
    s = MagicMock()
    s.llm_provider = llm_provider
    s.anthropic_api_key = anthropic_api_key
    s.openai_api_key = openai_api_key
    s.claude_model = claude_model
    s.claude_haiku_model = claude_haiku_model
    s.openai_model = openai_model
    s.openai_fast_model = openai_fast_model
    return s


# ---------------------------------------------------------------------------
# LLMRouter tests
# ---------------------------------------------------------------------------


class TestLLMRouter:
    """Tests for LLMRouter."""

    def test_default_provider_is_claude(self) -> None:
        """Router with claude default returns AnthropicProvider."""
        from app.services.llm.anthropic_provider import AnthropicProvider
        from app.services.llm.router import LLMRouter

        settings = _make_settings()
        with patch(
            "app.services.llm.anthropic_provider.AsyncAnthropic",
        ):
            router = LLMRouter(settings)
            provider = router.get()

        assert isinstance(provider, AnthropicProvider)

    def test_explicit_provider_openai(self) -> None:
        """get('openai') returns OpenAIProvider when configured."""
        from app.services.llm.openai_provider import OpenAIProvider
        from app.services.llm.router import LLMRouter

        settings = _make_settings(openai_api_key="test-openai-key")
        with (
            patch("app.services.llm.anthropic_provider.AsyncAnthropic"),
            patch("app.services.llm.openai_provider.OpenAIProvider.__init__", return_value=None),
        ):
            router = LLMRouter(settings)
            provider = router.get("openai")

        assert isinstance(provider, OpenAIProvider)

    def test_missing_provider_raises_error(self) -> None:
        """get('openai') raises LLMProviderError when not configured."""
        from app.services.llm.router import LLMRouter

        settings = _make_settings(openai_api_key="")
        with patch(
            "app.services.llm.anthropic_provider.AsyncAnthropic",
        ):
            router = LLMRouter(settings)

        with pytest.raises(LLMProviderError) as exc_info:
            router.get("openai")

        assert exc_info.value.code == "provider_not_configured"

    def test_invalid_default_raises_value_error(self) -> None:
        """Constructor raises ValueError when default provider is not configured."""
        from app.services.llm.router import LLMRouter

        settings = _make_settings(
            llm_provider="gemini",
            anthropic_api_key="",
            openai_api_key="",
        )
        with pytest.raises(ValueError, match="gemini"):
            LLMRouter(settings)

    def test_default_provider_name_property(self) -> None:
        """default_provider_name returns the configured default."""
        from app.services.llm.router import LLMRouter

        settings = _make_settings()
        with patch(
            "app.services.llm.anthropic_provider.AsyncAnthropic",
        ):
            router = LLMRouter(settings)

        assert router.default_provider_name == "claude"


# ---------------------------------------------------------------------------
# Singleton tests
# ---------------------------------------------------------------------------


class TestGetLlmRouter:
    """Tests for the get_llm_router() singleton."""

    def test_singleton_returns_same_instance(self) -> None:
        """Two calls to get_llm_router() return the same instance."""
        import app.services.llm.router as router_module

        # Reset singleton
        router_module._router_instance = None

        settings = _make_settings()
        with patch("app.services.llm.anthropic_provider.AsyncAnthropic"):
            # Manually set the singleton to test the caching behavior
            router_module._router_instance = LLMRouter(settings)
            r1 = router_module.get_llm_router()
            r2 = router_module.get_llm_router()

        assert r1 is r2

        # Cleanup
        router_module._router_instance = None
