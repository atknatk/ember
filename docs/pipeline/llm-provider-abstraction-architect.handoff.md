# Architect Handoff: LLM Provider Abstraction

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

A service-layer refactoring that implements ADR-006 by extracting all direct `AsyncAnthropic` usage from `chat_service.py` into a `LLMProvider` abstract interface, an `AnthropicProvider` concrete implementation, an `OpenAIProvider` stub, and an `LLMRouter` singleton that selects the active provider based on the `LLM_PROVIDER` environment variable. No API endpoints, database tables, or mobile code are affected.

## Key Decisions

- **Three-method interface (`complete`, `stream`, `complete_fast`)**: ADR-006 shows two methods, but Ember already uses two model tiers (Sonnet for conversation, Haiku for intent extraction). `complete_fast` encapsulates the fast/cheap model choice inside the provider so callers never pick the wrong model tier.
- **Provider constructs client once in `__init__`**: The `AsyncAnthropic` client manages its own connection pool. Creating it per-request (as the current code does) wastes resources. The provider holds a single client instance.
- **OpenAI stub, not full implementation**: ADR-006 specifies OpenAI as Phase 1 fallback, but the priority is getting the abstraction in place. The stub proves the interface with two implementations and gives future developers a template. Full OpenAI integration is a separate task.
- **LLMRouter as lazy singleton via `get_llm_router()`**: Follows the same pattern as `get_mem0_circuit_breaker()` in `app/core/circuit_breaker.py`. Avoids app-startup dependency ordering issues.
- **Injectable via constructor**: `ChatService.__init__` accepts an optional `llm_router` parameter, enabling unit tests to inject a mock without patching module-level globals.
- **`LLMProviderError` with structured codes**: Enables consumers to distinguish retryable errors (rate limit, connection) from permanent errors (auth, model not found) without inspecting exception messages.
- **No new API endpoints or database changes**: This is a pure internal refactoring. External behavior is identical.

## Spec Location

`shared/feature-specs/llm-provider-abstraction.md`

## Assumptions Made

- The `anthropic` package's `AsyncAnthropic` client is safe to construct once and reuse across multiple concurrent calls (it manages its own httpx connection pool).
- The `openai` package (`openai.AsyncOpenAI`) is either already in `requirements.txt` or will be added as part of this feature.
- The existing `settings.claude_haiku_model` value `"claude-haiku-4-5"` is the correct Haiku model identifier for fast operations.
- The `stream()` method on `AnthropicProvider` can be implemented as an `async def` returning an `AsyncIterator[str]` using `async for` over `client.messages.stream().text_stream`.

## Dependencies

- Requires: P01-06 (chat-streaming) -- `chat_service.py` must exist with the current structure
- Blocks: backend-dev (implements the refactoring), backend-tester (writes/updates tests)

## File Manifest

```
Backend:
  CREATE  backend/app/services/llm/__init__.py
  CREATE  backend/app/services/llm/provider.py
  CREATE  backend/app/services/llm/anthropic_provider.py
  CREATE  backend/app/services/llm/openai_provider.py
  CREATE  backend/app/services/llm/router.py
  CREATE  backend/app/services/llm/exceptions.py
  MODIFY  backend/app/services/chat_service.py
  MODIFY  backend/app/config.py
  CREATE  backend/tests/services/test_llm_anthropic_provider.py
  CREATE  backend/tests/services/test_llm_openai_provider.py
  CREATE  backend/tests/services/test_llm_router.py
  MODIFY  backend/tests/services/test_chat.py

Shared:
  CREATE  shared/feature-specs/llm-provider-abstraction.md
  CREATE  docs/pipeline/llm-provider-abstraction-architect.handoff.md
```

## Notes for Developers

- **Package structure**: All LLM code goes under `backend/app/services/llm/`. The `__init__.py` re-exports public names so consumers import from `app.services.llm`.
- **Streaming pattern**: `AnthropicProvider.stream()` must be an async generator (using `yield`), not return a pre-built iterator. This ensures the `async with client.messages.stream()` context manager stays open while chunks are being consumed.
- **Error wrapping**: Catch `anthropic.APIError`, `anthropic.APIConnectionError`, `anthropic.RateLimitError` in the provider. Wrap each in `LLMProviderError` with the appropriate `code` and `retryable` flag.
- **Testing the singleton**: Tests that need a clean `LLMRouter` should either inject via constructor or reset the module-level `_router_instance` to `None` in teardown.
- **OpenAI system message**: OpenAI does not have a separate `system` parameter. Prepend `{"role": "system", "content": system}` to the messages list before calling `chat.completions.create()`.

## Next Steps

backend-dev should read the spec at `shared/feature-specs/llm-provider-abstraction.md` and implement the refactoring. backend-tester follows with test coverage.
