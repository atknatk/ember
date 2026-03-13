# Feature Spec: P02-04 -- Proactive Message Generator

**Feature ID**: P02-04
**Phase**: 2
**Layer**: backend
**GitHub Issue**: #16
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature extracts, improves, and caches the notification message generation logic that currently lives inline in `notification_scheduler.py` (the `_generate_notification_message` function) into a dedicated `ProactiveMessageGenerator` service. The new service adds three capabilities beyond the current implementation:

1. **Per-user per-day caching** -- Generated messages are cached in-memory so that if the scheduler evaluates the same user multiple times in a day (e.g., across scheduler cycles or retries), the LLM is not called again for the same notification type. The cache key is `(user_id, notification_type, date_local)`.

2. **Character personality integration** -- The prompt now incorporates the character's `system_prompt` (which defines its personality and voice) to ensure notification text sounds like the character, not a generic bot. The current implementation only uses the character's name.

3. **Strict 100-character enforcement** -- The prompt instructs Claude Haiku to stay under 100 characters, and the service truncates any response that exceeds 100 characters at the last word boundary, appending an ellipsis if needed.

After this feature is implemented, `_generate_notification_message` in `notification_scheduler.py` is replaced by a call to `ProactiveMessageGenerator.generate()`, and all related helper functions (`_search_mem0`, `_get_fallback_message`) and constants (`TONE_MAP`, `MEM0_QUERIES`, `FALLBACK_MESSAGES`) move to the new module.

### Why It Exists

- **Cost reduction**: Without caching, each scheduler cycle that re-evaluates a user triggers a fresh Mem0 search + Claude Haiku call, even if the same notification type was already generated for that user today. Caching eliminates redundant LLM calls.
- **Brand consistency**: Notifications should sound like the character (the General Friend) speaking. Currently, only the character name is in the prompt; the character's personality/voice (stored in `system_prompt`) is not used.
- **Maintainability**: Message generation is a distinct concern from scheduling. Extracting it into its own service makes both modules easier to test, modify, and reuse (e.g., future goal_followup notifications can use the same generator).

### Dependencies

- **Requires**: P02-02 (notification-scheduler) -- the existing `_generate_notification_message` function and its constants are the starting point
- **Requires**: P01-02 (database-schema) -- `characters.system_prompt`, `profiles.mem0_user_id`, `profiles.preferred_language`
- **Extends**: `docs/06-bildirimler.md` -- the personalization flow described there

### What This Feature Does NOT Do

- It does not change the notification trigger conditions or time windows (those stay in `notification_scheduler.py`).
- It does not change the FCM sending logic (that stays in `notification_sender.py` and `notification_service.py`).
- It does not persist cached messages to the database -- the cache is in-memory and resets on process restart.
- It does not implement `goal_followup` message generation (deferred, per P02-02 spec).
- It does not expose any new API endpoints.

---

## 2. Data Models

### No New Tables

No new database tables are required.

### No Schema Changes

No `ALTER TABLE` statements are needed.

### Columns Read (Not Modified)

| Table | Columns Read | Purpose |
|-------|-------------|---------|
| `profiles` | `mem0_user_id`, `preferred_language`, `name` | Mem0 search context, language selection, user name in prompt |
| `characters` | `name`, `mem0_agent_id`, `system_prompt` | Character identity, Mem0 agent_id for memory search, personality voice for prompt |

### Mem0 Operations

**Search** (read-only, moved from `notification_scheduler.py`): Searches Mem0 for memories relevant to the notification type. Parameters:
- `user_id`: the profile's `mem0_user_id`
- `agent_id`: the default character's `mem0_agent_id`
- `query`: notification-type-specific query string (same as current `MEM0_QUERIES`)
- `limit`: 5

The `agent_id` follows the standard format `{template}_{user_id}` per `docs/05-ai-bellek.md`.

**No writes**: The generator does not add memories to Mem0.

---

## 3. API Changes

### No New Endpoints

This feature does not introduce any new API endpoints. It is an internal service used by the notification scheduler.

### No Response Changes

No existing endpoint responses are modified.

---

## 4. Backend Logic

### New Service: `backend/app/services/proactive_message_generator.py`

This module contains the `ProactiveMessageGenerator` class and all related constants moved from `notification_scheduler.py`.

#### Constants (Moved From `notification_scheduler.py`)

The following constants are moved verbatim from `notification_scheduler.py` to `proactive_message_generator.py`:

- `TONE_MAP` -- Maps notification type to tone descriptor.
- `MEM0_QUERIES` -- Maps notification type to Mem0 search query string.
- `FALLBACK_MESSAGES` -- Maps notification type and language to a deterministic fallback message string.

After the move, `notification_scheduler.py` imports these constants from the new module.

#### Class: `ProactiveMessageGenerator`

