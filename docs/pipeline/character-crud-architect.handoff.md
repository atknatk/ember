# Architect Handoff: Character CRUD

**Date**: 2026-02-23
**Agent**: architect
**Status**: COMPLETE

## What Was Designed

Four backend API endpoints for character management: GET /api/v1/characters (list with last_message_at join), POST /api/v1/characters (create with Claude Haiku system prompt generation and auto-conversation), PUT /api/v1/characters/:id (update name/system_prompt/avatar_style with ownership check), and DELETE /api/v1/characters/:id (soft delete with default character protection). All endpoints require JWT authentication.

## Key Decisions

- **Claude Haiku for prompt generation**: System prompt auto-generation uses `claude-haiku-4-5` (not Sonnet) because it is a short, one-time text generation task. This follows the model selection strategy in `docs/05-ai-bellek.md`.
- **No cursor pagination on list**: Characters are returned as a flat list because users are expected to have at most dozens of characters, not thousands.
- **`system_prompt` excluded from list response**: Included only in POST/PUT responses to keep the list payload small for the mobile character grid.
- **Soft delete only**: `is_active = false` instead of row deletion, per the data model design in `docs/04-veri-api.md`.
- **Template immutability**: Template and `mem0_agent_id` cannot be changed after creation to prevent Mem0 memory isolation breakage.
- **`mem0_agent_id` uniqueness fallback**: `{template}_{uuid[:8]}_{user_id}` format when a user creates a second character with the same template.
- **New config field**: `claude_haiku_model` added to `Settings` to make the Haiku model name configurable.

## Spec Location

`shared/feature-specs/character-crud.md`

## Assumptions Made

- The `anthropic` package (already in `requirements.txt`) supports `AsyncAnthropic` with `messages.create()` for non-streaming completions.
- The Claude Haiku model identifier is `claude-haiku-4-5` as referenced in `docs/05-ai-bellek.md`.
- Subscription tier enforcement (free users limited to one character) is deferred to Phase 2. Any authenticated user can currently create characters.
- No explicit Mem0 API calls are needed during character creation. The `mem0_agent_id` is stored for future use during messaging.
- The existing `idx_characters_user_active` index on `(user_id, is_active)` is sufficient for the list query performance.

## Dependencies

- Requires: P01-01 (project-setup), P01-02 (database-schema), P01-03 (cognito-auth-middleware), P01-04 (auth-endpoints)
- Blocks: backend-dev (implements the endpoints), backend-tester (writes tests)

## Next Steps

backend-dev should read the spec at `shared/feature-specs/character-crud.md` and implement the endpoints. backend-tester follows with test coverage.
