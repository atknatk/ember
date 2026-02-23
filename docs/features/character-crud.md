# Character CRUD

> Provides four REST endpoints for managing AI characters: list, create (with Claude Haiku system prompt generation), update, and soft-delete -- enabling the multi-character system that is central to Ember's identity.

**Status**: Released
**Added in**: Phase 1 (P01-05)
**Platforms**: Backend
**GitHub Issue**: #7

---

## Overview

Character CRUD is the foundation of Ember's multi-character system. Without these endpoints, users are limited to the single default companion character created during registration. This feature allows users to create additional specialized characters -- an English teacher, a therapist, a fitness coach, a career coach, or a fully custom character described in the user's own words.

The standout design element is automatic system prompt generation. When a user creates a character, they only provide a name and a template (or a custom description). The backend calls Claude Haiku (`claude-haiku-4-5`) with a meta-prompt to generate a tailored system prompt for that character. The user can then review the generated prompt and refine it via the update endpoint if desired.

Characters use soft deletion (`is_active = false`) rather than hard deletion, preserving database integrity and Mem0 memory associations. The default companion character created during registration is protected from deletion (HTTP 403). All endpoints require JWT authentication, and ownership checks ensure users can only manage their own characters.

---

## Architecture

### How It Works (Data Flow)

**List characters:**

1. Client sends `GET /api/v1/characters` with `Authorization: Bearer <jwt>`
2. `get_current_user()` extracts `user_id` from the JWT
3. `CharacterService.list_characters()` executes a LEFT JOIN query: `characters` joined with `conversations` to obtain `last_message_at`
4. Results are filtered to `is_active = true` and sorted by `last_message_at DESC NULLS LAST`, then `created_at DESC`
5. Each row maps to a `CharacterListItem` (excludes `system_prompt` and `mem0_agent_id`)
6. Response: `200 OK` with `{ "characters": [...] }`

**Create character:**

1. Client sends `POST /api/v1/characters` with `{ name, template, description? }`
2. Pydantic validates the request: template must be in the allowed set; `description` is required for `custom` template, forbidden for built-in templates
3. `CharacterService._generate_system_prompt()` calls Claude Haiku with a meta-prompt built from the template role description (or user-provided description for custom characters)
4. `CharacterService._compute_mem0_agent_id()` computes `{template}_{user_id}`, falling back to `{template}_{uuid[:8]}_{user_id}` if a uniqueness conflict exists
5. A `Character` row and a `Conversation` row are created and committed in a single transaction
6. Response: `201 Created` with the full character detail (including the generated `system_prompt`)

**Update character:**

1. Client sends `PUT /api/v1/characters/{character_id}` with `{ name?, system_prompt?, avatar_style? }`
2. Pydantic validates that at least one field is provided
3. The character is looked up (must be active); ownership is verified against the JWT user
4. Provided fields are applied to the ORM object; unchanged fields are left as-is
5. Response: `200 OK` with the full updated character detail

**Delete character (soft):**

1. Client sends `DELETE /api/v1/characters/{character_id}`
2. The character is looked up (must be active); ownership is verified
3. If `is_default = true`, the request is rejected with `403`
4. `is_active` is set to `false`; the row remains in the database
5. Response: `204 No Content`

### System Prompt Generation via Claude Haiku

Character creation delegates to Claude Haiku (`claude-haiku-4-5`) for system prompt generation. This is a non-streaming `messages.create()` call via `AsyncAnthropic`. The meta-prompt instructs Haiku to generate a 100-300 word system prompt written in second person ("You are..."), with natural memory usage and concise conversational tone.

For built-in templates, the meta-prompt includes the character name, user name, and a predefined role description. For custom templates, it includes the user's free-text description instead of a role description.

If the Claude API call fails for any reason (network error, rate limit, API error), the error is logged at ERROR level and the endpoint returns `503 "AI service unavailable, please try again"`. The character is not created with a placeholder prompt -- prompt generation must succeed.

### Template Role Descriptions

| Template | Role Description |
|----------|-----------------|
| `companion` | A personal AI companion and holistic life friend covering fitness, nutrition, work, stress, and relationships. Warm, honest, genuine but not overly positive. |
| `english_teacher` | An English language teacher who teaches through conversation. Corrects mistakes gently but stays motivating. Adapts to the user's level. |
| `therapist` | An emotional support assistant. Listens, reflects, does not judge. Never diagnoses or prescribes medication. Recommends professional help when needed. Uses CBT-based approaches. |
| `fitness_coach` | A fitness and nutrition coach. Provides workout programming, form advice, and nutrition support. Tracks progress and is mindful of injuries. |
| `career_coach` | A career development coach. Helps with goal setting, negotiation, leadership, and work-life balance. Pragmatic and honest. |

### Mem0 Agent ID Computation

