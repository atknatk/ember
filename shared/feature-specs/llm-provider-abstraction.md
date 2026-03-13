# Feature Spec: LLM Provider Abstraction (P1.5-05)

**Feature ID**: P1.5-05
**Layer**: backend
**Issue**: #87
**Dependencies**: P01-06 (chat-streaming)
**Date**: 2026-03-13

---

## 1. Overview

### What this feature does

Implements ADR-006 (multi-provider LLM) by extracting all direct `AsyncAnthropic` usage from `chat_service.py` into a provider abstraction layer. Introduces three new components:

1. **`LLMProvider`** -- an abstract base class defining the interface all LLM providers must implement (`complete` for non-streaming, `stream` for streaming).
2. **`AnthropicProvider`** -- concrete implementation wrapping `AsyncAnthropic` with Ember's conventions (model pinning from config, structured error handling, observability integration).
3. **`LLMRouter`** -- a singleton that holds configured provider instances and routes requests to the active provider based on `settings.llm_provider`.

After this refactoring, `chat_service.py` calls `llm_router.get().stream(...)` and `llm_router.get("fast").complete(...)` instead of constructing `AsyncAnthropic` clients directly. Adding future providers (OpenAI, Google) means implementing the two-method `LLMProvider` interface -- no changes to chat_service or any other consumer.

### Why it exists

- **Single point of failure**: Today if Anthropic's API goes down, all chat is broken. The abstraction enables operational failover by switching `LLM_PROVIDER` env var.
- **Cost optimization**: Different tasks need different models. The router codifies model-tier routing (conversation vs. fast) so cheap tasks use cheap models.
- **Testability**: Mocking a thin `LLMProvider` interface is far simpler than mocking `AsyncAnthropic` internals with streaming context managers.
- **ADR compliance**: ADR-006 was accepted but never implemented. This closes that gap.

### Which existing features it depends on or extends

- Extends P01-06 (chat-streaming): `chat_service.py` is the primary consumer.
- Uses the existing `app/config.py` settings (`llm_provider`, `claude_model`, `claude_haiku_model`, `anthropic_api_key`, `openai_api_key`, `openai_model`).
- Integrates with the existing `app/utils/timing.py` observability via `log_external_call`.

---

## 2. Data Models

No database changes. This feature is a pure service-layer refactoring. No new tables, no ALTER TABLE statements, no new indexes.

No Mem0 changes. Mem0 operations remain in `chat_service.py` and `memory_service.py` untouched.

---

## 3. API Endpoints

No new API endpoints. No changes to existing endpoint signatures or response shapes. This is an internal refactoring that preserves the exact same external behavior.

The SSE event sequence for `POST /api/v1/characters/:id/messages` remains unchanged:
- `{"type":"chunk","content":"..."}` (repeated)
- `{"type":"action","action":"...","payload":{}}` (optional)
- `{"type":"done","message_id":"..."}`
- `{"type":"error","message":"..."}` (on failure)

---

## 4. Backend Logic

### 4.1 LLMProvider Abstract Base Class

**File**: `backend/app/services/llm/provider.py`

```
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
    async def stream(
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
        """Fast/cheap completion for classification tasks (intent extraction, etc.).
        Uses the provider's fast/cheap model automatically."""
```

Design notes:
- `model` parameter on `complete` and `stream` defaults to `None`, meaning "use the provider's configured conversation model." Callers CAN override for specific use cases.
- `complete_fast` does NOT accept a `model` parameter. The provider picks its own fast model from config. This prevents callers from accidentally routing expensive tasks to cheap models or vice versa.
- The `messages` list uses the common `{"role": "user"|"assistant", "content": "..."}` format. Provider implementations translate this to provider-specific formats internally.
- Both `complete` and `stream` accept a `system` parameter as a separate string (not embedded in messages). Anthropic uses a dedicated `system` parameter; OpenAI prepends it as a system message. Each provider handles this translation.

### 4.2 AnthropicProvider

**File**: `backend/app/services/llm/anthropic_provider.py`

Responsibilities:
- Wraps `AsyncAnthropic` from the `anthropic` package.
- Reads `settings.anthropic_api_key` for client construction.
- Uses `settings.claude_model` as the default conversation model.
- Uses `settings.claude_haiku_model` as the fast model.
- `stream()` uses `client.messages.stream()` async context manager and yields from `.text_stream`.
- `complete()` uses `client.messages.create()` and returns `response.content[0].text`.
- `complete_fast()` calls `complete()` with the Haiku model, low max_tokens, and temperature 0.
- All external calls wrapped in `log_external_call("claude", ...)` for observability.
- On `anthropic.APIError` or `anthropic.APIConnectionError`, raises `LLMProviderError` (see section 4.5).
- The `AsyncAnthropic` client is constructed once in `__init__` and reused (it manages its own connection pool).

