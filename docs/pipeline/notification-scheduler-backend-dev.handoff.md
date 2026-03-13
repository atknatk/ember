# Backend Dev Handoff: Notification Scheduler

**Date**: 2026-03-13
**Agent**: backend-dev
**Status**: COMPLETE

## Implemented Files
- `backend/app/services/notification_scheduler.py` -- 7 functions (scheduler lifecycle, trigger evaluation, per-user processing, message generation, midnight reset, batch fetching)
- `backend/app/services/notification_sender.py` -- 2 functions (FCM push delivery, Firebase initialization)
- `backend/app/config.py` -- 3 new settings added (notification_scheduler_enabled, notification_scheduler_interval_minutes, notification_batch_size)
- `backend/app/main.py` -- lifespan modified (Firebase init, scheduler start/stop)
- `backend/requirements.txt` -- added apscheduler>=4.0.0a5,<5.0.0
- `docs/standards/backend.md` -- updated project structure and config documentation
- `backend/tests/services/test_notification_scheduler.py` -- 26 tests
- `backend/tests/services/test_notification_sender.py` -- 5 tests

## Endpoints Implemented
- None (this is a background scheduler, no new REST endpoints)

## Key Functions
- `start_notification_scheduler()` -- creates AsyncScheduler with interval + cron triggers
- `run_notification_cycle(now_utc)` -- main cron job, processes users in batches
- `evaluate_notification_triggers(...)` -- pure function, returns list of triggered notification types
- `reset_notifications_sent_today(now_utc)` -- hourly midnight reset per user timezone
- `send_push_notification(...)` -- FCM delivery wrapper with error classification
- `initialize_firebase(credentials_json)` -- idempotent Firebase Admin SDK init

## Test Results
- pytest: 31 passed, 0 failed (notification tests)
- pytest: 1879 passed, 0 failed (full suite, excluding pre-existing infra failures)
- ruff: clean
- doc-code-sync: clean

## Known Issues / Deviations from Spec
- The spec mentions `messaging.InvalidArgumentError` on `firebase_admin.messaging`, but the actual class is `firebase_admin.exceptions.InvalidArgumentError`. Used the correct import.
- APScheduler 4.x uses `stop()` not `shutdown()` for graceful teardown. Used the correct API.
- The spec says `asyncio.get_event_loop().run_in_executor(None, ...)` for Mem0; used `asyncio.to_thread()` instead, which is the modern Python 3.9+ equivalent and consistent with existing codebase patterns.

## Notes for Backend Tester
- Mock `app.services.notification_scheduler._search_mem0` for all Mem0 tests
- Mock `app.services.notification_scheduler.get_llm_router` for Claude Haiku tests
- Mock `app.services.notification_sender.messaging.send` for FCM tests
- Mock `app.services.notification_scheduler.AsyncSessionLocal` for DB session tests
- The `evaluate_notification_triggers` function is pure (no I/O) -- test directly without mocking
- For `UnregisteredError`, import from `firebase_admin.messaging`; for `InvalidArgumentError`, import from `firebase_admin.exceptions`
- The `run_notification_cycle` and `reset_notifications_sent_today` accept an optional `now_utc` parameter for deterministic time testing