No Mem0 API calls are made during character creation. The `mem0_agent_id` is computed and stored for future use during the messaging flow.

- **Default format**: `{template}_{user_id}` (e.g., `english_teacher_550e8400-e29b-41d4-a716-446655440000`)
- **Fallback format** (when a user creates a second character with the same template): `{template}_{character_uuid[:8]}_{user_id}`
- The uniqueness check queries existing characters (active and inactive) to avoid collisions with the `UNIQUE` constraint on `mem0_agent_id`

### Soft Delete Behavior

Deleting a character sets `is_active = false`. The row is not removed from the database. Consequences:

- The character no longer appears in `GET /characters` responses
- The associated conversation row is NOT deleted or deactivated
- Mem0 memories for the character are NOT deleted -- they persist and could be used if a reactivation feature is built later
- An already-inactive character returns `404` (treated as "not found" from the user's perspective)
- The default character (`is_default = true`) cannot be soft-deleted and returns `403`

### Database Tables Involved

| Table | Operation | Notes |
|-------|-----------|-------|
| `characters` | SELECT, INSERT, UPDATE | All four CRUD operations. `is_active` flag for soft delete. |
| `conversations` | SELECT (via JOIN), INSERT | LEFT JOIN for `last_message_at` in list; auto-created with new character. |

---

## API Reference

For the full API contract, see [`docs/04-veri-api.md`](../04-veri-api.md). All endpoints below are under `/api/v1/characters` and require `Authorization: Bearer <jwt>`.

### GET /api/v1/characters

**Auth**: Bearer JWT required
**Success Status**: `200 OK`

Lists all active characters for the authenticated user, ordered by most recently active first.

**Response Body**:

```json
{
  "characters": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Ember",
      "template": "companion",
      "description": null,
      "avatar_style": "default",
      "is_default": true,
      "last_message_at": "2026-02-23T14:30:00Z",
      "created_at": "2026-02-23T10:00:00Z"
    }
  ]
}
```

| Field | Type | Notes |
|-------|------|-------|
| `id` | string (UUID) | Character primary key |
| `name` | string | User-assigned name |
| `template` | string | Template identifier |
| `description` | string or null | Custom character description |
| `avatar_style` | string | UI differentiation key |
| `is_default` | boolean | True only for the General Friend |
| `last_message_at` | string (ISO 8601) or null | From conversations table via LEFT JOIN |
| `created_at` | string (ISO 8601) | Character creation time |

`system_prompt` and `mem0_agent_id` are intentionally excluded (backend-internal, not needed for the mobile character grid).

The response is a flat list, not cursor-paginated. Users are expected to have at most dozens of characters.

**Error Responses**:

| Status | Detail | When |
|--------|--------|------|
| 401 | `"Invalid or expired token"` | Missing or invalid JWT |

### POST /api/v1/characters

**Auth**: Bearer JWT required
**Content-Type**: `application/json`
**Success Status**: `201 Created`

**Request Body**:

```json
{
  "name": "Sarah",
  "template": "english_teacher",
  "description": null
}
```

For custom characters:

```json
{
  "name": "Marco",
  "template": "custom",
  "description": "An Italian language teacher. Only speaks Italian. Suitable for beginner level."
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `name` | string | yes | 1-100 chars, whitespace-trimmed, empty-after-trim rejected |
| `template` | string | yes | One of: `companion`, `english_teacher`, `therapist`, `fitness_coach`, `career_coach`, `custom` |
| `description` | string or null | conditional | Required for `custom` (min 10 chars, max 1000 chars). Must be null or absent for non-custom templates. |

**Response Body** (201):

```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "name": "Sarah",
  "template": "english_teacher",
  "description": null,
  "system_prompt": "You are Sarah, Alex's English teacher...",
  "avatar_style": "default",
  "is_default": false,
  "created_at": "2026-02-23T14:30:00Z"
}
```

The `system_prompt` is included so the mobile client can display it for user review. The user can then modify it via PUT. `mem0_agent_id` is NOT included (backend-internal).

**Error Responses**:

| Status | Detail | When |
|--------|--------|------|
| 401 | `"Invalid or expired token"` | Missing or invalid JWT |
| 422 | Standard FastAPI validation error | Invalid template, missing description for custom, description provided for non-custom, whitespace-only name, empty body |
| 503 | `"AI service unavailable, please try again"` | Claude Haiku API call fails |

### PUT /api/v1/characters/{character_id}

**Auth**: Bearer JWT required
**Content-Type**: `application/json`
**Success Status**: `200 OK`

**Request Body** (at least one field required):

```json
{
  "name": "Sarah the Great",
  "system_prompt": "You are Sarah, a patient and encouraging English teacher...",
  "avatar_style": "blue"
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `name` | string or null | no | 1-100 chars, whitespace-trimmed |
| `system_prompt` | string or null | no | 1-10000 chars |
| `avatar_style` | string or null | no | Max 50 chars |

`template`, `description`, `mem0_agent_id`, and `is_default` are immutable after creation.

**Response Body**: Same shape as the POST 201 response (full `CharacterDetail`).

**Error Responses**:

| Status | Detail | When |
|--------|--------|------|
| 401 | `"Invalid or expired token"` | Missing or invalid JWT |
| 403 | `"Character does not belong to user"` | Ownership mismatch |
| 404 | `"Character not found"` | Non-existent or inactive character |
| 422 | Standard FastAPI validation error | No fields provided, invalid field values |

### DELETE /api/v1/characters/{character_id}

**Auth**: Bearer JWT required
**Success Status**: `204 No Content`

Soft-deletes a character by setting `is_active = false`. The default character cannot be deleted.

**Error Responses**:

| Status | Detail | When |
|--------|--------|------|
| 401 | `"Invalid or expired token"` | Missing or invalid JWT |
| 403 | `"Default character cannot be deleted"` | Attempting to delete the default character |
| 403 | `"Character does not belong to user"` | Ownership mismatch |
| 404 | `"Character not found"` | Non-existent or already-inactive character |

Note on check ordering: the ownership check runs before the default character check. If a character belongs to another user and is also default, the ownership 403 takes priority.

---

## Pydantic Schemas

All schemas are defined in `backend/app/schemas/character.py`.

**Request schemas**:

- `CreateCharacterRequest` -- validates `name` (1-100 chars, trimmed), `template` (against `ALLOWED_TEMPLATES` frozenset), `description` (conditional on template via `@model_validator`)
- `UpdateCharacterRequest` -- validates that at least one of `name`, `system_prompt`, or `avatar_style` is provided (via `@model_validator`)

**Response schemas**:

- `CharacterListItem` -- used in the GET list response. Includes `last_message_at`, excludes `system_prompt`. Uses `ConfigDict(from_attributes=True)` for ORM compatibility. UUID `id` is coerced to `str` via `@field_validator`.
- `CharacterListResponse` -- wrapper containing `characters: list[CharacterListItem]`
- `CharacterDetail` -- used in POST and PUT responses. Includes `system_prompt`, excludes `last_message_at`. Same ORM-compatible config.

---

## Configuration

One new configuration field was added to `backend/app/config.py`:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `claude_haiku_model` | str | `"claude-haiku-4-5"` | Model identifier for system prompt generation |

The existing `anthropic_api_key` setting (from P01-01) provides the API key for the `AsyncAnthropic` client.

---

## Files

| File | Role |
|------|------|
| `backend/app/routes/characters.py` | Route handlers: `list_characters`, `create_character`, `update_character`, `delete_character`. Delegates all logic to `CharacterService`. |
| `backend/app/services/character_service.py` | `CharacterService` class with 4 public methods and 3 private helpers (`_get_active_character`, `_generate_system_prompt`, `_compute_mem0_agent_id`). Contains `TEMPLATE_ROLES` dict and `_build_meta_prompt()` module-level function. |
| `backend/app/schemas/character.py` | 5 Pydantic schemas: `CreateCharacterRequest`, `UpdateCharacterRequest`, `CharacterListItem`, `CharacterListResponse`, `CharacterDetail`. |
| `backend/app/config.py` | Modified: added `claude_haiku_model` setting. |
| `backend/app/main.py` | Modified: registered characters router at `/api/v1/characters`. |

### Service Layer

`CharacterService` is instantiated per-request with the database session: `CharacterService(db)`. Route handlers create the service and delegate entirely -- they contain no business logic.

Key private helpers:

- `_get_active_character(character_id)` -- shared by update and delete; queries for an active character and raises `404` if not found
- `_generate_system_prompt(character_name, user_name, template, description)` -- builds the meta-prompt via `_build_meta_prompt()` and calls Claude Haiku; catches all exceptions and converts them to `503`
- `_compute_mem0_agent_id(template, user_id, character_id)` -- checks for uniqueness conflicts and falls back to the discriminated format

---

## Testing

### Coverage Summary

| File | Tests (dev + tester) | Line Coverage | Branch Coverage |
|------|---------------------|---------------|-----------------|
| `test_character_routes.py` | 27 | -- | -- |
| `test_character_routes_extended.py` | 29 | -- | -- |
| `test_character_service.py` | 14 | -- | -- |
| `test_character_service_extended.py` | 31 | -- | -- |
| `test_character_schemas.py` | 18 | -- | -- |
| `test_character_schemas_extended.py` | 43 | -- | -- |
| **Total** | **162** | **100%** (195/195 statements) | **100%** (36/36 branches) |

Target was >= 80% line coverage and >= 70% branch coverage. Both are exceeded at 100%.

### Test Approach

- **Route tests**: Use the FastAPI test client. `get_current_user` is overridden to return a mock Profile. Claude Haiku is mocked at the service level. Database interactions use a mock `AsyncSession`.
- **Service tests**: Unit-test `CharacterService` directly with mock database session and mock Anthropic client.
- **Schema tests**: Validate Pydantic schemas directly -- template validation, description conditional logic, name trimming, boundary values, ORM-to-response mapping, UUID-to-string coercion.
- **Extended tests**: The backend tester added comprehensive edge case coverage including name/description length boundaries, Unicode handling, all five built-in templates via HTTP, meta-prompt structural verification, ownership check ordering, and soft-delete transaction behavior.

### Running Tests

Character tests only:

```bash
cd backend && python -m pytest tests/test_character_routes.py tests/test_character_routes_extended.py tests/test_character_service.py tests/test_character_service_extended.py tests/test_character_schemas.py tests/test_character_schemas_extended.py -v
```

Full backend suite:

```bash
cd backend && python -m pytest tests/ -v --ignore=tests/test_migration.py
```

---

## Known Limitations

- **No subscription-tier enforcement**: Any authenticated user can create unlimited characters. Free-tier limits (one character) are a Phase 2 feature.
- **No single-character detail endpoint**: `GET /characters/:id` is not implemented. The list endpoint returns all needed fields for the mobile character grid. A detail endpoint can be added later if needed.
- **No character reactivation**: Once soft-deleted, a character cannot be restored via the API. A reactivation feature could be added in the future.
- **No Mem0 cleanup on delete**: Soft-deleting a character does not delete its Mem0 memories. The memories persist in Mem0 under the character's `agent_id`.
- **Claude Haiku dependency for creation**: Character creation fails entirely if Claude Haiku is unavailable (503). There is no fallback to a static prompt or deferred generation.
- **Flat list, no pagination**: The GET endpoint returns all active characters as a flat array. This is by design for the expected scale (dozens of characters per user), but would need pagination if the character count grows significantly.

---

## Design Decisions

### Why Claude Haiku for system prompt generation (not Sonnet)

System prompt generation is a one-time operation producing short text (100-300 words). Claude Haiku is significantly cheaper and faster than Sonnet for this use case. Per `docs/05-ai-bellek.md`, Haiku is designated for "simple JSON output, cheap and fast" operations.

### Why soft delete instead of hard delete

Per `docs/04-veri-api.md`: "Characters with conversation history are deactivated, not physically deleted." Soft delete preserves foreign key integrity from messages, allows potential reactivation, and simplifies deletion logic.

### Why `template` is immutable after creation

The template determines the `mem0_agent_id`, which is the key for Mem0 memory isolation. Changing it would require migrating Mem0 memories or leave the agent ID inconsistent with the template. Per `docs/16-karakterler.md`: "mem0_agent_id cannot be changed after creation."

### Why `system_prompt` is excluded from the list response

The system prompt can be hundreds of words long. Including it in every list item would bloat the response unnecessarily. The mobile client needs the prompt only when editing a character (PUT flow), not when displaying the character grid.

### Why the list endpoint is not cursor-paginated

Users are expected to have at most a few dozen characters. Cursor pagination adds complexity for no benefit at this scale. The performance target for `GET /characters` is under 500ms, achievable without pagination for reasonable character counts.

---

## Extending This Feature

To add a new built-in template (e.g., `study_buddy`), add the template name to `ALLOWED_TEMPLATES` in `backend/app/schemas/character.py` and add the corresponding role description to `TEMPLATE_ROLES` in `backend/app/services/character_service.py`. No other changes are needed -- the meta-prompt builder and Claude Haiku call handle it automatically.

To add a single-character detail endpoint (`GET /characters/:id`), add a route in `backend/app/routes/characters.py` that calls `CharacterService._get_active_character()` (or a new public method wrapping it), performs an ownership check, and returns `CharacterDetail`.

To implement character reactivation, add a `PATCH /characters/:id/reactivate` endpoint that sets `is_active = true` on a soft-deleted character. Consider whether the character should reappear in the list with its original position or at the top.

To enforce subscription-tier limits on character count, add a count check at the beginning of `CharacterService.create_character()` that queries the number of active characters for the user and compares it against the tier limit.

---

## Related Documentation

- [Auth Endpoints](./auth-endpoints.md) -- registration creates the default companion character that this feature manages
- [Database Schema](./database-schema.md) -- the `characters` and `conversations` tables
- [Cognito Auth Middleware](./cognito-auth-middleware.md) -- JWT verification used by all four endpoints
- [Database Schema and API Endpoints](../04-veri-api.md) -- authoritative source for table definitions
- [AI Memory System](../05-ai-bellek.md) -- Mem0 integration patterns and the `agent_id` format
- [Multi-Character System](../16-karakterler.md) -- character templates, memory isolation design
