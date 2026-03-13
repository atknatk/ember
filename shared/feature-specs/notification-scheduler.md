# Feature Spec: P02-02 -- Notification Scheduler

**Feature ID**: P02-02
**Phase**: 2
**Layer**: backend
**GitHub Issue**: #14
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature adds an APScheduler-based async scheduler to the FastAPI backend, integrated via the application lifespan. A cron job runs every 30 minutes, iterating over all users who have a `user_activity` row and an `fcm_token`. For each user, the scheduler converts the current UTC time to the user's local timezone (from `profiles.timezone`), evaluates four notification trigger conditions, and -- when a condition is met and that notification type has not already been sent today -- generates a personalized notification message using Claude Haiku and sends it via Firebase Cloud Messaging (FCM).

The four notification types are:

| Type | Local Time Window | Condition |
|------|-------------------|-----------|
| `morning_checkin` | 08:00 -- 09:30 | No chat today (`last_chat_at` is NULL or before midnight local) |
| `afternoon_nudge` | 14:00 -- 15:30 | No chat today |
| `evening_reflection` | 20:00 -- 21:00 | No `evening_reflection` sent today |
| `sleep_reminder` | 23:00+ | User was active in the last 60 minutes (`last_active_at` within 60 min) |

Each notification type is sent at most once per day per user. The `notifications_sent_today` JSONB array on `user_activity` tracks which types have been sent. A separate midnight-reset job clears this array daily (based on user timezone).

### Why It Exists

Proactive notifications are a core differentiator for Ember. Unlike passive chatbots that wait for user input, Ember reaches out with context-aware, personalized messages. This drives engagement, retention, and establishes the companion relationship described in `docs/01-vizyon.md`. The notification system is fully specified in `docs/06-bildirimler.md`.

### Dependencies

- **Requires**: P02-01 (activity-tracking-middleware) -- populates the `user_activity` table that this scheduler reads
- **Requires**: P01-02 (database-schema) -- `user_activity` table, `profiles` table, `characters` table
- **Requires**: P01-04 (auth-endpoints) -- user registration creates the profile with `fcm_token` and `timezone`
- **Extends**: `docs/06-bildirimler.md` -- implements the cron job, trigger conditions, and personalization flow

### What This Feature Does NOT Do

- It does not implement the `goal_followup` notification type (requires deeper Mem0 integration, deferred to a later phase).
- It does not implement notification preferences UI or the `PUT /notifications/preferences` endpoint (separate feature).
- It does not implement the `PUT /notifications/token` endpoint for FCM token registration (separate feature).
- It does not implement "quiet hours" / "do not disturb" (Phase 11+, per `docs/06-bildirimler.md`).
- It does not modify any existing API endpoint behavior.
- It does not expose any new REST endpoints.

---

## 2. Data Models

### No New Tables

All required tables already exist per `docs/04-veri-api.md`:
- `user_activity` -- has `last_active_at`, `last_chat_at`, `notifications_sent_today`, `updated_at`
- `profiles` -- has `fcm_token`, `timezone`, `preferred_language`, `mem0_user_id`
- `characters` -- has `template`, `is_default`, `is_active`, `mem0_agent_id`

### No Schema Changes

No `ALTER TABLE` statements are needed. The existing schema supports all operations described in this spec.

### No New Indexes

The scheduler queries `user_activity` joined with `profiles`. Both tables use `user_id` as the primary key (or foreign key with an index). The join is on `user_activity.user_id = profiles.id`, which uses the primary key on both sides. The query also filters on `profiles.fcm_token IS NOT NULL`, but a partial index on this column is not warranted at this scale (the table scan is bounded by total user count, and users without FCM tokens are simply skipped in application code).

### Columns Read (Not Modified)

