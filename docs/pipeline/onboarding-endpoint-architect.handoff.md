# Architect Handoff: Onboarding Endpoint

**Date**: 2026-02-24
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

A single POST /api/v1/onboarding/complete endpoint that receives answers to 7 onboarding questions, uses Claude Haiku to convert the raw Q&A pairs into structured third-person memory statements, seeds those memories into Mem0 as global memories (visible to all characters), and sets profiles.onboarding_completed=true in the database.

## Spec Location

`shared/feature-specs/onboarding-endpoint.md`

## Layer

backend

## Key Decisions

- **Global memory scope (no agent_id)**: Onboarding memories are seeded as global memories (user_id only, no agent_id) because they contain basic user facts (name, profession, goals, sleep schedule) that all characters should see. Per docs/05-ai-bellek.md, global memories are "basic user information visible to all characters."

- **Single Claude Haiku call for all 7 answers**: One prompt with all Q&A pairs, not 7 separate calls. Cheaper, faster, and gives Haiku full context for generating coherent memory statements.

- **Deterministic fallback when Haiku fails**: If Haiku returns unparseable output, a deterministic template-based formatter produces functional memories. Onboarding never blocks on LLM flakiness.

- **409 Conflict for re-onboarding**: Once onboarding_completed=true, the endpoint rejects subsequent calls. Prevents duplicate memory seeding and simplifies client logic.

- **Profile name update from preferred_name**: If the onboarding "preferred name" answer differs from profiles.name (set during registration), the name is updated. Users often register with full names but prefer nicknames.

- **Retry-safe ordering**: Claude (stateless) -> Mem0 (idempotent) -> DB flag update. If Mem0 fails, flag stays false and client retries. If DB fails, Mem0 has memories (harmless duplicates) and next retry sets the flag.

- **Not a background task**: Unlike chat memory persistence (P01-06), onboarding runs in the foreground so the endpoint can report success/failure accurately and the client can retry on 503.

## File Manifest

```
Backend:
  CREATE  backend/app/routes/onboarding.py
  CREATE  backend/app/services/onboarding_service.py
  CREATE  backend/app/schemas/onboarding.py
  MODIFY  backend/app/main.py
  CREATE  backend/tests/test_onboarding_routes.py
  CREATE  backend/tests/test_onboarding_service.py
  CREATE  backend/tests/test_onboarding_schemas.py

Shared:
  CREATE  shared/feature-specs/onboarding-endpoint.md
  CREATE  docs/pipeline/onboarding-endpoint-architect.handoff.md
```

| Action | Count |
|--------|-------|
| CREATE | 6 backend + 2 shared = 8 |
| MODIFY | 1 |
| **Total** | **9** |

## Assumptions Made

- The 7 onboarding questions from docs/05-ai-bellek.md Section "Onboarding Memory Seed" are the definitive list. No questions have been added or removed since that doc was written.
- The default "Ember" companion character (template=companion, is_default=true) already exists for every user, created during registration (P01-04).
- Mem0's client.add() with user_id only (no agent_id) seeds global memories that are found by the two-layer search in the chat flow (P01-06 global search path).
- The Mem0 SDK's add() method deduplicates or handles duplicate memory additions gracefully on retries.
- Mobile clients check onboarding_completed from the login/register response and only show the onboarding flow when it is false.

## Dependencies

- Requires: P01-04 (auth-endpoints -- Profile with onboarding_completed, default Character, get_current_user)
- Requires: P01-01 (project-setup -- FastAPI scaffold, config.py with anthropic_api_key, mem0_api_key, claude_haiku_model)
- Requires: P01-02 (database-schema -- Profile and Character models)
- Requires: P01-03 (cognito-auth-middleware -- JWT verification)
- Blocks: No other Phase 1 features depend on this.

## Notes for Developers

### For backend-dev

1. **No new config values needed.** anthropic_api_key, claude_haiku_model, and mem0_api_key already exist in config.py.

2. **Claude pattern**: Use AsyncAnthropic (native async) like chat_service.py _extract_intent(). Do NOT wrap Claude calls in asyncio.to_thread -- the Anthropic SDK is already async.

3. **Mem0 pattern**: Use MemoryClient wrapped in asyncio.to_thread() like chat_service.py _persist_exchange(). Pass user_id only (no agent_id) for global scope.

4. **Haiku JSON parsing**: Strip markdown code block delimiters before json.loads(). LLMs sometimes wrap JSON responses in ```json ... ``` blocks.

5. **main.py change**: Add `onboarding` to the existing import: `from app.routes import auth, characters, chat, health, memories, onboarding`. Register with prefix `/api/v1/onboarding`.

6. **Profile name update**: Compare preferred_name case-insensitively with profile.name. Update in the same DB transaction as the onboarding_completed flag.

### For backend-tester

1. **Critical test**: When Mem0 fails, onboarding_completed must NOT be set to true. This is the most important correctness test.

2. **Mock both services**: Patch AsyncAnthropic and MemoryClient at the service module level.

3. **Fallback test**: Make Haiku return non-JSON and verify fallback memories are still seeded successfully.

4. **Pydantic validation**: Test all edge cases (missing keys, duplicates, invalid keys, empty answers, whitespace-only answers, 501-char answers).

## Next Steps

backend-dev should read the spec and implement. backend-tester follows after implementation is complete.
