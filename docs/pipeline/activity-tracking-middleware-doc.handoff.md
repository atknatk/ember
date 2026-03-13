# Doc Writer Handoff: Activity Tracking Middleware

**Date**: 2026-03-13
**Agent**: doc-writer
**Status**: COMPLETE

## Documents Written
- `docs/features/activity-tracking-middleware.md` — main feature documentation
- `CHANGELOG.md` — added entry under [Unreleased]

## Summary

Documented the P02-01 activity tracking middleware, a backend-only feature that records `last_active_at` and `last_chat_at` timestamps on the `user_activity` table as a Starlette `BackgroundTask` on every authenticated request. The documentation covers the upsert logic, middleware stack ordering, JWT extraction reuse, chat path regex, test approach, and extension guidance for future developers.

## Notes

- No backend-tester handoff file existed. The backend-dev agent wrote and ran all 22 tests in a single pass. This deviation is noted in the Known Limitations section of the feature doc.
- The `_extract_sub_from_jwt` import from `request_id.py` is documented as a candidate for extraction to a shared utility if a third middleware needs it.
