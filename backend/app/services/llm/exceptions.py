"""LLM provider exceptions.

Provides structured error types for all LLM provider failures, enabling
consumers to distinguish retryable errors (rate limit, connection) from
permanent errors (auth, model not found) without inspecting messages.
"""

from __future__ import annotations


class LLMProviderError(Exception):
    """Raised when an LLM provider call fails.

    Attributes:
        code: Machine-readable error code (e.g. "rate_limit_exceeded").
        provider: Name of the provider that failed (e.g. "claude", "openai").
        retryable: Whether the caller should retry the request.
    """

    def __init__(
        self,
        message: str,
        code: str,
        provider: str = "",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.retryable = retryable