```
class ProactiveMessageGenerator:
    def __init__(self) -> None
    async def generate(
        self,
        profile: Profile,
        character: Character,
        notification_type: str,
        local_now: datetime,
    ) -> str
    def clear_cache(self) -> None
    def _build_cache_key(
        self,
        user_id: uuid.UUID,
        notification_type: str,
        local_now: datetime,
    ) -> str
```

**Constructor**: Initializes an empty cache dictionary `_cache: dict[str, str]` and a `_cache_dates: dict[str, str]` to track which local date each cache entry belongs to (for stale entry cleanup).

#### Method: `generate`

The main entry point. Responsibilities:

1. **Check cache**: Build the cache key as `"{user_id}:{notification_type}:{local_date}"` where `local_date` is `local_now.strftime("%Y-%m-%d")`. If a cached message exists for this key, return it immediately.

2. **Search Mem0 for memories**: Use `asyncio.to_thread()` to call the synchronous Mem0 SDK. Use the notification-type-specific query from `MEM0_QUERIES`. If the Mem0 search fails, log a warning and continue with empty memories.

3. **Build prompt with character personality**: The system prompt now includes an excerpt from the character's `system_prompt` to capture the character's voice. The full prompt structure:

   ```
   System:
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

   User:
   Notification type: {notification_type}
   User's name: {profile.name}
   Current local time: {local_now.strftime('%H:%M')}
   Day of week: {local_now.strftime('%A')}
   Relevant memories:
   {formatted_memories or "None"}

   Generate a warm, personalized notification message.
   ```

   Key changes from the current prompt:
   - Added "Your personality" block with first 200 chars of `character.system_prompt`
   - Changed "under 100 characters if possible" to "Maximum 100 characters total" (strict)
   - Added day of week for temporal awareness (e.g., "Monday morning" context)

4. **Call Claude Haiku**: Use `get_llm_router().get().complete_fast()` with `max_tokens=100` and `temperature=0.7`. This is the same pattern as the current implementation.

5. **Enforce 100-character limit**: After receiving the response:
   - Strip whitespace.
   - If `len(message) <= 100`, use as-is.
   - If `len(message) > 100`, truncate at the last space before position 97, append `"..."`. If there is no space (single long word), hard-truncate at position 97 and append `"..."`.

6. **Cache and return**: Store the message in `_cache[key]` and return it.

7. **Fallback on error**: If either Claude Haiku or Mem0 fails completely, use the deterministic fallback message from `FALLBACK_MESSAGES` (same behavior as current code). The fallback message is also cached to prevent repeated failing calls within the same day.

#### Method: `clear_cache`

Clears the entire `_cache` dictionary. Called by the midnight reset job in `notification_scheduler.py` to ensure stale entries from the previous day are removed.

#### Method: `_build_cache_key`

Pure helper that returns `f"{user_id}:{notification_type}:{local_now.strftime('%Y-%m-%d')}"`.

#### Mem0 Helper Function: `_search_mem0`

This function moves from `notification_scheduler.py` to `proactive_message_generator.py`. The signature and behavior remain identical:

```
def _search_mem0(
    mem0_user_id: str,
    agent_id: str,
    query: str,
) -> list[dict[str, object]]
```

Synchronous. Called via `asyncio.to_thread()`. Creates a `MemoryClient`, calls `.search()` with `limit=5`.

#### Fallback Function: `_get_fallback_message`

This function moves from `notification_scheduler.py` to `proactive_message_generator.py`. Signature and behavior unchanged:

```
def _get_fallback_message(notification_type: str, language: str) -> str
```

### Modifications to `notification_scheduler.py`

1. **Remove**: Delete `_generate_notification_message`, `_search_mem0`, `_get_fallback_message`, `TONE_MAP`, `MEM0_QUERIES`, `FALLBACK_MESSAGES` from this module.

2. **Add import**: `from app.services.proactive_message_generator import ProactiveMessageGenerator, NOTIFICATION_TYPES` (the `NOTIFICATION_TYPES` tuple stays in `notification_scheduler.py` since it is about scheduling, not generation).

3. **Instantiate generator**: Create a module-level `_generator = ProactiveMessageGenerator()` instance. This single instance is shared across all scheduler cycles, allowing the cache to persist between cycles.

4. **Replace call site**: In `_process_notification`, replace the call to `_generate_notification_message(...)` with:
   ```python
   message = await _generator.generate(
       profile=profile,
       character=default_character,
       notification_type=notification_type,
       local_now=local_now,
   )
   ```

5. **Clear cache on midnight reset**: In `reset_notifications_sent_today`, after resetting the database, call `_generator.clear_cache()`.

### New Config Values

No new config values are needed. The cache is in-memory with implicit per-day TTL (entries are keyed by date and cleared on midnight reset). The existing `notification_scheduler_interval_minutes` and `notification_batch_size` settings remain unchanged.