| Table | Columns Read | Purpose |
|-------|-------------|---------|
| `user_activity` | `user_id`, `last_active_at`, `last_chat_at`, `notifications_sent_today` | Evaluate trigger conditions |
| `profiles` | `id`, `fcm_token`, `timezone`, `preferred_language`, `mem0_user_id`, `name` | Timezone conversion, FCM delivery, personalization |
| `characters` | `user_id`, `template`, `is_default`, `is_active`, `name` | Select default character for notification context |

### Columns Written

| Table | Column | Operation |
|-------|--------|-----------|
| `user_activity` | `notifications_sent_today` | Append notification type after successful send |
| `user_activity` | `updated_at` | Auto-updated by `onupdate=func.now()` |

### Mem0 Operations

**Search** (read-only): When generating a personalized notification message, the scheduler searches Mem0 for relevant memories to include in the Claude Haiku prompt. The search uses:
- `user_id`: the profile's `mem0_user_id`
- `agent_id`: the default character's `mem0_agent_id`
- `query`: a notification-type-specific query string (e.g., "morning routine and habits" for `morning_checkin`)
- `limit`: 5

The `agent_id` follows the standard format `{template}_{user_id}` per `docs/05-ai-bellek.md`.

**No writes**: The scheduler does not add memories to Mem0.

---

## 3. API Changes

### No New Endpoints

This feature does not introduce any new API endpoints. It is a background scheduler that runs within the FastAPI process.

### No Response Changes

No existing endpoint responses are modified.

---

## 4. Backend Logic

### New Dependency: APScheduler

Add `apscheduler>=4.0.0a5,<5.0.0` to `backend/requirements.txt`. APScheduler 4.x provides native asyncio support, which integrates cleanly with FastAPI's async event loop. Use the `AsyncScheduler` class with an `IntervalTrigger`.

### New Config Values in `backend/app/config.py`

```
# Notification Scheduler
notification_scheduler_enabled: bool = True
notification_scheduler_interval_minutes: int = 30
notification_batch_size: int = 100
```

- `notification_scheduler_enabled`: Allows disabling the scheduler in test environments or local development. Defaults to `True`.
- `notification_scheduler_interval_minutes`: The interval between scheduler runs. Defaults to 30 minutes.
- `notification_batch_size`: Number of users to process per batch to avoid loading all users into memory at once. Defaults to 100.

### Lifespan Integration in `backend/app/main.py`

The scheduler is started in the `lifespan` context manager and shut down on application exit. The scheduler runs inside the same event loop as FastAPI.

Modified lifespan behavior:

1. On startup, if `settings.notification_scheduler_enabled` is `True`:
   - Import and call `start_notification_scheduler()` from the scheduler service.
   - Store the scheduler reference in `app.state.scheduler` for graceful shutdown.
2. On shutdown:
   - If `app.state.scheduler` exists, call `await scheduler.shutdown()`.

### Service: `backend/app/services/notification_scheduler.py`

This is the main module. It contains the scheduler setup and the core scheduling logic.

#### Function: `start_notification_scheduler`

```
async def start_notification_scheduler() -> AsyncScheduler
```

Responsibilities:
1. Create an `AsyncScheduler` instance.
2. Add a job using `IntervalTrigger(minutes=settings.notification_scheduler_interval_minutes)` that calls `run_notification_cycle`.
3. Add a second job using `CronTrigger(minute=0)` (every hour on the hour) that calls `reset_notifications_sent_today`. This handles midnight resets across timezones by checking every hour.
4. Start the scheduler with `await scheduler.start_in_background()`.
5. Return the scheduler instance.

#### Function: `run_notification_cycle`

```
async def run_notification_cycle() -> None
```

This is the main cron job that runs every 30 minutes. Responsibilities:

1. Create a database session via `AsyncSessionLocal()`.
2. Query all users who have activity data and an FCM token, in batches of `notification_batch_size`. The query joins `user_activity` with `profiles` on `user_activity.user_id = profiles.id`, filtering where `profiles.fcm_token IS NOT NULL`.
3. For each user in the batch:
   a. Convert current UTC time to user's local time using `zoneinfo.ZoneInfo(profile.timezone)`.
   b. Handle invalid timezone gracefully (log warning, skip user).
   c. Call `evaluate_notification_triggers(user_activity, local_now)` to determine which notification types should fire.
   d. For each triggered notification type, call `process_notification(profile, user_activity, notification_type)`.
4. Catch and log all exceptions per-user. A failure for one user must not prevent processing other users.
5. Close the database session.

#### Function: `evaluate_notification_triggers`

```
def evaluate_notification_triggers(
    user_activity: UserActivity,
    local_now: datetime,
) -> list[str]
```

A pure function (no I/O) that returns a list of notification type strings that should be triggered. Logic:

1. Parse `notifications_sent_today` from JSONB (it is a list of strings).
2. Compute `local_today_start` as midnight in the user's local timezone for today.
3. Determine `chatted_today`: True if `last_chat_at` is not None and `last_chat_at >= local_today_start`.
4. Evaluate each trigger:

| Type | Condition |
|------|-----------|
| `morning_checkin` | 08:00 <= local_now.hour*60+local_now.minute < 570 (09:30) AND NOT chatted_today AND `morning_checkin` not in sent_today |
| `afternoon_nudge` | 14:00 <= local_time < 15:30 AND NOT chatted_today AND `afternoon_nudge` not in sent_today |
| `evening_reflection` | 20:00 <= local_time < 21:00 AND `evening_reflection` not in sent_today |
| `sleep_reminder` | local_time >= 23:00 AND `last_active_at` is not None AND `last_active_at` >= (now_utc - 60 minutes) AND `sleep_reminder` not in sent_today |

5. Return the list of triggered types.

Note on time comparison: `morning_checkin` and `afternoon_nudge` check `chatted_today` (no chat since midnight local). `evening_reflection` does NOT check chat activity -- it fires regardless of chat, as it is a reflective prompt. `sleep_reminder` checks `last_active_at` (recent activity), not chat.

#### Function: `process_notification`

```
async def process_notification(
    profile: Profile,
    user_activity: UserActivity,
    notification_type: str,
) -> None
```

Responsibilities:

1. Find the user's default character: query `characters` where `user_id = profile.id AND is_default = True AND is_active = True`. If no default character exists, skip (log warning).
2. Generate the personalized notification message:
   a. Search Mem0 for relevant memories using `asyncio.to_thread()` (Mem0 SDK is synchronous). Use the default character's `mem0_agent_id` and the notification-type-specific query.
   b. Build a prompt for Claude Haiku with the memories, notification type, user's name, current local time, and preferred language.
   c. Call Claude Haiku via the Anthropic SDK to generate a short (1-2 sentence) notification message.
   d. If Claude or Mem0 fails, use a deterministic fallback message per notification type and language.
