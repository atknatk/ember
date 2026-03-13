# Review Handoff — notification-scheduler

- **status**: APPROVED
- **feature**: P02-02 — notification-scheduler
- **layer**: backend
- **reviewer**: reviewer agent

## Review Summary

### Passed Checks (✅)

**Architecture**
- ✅ Correct endpoint pattern (background scheduler, not user-facing)
- ✅ agent_id format: `"{template}_{user_id}"` for all Mem0 calls
- ✅ user_id from JWT context (N/A — scheduler uses DB directly)
- ✅ asyncio.to_thread for blocking Mem0 + Firebase calls
- ✅ OFFSET usage justified (batch job over bounded user table, not user-facing pagination)

**Code Quality**
- ✅ No force unwrap
- ✅ No hardcoded secrets — all config via settings
- ✅ Error messages logged with context
- ✅ All API errors handled explicitly
- ✅ No TODO/FIXME in production code

**FCM Token Handling**
- ✅ SendResult class distinguishes SENT / INVALID_TOKEN / TRANSIENT_ERROR
- ✅ Token cleared ONLY on INVALID_TOKEN (UnregisteredError, InvalidArgumentError)
- ✅ Transient errors preserve the token (fixed in review cycle)

**Tests**
- ✅ 89 tests, all passing
- ✅ 98-100% coverage on new code
- ✅ Mem0 and Claude mocked — no real API calls
- ✅ All trigger windows tested with boundaries
- ✅ Token invalidation test updated for SendResult

## Fix Applied

- **Issue**: `notification_sender.py` returned `False` for both permanent and transient FCM failures, causing the scheduler to clear `fcm_token` on any error
- **Fix**: Introduced `SendResult` class with `SENT`, `INVALID_TOKEN`, `TRANSIENT_ERROR`. Scheduler now only clears token on `INVALID_TOKEN`.
- **Commit**: `fix(notification-scheduler): only clear FCM token on permanent failures`
