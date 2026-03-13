# LLM Provider Abstraction

> Decouples all LLM API calls from a direct Anthropic dependency into a provider-agnostic interface, enabling operational failover and cleaner testability without changing any external behavior.

**Status**: Released
**Added in**: Phase 1.5 (P1.5-05)
**Platforms**: Backend
**GitHub Issue**: #87

---

## Overview

Before this feature, `chat_service.py` imported and constructed `AsyncAnthropic` directly. Every LLM call was tightly coupled to one vendor: if Anthropic's API was unavailable, all chat was broken with no fallback path. Mocking streaming in tests required recreating `AsyncAnthropic`'s internal async context manager machinery, making test setup fragile and verbose.

This feature introduces a thin abstraction layer that sits between the service layer and the LLM vendors. A `LLMProvider` abstract base class defines three operations — non-streaming completion, streaming completion, and fast/cheap completion for classification tasks. `AnthropicProvider` implements this interface for Claude. `OpenAIProvider` provides a working stub for GPT-4o. An `LLMRouter` singleton, configured by the `LLM_PROVIDER` environment variable, holds the active provider instances and routes calls to the correct one.

The refactoring is strictly internal: no API endpoints change, no database tables are touched, and the SSE event sequence seen by mobile clients is identical. The only observable difference is that switching LLM providers now requires changing one environment variable (`LLM_PROVIDER`) rather than modifying Python source code. This closes ADR-006, which specified the multi-provider strategy but had not been implemented.

---

## Architecture

### How It Works (Data Flow)

**Streaming chat message (default: Anthropic)**:

1. The iOS or Android client sends `POST /api/v1/characters/{character_id}/messages` with a JWT and a message body.
2. The route handler creates a `ChatService(db)` instance. No explicit `llm_router` is passed.
3. On first access to `ChatService._llm_router`, the lazy property calls `get_llm_router()`, which constructs an `LLMRouter(settings)` singleton on first call and caches it.
4. `LLMRouter.__init__` reads `settings.llm_provider` (default `"claude"`) and `settings.anthropic_api_key`. It creates an `AnthropicProvider(settings)` instance and stores it under the key `"claude"`.
5. `ChatService.stream_response()` calls `self._llm_router.get()` to retrieve the default `AnthropicProvider`.
6. It calls `provider.stream(system=system_prompt, messages=formatted_messages, max_tokens=2048)`.
7. `AnthropicProvider.stream()` opens `self._client.messages.stream(...)` using the single `AsyncAnthropic` client constructed in `__init__`. It yields text chunks from `.text_stream`.
8. The service wraps each chunk as a `ChunkEvent` and yields `data: {...}\n\n` SSE events to the client.
9. After the full response, the service emits a `done` event and persists both messages to PostgreSQL.
10. `ChatService._extract_intent()` uses `self._llm_router.get().complete_fast(...)` for intent classification. This internally resolves to `AnthropicProvider.complete_fast()`, which calls `complete()` with `settings.claude_haiku_model` and `temperature=0.0`.

**Provider error during streaming**:

1. The Anthropic SDK raises a `RateLimitError`, `APIConnectionError`, or `APIError` inside `AnthropicProvider.stream()`.
2. The provider catches it and raises `LLMProviderError` with a structured `code` and `retryable` flag.
3. `ChatService.stream_response()` catches `LLMProviderError` (and generic `Exception`) and emits `{"type":"error","message":"AI service temporarily unavailable"}` as the final SSE event.

### Package Structure

All LLM abstraction code lives in `backend/app/services/llm/`:

| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports `LLMProvider`, `LLMRouter`, `get_llm_router`, `LLMProviderError` |
| `provider.py` | `LLMProvider` ABC with three abstract methods |
| `anthropic_provider.py` | `AnthropicProvider` — concrete Anthropic Claude implementation |
| `openai_provider.py` | `OpenAIProvider` — working OpenAI stub implementation |
| `router.py` | `LLMRouter` class and `get_llm_router()` singleton factory |
| `exceptions.py` | `LLMProviderError` with structured error codes |

Consumers import from the package root:

```python
from app.services.llm import LLMProvider, LLMRouter, get_llm_router, LLMProviderError
```

### LLMProvider Interface

`LLMProvider` is a Python ABC (`abc.ABC`) with three abstract methods. The `stream` method is declared as a regular method returning `AsyncIterator[str]` rather than as an abstract async generator; concrete implementations use `async def` with `yield`, which Python's ABC system handles correctly. The interface is:

