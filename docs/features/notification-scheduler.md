# Notification Scheduler

> Proactively reaches out to users with personalized push notifications at contextually appropriate times throughout the day, driven by each user's activity pattern and timezone.

**Status**: Released
**Added in**: Phase 2 (P02-02)
**Platforms**: Backend
**GitHub Issue**: #14

---

## Overview

The notification scheduler runs as a background job inside the FastAPI process, waking up every 30 minutes to evaluate whether each user should receive a push notification. It has no REST endpoints — it is purely an internal loop that reads activity data and fires Firebase Cloud Messaging (FCM) pushes.

Four notification types are defined, each tied to a local time window and a contextual trigger condition:

| Type | Local Time Window | Fires When |
|------|-------------------|------------|
| `morning_checkin` | 08:00 – 09:30 | User has not chatted today |
| `afternoon_nudge` | 14:00 – 15:30 | User has not chatted today |
| `evening_reflection` | 20:00 – 21:00 | Not yet sent today (regardless of chat) |
| `sleep_reminder` | 23:00+ | User was active within the last 60 minutes |

Each type is sent at most once per user per day. The `notifications_sent_today` JSONB array on `user_activity` tracks which types have been dispatched. A companion hourly job resets that array when a user's local clock crosses midnight, handling the full spread of timezones with a single cron expression.

Proactive outreach is a core differentiator described in `docs/01-vizyon.md`. The scheduler is the runtime implementation of the notification design in `docs/06-bildirimler.md`. It depends on `user_activity` data written by P02-01 (activity-tracking-middleware) and sends messages through the user's default character, personalizing content with Mem0 memories and Claude Haiku.

---

## Architecture

### How It Works (Data Flow)

**Notification cycle** (every 30 minutes):

1. `run_notification_cycle()` starts, fetches users with an FCM token in batches of 100 (`notification_batch_size`).
2. For each user, the scheduler converts the current UTC time to the user's local timezone via `zoneinfo.ZoneInfo(profile.timezone)`.
3. `evaluate_notification_triggers()` is called — a pure function that returns a list of notification types that should fire, based on local time windows, `last_chat_at`, `last_active_at`, and `notifications_sent_today`.
4. For each triggered type, `_process_notification()` is called:
   a. The user's default active character is fetched from the `characters` table.
   b. Mem0 is searched for relevant memories using `asyncio.to_thread()` (the SDK is synchronous). The query string is specific to the notification type (e.g., `"morning routine, daily plans, habits"` for `morning_checkin`).
   c. Claude Haiku is called via `get_llm_router().get().complete_fast()` with a prompt that includes the memories, notification type, user name, local time, and preferred language.
   d. If either Mem0 or Claude fails, a deterministic fallback message is used — the notification is still sent.
   e. `send_push_notification()` delivers the FCM message. The `title` is the character's name; `data` carries `character_id` and `notification_type` for client-side deep linking.
   f. On success, `notifications_sent_today` is updated in-database and in-memory so subsequent triggers in the same cycle see the updated state.
   g. On FCM token failure (`UnregisteredError` or `InvalidArgumentError`), `profiles.fcm_token` is set to `NULL` to prevent future attempts.
5. Per-user exceptions are caught and logged. A failure for one user never interrupts processing of the remaining users.

**Midnight reset** (every hour, on the hour):

1. `reset_notifications_sent_today()` queries all `user_activity` rows where `notifications_sent_today` is non-empty.
2. For each user, local time is computed. If the local hour is `0`, the user's `notifications_sent_today` is added to a reset list.
3. A single batched `UPDATE` clears the array for all eligible users.

### Trigger Evaluation Logic

`evaluate_notification_triggers()` accepts five parameters: `notifications_sent_today`, `last_chat_at`, `last_active_at`, `local_now`, and `now_utc`. It returns a list (potentially empty) of type strings to send.

The function is deliberately pure — it performs no I/O and accepts `local_now` as a parameter rather than calling `datetime.now()` internally. This makes it trivially testable without mocking the system clock.

`chatted_today` is computed by comparing `last_chat_at` (UTC-aware) against the user's local midnight converted to UTC. `morning_checkin` and `afternoon_nudge` suppress when `chatted_today` is true. `evening_reflection` fires regardless of chat activity. `sleep_reminder` checks `last_active_at >= now_utc - 60 minutes`.

### Mem0 Memory Integration

- **agent_id format**: `{template}_{user_id}` (e.g., `emma_usr_abc123`), from `character.mem0_agent_id`
- **What is searched**: notification-type-specific query strings (see table in the spec)
- **What is stored**: nothing — the scheduler only reads from Mem0, it does not write memories
- **Memory limit**: 5 results per search
- **Failure mode**: search failure yields an empty memory set; the Haiku prompt is sent with `"None"` in the memories field; fallback message is used only if Haiku itself also fails