3. Send the FCM push notification:
   a. Use `firebase_admin.messaging.send()` with the user's `fcm_token`.
   b. The notification payload includes: `title` (character name), `body` (generated message), `data.character_id` (the default character's UUID, for deep-link on tap), `data.notification_type`.
4. On successful send, update `notifications_sent_today`:
   a. Append the notification type string to the JSONB array.
   b. Use a SQL update: `UPDATE user_activity SET notifications_sent_today = notifications_sent_today || '["morning_checkin"]'::jsonb WHERE user_id = $1`.
5. On FCM failure (invalid token, etc.), log the error. If the error indicates an invalid/expired token, set `profiles.fcm_token = NULL` to prevent future attempts.

#### Function: `reset_notifications_sent_today`

```
async def reset_notifications_sent_today() -> None
```

Runs every hour. Responsibilities:

1. Create a database session.
2. Query all `user_activity` rows joined with `profiles` where `notifications_sent_today != '[]'::jsonb`.
3. For each user, compute the current local time. If the local time has crossed midnight (i.e., local hour is 0), reset `notifications_sent_today` to `[]`.
4. Execute the reset as a batched UPDATE.

The hourly check (rather than a single midnight run) handles the fact that users span many timezones. Each user's midnight is different.

#### Mem0 Search Queries by Notification Type

| Notification Type | Mem0 Search Query |
|-------------------|-------------------|
| `morning_checkin` | `"morning routine, daily plans, habits"` |
| `afternoon_nudge` | `"hobbies, interests, current goals"` |
| `evening_reflection` | `"daily reflection, mood, feelings, evening routine"` |
| `sleep_reminder` | `"sleep schedule, wake up time, rest"` |

#### Claude Haiku Prompt Template

The prompt sent to Claude Haiku for notification text generation:

```
System: You are {character_name}, the user's personal AI companion. Generate a short push notification message (1-2 sentences max, under 100 characters if possible). The tone should be {tone}. Write in {language}.

User:
Notification type: {notification_type}
User's name: {user_name}
Current local time: {local_time}
Relevant memories:
{formatted_memories}

Generate a warm, personalized notification message. Do not use quotes. Do not include emoji.
```

Tone mapping:
- `morning_checkin`: "warm and energetic"
- `afternoon_nudge`: "curious and light"
- `evening_reflection`: "calm and reflective"
- `sleep_reminder`: "gentle and caring"

#### Deterministic Fallback Messages

When Claude Haiku or Mem0 is unavailable, use these fallback messages:

| Type | English | Turkish |
|------|---------|---------|
| `morning_checkin` | "Good morning! How are you feeling today?" | "Gunaydin! Bugun nasil hissediyorsun?" |
| `afternoon_nudge` | "Hey! Haven't heard from you today. Everything okay?" | "Selam! Bugun konusmadik, her sey yolunda mi?" |
| `evening_reflection` | "How was your day? I'd love to hear about it." | "Gunun nasil gecti? Duymak isterim." |
| `sleep_reminder` | "It's getting late. Time to wind down?" | "Gec oldu. Yatma vakti geldi mi?" |

#### Firebase FCM Integration

The `firebase_admin` SDK is already in `requirements.txt`. The scheduler uses it to send individual push notifications.

FCM message structure:
```python
messaging.Message(
    notification=messaging.Notification(
        title=character_name,
        body=generated_message,
    ),
    data={
        "character_id": str(character_id),
        "notification_type": notification_type,
    },
    token=fcm_token,
)
```

Firebase Admin SDK initialization: call `firebase_admin.initialize_app()` during lifespan startup, using credentials from `settings.firebase_credentials_json`. If already initialized (idempotent check), skip. This initialization should happen in the lifespan before the scheduler starts.

#### Error Handling

| Error | Handling |
|-------|----------|
| Invalid user timezone | Log warning, skip user |
| Mem0 search failure | Use fallback message (no memories) |
| Claude Haiku failure | Use deterministic fallback message |
| FCM send failure (invalid token) | Log error, set `fcm_token = NULL` on profile |
| FCM send failure (other) | Log error, skip -- will retry next cycle |
| Database error during notifications_sent_today update | Log error, skip -- worst case user gets a duplicate next cycle |
| Unhandled exception for one user | Log error, continue processing remaining users |

#### Concurrency and Performance

- The scheduler runs in the same event loop as FastAPI. Since all I/O is async (database via asyncpg, Claude via httpx, Mem0 via `asyncio.to_thread`), it does not block request handling.
- Users are processed sequentially within each batch to avoid overwhelming external services (Claude API rate limits, FCM quotas). If performance becomes an issue at scale, introduce `asyncio.Semaphore`-bounded concurrency (not in scope for P02-02).
- The Mem0 search and Claude Haiku call for a single notification can be parallelized with `asyncio.gather()` only if memories are not needed for the prompt. Since memories ARE part of the Haiku prompt, these must be sequential: Mem0 search first, then Haiku call.

### Service: `backend/app/services/notification_sender.py`

Extracted FCM sending logic for testability.

#### Function: `send_push_notification`

```
async def send_push_notification(
    fcm_token: str,
    title: str,
    body: str,
    data: dict[str, str],
) -> bool
```

Responsibilities:
1. Construct a `messaging.Message` with the provided fields.
2. Call `messaging.send()` via `asyncio.to_thread()` (firebase-admin is synchronous).
3. Return `True` on success.
4. On `messaging.UnregisteredError` or `messaging.InvalidArgumentError`, return `False` and the caller should invalidate the token.
5. On other errors, log and return `False`.

#### Function: `initialize_firebase`

```
def initialize_firebase(credentials_json: str) -> None
```

Parses the JSON credentials string, creates a `credentials.Certificate`, and calls `firebase_admin.initialize_app()`. Idempotent -- checks `firebase_admin._apps` before initializing.

---

## 5. iOS Screens and Components

Not applicable. This is a backend-only feature with no mobile UI changes.

---

## 6. Android Screens and Components

Not applicable. This is a backend-only feature with no mobile UI changes.

---

## 7. Test Plan

### Backend Tests

#### Unit Tests: `backend/tests/services/test_notification_scheduler.py`

| # | Scenario | Expected |
|---|----------|----------|
| 1 | `evaluate_notification_triggers` at 08:30 local, no chat today, no prior notifications | Returns `["morning_checkin"]` |
| 2 | `evaluate_notification_triggers` at 08:30 local, user chatted today | Returns `[]` (morning_checkin suppressed) |
| 3 | `evaluate_notification_triggers` at 08:30 local, `morning_checkin` already in `notifications_sent_today` | Returns `[]` |
| 4 | `evaluate_notification_triggers` at 14:30 local, no chat today | Returns `["afternoon_nudge"]` |
| 5 | `evaluate_notification_triggers` at 14:30 local, user chatted today | Returns `[]` |
| 6 | `evaluate_notification_triggers` at 20:30 local, no prior evening notification | Returns `["evening_reflection"]` |
| 7 | `evaluate_notification_triggers` at 20:30 local, `evening_reflection` already sent | Returns `[]` |
| 8 | `evaluate_notification_triggers` at 23:15 local, user active 30 min ago | Returns `["sleep_reminder"]` |
| 9 | `evaluate_notification_triggers` at 23:15 local, user last active 2 hours ago | Returns `[]` (not recently active) |
| 10 | `evaluate_notification_triggers` at 23:15 local, `sleep_reminder` already sent | Returns `[]` |
| 11 | `evaluate_notification_triggers` at 10:00 local (outside all windows) | Returns `[]` |
| 12 | `evaluate_notification_triggers` at 08:30 AND 20:30 simultaneously applicable (edge: multiple triggers in one cycle is impossible due to non-overlapping windows) | Correct single result returned |
| 13 | `process_notification` with valid user, Mem0 returns memories, Haiku generates message | FCM send called with personalized message, `notifications_sent_today` updated |
| 14 | `process_notification` when Mem0 search fails | Haiku called with empty memories, or fallback used |
| 15 | `process_notification` when Haiku call fails | Fallback message used, FCM still called |
| 16 | `process_notification` when FCM send returns invalid token error | `fcm_token` set to NULL on profile |
| 17 | `run_notification_cycle` skips users without `fcm_token` | No FCM call for tokenless users |
| 18 | `run_notification_cycle` skips users with invalid timezone | Warning logged, user skipped |
| 19 | `run_notification_cycle` exception for one user does not prevent processing others | Subsequent users still processed |
| 20 | `reset_notifications_sent_today` resets only users whose local time crossed midnight | Users in UTC+0 reset at UTC midnight, UTC+5 reset at UTC 19:00 |

#### Unit Tests: `backend/tests/services/test_notification_sender.py`

| # | Scenario | Expected |
|---|----------|----------|
| 21 | `send_push_notification` with valid token | Returns `True`, `messaging.send` called |
| 22 | `send_push_notification` with unregistered token | Returns `False` |
| 23 | `send_push_notification` with other FCM error | Returns `False`, error logged |
| 24 | `initialize_firebase` called twice | Second call is a no-op (idempotent) |

#### How to Mock

- **Mem0**: Mock the `MemoryClient.search` method. Since Mem0 calls are wrapped in `asyncio.to_thread`, mock at the service level where the Mem0 client is called.
- **Claude Haiku**: Mock the Anthropic client's `messages.create` method. Return a fixed response with a `content[0].text` field.
- **Firebase**: Mock `firebase_admin.messaging.send` via `unittest.mock.patch`. For unregistered token tests, raise `messaging.UnregisteredError`.
- **Database**: Use the test database fixture from `conftest.py`. Insert test `profiles` and `user_activity` rows directly.
- **Time**: Use `unittest.mock.patch` on `datetime.now` or pass `now_utc` as a parameter to `run_notification_cycle` and `evaluate_notification_triggers` for deterministic testing.

#### Integration Tests: `backend/tests/services/test_notification_scheduler_integration.py`

| # | Scenario | Expected |
|---|----------|----------|
| 25 | Full cycle: user with `fcm_token`, in morning window, no chat today | `notifications_sent_today` contains `"morning_checkin"` after cycle |
| 26 | Full cycle: user already notified today | No duplicate notification sent |
| 27 | Midnight reset: user in timezone where it is now past midnight | `notifications_sent_today` is reset to `[]` |

---

## 8. Acceptance Criteria

1. Given the FastAPI application starts with `notification_scheduler_enabled=True`, when the lifespan initializes, then APScheduler is running with a job that executes every 30 minutes.

2. Given a user with timezone "America/New_York" and local time 08:15, who has not chatted today and has an FCM token, when the notification cycle runs, then the user receives a `morning_checkin` push notification.

3. Given a user who has already received a `morning_checkin` today (recorded in `notifications_sent_today`), when the notification cycle runs again during the 08:00-09:30 window, then no duplicate `morning_checkin` is sent.

4. Given a user with timezone "Europe/Istanbul" and local time 14:30, who has not chatted today, when the notification cycle runs, then the user receives an `afternoon_nudge` push notification.

5. Given a user who chatted at 10:00 today (local time), when the notification cycle runs at 14:30 local, then no `afternoon_nudge` is sent (chatted_today is true).

6. Given a user with local time 20:30, when the notification cycle runs, then the user receives an `evening_reflection` push notification regardless of chat activity.

7. Given a user with local time 23:15 who was active 30 minutes ago, when the notification cycle runs, then the user receives a `sleep_reminder` push notification.

8. Given a user with local time 23:15 who was last active 2 hours ago, when the notification cycle runs, then no `sleep_reminder` is sent.

9. Given a user without an FCM token, when the notification cycle runs, then that user is skipped entirely (no error, no notification attempt).

10. Given Mem0 search fails during notification generation, when the scheduler processes a notification, then a fallback message is used and the notification is still sent.

11. Given Claude Haiku API fails during notification generation, when the scheduler processes a notification, then a deterministic fallback message (appropriate to the notification type and user language) is sent.

12. Given an FCM send returns an invalid/unregistered token error, when the send fails, then `profiles.fcm_token` is set to NULL for that user.

13. Given an exception occurs while processing one user, when the scheduler continues, then remaining users in the batch are still processed.

14. Given a user whose local time has crossed midnight, when the hourly reset job runs, then `notifications_sent_today` is reset to `[]` for that user.

15. Given `notification_scheduler_enabled=False` in configuration, when the application starts, then no scheduler is created and no background jobs run.

16. Given the backend test suite, when `pytest backend/tests/services/test_notification_scheduler.py backend/tests/services/test_notification_sender.py -v` is run, then all tests pass with exit code 0.

---

## 9. File Manifest

```
Backend:
  CREATE  backend/app/services/notification_scheduler.py
  CREATE  backend/app/services/notification_sender.py
  MODIFY  backend/app/main.py                              (lifespan: start/stop scheduler, initialize Firebase)
  MODIFY  backend/app/config.py                            (add 3 notification scheduler settings)
  MODIFY  backend/requirements.txt                         (add apscheduler)
  CREATE  backend/tests/services/test_notification_scheduler.py
  CREATE  backend/tests/services/test_notification_sender.py

Shared:
  CREATE  shared/feature-specs/notification-scheduler.md           (this file)
  CREATE  docs/pipeline/notification-scheduler-architect.handoff.md
```

### Summary

| Action | Count |
|--------|-------|
| CREATE | 5 |
| MODIFY | 3 |
| DELETE | 0 |
| **Total** | **8** |

### Files NOT Modified

- `backend/app/models/user_activity.py` -- the model already has `notifications_sent_today` and all required columns.
- `backend/app/models/profile.py` -- already has `fcm_token`, `timezone`, `preferred_language`, `mem0_user_id`.
- `backend/app/models/character.py` -- already has `is_default`, `is_active`, `mem0_agent_id`, `template`.
- `backend/app/services/activity_service.py` -- activity tracking is unchanged; this feature only reads the data that P02-01 writes.
- `backend/app/routes/` -- no new endpoints; no route files are modified.
- `backend/app/middleware/` -- no middleware changes.

---

## 10. Design Decisions and Rationale

### Why APScheduler instead of Celery or external cron

APScheduler runs in-process with FastAPI, sharing the same event loop. This avoids the operational complexity of a separate Celery worker, Redis broker, and additional ECS task definitions. For a job that runs every 30 minutes and processes users sequentially, in-process scheduling is sufficient. If Ember scales to millions of users and the notification cycle takes longer than 30 minutes, this can be migrated to a Celery task or a separate ECS scheduled task. For now, simplicity wins.

### Why sequential user processing instead of concurrent

Each user's notification potentially involves a Mem0 search and a Claude Haiku API call. Running these concurrently for all users would spike API usage and risk rate limiting from Anthropic or Mem0. Sequential processing with per-user error isolation is safer and simpler. If the cycle takes too long at scale, introduce bounded concurrency with `asyncio.Semaphore`.

### Why hourly midnight reset instead of per-user cron

A single job that runs every hour and checks each user's local time is simpler than scheduling a per-user cron job at their local midnight. With users across all timezones, the hourly approach catches every midnight within a 1-hour window, which is acceptable for a daily reset.

### Why fallback messages instead of skipping

If Claude or Mem0 is down, the user still benefits from a generic notification. A missed notification is worse than a generic one -- the proactive outreach is the feature, and personalization is an enhancement.

### Why not use notification preferences in this feature

Notification preferences (`PUT /notifications/preferences`) are a separate feature. This scheduler currently sends all applicable notification types. When preferences are implemented, the scheduler will check preferences before sending. This is a deliberate scope boundary to keep P02-02 focused.

### Why `asyncio.to_thread` for Firebase and Mem0

Both `firebase_admin.messaging.send()` and the Mem0 SDK are synchronous (blocking). Wrapping them in `asyncio.to_thread()` offloads the blocking call to a thread pool, preventing the async event loop from stalling. This is consistent with the existing Mem0 usage pattern in `backend/app/services/chat_service.py`.

### Why pass `now_utc` as parameter to core functions

Making `evaluate_notification_triggers` accept `local_now` as a parameter (rather than calling `datetime.now()` internally) makes it a pure function that is trivially testable without mocking `datetime`. The caller (`run_notification_cycle`) is responsible for computing the current time and converting to the user's timezone.