```python
class LLMProvider(ABC):
    async def complete(self, system, messages, model=None, max_tokens=1024, temperature=0.8) -> str: ...
    def stream(self, system, messages, model=None, max_tokens=1024, temperature=0.8) -> AsyncIterator[str]: ...
    async def complete_fast(self, system, messages, max_tokens=256, temperature=0.0) -> str: ...
```

Design choices:
- `complete` and `stream` accept an optional `model` override. Passing `None` uses the provider's configured conversation model.
- `complete_fast` does not accept a `model` parameter. The provider picks its fast/cheap model from config. This prevents callers from accidentally routing expensive tasks through the cheap tier or vice versa.
- The `system` prompt is a separate string, not embedded in the `messages` list. `AnthropicProvider` passes it as the Anthropic-native `system` parameter. `OpenAIProvider` prepends `{"role": "system", "content": system}` to the messages list before the API call.

### LLMRouter Singleton

`LLMRouter` is constructed once per process via `get_llm_router()`, which caches the instance in a module-level `_router_instance` variable. This is the same pattern as `get_mem0_circuit_breaker()` in `app/core/circuit_breaker.py`.

The router's `__init__` registers providers conditionally:
- `AnthropicProvider` is registered as `"claude"` if `settings.anthropic_api_key` is non-empty.
- `OpenAIProvider` is registered as `"openai"` if `settings.openai_api_key` is non-empty.

If the configured default provider (`settings.llm_provider`) is not registered (because its API key is missing), the constructor raises `ValueError` at startup, surfacing the misconfiguration early rather than failing on the first chat request.

`LLMRouter.get(provider=None)` returns the `LLMProvider` for the given name, or the default if `None` is passed. If the requested provider was not registered, it raises `LLMProviderError(code="provider_not_configured")`.

### AnthropicProvider

`AnthropicProvider` constructs a single `AsyncAnthropic` client in `__init__` and reuses it for all calls. The `AsyncAnthropic` client manages its own `httpx` connection pool; creating it per-request wastes resources and was the pre-refactoring behavior in `chat_service.py`.

Model assignments from config:
- `self._conversation_model = settings.claude_model` — defaults to `"claude-sonnet-4-6"`
- `self._fast_model = settings.claude_haiku_model` — defaults to `"claude-haiku-4-5"`

All external calls are wrapped in `log_external_call("claude", "stream")` or `log_external_call("claude", "create")` from `app/utils/timing.py` for observability.

### OpenAIProvider

`OpenAIProvider` is a complete, functional implementation of the interface for OpenAI's Chat Completions API, but it is considered a stub in the sense that it has not been validated against a live OpenAI endpoint in production. It imports `openai.AsyncOpenAI` lazily inside `__init__`; if the `openai` package is not installed, it raises `LLMProviderError(code="provider_not_configured")` immediately rather than at call time.

Model assignments:
- `self._conversation_model = settings.openai_model` — defaults to `"gpt-4o"`
- `self._fast_model = settings.openai_fast_model` — defaults to `"gpt-4o-mini"` (new config field added in this feature)

### Error Handling

`LLMProviderError` carries structured metadata beyond the exception message:

| Field | Type | Purpose |
|-------|------|---------|
| `code` | `str` | Machine-readable error category |
| `provider` | `str` | Which provider raised the error (`"claude"`, `"openai"`, `""`) |
| `retryable` | `bool` | Whether the caller should retry the request |

Error code taxonomy:

| Code | Meaning | Retryable |
|------|---------|-----------|
| `provider_not_configured` | API key missing or provider unknown | No |
| `authentication_error` | API key rejected by provider | No |
| `rate_limit_exceeded` | Provider rate limit hit | Yes |
| `model_not_available` | Requested model does not exist | No |
| `context_length_exceeded` | Input too long for model | No |
| `connection_error` | Cannot reach provider API | Yes |
| `provider_error` | Generic provider-side error | Yes |

`chat_service.py` catches `LLMProviderError` along with the general `Exception` branch and emits the same user-safe SSE error event in both cases. The structured error data is available for future logic (e.g., retrying only when `retryable=True`).

### ChatService Integration