### Scheduler Lifecycle and Lifespan Integration

The scheduler is registered as two APScheduler 4.x jobs inside the FastAPI `lifespan` context manager in `backend/app/main.py`:

- Job `notification_cycle`: `IntervalTrigger(minutes=settings.notification_scheduler_interval_minutes)`
- Job `midnight_reset`: `CronTrigger(minute=0)`

On startup, `initialize_firebase()` runs first (idempotent), then `start_notification_scheduler()` creates an `AsyncScheduler`, adds both jobs, and calls `await scheduler.start_in_background()`. The scheduler instance is stored in `app.state.scheduler`.

On shutdown, `await scheduler.stop()` is called. Note: APScheduler 4.x uses `stop()`, not `shutdown()` — see the Known Limitations section.

If `settings.notification_scheduler_enabled` is `False`, neither Firebase nor the scheduler is initialized. This is the expected configuration for test environments.

### Database Tables Involved

| Table | Operation | Notes |
|-------|-----------|-------|
| `user_activity` | SELECT, UPDATE | Reads trigger conditions; writes `notifications_sent_today` after each send |
| `profiles` | SELECT, UPDATE | Reads `fcm_token`, `timezone`, `preferred_language`, `mem0_user_id`, `name`; clears `fcm_token` on invalid token error |
| `characters` | SELECT | Fetches the user's default active character for notification context |

No new tables or schema changes were introduced. All columns were already present from P01-02 (database-schema).

### Concurrency Model

Users are processed sequentially within each batch. Concurrent processing was explicitly deferred to avoid rate-limit spikes on the Anthropic and Mem0 APIs. Within a single user's notification pipeline, Mem0 search must complete before Claude Haiku is called (memories are part of the prompt), so these two I/O calls are sequential as well.

Both `firebase_admin.messaging.send()` and the Mem0 SDK are synchronous. Both are wrapped in `asyncio.to_thread()` to prevent blocking the event loop.

Batch iteration uses OFFSET-based pagination. This is intentional: the `user_activity` table is bounded by total user count (not a high-volume append table), and the background batch job is not a user-facing API. The cursor-based pagination rule in `CLAUDE.md` applies only to the `messages` table.

---

## API Reference

This feature introduces no new REST endpoints. It is a pure background service. No existing endpoint responses are changed.

For the FCM token registration and notification preferences endpoints (which feed this scheduler), see the relevant future feature specifications. For the Firebase notification design, see [`docs/06-bildirimler.md`](../06-bildirimler.md).

### FCM Payload Structure

The push notification delivered to each device has this structure:

```
title:  {character.name}
body:   {generated or fallback message}
data:
  character_id:      {UUID of the default character}
  notification_type: morning_checkin | afternoon_nudge | evening_reflection | sleep_reminder
```

The `data` fields enable the mobile client to open the correct character's chat screen when the user taps the notification.

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
| Backend | `tests/services/test_notification_scheduler.py` | 26 | 26 passed, 0 failed |
| Backend | `tests/services/test_notification_sender.py` | 5 | 5 passed, 0 failed |

The backend-dev handoff reports 31 notification-specific tests and 1879 total tests passing (full suite).

### Test Approach

**`evaluate_notification_triggers` unit tests**: The pure function is tested directly — no mocks required. Twelve scenarios cover each of the four notification types: correct firing within the time window, suppression when already sent, `morning_checkin`/`afternoon_nudge` suppression when the user has chatted, `sleep_reminder` suppression for inactive users, and the outside-all-windows case.

**`_process_notification` unit tests**: `AsyncSessionLocal`, `_search_mem0`, `get_llm_router`, and `send_push_notification` are mocked. Tests verify the full happy path (Mem0 memories retrieved, Haiku message generated, FCM sent, `notifications_sent_today` updated), Mem0 failure fallback, Claude failure fallback, and FCM invalid-token handling (`fcm_token` set to `NULL`).

**`run_notification_cycle` unit tests**: Verifies that users without FCM tokens are skipped, users with invalid timezones are skipped and logged, and per-user exceptions do not prevent subsequent users from being processed.

**`reset_notifications_sent_today` unit tests**: Verifies that only users whose local hour is 0 have their array reset, leaving users in other timezones untouched.

**`send_push_notification` and `initialize_firebase` unit tests** (in `test_notification_sender.py`): `firebase_admin.messaging.send` is mocked. Tests cover successful send (`True` return), `UnregisteredError` (`False` return), other FCM errors (`False` return), and double-initialization idempotency of `initialize_firebase`.

