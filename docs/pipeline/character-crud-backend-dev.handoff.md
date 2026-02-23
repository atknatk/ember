# Backend Dev Handoff: Character CRUD

**Date**: 2026-02-23
**Agent**: backend-dev
**Status**: COMPLETE

## Implemented Files

### Created
- `backend/app/routes/characters.py` -- 4 endpoints (GET, POST, PUT, DELETE)
- `backend/app/services/character_service.py` -- CharacterService with 4 public methods + 3 private helpers
- `backend/app/schemas/character.py` -- 5 schemas (CreateCharacterRequest, UpdateCharacterRequest, CharacterListItem, CharacterListResponse, CharacterDetail)
- `backend/tests/test_character_routes.py` -- 27 route-level tests
- `backend/tests/test_character_service.py` -- 14 service-level tests
- `backend/tests/test_character_schemas.py` -- 18 schema-level tests

### Modified
- `backend/app/config.py` -- Added `claude_haiku_model: str = "claude-haiku-4-5"` to Settings
- `backend/app/main.py` -- Registered characters router at `/api/v1/characters`

## Endpoints Implemented

| Method | Path | Status Code | Description |
|--------|------|-------------|-------------|
| GET | `/api/v1/characters` | 200 | List active characters with last_message_at (LEFT JOIN conversations) |
| POST | `/api/v1/characters` | 201 | Create character with Claude Haiku system prompt generation + auto conversation |
| PUT | `/api/v1/characters/{character_id}` | 200 | Update name, system_prompt, avatar_style (ownership enforced) |
| DELETE | `/api/v1/characters/{character_id}` | 204 | Soft-delete (is_active=false), default character protected (403) |

## Test Results

```
backend/.venv/bin/python -m pytest backend/tests/test_character_routes.py backend/tests/test_character_service.py backend/tests/test_character_schemas.py -v
```

- test_character_schemas.py: 18 passed
- test_character_service.py: 14 passed
- test_character_routes.py: 27 passed
- Full suite (657 tests): 0 failed
- ruff: clean (all checks passed)

## Test Command

```bash
backend/.venv/bin/python -m pytest backend/tests/test_character_routes.py backend/tests/test_character_service.py backend/tests/test_character_schemas.py -v
```

## Known Issues / Deviations from Spec

- None. Implementation matches the spec exactly.

## Notes for Backend Tester

### Mock Setup for Claude Haiku

```python
from unittest.mock import AsyncMock, MagicMock, patch

mock_response = MagicMock()
mock_response.content = [MagicMock(text="Generated system prompt...")]

with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    mock_cls.return_value = mock_client
    # ... run test
```

### Auth Fixture Pattern

Override `get_current_user` with a function that returns a MagicMock with `.id` (uuid.UUID) and `.name` (str) attributes. Do NOT use `Profile.__new__(Profile)` -- SQLAlchemy ORM objects require `_sa_instance_state`.

### Key Test Areas

- **List ordering**: Seed with characters having different `last_message_at` (including null) and verify DESC NULLS LAST order
- **Ownership checks**: PUT and DELETE both check `character.user_id == current_user.id` -- test with another user's characters
- **Default character protection**: DELETE returns 403 when `is_default=True`
- **Soft delete verification**: After DELETE, `is_active` is `False` (row not removed)
- **mem0_agent_id uniqueness**: When creating a second character with the same template, the agent_id uses `{template}_{uuid[:8]}_{user_id}` fallback
- **Claude 503 handling**: When `AsyncAnthropic.messages.create()` raises, service returns 503 with "AI service unavailable, please try again"
- **system_prompt excluded from list**: `GET /characters` response has no `system_prompt` or `mem0_agent_id` fields
