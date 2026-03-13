# Backend Test Handoff: Observability Stack

**Date**: 2026-03-13
**Agent**: backend-tester
**Status**: COMPLETE

## Test Files Written / Extended

| File | Tests Added | Total Tests |
|------|-------------|-------------|
| `backend/tests/middleware/test_request_id.py` | +16 | 23 |
| `backend/tests/infra/test_health.py` | +14 | 23 |
| `backend/tests/infra/test_sentry.py` | 0 (already complete) | 6 |
| `backend/tests/utils/test_timing.py` | 0 (already complete) | 5 |
| `backend/tests/infra/test_logging.py` | 0 (already complete) | 9 |
| **Total** | **30 new** | **66** |

## Coverage Results

| Module | Lines | Branches |
|--------|-------|----------|
| `app/core/logging.py` | 100% | — |
| `app/core/sentry.py` | 100% | — |
| `app/middleware/request_id.py` | 97% | — |
| `app/utils/timing.py` | 100% | — |
| `app/services/health_service.py` | 94% | — |
| `app/routes/health.py` | 100% | — |
| **Overall** | **97%** | **(target: ≥ 80%)** |

### Intentionally Uncovered Lines

- `request_id.py` lines 101-102: Sentry `set_tag` call. Always runs in a silent `try/except`; only reachable if Sentry is initialized (requires a real DSN). Functional Sentry tests cover `init_sentry()` separately.
- `health_service.py` lines 95-96, 125-126: Inner `_do_probe()` coroutine bodies (actual MemoryClient / AsyncAnthropic call sites). These require real Mem0 / Claude API credentials and are intentionally excluded from unit tests.

## Test Run Results

```
66 passed, 0 failed, 9 warnings
```

Full suite (excluding pre-existing infra failures):
```
1603 passed, 13 skipped, 20 warnings
```

## New Tests Added

### `test_request_id.py` additions

**`TestExtractSubFromJwt`** (7 tests) — unit tests for the `_extract_sub_from_jwt` helper:
- Returns sub from valid JWT
- Returns None without Authorization header
- Returns None for non-Bearer auth
- Returns None for malformed JWT (wrong number of parts)
- Returns None for JWT without sub
- Returns None for JWT with non-string sub
- Returns None for invalid base64 payload (fail-open)

**`TestRequestIDMiddlewareLogging`** (9 tests) — middleware logging behavior:
- `request_started` and `request_completed` are both logged per request
- `request_completed` record includes `status_code` and `duration_ms` extra fields
- 4xx responses log at WARNING level
- 2xx responses log at INFO level
- JWT sub extraction verified via unit helper (authenticated path)
- Context vars cleared between requests (no leakage)
- `dispatch()` exception path logs `request_failed` at ERROR and re-raises
- 5xx responses log `request_completed` at ERROR level (tested via direct middleware dispatch)
- `user_id` binding verified for authenticated requests

### `test_health.py` additions

**`TestHealthServiceProbes`** (14 tests) — HealthService probe methods:
- `_probe_database`: ok (fast), unavailable (exception), unavailable (timeout), degraded (slow)
- `_probe_mem0`: unavailable (exception via wait_for), unavailable (TimeoutError), ok (fast via wait_for mock), degraded (slow via wait_for mock)
- `_probe_claude`: unavailable (exception via wait_for), unavailable (TimeoutError), ok (fast), degraded (slow)
- `check_dependencies`: treats gather exceptions as "unavailable" for each dep
- Parallel probes run concurrently (3 × 50ms completes in ~50ms, not 150ms)

## Issues Found During Testing

None. The implementation matches the spec exactly.

### Minor Observations (non-blocking)

1. The `RuntimeWarning: coroutine was never awaited` warnings from `_probe_claude` and `_probe_mem0` tests are benign and stem from the implementation design: `_do_probe()` is created and passed to `asyncio.wait_for`, but when `wait_for` is mocked to raise before awaiting, the coroutine object is garbage-collected without running. This is an implementation detail, not a test bug.

2. `request_id.py` lines 101-102 (Sentry `set_tag`) are executed in production but silently no-op in tests (Sentry not initialized). Coverage tools count them as uncovered. This is acceptable — the Sentry integration is tested through `test_sentry.py`.

## Notes for Reviewer

- All 36 tests that the backend-dev wrote continue to pass — no regressions.
- The `_extract_sub_from_jwt` helper was previously untested; 7 new unit tests cover all branches including malformed JWTs.
- The exception path in `RequestIDMiddleware.dispatch` (lines 114-125) was untested; now covered by `test_dispatch_exception_path_clears_context_and_reraises`.
- Health service probe "ok" and "degraded" status paths for Mem0 and Claude are now covered via `asyncio.wait_for` mocking.
- The parallel execution test verifies `asyncio.gather` is actually used (3 concurrent 50ms probes complete in ~50ms, not ~150ms).
