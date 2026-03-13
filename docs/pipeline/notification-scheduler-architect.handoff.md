# Architect Handoff: Notification Scheduler

**Date**: 2026-03-13
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

An APScheduler-based async notification scheduler that integrates with FastAPI's lifespan to run a cron job every 30 minutes. The job evaluates four notification trigger conditions (morning check-in, afternoon nudge, evening reflection, sleep reminder) per user based on their local timezone, generates personalized messages using Claude Haiku with Mem0 memories, and delivers them via Firebase Cloud Messaging. A separate hourly job resets the daily notification tracking array at each user's local midnight.

## Key Decisions

- APScheduler (in-process) over Celery/external cron: avoids operational complexity of a separate worker process for a job that runs every 30 minutes
- Sequential user processing over concurrent: prevents API rate limit spikes on Anthropic and Mem0; bounded concurrency deferred to scale phase
- Hourly midnight reset job instead of per-user cron: simpler than scheduling per-user jobs across all timezones
- Deterministic fallback messages when Claude or Mem0 is unavailable: a generic notification is better than no notification
- Notification preferences are out of scope: the preferences endpoint and preference checking will be a separate feature
- `evaluate_notification_triggers` is a pure function (receives `local_now` as parameter) for testability

## Spec Location

`shared/feature-specs/notification-scheduler.md`

## Assumptions Made

- The `firebase_admin` SDK is already in `requirements.txt` but `firebase_admin.initialize_app()` has not been called anywhere yet. This feature adds the initialization call.
- Users without an `fcm_token` are simply skipped (no error). FCM token registration is handled by a separate feature.
- Notification preferences are not yet implemented. The scheduler sends all applicable types. When preferences are added, the scheduler will gain a preference check step.
- The `goal_followup` notification type from `docs/06-bildirimler.md` is deferred to a later phase (requires deeper Mem0 goal-tracking integration).

## Dependencies

- Requires: P02-01 (activity-tracking-middleware) -- must be implemented first so `user_activity` has data
- Requires: P01-02 (database-schema) -- `user_activity`, `profiles`, `characters` tables
- Blocks: backend-dev, backend-tester (they implement and test this spec)

## Next Steps

backend-dev should read the spec and implement. backend-tester follows after implementation is complete.