Method details:

**`__init__(self, settings: Settings)`**
- Stores settings reference.
- Creates `self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)`.
- Stores `self._conversation_model = settings.claude_model`.
- Stores `self._fast_model = settings.claude_haiku_model`.

**`async def stream(...) -> AsyncIterator[str]`**
- Resolves model: `model or self._conversation_model`.
- Calls `self._client.messages.stream(model=..., system=system, messages=messages, max_tokens=max_tokens)`.
- Wraps in `log_external_call("claude", "stream")`.
- Catches `anthropic.APIError`, `anthropic.APIConnectionError`, and `anthropic.RateLimitError` and wraps them in `LLMProviderError` with appropriate error codes.

**`async def complete(...) -> str`**
- Resolves model: `model or self._conversation_model`.
- Calls `self._client.messages.create(model=..., system=system, messages=messages, max_tokens=max_tokens)`.
- Wraps in `log_external_call("claude", "create")`.
- Returns `response.content[0].text`.

**`async def complete_fast(...) -> str`**
- Delegates to an internal `_complete` that calls `self._client.messages.create(model=self._fast_model, ...)`.
- Uses `temperature=0.0` for deterministic classification.

### 4.3 OpenAIProvider (Stub)

**File**: `backend/app/services/llm/openai_provider.py`

This file is a minimal stub that will be fully implemented when OpenAI fallback is activated. It exists now so that:
- The router can validate the `LLM_PROVIDER=openai` config path.
- The interface contract is proven with two implementations.
- Future developers have a template.

Responsibilities:
- Wraps `openai.AsyncOpenAI`.
- Reads `settings.openai_api_key` for client construction.
- Uses `settings.openai_model` as the default conversation model (currently `gpt-4o`).
- For the fast model, uses `gpt-4o-mini` (new config field, see section 4.6).
- Translates the `system` parameter into a system message prepended to the messages list (OpenAI format).
- `stream()` uses `client.chat.completions.create(stream=True)` and yields `chunk.choices[0].delta.content`.
- `complete()` uses non-streaming `client.chat.completions.create()`.
- `complete_fast()` routes to `gpt-4o-mini`.

Note: The `openai` package is already listed in `requirements.txt` for future use. If it is not, it should be added as a dependency.

### 4.4 LLMRouter

**File**: `backend/app/services/llm/router.py`

```
class LLMRouter:
    """Routes LLM requests to the configured provider."""

    def __init__(self, settings: Settings) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._default: str = settings.llm_provider

        # Always register providers with valid API keys
        if settings.anthropic_api_key:
            self._providers["claude"] = AnthropicProvider(settings)
        if settings.openai_api_key:
            self._providers["openai"] = OpenAIProvider(settings)

        if self._default not in self._providers:
            raise ValueError(
                f"Default LLM provider '{self._default}' is not configured. "
                f"Set {self._default.upper()}_API_KEY or change LLM_PROVIDER."
            )

    def get(self, provider: str | None = None) -> LLMProvider:
        """Get a provider instance. None means default."""
        name = provider or self._default
        if name not in self._providers:
            raise LLMProviderError(
                f"Provider '{name}' not configured",
                code="provider_not_configured",
            )
        return self._providers[name]

    @property
    def default_provider_name(self) -> str:
        return self._default
```

**Singleton pattern**: The router is created once at app startup and injected via FastAPI dependency. A module-level factory function provides the singleton:

```
_router_instance: LLMRouter | None = None

def get_llm_router() -> LLMRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = LLMRouter(settings)
    return _router_instance
```

This follows the same pattern as `get_mem0_circuit_breaker()` in `app/core/circuit_breaker.py`.

### 4.5 Error Handling

**File**: `backend/app/services/llm/exceptions.py`

```
class LLMProviderError(Exception):
    """Raised when an LLM provider call fails."""

    def __init__(self, message: str, code: str, provider: str = "", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.retryable = retryable
```

Error code taxonomy:

| Code | Meaning | Retryable | HTTP mapping |
|------|---------|-----------|--------------|
| `provider_not_configured` | API key missing or provider unknown | No | 503 |
| `authentication_error` | API key invalid | No | 503 |
| `rate_limit_exceeded` | Provider rate limit hit | Yes | 503 |
| `model_not_available` | Requested model does not exist | No | 503 |
| `context_length_exceeded` | Input too long for model | No | 400 |
| `connection_error` | Cannot reach provider API | Yes | 503 |
| `provider_error` | Generic provider-side error | Yes | 503 |

Providers catch their SDK-specific exceptions and wrap them in `LLMProviderError` with the appropriate code. Consumers (like `chat_service.py`) catch `LLMProviderError` and translate to user-facing errors.