### Mocking Guide

| Component | Mock target |
|-----------|-------------|
| Mem0 | `app.services.notification_scheduler._search_mem0` |
| Claude Haiku | `app.services.notification_scheduler.get_llm_router` |
| FCM send | `firebase_admin.messaging.send` |
| Database session | `app.services.notification_scheduler.AsyncSessionLocal` |
| Time | Pass `now_utc` parameter directly to `run_notification_cycle` and `reset_notifications_sent_today` |

For FCM error types: `UnregisteredError` is in `firebase_admin.messaging`; `InvalidArgumentError` is in `firebase_admin.exceptions`. This differs from the spec, which listed both under `firebase_admin.messaging` — see Known Limitations.

### Running Tests

```bash
cd /path/to/ember/backend && python -m pytest tests/services/test_notification_scheduler.py tests/services/test_notification_sender.py -v
```

Full backend suite:

```bash
cd /path/to/ember/backend && python -m pytest tests/ -v
```

---

## Known Limitations

- **No notification preferences**: The scheduler currently sends all applicable notification types to all eligible users. User-level opt-outs (e.g., "no morning check-ins") and the `PUT /notifications/preferences` endpoint are a separate future feature. When that feature is implemented, a preference check step will be added inside `_process_notification()` before the Mem0/Haiku call.
- **No quiet hours / do-not-disturb**: Per `docs/06-bildirimler.md`, quiet hours are deferred to Phase 11+. The scheduler sends within the defined time windows only, which is a partial mitigation.
- **`goal_followup` notification type deferred**: The spec in `docs/06-bildirimler.md` defines a `goal_followup` type requiring deeper Mem0 goal-tracking integration. It is not implemented in this feature.
- **Sequential user processing**: Notifications are delivered to users one at a time within each cycle. At high user counts the 30-minute cycle window could be exhausted before all users are processed. Bounded concurrency via `asyncio.Semaphore` is the planned mitigation, deferred to a later scale phase.
- **Implementation deviations from spec**:
  - The spec referenced `messaging.InvalidArgumentError`; the actual class is `firebase_admin.exceptions.InvalidArgumentError`. The implementation uses the correct import.
  - The spec referenced `await scheduler.shutdown()`; APScheduler 4.x uses `await scheduler.stop()`. The implementation uses the correct API.
  - The spec recommended `asyncio.get_event_loop().run_in_executor()` for Mem0; the implementation uses `asyncio.to_thread()`, which is the idiomatic Python 3.9+ replacement and consistent with the existing codebase.

---

## Extending This Feature

**Adding a new notification type**: Add the type string to `NOTIFICATION_TYPES` in `notification_scheduler.py`. Add its tone to `TONE_MAP`, its Mem0 query to `MEM0_QUERIES`, and its fallback messages (English and Turkish) to `FALLBACK_MESSAGES`. Add the trigger condition as a new `if` block inside `evaluate_notification_triggers()`, following the existing pattern. Add corresponding unit tests.

**Adding notification preferences**: Inside `_process_notification()`, after fetching the default character, add a query against a future `notification_preferences` table. If the user has opted out of the given `notification_type`, return early. No changes to `evaluate_notification_triggers()` are needed — it evaluates conditions, not preferences.

**Increasing throughput with bounded concurrency**: Replace the sequential `for notification_type in triggers` loop with a `asyncio.Semaphore`-bounded `asyncio.gather()`. The per-user error isolation pattern (`try/except` per user in `run_notification_cycle`) should be preserved.

**Disabling the scheduler in a specific environment**: Set `NOTIFICATION_SCHEDULER_ENABLED=false` in the environment. Neither Firebase nor APScheduler will be initialized at startup.

**Adding a new language for fallback messages**: Add the language code as a new key inside each type's dict in `FALLBACK_MESSAGES`. The `_get_fallback_message()` function falls back to `"en"` for unrecognized language codes.

---

## Related Documentation

- [Proactive Notification System Design](../06-bildirimler.md) — full notification type definitions, FCM architecture, trigger conditions
- [Database Schema and API Endpoints](../04-veri-api.md) — `user_activity`, `profiles`, `characters` table definitions
- [AI Memory System](../05-ai-bellek.md) — Mem0 `agent_id` format, memory isolation per character
- [Activity Tracking Middleware](./activity-tracking-middleware.md) — P02-01, which populates `last_active_at` and `last_chat_at` that this scheduler reads
- [LLM Provider Abstraction](./llm-provider-abstraction.md) — P1.5-05, which provides `get_llm_router()` and `complete_fast()` used for Haiku calls
