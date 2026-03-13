# Backend Test Handoff: Notification Scheduler

**Date**: 2026-03-13
**Agent**: backend-tester
**Status**: COMPLETE

## Test Files Written

- `backend/tests/services/test_notification_scheduler_extended.py` — 50 tests
- `backend/tests/services/test_notification_sender_extended.py` — 8 tests

## Coverage Results

| File | Lines | % | Branches | Target |
|------|-------|---|----------|--------|
| `app/services/notification_scheduler.py` | 171 | **98%** | — | >= 80% |
| `app/services/notification_sender.py` | 34 | **100%** | — | >= 80% |

Uncovered lines (4 total, intentionally excluded):
- Lines 215-216: `reset_notifications_sent_today` default `now_utc = datetime.now(UTC)` path — not reachable via unit test without real scheduler invocation; covered implicitly by the `run_notification_cycle` default-arg test
- Lines 525-526: `_search_mem0` direct execution body — always bypassed via `asyncio.to_thread` mock in unit tests; requires real Mem0 credentials to exercise directly

## Test Run Results

Combined (new + existing tests):
- Passed: **89**
- Failed: **0**
- Skipped: **0**

New tests only:
- `test_notification_scheduler_extended.py`: 50 passed
- `test_notification_sender_extended.py`: 8 passed

## What the New Tests Add

### Timezone edge cases (`TestTimezoneEdgeCases` — 7 tests)
- Verified trigger evaluation uses user's local timezone, not UTC
- America/New_York (UTC-4 DST), Asia/Tokyo (UTC+9), America/Los_Angeles, Europe/Berlin
- `chatted_today` boundary: chat at UTC 23:30 the day before = yesterday locally for UTC-8 user
- UTC+13 user: local date is ahead of UTC date, chat-today suppression still works

### Window boundary conditions (`TestWindowBoundaries` — 10 tests)
- 07:59 excluded from morning window
- 14:00 included, 15:30 excluded from afternoon window
- 20:00 included, 21:00 excluded from evening window
- 23:00 exactly included in sleep window
- `last_active_at` exactly 60 minutes ago is within window (boundary is `>=`)
- `last_active_at` 61 minutes ago is outside window
- `last_chat_at` exactly at local midnight counts as "today" (boundary is `>=`)

### Deduplication edge cases (`TestDeduplicationEdgeCases` — 4 tests)
- All 4 types in `notifications_sent_today` blocks all triggers at all windows
- `evening_reflection` and `sleep_reminder` windows cannot overlap (verified)
- Having `morning_checkin` in sent_today does NOT suppress `afternoon_nudge`
- Unknown/future types in `notifications_sent_today` are silently ignored

### Midnight reset edge cases (`TestMidnightResetEdgeCases` — 5 tests)
- Istanbul (UTC+3) at UTC 00:30 = local 03:30, NOT midnight — no UPDATE
- New York (UTC-4 DST) at UTC 04:00 = local midnight — UPDATE issued
- Invalid timezone silently skipped (no raise, no UPDATE)
- Empty result set → no UPDATE, no commit
- Multiple users crossing midnight in same UTC hour all reset in one UPDATE

### Scheduler lifecycle (`TestSchedulerLifecycle` — 3 tests)
- `start_notification_scheduler` returns the scheduler instance
- Exactly two jobs are added (`add_schedule` called twice)
- One job uses `IntervalTrigger`, one uses `CronTrigger`

### Batch processing (`TestBatchProcessing` — 2 tests)
- Three DB fetch calls (first batch, second batch, empty terminator) for 2 users with batch_size=100
- Empty first batch causes zero `_process_user` calls

### _process_user edge cases (`TestProcessUserEdgeCases` — 3 tests)
- Returns 0 at midday (outside all windows)
- Returns count equal to triggered notifications processed
- `notifications_sent_today = None` is treated as empty list (no crash)

### _process_notification edge cases (`TestProcessNotificationEdgeCases` — 3 tests)
- No default character → FCM never called, returns silently
- FCM returns False → `notifications_sent_today` is NOT updated (token cleared instead)
- DB write failure on `notifications_sent_today` update → caught, not re-raised

### Message generation fallbacks (`TestGenerateNotificationMessageFallbacks` — 4 tests)
- Mem0 works + Claude fails → deterministic English fallback
- Mem0 works + Claude works → stripped Claude message returned
- `preferred_language = None` → English fallback
- All 4 notification types produce non-empty fallbacks

### _get_fallback_message edge cases (`TestGetFallbackMessage` — 5 tests)
- Unknown notification type → returns some non-empty string (ultimate default)
- Unknown language for valid type → English fallback
- All 4 types have distinct Turkish fallbacks
- Specific content assertions for `evening_reflection` and `sleep_reminder` Turkish

### run_notification_cycle edge cases (`TestRunNotificationCycleEdgeCases` — 3 tests)
- DB session open failure → logged, no propagation
- `now_utc = None` → uses `datetime.now(UTC)` without error
- Reset function `now_utc = None` → uses `datetime.now(UTC)` without error

### _process_user exception handling (`TestProcessUserExceptionHandling` — 1 test)
- Exception from `_process_notification` is caught, count stays 0, no re-raise

### No FCM token at process time (`TestProcessNotificationNoFcmToken` — 1 test)
- `profile.fcm_token = None` when character is found → `send_push_notification` not called

### FCM sender extras (`TestSendPushNotificationExtended` — 4 tests)
- `InvalidArgumentError` (distinct from `UnregisteredError`) returns False
- Message constructed with correct fields (title, body, data, token)
- Short token (< 20 chars) does not raise `IndexError` on `[:20]` slice in logging
- Both token-invalidity error types return False

### Firebase init extras (`TestInitializeFirebaseExtended` — 4 tests)
- Invalid JSON credentials raises exception (propagated to caller)
- Valid JSON with no prior app → `initialize_app` called once
- Already initialized → `initialize_app` not called
- Empty string → skipped (same as existing test, confirms idempotency)

## Issues Found During Testing

- **DST hazard in test assertions**: `America/New_York` is UTC-4 (not UTC-5) on 2026-03-13 due to DST. Initial test used UTC 05:00; corrected to UTC 04:00. Future test authors should compute the actual offset at the test date using `ZoneInfo` rather than assuming standard time.
- No bugs found in the implementation itself. All spec behaviors are correctly implemented.

## Notes for Reviewer

- The `_search_mem0` function (lines 525-526) is always mocked at the `asyncio.to_thread` level in unit tests. If a future integration test wants to cover this path, it would need a real Mem0 API key. This is intentional and consistent with the existing codebase pattern of mocking external service clients.
- The 98% line coverage for `notification_scheduler.py` is well above the 80% threshold. The 2% gap is from the two described unreachable-in-unit-test paths.
- All tests are pure unit tests with mocked DB sessions; no integration DB is required.