### 4.6 Config Changes

**File**: `backend/app/config.py`

One new setting added to the `Settings` class:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `openai_fast_model` | `str` | `"gpt-4o-mini"` | OpenAI model for fast/cheap operations |

The following existing settings are already present and remain unchanged:
- `llm_provider: str = "claude"`
- `claude_model: str = "claude-sonnet-4-6"`
- `claude_haiku_model: str = "claude-haiku-4-5"`
- `anthropic_api_key: str = ""`
- `openai_api_key: str = ""`
- `openai_model: str = "gpt-4o"`

### 4.7 Refactoring chat_service.py

The following changes are made to `backend/app/services/chat_service.py`:

**Remove**: `from anthropic import AsyncAnthropic` import.

**Add**: `from app.services.llm.router import get_llm_router`

**Constructor change**: `ChatService.__init__` gains an optional `llm_router` parameter:

```
def __init__(self, db: AsyncSession, llm_router: LLMRouter | None = None) -> None:
    self.db = db
    self._llm_router = llm_router or get_llm_router()
```

**`stream_response` method changes**:
- Replace the `AsyncAnthropic` client construction and `client.messages.stream()` block with:
  ```
  provider = self._llm_router.get()
  async for text in provider.stream(
      system=system_prompt,
      messages=formatted_messages,
      max_tokens=2048,
  ):
      full_response += text
      event = ChunkEvent(content=text)
      yield f"data: {event.model_dump_json()}\n\n"
  ```
- The `except Exception` block catches `LLMProviderError` specifically (in addition to general exceptions) and emits the same `ErrorEvent`.

**`_extract_intent` method changes**:
- Replace the `AsyncAnthropic` client construction and `client.messages.create()` call with:
  ```
  provider = self._llm_router.get()
  raw_text = await provider.complete_fast(
      system="",
      messages=[{"role": "user", "content": prompt}],
      max_tokens=256,
      temperature=0.0,
  )
  ```
- The intent extraction prompt is passed as a user message (not system). The `system` parameter is empty string.
- Error handling remains the same (catch Exception, log, return None).

### 4.8 Package Structure

The LLM abstraction lives in a new sub-package under services:

```
backend/app/services/llm/
    __init__.py          -- re-exports LLMProvider, LLMRouter, get_llm_router, LLMProviderError
    provider.py          -- LLMProvider ABC
    anthropic_provider.py -- AnthropicProvider implementation
    openai_provider.py   -- OpenAIProvider stub implementation
    router.py            -- LLMRouter + get_llm_router() singleton
    exceptions.py        -- LLMProviderError
```

The `__init__.py` re-exports public names so consumers can write:
```
from app.services.llm import LLMProvider, LLMRouter, get_llm_router, LLMProviderError
```

---

## 5. iOS Screens and Components

Not applicable. This is a backend-only feature. No mobile changes.

---

## 6. Android Screens and Components

Not applicable. This is a backend-only feature. No mobile changes.

---

## 7. Test Plan

### Backend Tests

#### Unit Tests: AnthropicProvider

**File**: `backend/tests/services/test_llm_anthropic_provider.py`

| Scenario | What to test |
|----------|-------------|
| `stream` happy path | Mock `AsyncAnthropic.messages.stream()` to yield 3 chunks. Verify all 3 chunks are yielded by provider. |
| `stream` with explicit model | Verify the mock receives the overridden model string. |
| `stream` API error | Mock raises `anthropic.APIError`. Verify `LLMProviderError` is raised with `code="provider_error"`. |
| `stream` rate limit | Mock raises `anthropic.RateLimitError`. Verify `LLMProviderError` with `code="rate_limit_exceeded"` and `retryable=True`. |
| `stream` connection error | Mock raises `anthropic.APIConnectionError`. Verify `LLMProviderError` with `code="connection_error"` and `retryable=True`. |
| `complete` happy path | Mock `AsyncAnthropic.messages.create()` returning a response. Verify full text is returned. |
| `complete` API error | Same error wrapping as stream. |
| `complete_fast` happy path | Verify the Haiku model is used (from config), temperature is 0.0. |
| `complete_fast` uses fast model | Verify the mock receives `settings.claude_haiku_model`, not `settings.claude_model`. |
| Client reuse | Verify `AsyncAnthropic` is constructed once in `__init__`, not per call. |

**Mocking strategy**: Mock `anthropic.AsyncAnthropic` at the import level using `unittest.mock.patch`. For streaming, create a mock async context manager that yields from a list.

#### Unit Tests: OpenAIProvider

**File**: `backend/tests/services/test_llm_openai_provider.py`

