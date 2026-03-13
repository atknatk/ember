# Architect Handoff: Proactive Message Generator

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

Extracted and improved the notification message generation logic from `notification_scheduler.py` into a dedicated `ProactiveMessageGenerator` service. The new service adds per-user per-day in-memory caching to avoid redundant LLM calls, integrates the character's `system_prompt` personality into the generation prompt, and enforces a strict 100-character limit with word-boundary truncation.

## Key Decisions

- **In-memory cache keyed by `(user_id, notification_type, local_date)`** -- avoids redundant Mem0 + Claude Haiku calls across scheduler cycles on the same day. No Redis or database storage needed at current scale.
- **First 200 characters of `character.system_prompt` included in prompt** -- gives Claude Haiku enough personality context for voice-matched notifications without inflating token usage.
- **Word-boundary truncation at 100 chars** -- cheaper and more deterministic than retrying the LLM with a stricter prompt.
- **Constants moved, not duplicated** -- `TONE_MAP`, `MEM0_QUERIES`, `FALLBACK_MESSAGES` move from `notification_scheduler.py` to the new module to keep related code together.
- **Module-level singleton** -- the generator instance persists across scheduler cycles for cache effectiveness, consistent with existing singleton patterns in the codebase.
- **Cache cleared in midnight reset job** -- leverages the existing hourly job instead of adding TTL-based expiry complexity.

## Spec Location

`shared/feature-specs/proactive-message-generator.md`

## Assumptions Made

- The notification scheduler continues to process users sequentially (no concurrency), so no locking is needed for the cache dictionary.
- Character `system_prompt` is always populated for default characters (it is a NOT NULL column).
- The existing `complete_fast()` LLM interface is sufficient (no new LLM methods needed).
- Mem0 SDK remains synchronous, wrapped in `asyncio.to_thread()`.

## Dependencies

- Requires: P02-02 (notification-scheduler) -- the existing `_generate_notification_message` function being refactored
- Requires: P02-03 (fcm-push-service) -- notification sending infrastructure
- Blocks: backend-dev (implements), backend-tester (tests)

## Next Steps

backend-dev should read the spec and implement. Key tasks:
1. Create `proactive_message_generator.py` with `ProactiveMessageGenerator` class
2. Move constants and helper functions from `notification_scheduler.py`
3. Update `notification_scheduler.py` to use the new generator
4. Add `clear_cache()` call to midnight reset job
5. Write unit tests for the generator
6. Update existing scheduler tests to mock the new generator
