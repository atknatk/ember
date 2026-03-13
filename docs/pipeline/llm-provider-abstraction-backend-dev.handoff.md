# Backend Dev Handoff: LLM Provider Abstraction

**Date**: 2026-03-13
**Agent**: backend-dev
**Status**: COMPLETE

## Implemented Files
- `backend/app/services/llm/__init__.py` -- re-exports public names (LLMProvider, LLMRouter, get_llm_router, LLMProviderError)
- `backend/app/services/llm/provider.py` -- LLMProvider ABC with 3 abstract methods
- `backend/app/services/llm/anthropic_provider.py` -- AnthropicProvider implementation
- `backend/app/services/llm/openai_provider.py` -- OpenAIProvider stub implementation
- `backend/app/services/llm/router.py` -- LLMRouter + get_llm_router() singleton
- `backend/app/services/llm/exceptions.py` -- LLMProviderError with structured error codes
- `backend/app/services/chat_service.py` -- MODIFIED: removed AsyncAnthropic, uses LLMRouter
- `backend/app/config.py` -- MODIFIED: added openai_fast_model setting
- `backend/requirements.txt` -- MODIFIED: added openai>=1.0.0 dependency
- `backend/tests/services/test_llm_anthropic_provider.py` -- 10 tests
- `backend/tests/services/test_llm_openai_provider.py` -- 6 tests
- `backend/tests/services/test_llm_router.py` -- 6 tests
- `backend/tests/services/test_chat.py` -- MODIFIED: updated all mocks from AsyncAnthropic to LLMRouter

## Endpoints Implemented
No new endpoints. This is a pure internal refactoring. All existing endpoints behave identically.

## Test Results
- pytest: 1720 passed, 13 skipped, 0 failed
- ruff: clean (0 errors)
- No hardcoded secrets found

## Known Issues / Deviations from Spec
- The `LLMProvider` ABC's `stream()` method is declared as a regular method returning `AsyncIterator[str]` rather than an `@abstractmethod` async generator, because Python's ABC system does not support abstract async generators cleanly. Concrete implementations use `async def stream(...) -> AsyncIterator[str]` with `yield` and it works correctly.
- `ChatService.__init__` uses a lazy property for `_llm_router` instead of eagerly calling `get_llm_router()` in the constructor. This avoids breaking existing tests that create `ChatService(mock_db)` without providing an LLM router (e.g., tests for `get_messages`, `_build_system_prompt`, and other methods that don't touch the LLM).

## Notes for Backend Tester
- Mock `app.services.llm.router.get_llm_router` or inject a mock `LLMRouter` via the `ChatService(db, llm_router=mock_router)` constructor for all LLM tests.
- The `_make_mock_llm_router()` helper in `test_chat.py` shows how to create a mock router with configurable stream chunks and complete_fast results.
- For `AnthropicProvider` tests, mock `app.services.llm.anthropic_provider.AsyncAnthropic` at the import level.
- For `OpenAIProvider` tests, use `__init__` patching since `openai.AsyncOpenAI` is imported lazily.
- The singleton `get_llm_router()` caches the instance -- tests must reset `_router_instance = None` in teardown.
- SSE streaming behavior is identical after refactoring -- stream tests produce the same events in the same order.
