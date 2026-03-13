# Backend Dev Handoff: Proactive Message Generator

**Date**: 2026-03-13
**Agent**: backend-dev
**Status**: COMPLETE

## Implemented Files

### Created
- `backend/app/services/proactive_message_generator.py` -- `ProactiveMessageGenerator` class, constants (`TONE_MAP`, `MEM0_QUERIES`, `FALLBACK_MESSAGES`), helpers (`_search_mem0`, `_get_fallback_message`, `_truncate_to_limit`)
- `backend/tests/services/test_proactive_message_generator.py` -- 27 unit tests covering caching, truncation, fallbacks, personality integration, day-of-week, language

### Modified
- `backend/app/services/notification_scheduler.py` -- Removed inline generation logic; imports and delegates to `ProactiveMessageGenerator`; `_generator` module-level singleton; backward-compatible re-exports of constants and helpers; `reset_notifications_sent_today` calls `_generator.clear_cache()`; `_generate_notification_message` kept as thin wrapper for backward compat
- `backend/tests/services/test_notification_scheduler.py` -- Updated mock paths from `notification_scheduler._generate_notification_message` to `_generator.generate` (patch.object) for `_process_notification` tests; updated `_search_mem0`/`get_llm_router` mock paths to `proactive_message_generator` module for direct `_generate_notification_message` tests; added `_generator.clear_cache()` before tests that call the wrapper directly
- `backend/tests/services/test_notification_scheduler_extended.py` -- Same mock path updates as above (all `_search_mem0`, `get_llm_router`, `_generate_notification_message` mock paths updated)
- `docs/standards/backend.md` -- Added `proactive_message_generator.py` to project structure listing

## Endpoints Implemented

No new API endpoints. This is an internal service used by the notification scheduler.

## Test Results

- pytest: 2401 passed, 0 failed, 13 skipped
- ruff: clean
- New test file: 27 tests in `test_proactive_message_generator.py`
- Existing scheduler tests: all 103 notification tests pass (52 base + 51 extended)

## Test Command

```bash
cd backend && python -m pytest tests/services/test_proactive_message_generator.py tests/services/test_notification_scheduler.py tests/services/test_notification_scheduler_extended.py -v
```

## Known Issues / Deviations from Spec

- None. Implementation follows spec exactly.

## Notes for Backend Tester

- Mock `app.services.proactive_message_generator._search_mem0` for all Mem0 tests (not the scheduler module)
- Mock `app.services.proactive_message_generator.get_llm_router` for Claude Haiku tests
- The `ProactiveMessageGenerator` uses a module-level singleton `_generator` in `notification_scheduler.py` -- when testing `_process_notification`, use `patch.object(_generator, "generate", ...)` rather than patching the function by path
- Each test that calls `_generate_notification_message` directly should clear the cache first via `_generator.clear_cache()` if reusing the same user_id across tests (tests using `uuid.uuid4()` are safe without clearing)
- The `_truncate_to_limit` function is independently testable as a pure function
- Character `system_prompt` can be `None` or empty string -- both paths are covered
- The cache is NOT thread-safe (by design, per spec) -- concurrency tests are not needed