| Scenario | What to test |
|----------|-------------|
| `complete` happy path | Mock `openai.AsyncOpenAI.chat.completions.create()`. Verify response text extraction. |
| `complete` system message prepend | Verify the system string is prepended as `{"role": "system", "content": system}` to the messages list. |
| `stream` happy path | Mock streaming response. Verify chunks yielded. |
| `complete_fast` uses fast model | Verify `gpt-4o-mini` is used. |
| Error wrapping | Verify OpenAI exceptions are wrapped in `LLMProviderError`. |

#### Unit Tests: LLMRouter

**File**: `backend/tests/services/test_llm_router.py`

| Scenario | What to test |
|----------|-------------|
| Default provider | Create router with `llm_provider="claude"` and valid `anthropic_api_key`. `get()` returns `AnthropicProvider`. |
| Explicit provider | `get("openai")` returns `OpenAIProvider` when `openai_api_key` is set. |
| Missing provider | `get("openai")` raises `LLMProviderError` when `openai_api_key` is empty. |
| Invalid default | Constructor raises `ValueError` when `llm_provider="gemini"` and no Gemini key exists. |
| Singleton | Two calls to `get_llm_router()` return the same instance. |

**Mocking strategy**: Create a `Settings` mock/override with controlled API keys and provider names.

#### Integration Tests: chat_service.py refactoring

**File**: Modify existing `backend/tests/services/test_chat.py`

| Scenario | What to test |
|----------|-------------|
| `stream_response` uses provider | Mock `LLMRouter.get().stream()` instead of `AsyncAnthropic`. Verify SSE events are yielded. |
| `_extract_intent` uses provider | Mock `LLMRouter.get().complete_fast()`. Verify intent parsing still works. |
| Provider error mid-stream | Mock provider stream to raise `LLMProviderError`. Verify error SSE event is emitted. |

**Mocking strategy**: Pass a mock `LLMRouter` to `ChatService.__init__` via the new `llm_router` parameter.

#### Tests NOT needed

- No route-level tests needed (no endpoint changes).
- No auth failure tests needed (no new endpoints).
- No Mem0 mock changes (Mem0 code is untouched).

---

## 8. Acceptance Criteria

1. Given a running backend with `LLM_PROVIDER=claude` and a valid `ANTHROPIC_API_KEY`, when a user sends `POST /api/v1/characters/:id/messages`, then the SSE response streams normally with no behavioral change from the previous implementation.

2. Given `chat_service.py`, when inspecting the import statements, then there is NO direct import of `anthropic.AsyncAnthropic` -- all LLM calls go through `LLMProvider`.

3. Given a test that mocks `LLMRouter`, when `ChatService` is instantiated with the mock router, then streaming and intent extraction use the mock provider, proving the abstraction is injectable.

4. Given `LLM_PROVIDER=openai` and a valid `OPENAI_API_KEY`, when the LLMRouter is constructed, then `get()` returns an `OpenAIProvider` instance without errors.

5. Given an `AnthropicProvider` instance, when `stream()` is called, then the underlying `AsyncAnthropic` client is the one created in `__init__` (not a new client per call).

6. Given an `AnthropicProvider` instance, when `complete_fast()` is called, then the model used is `settings.claude_haiku_model` (not the conversation model).

7. Given an Anthropic API rate limit error during streaming, when the provider catches it, then a `LLMProviderError` is raised with `code="rate_limit_exceeded"` and `retryable=True`.

8. Given `chat_service.stream_response()`, when an `LLMProviderError` is raised by the provider, then an SSE error event `{"type":"error","message":"AI service temporarily unavailable"}` is emitted (same behavior as before).

9. Given the `LLMRouter` constructor with `llm_provider="gemini"` and no Gemini API key, when instantiated, then a `ValueError` is raised with a descriptive message.

10. Given all existing chat-related tests, when run against the refactored code, then they pass (possibly with updated mocks) with no regressions.

---

## 9. File Manifest

```
Backend:
  CREATE  backend/app/services/llm/__init__.py
  CREATE  backend/app/services/llm/provider.py
  CREATE  backend/app/services/llm/anthropic_provider.py
  CREATE  backend/app/services/llm/openai_provider.py
  CREATE  backend/app/services/llm/router.py
  CREATE  backend/app/services/llm/exceptions.py
  MODIFY  backend/app/services/chat_service.py (remove AsyncAnthropic, use LLMRouter)
  MODIFY  backend/app/config.py (add openai_fast_model)
  CREATE  backend/tests/services/test_llm_anthropic_provider.py
  CREATE  backend/tests/services/test_llm_openai_provider.py
  CREATE  backend/tests/services/test_llm_router.py
  MODIFY  backend/tests/services/test_chat.py (update mocks to use LLMRouter)

Shared:
  CREATE  shared/feature-specs/llm-provider-abstraction.md (this file)
  CREATE  docs/pipeline/llm-provider-abstraction-architect.handoff.md
```
