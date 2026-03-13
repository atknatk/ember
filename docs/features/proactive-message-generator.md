# Proactive Message Generator

> Generates personalized, character-voiced push notification messages for users by querying Mem0 memories and calling Claude Haiku, with per-user per-day in-memory caching to eliminate redundant LLM calls.

**Status**: Released
**Added in**: Phase 2 (P02-04)
**Platforms**: Backend
**GitHub Issue**: #16

---

## Overview

The proactive message generator extracts notification message creation from `notification_scheduler.py` into a dedicated `ProactiveMessageGenerator` service. Before this feature, the scheduler called an inline `_generate_notification_message()` function that accepted only the character's name. The generated notifications sounded generic — the character's personality (stored in `system_prompt`) was not part of the prompt. Additionally, every scheduler cycle that re-evaluated a user would trigger a fresh Mem0 search and Claude Haiku call, even if the same notification type had already been generated for that user earlier in the day.

This service adds three improvements over the previous inline implementation:

1. **Character personality integration** — The first 200 characters of `character.system_prompt` are injected into the Claude Haiku prompt. Notifications now sound like the character speaking, not a generic bot.

2. **Per-user per-day caching** — Generated messages are cached in-memory using the key `"{user_id}:{notification_type}:{local_date}"`. If the scheduler evaluates the same user and notification type a second time on the same local day, the cached message is returned immediately without calling Mem0 or Claude.

3. **Strict 100-character enforcement** — The prompt instructs Claude Haiku to stay under 100 characters. Responses that exceed the limit are truncated at the last word boundary before position 97, with `"..."` appended. This is O(1) and deterministic — no retry needed.

After this feature, `notification_scheduler.py` delegates all message generation to a module-level `_generator = ProactiveMessageGenerator()` singleton. The original constants (`TONE_MAP`, `MEM0_QUERIES`, `FALLBACK_MESSAGES`) and helpers (`_search_mem0`, `_get_fallback_message`) now live in `proactive_message_generator.py` and are re-exported from the scheduler module for backward compatibility.

---

## Architecture

### How It Works (Data Flow)

The following describes a single call to `ProactiveMessageGenerator.generate()` from `notification_scheduler._process_notification()`:

1. The scheduler determines that a notification type should fire for a user and calls `await _generator.generate(profile, character, notification_type, local_now)`.
2. The generator builds the cache key: `"{profile.id}:{notification_type}:{local_date}"` where `local_date` is `local_now.strftime("%Y-%m-%d")`.
3. If the key exists in `_cache`, the cached string is returned immediately. Steps 4-8 are skipped.
4. The generator calls `asyncio.to_thread(_search_mem0, ...)` to query Mem0 for up to 5 memories relevant to the notification type. The synchronous Mem0 SDK is wrapped in `to_thread` to avoid blocking the event loop.
5. If the Mem0 search fails, a warning is logged and generation continues with empty memories.
6. The generator builds two prompt parts: a system prompt that includes the character's name and the first 200 characters of `character.system_prompt`, plus a user prompt containing the notification type, user name, local time (HH:MM), day of week, and the retrieved memories.
7. Claude Haiku is called via `get_llm_router().get().complete_fast()` with `max_tokens=100` and `temperature=0.7`.
8. The response is stripped of whitespace, then passed through `_truncate_to_limit()`. If the result is over 100 characters, it is truncated at the last word boundary before position 97 and `"..."` is appended.
9. If Claude Haiku fails, a deterministic fallback from `FALLBACK_MESSAGES` is used instead. The fallback is also cached.
10. The final message is stored in `_cache[key]` and returned to the scheduler.

**Cache reset (midnight)**: When `reset_notifications_sent_today()` runs (every hour, on the hour), it calls `_generator.clear_cache()` after resetting the database. This ensures that stale entries from the previous day are freed from memory. Because cache keys encode the local date, a stale entry would never produce a cache hit even without this cleanup — `clear_cache()` is a memory optimization, not a correctness requirement.

### Mem0 Memory Integration

- **agent_id format**: `{template}_{user_id}` (e.g., `emma_usr_abc123`), taken directly from `character.mem0_agent_id`
- **What is searched**: notification-type-specific queries defined in `MEM0_QUERIES` (e.g., `"morning routine, daily plans, habits"` for `morning_checkin`)
- **What is stored**: nothing — the generator performs read-only Mem0 searches
- **Memory limit**: 5 results per search
- **Failure mode**: if the search throws, generation continues with empty memories; Claude Haiku receives `"None"` in the memories field

### Character Personality in the Prompt

The system prompt sent to Claude Haiku includes:

