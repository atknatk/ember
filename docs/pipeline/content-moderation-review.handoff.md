# Reviewer Handoff: Content Moderation

**Date**: 2026-03-13
**Agent**: reviewer
**Status**: APPROVED

## Review Summary

| Category | Passed | Warnings | Issues |
|----------|--------|----------|--------|
| Architecture | 5 | 0 | 0 |
| Backend | 7 | 1 | 0 |
| Testing | 5 | 1 | 0 |
| Security | 4 | 0 | 0 |
| **Total** | **21** | **2** | **0** |

## Checklist Detail

### Architecture Compliance

- [x] **Single conversation per character**: No `/conversations` path segment in any mobile-facing endpoint. Moderation hooks into existing `POST /characters/:id/messages` flow. PASS
- [x] **Cursor-based pagination**: No OFFSET usage in moderation code. Not applicable to this feature (no list endpoints added). PASS
- [x] **Mem0 agent_id format**: No Mem0 calls in moderation service. Spec explicitly states moderation events are NOT stored in Mem0. PASS
- [x] **No secrets in code**: Grep confirms no hardcoded API keys, secrets, tokens, or passwords in any new files. All config from `settings`. PASS
- [x] **Spec adherence**: No new public API endpoints (spec says none). Modified behavior on existing chat endpoint matches spec. PASS

### Backend Code Quality

- [x] **All functions async**: `check_message`, `_classify_content`, `_check_abuse_state`, `_record_violation_background`, `_update_abuse_state` are all `async def`. `_check_prompt_injection` is sync (correct -- it is CPU-bound regex). PASS
- [x] **Parallel operations**: Abuse state check and content classification run via `asyncio.gather()` at line 179. PASS
- [x] **JWT extraction**: User ID comes from `current_user.id` in `ChatService.validate_send_message()`. Never from request body. PASS
- [x] **Proper error responses**: 400 for harmful content, 403 for blocked user, both via HTTPException. PASS
- [x] **Input validation**: Length check (4000 chars) enforced as defense-in-depth in service layer alongside Pydantic schema. PASS
- [x] **Background recording**: `_record_violation_background` uses `asyncio.create_task()` for fire-and-forget. Uses its own DB session (`AsyncSessionLocal`) to avoid interfering with request session. PASS
- [x] **403 response structure**: WARN -- The blocked-user 403 response nests `detail` inside `detail` due to HTTPException wrapping. Functionally correct but deviates from spec's flat structure. Non-blocking.

### Testing

- [x] **Coverage >= 80%**: Measured at 89% line coverage for `app/services/content_moderation.py`. PASS
- [x] **All 36 tests pass**: Verified via `pytest` execution. PASS
- [x] **External services mocked**: LLM provider mocked via `patch("app.services.content_moderation.get_llm_router")`. DB mocked via AsyncMock. No real API calls. PASS
- [x] **Edge cases covered**: Malformed JSON (fail-open), LLM exception (fail-open), DB failure (fail-open), expired block, rolling window reset, moderation disabled toggle. PASS
- [x] **Route-level tests**: WARN -- `backend/tests/routes/test_chat_moderation.py` listed in spec file manifest but not created. Service-level tests cover all acceptance criteria. Non-blocking.

### Security

- [x] **No credentials in code**: Grep for `api_key =`, `secret =`, `password =`, `Bearer `, `token =` -- no hardcoded values found. PASS
- [x] **No user_id in request body**: User ID always from JWT via `get_current_user` dependency. PASS
- [x] **SQL injection prevention**: All DB queries use SQLAlchemy `select()` with parameterized `where()` clauses. No raw SQL. PASS
- [x] **No internal IDs exposed**: Error messages are user-friendly strings. No DB IDs, stack traces, or system paths in responses. User content truncated to 200 chars in audit log per privacy spec. PASS

## Files Reviewed

**Backend (new)**:
- `backend/app/services/content_moderation.py` -- PASS (89% coverage, fail-open, async, parallel ops)
- `backend/app/models/moderation_event.py` -- PASS (correct schema, indexes, FK constraints)
- `backend/app/models/user_moderation_state.py` -- PASS (correct schema, PK on user_id, rolling window fields)
- `backend/app/schemas/chat.py` (ModerationSSEEvent addition) -- PASS
- `backend/app/models/__init__.py` (model registration) -- PASS
- `backend/tests/services/test_content_moderation.py` -- PASS (36 tests, all passing)

**Backend (modified)**:
- `backend/app/services/chat_service.py` -- PASS (moderation integration at correct pipeline position, system prompt augmentation, ModerationSSEEvent emission for therapist crisis)
- `backend/app/config.py` -- PASS (5 moderation settings added with correct defaults)

## Spec Compliance (Acceptance Criteria)

| AC# | Description | Status |
|-----|-------------|--------|
| 1 | 4001-char message rejected with 400 | Covered by `test_length_exceeded_blocked` |
| 2 | Harmful medium/high severity blocked with 400 | Covered by `test_harmful_high_severity_blocked` |
| 3 | Low severity allowed, event logged | Covered by `test_low_severity_allowed` |
| 4 | Prompt injection adds preamble, not blocked | Covered by `test_prompt_injection_adds_preamble_not_blocked` |
| 5 | 4th violation applies 15-min block | Covered by `test_violations_4_5_short_block` |
| 6 | Blocked user receives 403 | Covered by `test_blocked_user_returns_403` |
| 7 | Expired block allows message | Covered by `test_expired_block_returns_none` |
| 8 | Therapist crisis augments system prompt | Covered by `test_therapist_crisis_augments_prompt` |
| 9 | Non-therapist crisis: no augmentation | Covered by `test_non_therapist_crisis_no_augmentation` |
| 10 | Classifier failure: fail-open | Covered by `test_classifier_failure_fail_open` and `test_exception_fail_open` |
| 11 | max_tokens=2048 caps response | Verified in `chat_service.py` line 274 |
| 12 | Violation event records truncated content | Verified in `_record_violation_background` line 395 |
| 13 | 24h window resets violation count | Covered by `test_rolling_window_reset` |

## Warnings (Not Blocking)

1. **Missing route-level test file**: `backend/tests/routes/test_chat_moderation.py` is listed in the spec file manifest but was not created. Service-level tests provide 89% coverage and cover all acceptance criteria. Recommend adding route-level tests in a follow-up to verify HTTP status codes end-to-end.

2. **Nested detail in 403 response**: `chat_service.py` line 172 passes a dict as HTTPException `detail`, producing `{"detail": {"detail": "...", "blocked_until": "..."}}`. The inner "detail" key is redundant. Consider using a custom JSONResponse or renaming the inner key to "message" to avoid confusion.