### Error Handling

| Error | Handling |
|-------|----------|
| Mem0 search failure | Log warning, generate message without memories |
| Claude Haiku failure | Use deterministic fallback message, cache the fallback |
| LLMProviderError | Caught as part of Claude Haiku failure, same fallback path |
| Character `system_prompt` is empty/None | Use empty string for personality block (the prompt still works) |
| Generated message exceeds 100 chars | Truncate at last word boundary, append "..." |

### Concurrency

The `ProactiveMessageGenerator` instance is used from a single scheduler coroutine that processes users sequentially (per P02-02 design). Therefore, no locking is needed for the cache dictionary. If concurrency is introduced later (e.g., `asyncio.Semaphore`-bounded parallel processing), a simple `asyncio.Lock` should be added around cache reads/writes.

---

## 5. iOS Screens and Components

Not applicable. This is a backend-only feature with no mobile UI changes.

---

## 6. Android Screens and Components

Not applicable. This is a backend-only feature with no mobile UI changes.

---

## 7. Test Plan

### Backend Tests

#### Unit Tests: `backend/tests/services/test_proactive_message_generator.py`

| # | Scenario | Expected |
|---|----------|----------|
| 1 | `generate()` with valid Mem0 memories and Claude Haiku response under 100 chars | Returns the Claude-generated message |
| 2 | `generate()` called twice for same user/type/date | Second call returns cached result without calling Mem0 or Claude |
| 3 | `generate()` called for same user/type but different dates | Both calls hit Mem0 + Claude (no cache hit) |
| 4 | `generate()` when Mem0 search fails | Claude is called with empty memories, returns generated message |
| 5 | `generate()` when Claude Haiku fails | Returns fallback message from `FALLBACK_MESSAGES` |
| 6 | `generate()` when both Mem0 and Claude fail | Returns fallback message |
| 7 | `generate()` when Claude returns message > 100 chars | Message is truncated at word boundary with "..." |
| 8 | `generate()` when Claude returns exactly 100 chars | Message is returned as-is (no truncation) |
| 9 | `generate()` when Claude returns message of 101 chars with no space | Hard-truncate at 97 + "..." |
| 10 | `generate()` includes character.system_prompt excerpt in LLM prompt | Assert the system prompt passed to `complete_fast` contains first 200 chars of character.system_prompt |
| 11 | `generate()` includes day of week in user prompt | Assert the user prompt passed to `complete_fast` contains the day of week |
| 12 | `generate()` with Turkish language profile | System prompt instructs "Language: tr" |
| 13 | `generate()` fallback is also cached | After a Claude failure, a second call returns the cached fallback without retrying Claude |
| 14 | `clear_cache()` empties the cache | After `clear_cache()`, next `generate()` call hits Claude again |
| 15 | `_build_cache_key()` produces correct format | Returns `"{user_id}:{notification_type}:{YYYY-MM-DD}"` |
| 16 | `_get_fallback_message()` returns correct language variant | English for "en", Turkish for "tr", English for unknown language |

#### How to Mock

- **Mem0**: Mock `_search_mem0` at the module level using `unittest.mock.patch("app.services.proactive_message_generator._search_mem0")`. Since it is called via `asyncio.to_thread`, the mock replaces the synchronous function.
- **Claude Haiku**: Mock `get_llm_router` to return a mock LLM provider whose `complete_fast` returns a fixed string. Use `unittest.mock.patch("app.services.proactive_message_generator.get_llm_router")`.
- **Profile and Character**: Create simple mock/fake objects with the required attributes (`name`, `mem0_user_id`, `preferred_language`, `mem0_agent_id`, `system_prompt`).
- **Time**: Pass `local_now` as a parameter (already the design).

#### Integration-Level Tests in Existing Test Files

The existing `test_notification_scheduler.py` tests (scenarios 13-15 from P02-02 spec) that test `_process_notification` need to be updated to mock `ProactiveMessageGenerator.generate()` instead of `_generate_notification_message`. These are MODIFY operations on existing test files, not new tests.

| # | Scenario | Expected |
|---|----------|----------|
| 17 | `_process_notification` calls `_generator.generate()` with correct arguments | Arguments match profile, character, notification_type, local_now |
| 18 | `reset_notifications_sent_today` calls `_generator.clear_cache()` | Cache is cleared after midnight reset |

---

## 8. Acceptance Criteria

1. Given a user with Mem0 memories and a default character with a `system_prompt`, when the notification scheduler triggers a `morning_checkin`, then the generated message incorporates the character's personality voice and references user memories.

2. Given the same user and notification type evaluated twice in the same scheduler cycle (or across two cycles on the same local date), when `generate()` is called the second time, then the cached message is returned without calling Mem0 or Claude Haiku.