```
You are {character.name}, the user's personal AI companion.

Your personality:
{first 200 characters of character.system_prompt}

Generate a push notification message. Rules:
- Maximum 100 characters total
- Tone: {tone from TONE_MAP}
- Language: {profile.preferred_language}
- 1-2 sentences max
- No quotes, no emoji
- Address the user by name if it fits naturally
```

Only the first 200 characters of `system_prompt` are used to limit token usage for this short-text generation task. If `system_prompt` is `None` or empty, the "Your personality:" block is present but empty — the prompt still produces valid output.

### Truncation Algorithm

`_truncate_to_limit(message, limit=100)` is a pure function:

- If `len(message) <= limit`: return unchanged.
- Otherwise: find the last space before index `limit - 3`. If found, slice there and append `"..."`. If no space (single long word), hard-slice at `limit - 3` and append `"..."`.

This guarantees the result is at most `limit` characters in all cases.

### Caching Design

The cache is a plain `dict[str, str]` on the `ProactiveMessageGenerator` instance. The scheduler creates one module-level instance (`_generator = ProactiveMessageGenerator()`) that persists across all scheduler cycles. Cache keys encode `(user_id, notification_type, local_date)`, so:

- A second evaluation of the same user and type on the same day is served from cache (zero LLM calls).
- A different notification type for the same user gets its own key (both are cached independently).
- Entries from a previous day are never returned (the date is part of the key).

At 10,000 users with 4 notification types each, the maximum cache size is approximately 40,000 entries × ~200 bytes = ~8 MB. No database or Redis storage is needed.

### Concurrency Note

The scheduler processes users sequentially, so no locking is needed on `_cache`. If parallel processing is introduced in a future scale phase (e.g., `asyncio.Semaphore`-bounded `asyncio.gather()`), an `asyncio.Lock` should be added around cache reads and writes in `generate()`.

### Constants

| Constant | Location | Purpose |
|----------|----------|---------|
| `TONE_MAP` | `proactive_message_generator.py` | Maps notification type → tone descriptor for the system prompt |
| `MEM0_QUERIES` | `proactive_message_generator.py` | Maps notification type → Mem0 search query string |
| `FALLBACK_MESSAGES` | `proactive_message_generator.py` | Maps notification type → `{"en": ..., "tr": ...}` deterministic fallbacks |

All three constants are re-exported from `notification_scheduler.py` (with `# noqa: F401`) for backward compatibility.

### Database Tables Involved

| Table | Operation | Notes |
|-------|-----------|-------|
| `profiles` | SELECT (via scheduler) | `mem0_user_id`, `preferred_language`, `name` |
| `characters` | SELECT (via scheduler) | `name`, `mem0_agent_id`, `system_prompt` |

The generator itself performs no database queries. The profile and character objects are fetched by `notification_scheduler._process_notification()` and passed in.

---

## API Reference

This feature introduces no new REST endpoints. It is an internal service used exclusively by the notification scheduler.

For the notification pipeline context, see the [Notification Scheduler](./notification-scheduler.md) feature doc and [`docs/06-bildirimler.md`](../06-bildirimler.md).

---

## Configuration

No new configuration values are introduced. The generator uses existing settings:

| Setting | Used via | Purpose |
|---------|----------|---------|
| `settings.mem0_api_key` | `_search_mem0()` | Mem0 API authentication |
| `get_llm_router()` | `generate()` | Selects Claude Haiku provider via the LLM abstraction layer |

The cache has no configurable TTL — it is keyed by local date and reset by the midnight job. The 100-character limit is hardcoded as the `limit` default parameter in `_truncate_to_limit`.

---

## iOS Implementation

Not applicable. This is a backend-only feature with no mobile code changes.

---

## Android Implementation

Not applicable. This is a backend-only feature with no mobile code changes.

---

## Testing

### Coverage Summary

| Platform | File | Tests | Result |
|----------|------|-------|--------|
| Backend (dev) | `tests/services/test_proactive_message_generator.py` | 27 | 27 passed, 0 failed |
| Backend (tester) | `tests/services/test_proactive_message_generator_extended.py` | 54 | 54 passed, 0 failed |
| Backend (updated) | `tests/services/test_notification_scheduler.py` | 52 | 52 passed, 0 failed |
| Backend (updated) | `tests/services/test_notification_scheduler_extended.py` | 51 | 51 passed, 0 failed |

Combined: 81 proactive-message-generator tests, 0 failures. Lines coverage: >80%. Branch coverage: >70%.

### Key Test Scenarios

The 27 dev-written tests cover: cache hit on second call, cache miss on different date, Mem0 failure with graceful degradation, Claude Haiku failure with fallback, fallback caching, message truncation at word boundary, hard truncation when no space, exact 100-char boundary, character `system_prompt` excerpt in prompt, day-of-week in prompt, Turkish language instruction, `clear_cache()` behavior, and `_build_cache_key()` format.