`ChatService.__init__` accepts an optional `llm_router: LLMRouter | None = None` parameter. If a router is injected, it is used directly. If `None`, the `_llm_router` lazy property calls `get_llm_router()` on first access. This avoids breaking tests that create `ChatService(mock_db)` for methods that do not touch the LLM (e.g., `get_messages`, `_build_system_prompt`).

Changes to `chat_service.py`:
- Removed: `from anthropic import AsyncAnthropic`
- Added: `from app.services.llm.router import get_llm_router`
- `stream_response`: replaced inline `AsyncAnthropic` client creation with `self._llm_router.get().stream(...)`
- `_extract_intent`: replaced inline `AsyncAnthropic.messages.create()` with `self._llm_router.get().complete_fast(...)`

### Configuration

| Environment Variable | Config Field | Type | Default | Description |
|---------------------|-------------|------|---------|-------------|
| `LLM_PROVIDER` | `llm_provider` | `str` | `"claude"` | Active provider (`"claude"` or `"openai"`) |
| `CLAUDE_MODEL` | `claude_model` | `str` | `"claude-sonnet-4-6"` | Anthropic conversation model |
| `CLAUDE_HAIKU_MODEL` | `claude_haiku_model` | `str` | `"claude-haiku-4-5"` | Anthropic fast model |
| `ANTHROPIC_API_KEY` | `anthropic_api_key` | `str` | `""` | Required when `LLM_PROVIDER=claude` |
| `OPENAI_MODEL` | `openai_model` | `str` | `"gpt-4o"` | OpenAI conversation model |
| `OPENAI_FAST_MODEL` | `openai_fast_model` | `str` | `"gpt-4o-mini"` | OpenAI fast model (new in P1.5-05) |
| `OPENAI_API_KEY` | `openai_api_key` | `str` | `""` | Required when `LLM_PROVIDER=openai` |

---

## API Reference

No new endpoints. No changes to existing endpoint signatures or response shapes. The SSE event sequence for `POST /api/v1/characters/{character_id}/messages` is identical before and after this refactoring:

```
data: {"type": "chunk", "content": "Hello"}
data: {"type": "chunk", "content": " there!"}
data: {"type": "action", "action": "ADD_CALENDAR_EVENT", "payload": {...}}  (optional)
data: {"type": "done", "message_id": "uuid", "tokens_used": 42}
```

On LLM failure:

```
data: {"type": "error", "message": "AI service temporarily unavailable"}
```

See [`docs/04-veri-api.md`](../04-veri-api.md) for the full chat endpoint contract.

---

## iOS Implementation

Not applicable. This is a backend-only internal refactoring. iOS clients call the same SSE endpoint and observe no behavioral difference.

---

## Android Implementation

Not applicable. This is a backend-only internal refactoring. Android clients call the same SSE endpoint and observe no behavioral difference.

---

## Testing

### Coverage Summary

| File | Statements | Missed | Coverage |
|------|-----------|--------|----------|
| `app/services/llm/__init__.py` | 4 | 0 | 100% |
| `app/services/llm/anthropic_provider.py` | 40 | 0 | 100% |
| `app/services/llm/exceptions.py` | 7 | 0 | 100% |
| `app/services/llm/openai_provider.py` | 52 | 0 | 100% |
| `app/services/llm/provider.py` | 10 | 0 | 100% |
| `app/services/llm/router.py` | 33 | 0 | 100% |

Target was >= 80% lines / >= 70% branches. All six files reached 100%.

### Test Files

| File | Tests | What It Covers |
|------|-------|----------------|
| `backend/tests/services/test_llm_anthropic_provider.py` | 10 | `AnthropicProvider`: stream/complete/complete_fast happy paths, model override, all error wrapping paths, client reuse |
| `backend/tests/services/test_llm_openai_provider.py` | 6 | `OpenAIProvider`: complete/stream/complete_fast, system message prepend, ImportError path |
| `backend/tests/services/test_llm_router.py` | 6 | `LLMRouter`: default/explicit provider selection, missing provider, invalid default, singleton reuse |
| `backend/tests/services/test_llm_provider_contract.py` | 32 | ABC contract, `LLMProviderError` all error codes, OpenAI error paths, singleton lazy-creation, ChatService router integration |
| `backend/tests/services/test_chat.py` | updated | All existing chat tests updated to mock `LLMRouter` instead of `AsyncAnthropic` |

### Running Tests

LLM abstraction tests only:

