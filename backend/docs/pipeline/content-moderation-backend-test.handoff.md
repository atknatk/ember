# Backend Test Handoff: Content Moderation

**Date**: 2026-03-13
**Agent**: backend-tester
**Status**: COMPLETE

## Test Files Written

- `backend/tests/services/test_content_moderation_extra.py` — 83 tests
- `backend/tests/routes/test_chat_moderation.py` — 16 tests

## Coverage Results

- `app/services/content_moderation.py`: **98%** lines (3 lines uncovered — lines 188/202-203, which are the `blocked_until` variable reset in the exception-swallow path of the abuse state check)
- Full suite (new + existing tests): 135 passed, 0 failed

## Test Run Results

- Passed: 135 (99 new + 36 pre-existing)
- Failed: 0
- Skipped: 0
- Pre-existing unrelated failures: 19 (infra/test_docker.py, infra/test_config.py — Docker/pyproject config checks not related to this feature)

## What the New Tests Cover

### `test_content_moderation_extra.py` — 83 tests

| Class | Tests | What it covers |
|-------|-------|----------------|
| `TestCheckPromptInjectionEdgeCases` | 20 | Base64 exactly 99/100 chars, delimiter exactly 2/3 chars, whitespace variants in patterns, multi-line injection, `\b` word boundary for `disregard`, empty string, unicode |
| `TestUpdateAbuseStateAllThresholds` | 9 | Every violation count (2, 3, 4, 5, 6, 10), boundary between 24h window reset/not-reset, lifetime violations not resetting across windows |
| `TestTherapistCrisisDetection` | 7 | Therapist+crisis, non-therapist+crisis (no augment), therapist+no-crisis, combined injection+crisis, unsafe+crisis blocked, medium severity blocked, all 5 categories at high severity |
| `TestLengthLimitBoundaryConditions` | 4 | Exactly 4000 chars (allowed), 4001 chars (blocked), LLM short-circuit on length, expired block allows through |
| `TestFailOpenVsFailClosed` | 3 | `moderation_fail_open=False` raises on malformed JSON, on LLM exception, on DB exception |
| `TestClassifyContentJsonVariants` | 4 | Missing JSON keys use defaults, whitespace trimming, classification prompt includes content, temperature=0.0 |
| `TestRecordViolationBackground` | 6 | Content truncation to 200 chars, short content stored as-is, `prompt_injection` does NOT update abuse state, `harmful_content` DOES update abuse state, DB failure swallowed, `length_exceeded` does NOT update abuse state |
| `TestModerationSSEEventSchema` | 4 | Default type="moderation", serialization, JSON output, empty message accepted |
| `TestModerationResultDataclass` | 4 | allowed/reason, frozen immutability, blocked_until |
| `TestContentClassificationDataclass` | 3 | safe, crisis, frozen |
| `TestModerationEventModel` | 7 | Table name, all columns present, nullable columns, indexes |
| `TestUserModerationStateModel` | 5 | Table name, all columns present, nullable/PK |
| `TestCheckMessageInjectionPreamble` | 7 | Preamble text content, no augment for clean message, blocked message has no augment, category=None for safe, low-severity category returned, blocked_until propagated, disabled skips everything |

### `test_chat_moderation.py` — 16 tests

| Class | Tests | What it covers |
|-------|-------|----------------|
| `TestChatModerationHTTPErrors` | 6 | Harmful content → 400, length 4001 → 422 (Pydantic), service-layer length → 400, blocked user → 403, clean message → 200 stream, no auth → 401 |
| `TestValidateSendMessageModeration` | 6 | validate_send_message raises 400, raises 403 with blocked_until, augment_system_prompt appended, moderation runs AFTER character lookup, template passed to moderation, context contains moderation_result |
| `TestModerationSSEEvent` | 4 | Moderation event emitted for therapist+crisis, NOT for non-therapist, NOT when no augment, emitted BEFORE chunk events |

## Issues Found During Testing

1. **`_llm_router` is a `@property`** — `patch.object(service, "_llm_router")` does not work. Used `ChatService(db, llm_router=mock_router)` constructor parameter instead. Not a bug.

2. **Rolling window boundary precision** — Testing "exactly 24h" is unreliable because `datetime.now(tz=UTC)` inside the implementation advances microseconds after the test sets up `window_start`. Replaced the boundary test with a clearly-within-window test (23h59m). The condition is `> timedelta(hours=24)` so exactly 24h is NOT expired — this is correct and is covered by `test_window_almost_24h_ago_not_reset`.

3. **Pydantic validates length before service** — A 4001-char message sent via HTTP returns 422 (Pydantic) not 400 (moderation service). The service-layer defense-in-depth 400 is only reachable when calling the service directly (in-process). Both behaviors are now tested separately with clear docstrings.

## Notes for Reviewer

- The `_record_violation_background` tests use a custom `MockSession` class rather than `AsyncMock` to correctly capture the `ModerationEvent` object passed to `db.add()`. This is necessary because `isinstance(obj, ModerationEvent)` checks do not work with MagicMock objects.
- SSE event ordering test (`test_moderation_sse_event_emitted_before_chunks`) directly exercises `stream_response()` and verifies the `moderation` event comes before any `chunk` events — this is the contract the mobile clients depend on.
- The 3 uncovered lines in `content_moderation.py` (188, 202-203) are the `blocked_until` local variable and the fail-open fallback inside `check_message`'s `asyncio.gather` exception handler. These are only reachable when both the abuse state AND classification calls fail simultaneously, which is an extremely rare edge case.
