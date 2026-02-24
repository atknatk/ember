# Backend Dev Handoff: Onboarding Endpoint

**Date**: 2026-02-24
**Agent**: backend-dev
**Status**: COMPLETE

## Implemented Files

- `backend/app/schemas/onboarding.py` -- 3 schemas (OnboardingAnswer, OnboardingRequest, OnboardingResponse) + VALID_QUESTION_KEYS constant
- `backend/app/services/onboarding_service.py` -- OnboardingService class with 5 methods (complete_onboarding, _convert_answers_to_memories, _parse_haiku_response, _fallback_memories, _seed_memories)
- `backend/app/routes/onboarding.py` -- 1 endpoint (POST /complete)
- `backend/app/main.py` -- MODIFIED: added onboarding router registration at /api/v1/onboarding

## Endpoints Implemented

- `POST /api/v1/onboarding/complete` -- Receives 7 Q&A answers, converts to structured memories via Claude Haiku, seeds into Mem0 (global scope), updates profile.onboarding_completed = true

## Test Results

- pytest: 49 onboarding tests passed, 0 failed (1111 total suite passed)
- ruff: clean (0 errors)
- All spec scenarios covered (R1-R14 route tests, S1-S14 service tests, T1-T8 schema tests)

## Test Files

- `backend/tests/test_onboarding_schemas.py` -- 15 tests covering Pydantic validation
- `backend/tests/test_onboarding_service.py` -- 18 tests covering service logic
- `backend/tests/test_onboarding_routes.py` -- 16 tests covering HTTP integration

## Test Command

```bash
cd backend && python -m pytest tests/test_onboarding_schemas.py tests/test_onboarding_service.py tests/test_onboarding_routes.py -v
```

## Known Issues / Deviations from Spec

- None. Implementation follows the spec exactly.

## Key Design Decisions (Matching Spec)

1. **Global memory scope**: Onboarding memories seeded with `user_id` only (no `agent_id`), visible to all characters
2. **Retry-safe ordering**: Haiku (stateless) -> Mem0 (idempotent) -> DB flag update
3. **Deterministic fallback**: If Haiku returns unparseable JSON, fallback templates generate functional memories
4. **409 on re-onboarding**: Returns HTTP 409 Conflict if `onboarding_completed` is already `true`
5. **Profile name update**: Compares `preferred_name` answer case-insensitively with `profile.name`; updates if different
6. **Markdown code block stripping**: Strips `\`\`\`json` and `\`\`\`` delimiters from Haiku response before JSON parsing

## Notes for Backend Tester

- **Mock Claude at import level**: Patch `app.services.onboarding_service.AsyncAnthropic` -- Claude SDK is natively async (no `asyncio.to_thread` wrapper)
- **Mock Mem0 at import level**: Patch `app.services.onboarding_service.MemoryClient` -- synchronous SDK, wrapped in `asyncio.to_thread()`
- **Critical test**: When Mem0 fails (step 3), `onboarding_completed` must remain `False` and DB must NOT be committed. The Mem0 failure raises 503 before the DB flag update.
- **Fallback test**: Make Haiku return non-JSON text and verify fallback memories are seeded. The `_parse_haiku_response` method handles this.
- **Mem0 global scope verification**: Ensure `client.add()` is called with `user_id` kwarg only -- `agent_id` must NOT be present in the call kwargs
- **Edge cases to cover**: whitespace-only answers (422), empty answers (422), 501-char answers (422), duplicate keys (422), missing keys (422)
- **`asyncio.to_thread` mock**: For Mem0 failure tests, patch `app.services.onboarding_service.asyncio.to_thread` directly with `side_effect=Exception(...)` since the actual `to_thread` wraps the sync Mem0 call