The 54 extended tests add: cache key uniqueness across users/types/dates, timezone-aware local date usage, `_truncate_to_limit` edge cases (empty string, single char, whitespace-only), Mem0 results with empty `"memory"` fields, unknown notification type defaulting to `"warm"` tone, `system_prompt` length boundaries (under/at/over 200 chars), `max_tokens=100` and `temperature=0.7` assertion, `preferred_language=None` defaulting to `"en"`, backward-compat re-exports from `notification_scheduler`, and scheduler integration (that `_generator.clear_cache()` is called by midnight reset and `_process_notification` passes the correct arguments).

### Mocking Guide

| Component | Mock target |
|-----------|-------------|
| Mem0 SDK | `app.services.proactive_message_generator._search_mem0` |
| Claude Haiku | `app.services.proactive_message_generator.get_llm_router` |
| `_process_notification` (scheduler tests) | `patch.object(_generator, "generate", ...)` — do not patch by function path |

The `_truncate_to_limit` function is a pure function and requires no mocking.

Each test that calls `_generate_notification_message` (the backward-compat wrapper) and reuses the same `user_id` should call `_generator.clear_cache()` first. Tests using `uuid.uuid4()` per test are safe without clearing.

### Running Tests

```bash
cd /path/to/ember/backend && python -m pytest tests/services/test_proactive_message_generator.py tests/services/test_proactive_message_generator_extended.py -v
```

Full notification suite:

```bash
cd /path/to/ember/backend && python -m pytest tests/services/test_proactive_message_generator.py tests/services/test_proactive_message_generator_extended.py tests/services/test_notification_scheduler.py tests/services/test_notification_scheduler_extended.py -v
```

---

## Known Limitations

- **In-memory cache only** — the cache does not survive a process restart. If the ECS task is recycled mid-day, all users will generate fresh messages on the next scheduler cycle. This is acceptable: regeneration is inexpensive, and ECS restarts are infrequent.
- **Not thread-safe** — `_cache` has no locking. This is safe only because the scheduler processes users sequentially. If parallel processing is introduced (bounded concurrency via `asyncio.Semaphore`), an `asyncio.Lock` must be added.
- **`goal_followup` not implemented** — the `TONE_MAP`, `MEM0_QUERIES`, and `FALLBACK_MESSAGES` constants do not include a `goal_followup` entry. When this notification type is added (per `docs/06-bildirimler.md`), all three constants need new entries.
- **200-character personality excerpt is fixed** — there is no configuration to adjust how much of `system_prompt` is sent to Claude. If character prompts are restructured so that the core personality directive is not in the first 200 characters, the excerpt boundary should be revisited.

---

## Extending This Feature

**Adding a new notification type**: Add the type string to `NOTIFICATION_TYPES` in `notification_scheduler.py`. Add its entries to `TONE_MAP`, `MEM0_QUERIES`, and `FALLBACK_MESSAGES` in `proactive_message_generator.py`. Add the trigger condition in `evaluate_notification_triggers()`. No changes to `ProactiveMessageGenerator` itself are needed.

**Adding a new fallback language**: Add the language code as a new key inside each type's dict in `FALLBACK_MESSAGES`. The `_get_fallback_message()` function falls back to `"en"` for unrecognized language codes, so no other changes are required.

**Adjusting the character personality excerpt length**: Change the slice length in `generate()`:
```python
personality_excerpt = character.system_prompt[:200]  # change 200 here
```
Increasing this value raises token usage per notification generation call.

**Persisting the cache across restarts**: Replace `self._cache: dict[str, str]` with a Redis-backed store (using `aioredis`). The cache key format `"{user_id}:{notification_type}:{local_date}"` is already suitable for a Redis key. Set a TTL of 24 hours on each entry rather than relying on `clear_cache()`.

**Adding a configurable character limit**: The 100-character limit is currently hardcoded as the `limit` default in `_truncate_to_limit`. To make it configurable, add a `settings.notification_max_message_length` config value and pass it as the `limit` argument.

---

## Related Documentation

- [Notification Scheduler](./notification-scheduler.md) — P02-02, the caller of this service
- [FCM Push Service](./fcm-push-service.md) — P02-03, which delivers the messages generated here
- [Proactive Notification System Design](../06-bildirimler.md) — full notification type definitions, FCM architecture, trigger conditions
- [AI Memory System](../05-ai-bellek.md) — Mem0 `agent_id` format and memory isolation per character
- [LLM Provider Abstraction](./llm-provider-abstraction.md) — P1.5-05, which provides `get_llm_router()` and `complete_fast()` used for Haiku calls
- [Database Schema](../04-veri-api.md) — `profiles` and `characters` table definitions