3. Given a generated message that is 120 characters long, when the generator processes it, then the returned message is at most 100 characters and ends with "..." at a word boundary.

4. Given Mem0 is unavailable, when the generator attempts to create a notification message, then it generates a message using Claude Haiku without memories (no crash, no skip).

5. Given Claude Haiku is unavailable, when the generator attempts to create a notification message, then it returns the appropriate deterministic fallback message for the notification type and user language.

6. Given the midnight reset job runs, when `reset_notifications_sent_today` completes, then the generator's cache is cleared.

7. Given a character whose `system_prompt` is "Sen Atakan'in en yakin AI arkadasisin...", when the generator builds the Claude Haiku prompt, then the system prompt includes the first 200 characters of that system_prompt under "Your personality:".

8. Given the existing notification scheduler tests, when `pytest backend/tests/services/test_notification_scheduler.py -v` is run after refactoring, then all existing tests still pass (they now mock the new generator instead of the old inline function).

9. Given the new generator tests, when `pytest backend/tests/services/test_proactive_message_generator.py -v` is run, then all tests pass with exit code 0.

10. Given the `TONE_MAP`, `MEM0_QUERIES`, and `FALLBACK_MESSAGES` constants, when they are imported from `proactive_message_generator.py`, then they contain the same values as the current `notification_scheduler.py`.

---

## 9. File Manifest

```
Backend:
  CREATE  backend/app/services/proactive_message_generator.py
  CREATE  backend/tests/services/test_proactive_message_generator.py
  MODIFY  backend/app/services/notification_scheduler.py           (remove generation logic, import and use ProactiveMessageGenerator)

Shared:
  CREATE  shared/feature-specs/proactive-message-generator.md      (this file)
  CREATE  docs/pipeline/proactive-message-generator-architect.handoff.md
```

### Summary

| Action | Count |
|--------|-------|
| CREATE | 4 |
| MODIFY | 1 |
| DELETE | 0 |
| **Total** | **5** |

### Files NOT Modified

- `backend/app/services/notification_sender.py` -- FCM sending logic is unchanged.
- `backend/app/services/notification_service.py` -- High-level notification service is unchanged.
- `backend/app/config.py` -- No new configuration values needed.
- `backend/app/main.py` -- No lifespan or router changes needed.
- `backend/app/routes/` -- No new endpoints; no route files are modified.
- `backend/app/models/` -- No model changes.
- `backend/requirements.txt` -- No new dependencies.

---

## 10. Design Decisions and Rationale

### Why in-memory cache instead of database or Redis

The cache stores at most `N_users * 4` entries (one per notification type per user per day), where each entry is a short string (<= 100 chars). For 10,000 users, this is roughly 40,000 entries at ~200 bytes each = ~8 MB. This is trivially small for in-memory storage. A database table or Redis adds operational complexity and latency for no practical benefit at this scale. The cache is cleared daily by the midnight reset job and on process restart, which is acceptable since regeneration is inexpensive.

### Why truncate at word boundary instead of rejecting and retrying

Retrying the LLM with a stricter prompt is wasteful (doubles cost) and non-deterministic (may still fail). Truncating at the last word boundary before position 97 and appending "..." produces a readable result in all cases and is O(1).

### Why include only the first 200 characters of system_prompt

Character system prompts can be long (500+ characters). Including the full prompt in the notification generation prompt would inflate token usage for a short-text generation task. The first 200 characters typically capture the core personality directive (e.g., "You are a warm, supportive friend who speaks casually in Turkish..."). This is sufficient for voice matching in a 100-character notification.

### Why module-level singleton instead of dependency injection

The `ProactiveMessageGenerator` instance needs to persist across scheduler cycles for the cache to be effective. A module-level instance in `notification_scheduler.py` is the simplest approach, consistent with the existing module-level patterns in the codebase (e.g., `settings` singleton in `config.py`). Dependency injection could be added later if testing requires it, but `unittest.mock.patch` on the module-level variable works cleanly.

### Why move constants instead of duplicating them

The constants (`TONE_MAP`, `MEM0_QUERIES`, `FALLBACK_MESSAGES`) are exclusively used by the message generation logic. Keeping them in `notification_scheduler.py` after extracting the generation logic would create an awkward cross-module dependency. Moving them to the new module keeps related code together. `notification_scheduler.py` no longer needs these constants directly.

### Why clear_cache in midnight reset instead of TTL-based expiry

TTL-based expiry would require either a background thread or checking timestamps on every cache access. The midnight reset job already runs hourly and knows when a user crosses midnight. Adding `clear_cache()` to this existing job is trivial and deterministic. The cache is bounded by date in the key, so stale entries from yesterday are never returned even without explicit clearing -- `clear_cache()` is a memory optimization, not a correctness requirement.