```bash
cd backend && python -m pytest tests/services/test_llm_anthropic_provider.py tests/services/test_llm_openai_provider.py tests/services/test_llm_router.py tests/services/test_llm_provider_contract.py -v
```

Full backend suite:

```bash
cd backend && python -m pytest tests/ -v
```

### Key Testing Patterns

**Injecting a mock router**: Pass a mock `LLMRouter` to `ChatService.__init__` via the `llm_router` parameter. This avoids patching module-level globals:

```python
mock_router = MagicMock(spec=LLMRouter)
service = ChatService(db=mock_db, llm_router=mock_router)
```

**Mocking AnthropicProvider**: Patch `app.services.llm.anthropic_provider.AsyncAnthropic` at the import level, not at `anthropic.AsyncAnthropic`. The provider imports directly.

**Mocking OpenAIProvider**: The `openai` import is lazy (inside `__init__`). Tests for the `ImportError` path must patch `builtins.__import__`.

**Singleton reset**: The module-level `_router_instance` in `router.py` must be reset to `None` in test teardown to prevent state from leaking between tests. Unlike the circuit breaker, there is no autouse fixture for this — each LLM router test manages its own reset.

---

## Known Limitations

- **OpenAIProvider is untested against a live endpoint**: The stub is functionally complete and passes all unit tests with mocks, but has not been exercised against the OpenAI API in a staging or production environment. Switching `LLM_PROVIDER=openai` should be treated as experimental until a live validation pass is done.
- **No automatic failover at runtime**: The router does not automatically switch providers when the active one fails. A `LLMProviderError` propagates to `chat_service.py`, which emits an error SSE event. Failover requires manually changing `LLM_PROVIDER` and redeploying (or restarting the ECS task).
- **Singleton state is per ECS task**: Like the rate limiter (P1.5-01) and circuit breaker (P1.5-04), the `LLMRouter` singleton is in-process. All tasks share nothing at runtime. If `LLM_PROVIDER` is changed via environment variable, all tasks must be recycled to pick up the new value.
- **Implementation deviation from spec**: The spec describes `ChatService.__init__` as eagerly calling `get_llm_router()`. The implementation uses a lazy property instead. This avoids breaking existing tests that construct `ChatService(mock_db)` for methods that never touch the LLM. The behavior is functionally equivalent for production usage.

---

## Extending This Feature

**Adding a new provider (e.g., Google Gemini)**: Create `backend/app/services/llm/gemini_provider.py` implementing the `LLMProvider` ABC (all three methods). Register it in `LLMRouter.__init__` under a key (e.g., `"gemini"`) when `settings.gemini_api_key` is non-empty. Add `GEMINI_API_KEY` and `GEMINI_MODEL` to `backend/app/config.py`. Set `LLM_PROVIDER=gemini` in the environment. No changes to `chat_service.py` or any other consumer are required.

**Activating automatic runtime failover**: Override `ChatService.stream_response()` to catch `LLMProviderError` with `retryable=True`, call `self._llm_router.get("openai")` as a fallback, and retry the stream. The structured `retryable` flag on `LLMProviderError` is designed for exactly this use case.

**Switching providers in a test**: Construct `LLMRouter` with a custom `Settings` mock that sets `llm_provider`, `anthropic_api_key`, and `openai_api_key` to the desired values. Or inject a mock provider directly into a mock router via `mock_router.get.return_value = my_mock_provider`.

**Observing which provider handled a request**: `LLMProviderError.provider` carries the provider name on failure. For success paths, add a structured log line inside each provider's `stream` or `complete` method using `logger.info("llm_call", provider=..., model=..., tokens=...)`. The observability stack (P1.5-03) will capture this automatically via `structlog`.

---

## Related Documentation

- [ADR-006: Multi-Provider LLM](../adr/ADR-006-multi-provider-llm.md) — the architectural decision this feature implements
- [Chat Streaming](./chat-streaming.md) — P01-06, the primary consumer of the LLM provider abstraction
- [Database Schema and API Endpoints](../04-veri-api.md) — full API contract for the chat endpoint
- [AI Memory System](../05-ai-bellek.md) — Mem0 integration context for `ChatService`
- [Observability Stack](./observability-stack.md) — P1.5-03, `log_external_call` used by `AnthropicProvider`
- [Mem0 Circuit Breaker](./mem0-circuit-breaker.md) — P1.5-04, the parallel singleton pattern `get_llm_router()` follows
