# Feature Spec: P01-05 -- Character CRUD

**Feature ID**: P01-05
**Phase**: 1
**Layer**: backend
**GitHub Issue**: #7
**Date**: 2026-02-23
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature implements the four CRUD endpoints for AI characters on the Ember backend:

1. **GET /api/v1/characters** -- Lists the authenticated user's characters. Each character in the response includes `last_message_at` obtained by joining with the `conversations` table. Characters are sorted by `last_message_at DESC NULLS LAST` (most recently active character first), with a fallback to `created_at DESC` for characters that have never been messaged.

2. **POST /api/v1/characters** -- Creates a new character. Validates the `template` field against the allowed set (`companion`, `english_teacher`, `therapist`, `fitness_coach`, `career_coach`, `custom`). Auto-generates a `system_prompt` by calling Claude Haiku (claude-haiku-4-5). Computes the `mem0_agent_id` as `{template}_{user_id}`. Auto-creates the corresponding single `conversations` row. Returns the newly created character.

3. **PUT /api/v1/characters/:id** -- Updates a character's `name`, `system_prompt`, and/or `avatar_style`. Enforces ownership: the character must belong to the authenticated user. Returns the updated character.

4. **DELETE /api/v1/characters/:id** -- Soft-deletes a character by setting `is_active = false`. If the character has `is_default = true` (the General Friend), returns HTTP 403. Enforces ownership.

All four endpoints require JWT authentication and extract `user_id` from the token.

### Why It Exists

Without this feature, users cannot create additional AI characters beyond the default companion created during registration. The multi-character system is a core differentiator for Ember -- users need to create, customize, and manage characters with different specializations (language teacher, therapist, fitness coach, etc.).

### Dependencies

- **Requires**: P01-01 (project-setup -- FastAPI scaffold, config)
- **Requires**: P01-02 (database-schema -- Character, Conversation, Profile models)
- **Requires**: P01-03 (cognito-auth-middleware -- `get_current_user` dependency)
- **Requires**: P01-04 (auth-endpoints -- user can register and obtain a JWT)
- **Blocks**: All features that depend on character selection (messaging, memory display, notifications)

### What This Feature Does NOT Do

- It does not implement message sending or SSE streaming. That is a separate feature.
- It does not implement character memory endpoints (`GET /characters/:id/memories`). That is a separate feature.
- It does not implement subscription-tier enforcement (limiting free users to one character). That is a Phase 2 feature. For now, any authenticated user can create characters.
- It does not implement `GET /characters/:id` (single character detail). The list endpoint returns all needed fields. A detail endpoint can be added later if needed.
- It does not modify or re-generate the default companion character's `system_prompt`. The default character was created during registration (P01-04) with a hardcoded prompt.

---

## 2. Data Models

### No New Tables

This feature does not create or modify any database tables. It reads from and writes to two existing tables defined in P01-02 (documented in `docs/04-veri-api.md`):

- **characters** -- CRUD operations on character rows.
- **conversations** -- A new row is auto-created when a character is created. The `last_message_at` column is read (via join) for the list endpoint.

### Key Column References

| Table | Column | Usage in This Feature |
|-------|--------|----------------------|
| `characters.id` | UUID PK | Returned in responses, used as path parameter for PUT/DELETE |
| `characters.user_id` | UUID FK -> profiles | Set from JWT `user_id`, used for ownership checks |
| `characters.name` | TEXT | Set from request body, updatable via PUT |
| `characters.template` | TEXT | Set from request body on POST, immutable after creation |
| `characters.description` | TEXT / NULL | Set from request body on POST (required for `custom` template, null otherwise) |
| `characters.system_prompt` | TEXT | Auto-generated via Claude Haiku on POST, updatable via PUT |
| `characters.mem0_agent_id` | TEXT UNIQUE | Computed as `{template}_{user_id}` on POST, immutable after creation |
| `characters.avatar_style` | TEXT | Defaults to `"default"`, updatable via PUT |
| `characters.is_default` | BOOLEAN | Checked on DELETE (cannot delete if true) |
| `characters.is_active` | BOOLEAN | Set to `false` on DELETE (soft delete) |
| `characters.created_at` | TIMESTAMPTZ | Auto-set by server_default, returned in responses |
| `conversations.character_id` | UUID FK UNIQUE | Points to the new character (auto-created row) |
| `conversations.user_id` | UUID FK | Points to the authenticated user |
| `conversations.last_message_at` | TIMESTAMPTZ / NULL | Read via join for the list endpoint |

### Mem0 Operations

No Mem0 API calls are made by this feature. The `mem0_agent_id` is computed and stored in the database as `{template}_{user_id}`. Actual Mem0 interactions (add, search) happen during the messaging flow, not during character creation. The `mem0_agent_id` is the identifier that will be passed to Mem0 calls in future features.

### Note on `mem0_agent_id` Uniqueness

The `mem0_agent_id` column has a UNIQUE constraint. If a user creates a second character with the same template, the `mem0_agent_id` would collide (`english_teacher_{user_id}` twice). To handle this, the service must append a short discriminator when a user already has an active or inactive character with the same template. The format becomes `{template}_{user_id}` for the first character of that template, and `{template}_{short_uuid}_{user_id}` for subsequent ones (where `short_uuid` is the first 8 characters of the new character's UUID). This preserves Mem0 memory isolation per character instance.

---

## 3. API Endpoints

All endpoints are under the `/api/v1` prefix. All four require `Authorization: Bearer <jwt>`.

---

### GET /api/v1/characters

Lists the authenticated user's characters, ordered by most recently active first.

```
Auth: Bearer JWT required
Content-Type: application/json
```

**Query Parameters**: None.

**Response 200 OK:**

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
    },
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "name": "Sarah",
      "template": "english_teacher",
      "description": null,
      "avatar_style": "blue",
      "is_default": false,
      "last_message_at": null,
      "created_at": "2026-02-23T12:00:00Z"
    }
  ]
}
```

| Response Field | Type | Notes |
|----------------|------|-------|
| `characters` | array | All active characters for the user |
| `characters[].id` | string (UUID) | Character primary key |
| `characters[].name` | string | User-assigned name |
| `characters[].template` | string | Template identifier |
| `characters[].description` | string or null | Custom character description |
| `characters[].avatar_style` | string | UI differentiation key |
| `characters[].is_default` | boolean | True only for General Friend |
| `characters[].last_message_at` | string (ISO 8601) or null | From conversations table |
| `characters[].created_at` | string (ISO 8601) | Character creation time |

**Notes:**
- Only characters with `is_active = true` are returned.
- The `system_prompt` and `mem0_agent_id` are intentionally excluded from the list response (they are backend-internal and not needed by the mobile client for the character grid).
- The response is a flat list, not cursor-paginated. Users are expected to have at most dozens of characters, not thousands.

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 401 | Missing or invalid JWT | `{"detail": "Invalid or expired token"}` |

---

### POST /api/v1/characters

Creates a new character.

```
Auth: Bearer JWT required
Content-Type: application/json
```

**Request Body:**

```json
{
  "name": "Sarah",
  "template": "english_teacher",
  "description": null
}
```

For custom template:

```json
{
  "name": "Marco",
  "template": "custom",
  "description": "An Italian language teacher. Only speaks Italian. Suitable for beginner level."
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `name` | string | yes | Min 1 char, max 100 chars, whitespace-trimmed |
| `template` | string | yes | One of: `companion`, `english_teacher`, `therapist`, `fitness_coach`, `career_coach`, `custom` |
| `description` | string or null | conditional | Required when `template = "custom"`, min 10 chars, max 1000 chars. Must be null or absent for non-custom templates. |

**Response 201 Created:**

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

| Response Field | Type | Notes |
|----------------|------|-------|
| `id` | string (UUID) | Newly created character ID |
| `name` | string | The name from the request |
| `template` | string | The template from the request |
| `description` | string or null | The description from the request |
| `system_prompt` | string | Auto-generated by Claude Haiku |
| `avatar_style` | string | Always `"default"` on creation |
| `is_default` | boolean | Always `false` for user-created characters |
| `created_at` | string (ISO 8601) | Server-assigned timestamp |

**Notes:**
- The `system_prompt` is included in the creation response so the mobile client can display it for user review/editing. The user can then call PUT to modify it.
- The `mem0_agent_id` is NOT included in the response (backend-internal).
- A Conversation row is auto-created with `last_message_at = null`.

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 400 | Invalid template value | `{"detail": "Invalid template. Must be one of: companion, english_teacher, therapist, fitness_coach, career_coach, custom"}` |
| 400 | Template is `custom` but description is missing or empty | `{"detail": "Description is required for custom characters"}` |
| 400 | Template is not `custom` but description is provided | `{"detail": "Description is only allowed for custom characters"}` |
| 401 | Missing or invalid JWT | `{"detail": "Invalid or expired token"}` |
| 422 | Pydantic validation failure | Standard FastAPI 422 response |
| 503 | Claude Haiku API unavailable | `{"detail": "AI service unavailable, please try again"}` |

---

### PUT /api/v1/characters/:id

Updates a character's mutable fields.

```
Auth: Bearer JWT required
Content-Type: application/json
```

**Path Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `id` | UUID string | Character ID |

**Request Body:**

```json
{
  "name": "Sarah the Great",
  "system_prompt": "You are Sarah, a patient and encouraging English teacher...",
  "avatar_style": "blue"
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `name` | string or null | no | Min 1 char, max 100 chars, whitespace-trimmed. Null or absent means no change. |
| `system_prompt` | string or null | no | Min 1 char, max 10000 chars. Null or absent means no change. |
| `avatar_style` | string or null | no | Max 50 chars. Null or absent means no change. |

At least one field must be provided in the request body. If all fields are null or absent, return 400.

**Response 200 OK:**

```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "name": "Sarah the Great",
  "template": "english_teacher",
  "description": null,
  "system_prompt": "You are Sarah, a patient and encouraging English teacher...",
  "avatar_style": "blue",
  "is_default": false,
  "created_at": "2026-02-23T14:30:00Z"
}
```

The response returns the full updated character (same shape as the POST 201 response).

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 400 | No updatable fields provided | `{"detail": "At least one field must be provided for update"}` |
| 401 | Missing or invalid JWT | `{"detail": "Invalid or expired token"}` |
| 403 | Character does not belong to the authenticated user | `{"detail": "Character does not belong to user"}` |
| 404 | Character not found or is inactive | `{"detail": "Character not found"}` |
| 422 | Pydantic validation failure | Standard FastAPI 422 response |

**Notes:**
- The `template`, `description`, `mem0_agent_id`, and `is_default` fields are immutable. They cannot be changed after creation.
- Ownership check: the character's `user_id` must match the JWT `user_id`.
- Only active characters can be updated (`is_active = true`).

---

### DELETE /api/v1/characters/:id

Soft-deletes a character by setting `is_active = false`.

```
Auth: Bearer JWT required
```

**Path Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `id` | UUID string | Character ID |

**Response 204 No Content:**

Empty body.

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 401 | Missing or invalid JWT | `{"detail": "Invalid or expired token"}` |
| 403 | Character is the default (General Friend) | `{"detail": "Default character cannot be deleted"}` |
| 403 | Character does not belong to the authenticated user | `{"detail": "Character does not belong to user"}` |
| 404 | Character not found or already inactive | `{"detail": "Character not found"}` |

**Notes:**
- Soft delete only: `is_active` is set to `false`. The row is not removed from the database.
- The associated conversation row is NOT deleted or deactivated. It remains in the database but is effectively orphaned (the character will not appear in the list).
- Mem0 memories for this character are NOT deleted. They persist and could be restored if the character is reactivated in a future feature.
- Checking `is_default` MUST happen before the delete, not after. If `is_default = true`, return 403 immediately.
- If the character is already inactive (`is_active = false`), return 404 (treat it as "not found" from the user's perspective).

---

## 4. Backend Logic

### CharacterService Class

The `CharacterService` class in `backend/app/services/character_service.py` encapsulates all character business logic. Route handlers delegate to this service.

```
class CharacterService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_characters(self, user_id: uuid.UUID) -> list[CharacterListItem]:
        """List all active characters for a user, with last_message_at from conversations."""

    async def create_character(
        self,
        user_id: uuid.UUID,
        user_name: str,
        name: str,
        template: str,
        description: str | None,
    ) -> CharacterDetail:
        """Create a new character with auto-generated system prompt and conversation."""

    async def update_character(
        self,
        character_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str | None,
        system_prompt: str | None,
        avatar_style: str | None,
    ) -> CharacterDetail:
        """Update mutable fields on an existing character."""

    async def delete_character(
        self,
        character_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Soft-delete a character (set is_active=false)."""
```

### List Characters Flow

```
Client sends: GET /api/v1/characters
Authorization: Bearer <jwt>
    |
    v
1. get_current_user extracts user_id from JWT
    |
    v
2. Query: SELECT characters + LEFT JOIN conversations
   WHERE characters.user_id = $user_id
     AND characters.is_active = true
   ORDER BY conversations.last_message_at DESC NULLS LAST,
            characters.created_at DESC
    |
    v
3. Map rows to CharacterListItem response objects
    |
    v
4. Return 200 { characters: [...] }
```

**SQL Join Details:**

The query must join `characters` with `conversations` to obtain `last_message_at`. Since every character has exactly one conversation (enforced by the UNIQUE constraint on `conversations.character_id`), this is a one-to-one join. Use a LEFT JOIN in case the conversation row is somehow missing (defensive).

The SQLAlchemy query:

```python
stmt = (
    select(Character, Conversation.last_message_at)
    .outerjoin(Conversation, Conversation.character_id == Character.id)
    .where(Character.user_id == user_id, Character.is_active == true())
    .order_by(
        Conversation.last_message_at.desc().nulls_last(),
        Character.created_at.desc(),
    )
)
result = await self.db.execute(stmt)
rows = result.all()
```

Each row is a tuple of `(Character, last_message_at)`.

### Create Character Flow

```
Client sends: POST /api/v1/characters
    { name, template, description }
    |
    v
1. Validate request body (Pydantic)
   - Validate template is in allowed set
   - If template == "custom", require description (min 10 chars)
   - If template != "custom", reject description if provided
    |
    v
2. Generate system_prompt via Claude Haiku
   - Build a meta-prompt asking Haiku to generate a character system prompt
   - Pass: template, character name, user name
   - For custom: also pass the user's description
   - Await the Claude API response (non-streaming, complete)
    |
    +--> Claude API error → 503 "AI service unavailable, please try again"
    |
    v
3. Compute mem0_agent_id
   - Default: f"{template}_{user_id}"
   - Check for UNIQUE constraint conflict by querying existing characters
     with same template for this user (including inactive ones)
   - If conflict: f"{template}_{character_uuid[:8]}_{user_id}"
    |
    v
4. Create Character row:
     id = uuid4()
     user_id = user_id (from JWT)
     name = request.name (trimmed)
     template = request.template
     description = request.description (or null)
     system_prompt = generated prompt from step 2
     mem0_agent_id = computed in step 3
     avatar_style = "default"
     is_default = false
     is_active = true
    |
    v
5. Create Conversation row:
     id = uuid4()
     user_id = user_id (from JWT)
     character_id = character.id (from step 4)
     last_message_at = null
    |
    v
6. Commit both rows in a single transaction
    |
    v
7. Return 201 { id, name, template, description, system_prompt, avatar_style, is_default, created_at }
```

### System Prompt Generation via Claude Haiku

The service calls Claude Haiku (`claude-haiku-4-5`) with a meta-prompt to generate the character's system prompt. This is a non-streaming, synchronous (from the caller's perspective) `messages.create` call.

**Template for built-in templates:**

```
Meta-prompt sent to Haiku:

"Generate a system prompt for an AI character with the following specifications:

Character name: {character_name}
User's name: {user_name}
Role: {role_description_from_template}

The system prompt should:
- Address the user by name naturally
- Define the character's personality, tone, and expertise
- Include instructions to remember things naturally (never say 'I remember that...')
- Keep responses concise and conversational
- Be written in second person ('You are...')
- Be between 100-300 words

Output ONLY the system prompt text, nothing else."
```

Where `role_description_from_template` maps to:

| Template | Role Description |
|----------|-----------------|
| `companion` | "A personal AI companion and holistic life friend covering fitness, nutrition, work, stress, and relationships. Warm, honest, genuine but not overly positive." |
| `english_teacher` | "An English language teacher who teaches through conversation. Corrects mistakes gently but stays motivating. Adapts to the user's level." |
| `therapist` | "An emotional support assistant. Listens, reflects, does not judge. Never diagnoses or prescribes medication. Recommends professional help when needed. Uses CBT-based approaches." |
| `fitness_coach` | "A fitness and nutrition coach. Provides workout programming, form advice, and nutrition support. Tracks progress and is mindful of injuries." |
| `career_coach` | "A career development coach. Helps with goal setting, negotiation, leadership, and work-life balance. Pragmatic and honest." |

**Template for custom characters:**

```
Meta-prompt sent to Haiku:

"Generate a system prompt for a custom AI character with the following specifications:

Character name: {character_name}
User's name: {user_name}
Character description (provided by the user): {description}

The system prompt should:
- Faithfully implement the user's description
- Address the user by name naturally
- Define the character's personality, tone, and expertise based on the description
- Include instructions to remember things naturally (never say 'I remember that...')
- Keep responses concise and conversational
- Be written in second person ('You are...')
- Be between 100-300 words

Output ONLY the system prompt text, nothing else."
```

**Claude Haiku call details:**

```python
from anthropic import AsyncAnthropic
from app.config import settings

client = AsyncAnthropic(api_key=settings.anthropic_api_key)

response = await client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=512,
    messages=[{"role": "user", "content": meta_prompt}],
)
system_prompt = response.content[0].text
```

The Anthropic client is instantiated in the service or via dependency injection, not in the route handler. Use `AsyncAnthropic` (async client) since we are in an async context.

**Error handling for Claude call:**

If the Claude API call raises an exception (network error, rate limit, API error), catch it and raise `HTTPException(503, detail="AI service unavailable, please try again")`. Log the underlying error at ERROR level but do not expose the raw error to the client.

### Update Character Flow

```
Client sends: PUT /api/v1/characters/:id
    { name?, system_prompt?, avatar_style? }
    |
    v
1. Validate at least one field is provided (not all null)
    |
    v
2. Look up character by id:
   SELECT * FROM characters WHERE id = $id AND is_active = true
    |
    +--> Not found → 404 "Character not found"
    |
    v
3. Ownership check: character.user_id == jwt_user_id
    |
    +--> Mismatch → 403 "Character does not belong to user"
    |
    v
4. Apply updates to the ORM object:
   - If name is not None: character.name = name.strip()
   - If system_prompt is not None: character.system_prompt = system_prompt
   - If avatar_style is not None: character.avatar_style = avatar_style
    |
    v
5. Commit
    |
    v
6. Return 200 { full character object }
```

### Delete Character Flow

```
Client sends: DELETE /api/v1/characters/:id
    |
    v
1. Look up character by id:
   SELECT * FROM characters WHERE id = $id AND is_active = true
    |
    +--> Not found → 404 "Character not found"
    |
    v
2. Ownership check: character.user_id == jwt_user_id
    |
    +--> Mismatch → 403 "Character does not belong to user"
    |
    v
3. Default check: character.is_default == true
    |
    +--> Is default → 403 "Default character cannot be deleted"
    |
    v
4. Soft delete: character.is_active = false
    |
    v
5. Commit
    |
    v
6. Return 204 (no body)
```

### Config Change: Add Claude Haiku Model Setting

The `config.py` `Settings` class needs a new field for the Haiku model name, since `claude_model` is used for the main conversation model (Sonnet).

```
claude_haiku_model: str = "claude-haiku-4-5"
```

This keeps the Haiku model name configurable without hardcoding it in the service.

---

## 5. Pydantic Schemas

All schemas are defined in `backend/app/schemas/character.py`.

### Request Schemas

```
class CreateCharacterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    template: str = Field(...)
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Name must not be empty after trimming whitespace")
        return stripped

    @field_validator("template")
    @classmethod
    def validate_template(cls, v: str) -> str:
        allowed = {"companion", "english_teacher", "therapist", "fitness_coach", "career_coach", "custom"}
        if v not in allowed:
            raise ValueError(
                "Invalid template. Must be one of: companion, english_teacher, "
                "therapist, fitness_coach, career_coach, custom"
            )
        return v

    @model_validator(mode="after")
    def validate_description_for_template(self) -> Self:
        if self.template == "custom":
            if not self.description or len(self.description.strip()) < 10:
                raise ValueError("Description is required for custom characters (min 10 chars)")
            self.description = self.description.strip()
        elif self.description is not None:
            raise ValueError("Description is only allowed for custom characters")
        return self
```

```
class UpdateCharacterRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=10000)
    avatar_style: str | None = Field(default=None, max_length=50)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            raise ValueError("Name must not be empty after trimming whitespace")
        return stripped

    @model_validator(mode="after")
    def check_at_least_one_field(self) -> Self:
        if self.name is None and self.system_prompt is None and self.avatar_style is None:
            raise ValueError("At least one field must be provided for update")
        return self
```

### Response Schemas

```
class CharacterListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    template: str
    description: str | None
    avatar_style: str
    is_default: bool
    last_message_at: datetime | None
    created_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id_to_str(cls, v: object) -> str:
        return str(v)
```

```
class CharacterListResponse(BaseModel):
    characters: list[CharacterListItem]
```

```
class CharacterDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    template: str
    description: str | None
    system_prompt: str
    avatar_style: str
    is_default: bool
    created_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id_to_str(cls, v: object) -> str:
        return str(v)
```

**Notes:**
- `CharacterListItem` is used for the GET list response. It includes `last_message_at` but NOT `system_prompt` (not needed for the character grid).
- `CharacterDetail` is used for POST and PUT responses. It includes `system_prompt` but NOT `last_message_at` (not relevant for single-character operations).
- Both response schemas use `from_attributes=True` for ORM compatibility.
- The `id` field is `str` (UUID as string) per `docs/standards/common.md` Section 5.

---

## 6. Test Requirements

### Route Tests (`backend/tests/test_character_routes.py`)

These tests use the FastAPI test client. The `get_current_user` dependency is overridden to return a fake Profile. The Claude Haiku call is mocked.

| # | Scenario | Expected |
|---|----------|----------|
| 1 | GET /characters with no characters (empty list) | 200, `{"characters": []}` |
| 2 | GET /characters with multiple characters | 200, characters sorted by `last_message_at DESC NULLS LAST` |
| 3 | GET /characters excludes inactive characters | 200, only `is_active=true` characters returned |
| 4 | GET /characters includes `last_message_at` from conversations | 200, `last_message_at` present and correct |
| 5 | GET /characters without auth header | 401 (or 403 from HTTPBearer) |
| 6 | POST /characters with valid template | 201, character created with generated `system_prompt` |
| 7 | POST /characters with `custom` template and description | 201, character created |
| 8 | POST /characters with invalid template | 422 (Pydantic validation) |
| 9 | POST /characters with `custom` template and missing description | 422 (Pydantic validation) |
| 10 | POST /characters with non-custom template and description provided | 422 (Pydantic validation) |
| 11 | POST /characters with name that is only whitespace | 422 (after strip, name is empty) |
| 12 | POST /characters without auth header | 401 |
| 13 | POST /characters when Claude Haiku is unavailable | 503, detail = "AI service unavailable, please try again" |
| 14 | PUT /characters/:id with valid fields | 200, updated character returned |
| 15 | PUT /characters/:id with no fields provided | 422 (at least one required) |
| 16 | PUT /characters/:id for character belonging to another user | 403, detail = "Character does not belong to user" |
| 17 | PUT /characters/:id for non-existent character | 404, detail = "Character not found" |
| 18 | PUT /characters/:id for inactive character | 404, detail = "Character not found" |
| 19 | PUT /characters/:id without auth header | 401 |
| 20 | DELETE /characters/:id for a normal character | 204, no body |
| 21 | DELETE /characters/:id for the default character | 403, detail = "Default character cannot be deleted" |
| 22 | DELETE /characters/:id for character belonging to another user | 403, detail = "Character does not belong to user" |
| 23 | DELETE /characters/:id for non-existent character | 404, detail = "Character not found" |
| 24 | DELETE /characters/:id for already inactive character | 404, detail = "Character not found" |
| 25 | DELETE /characters/:id without auth header | 401 |

### Service Tests (`backend/tests/test_character_service.py`)

These tests unit-test the `CharacterService` class directly. The database session and Claude API are mocked.

| # | Scenario | Expected |
|---|----------|----------|
| 26 | `list_characters()` joins characters with conversations | Correct `last_message_at` values in result |
| 27 | `list_characters()` filters by user_id and is_active | Only active characters for the specified user returned |
| 28 | `list_characters()` orders by last_message_at DESC NULLS LAST | Correct ordering |
| 29 | `create_character()` calls Claude Haiku with correct meta-prompt for built-in template | Claude called with expected prompt content |
| 30 | `create_character()` calls Claude Haiku with correct meta-prompt for custom template | Claude called with description included in prompt |
| 31 | `create_character()` creates both Character and Conversation rows | Two `db.add()` calls, one `db.commit()` |
| 32 | `create_character()` computes mem0_agent_id as `{template}_{user_id}` | Correct agent_id on Character row |
| 33 | `create_character()` handles mem0_agent_id uniqueness conflict | Falls back to `{template}_{uuid[:8]}_{user_id}` |
| 34 | `create_character()` sets is_default=false and is_active=true | Correct boolean fields |
| 35 | `update_character()` only modifies provided fields | Unset fields remain unchanged |
| 36 | `update_character()` raises 404 for non-existent character | HTTPException(404) |
| 37 | `update_character()` raises 403 for wrong user | HTTPException(403) |
| 38 | `delete_character()` sets is_active=false | Character row updated, not deleted |
| 39 | `delete_character()` raises 403 for default character | HTTPException(403) |
| 40 | `delete_character()` raises 403 for wrong user | HTTPException(403) |
| 41 | `delete_character()` raises 404 for non-existent character | HTTPException(404) |

### Schema Tests (`backend/tests/test_character_schemas.py`)

| # | Scenario | Expected |
|---|----------|----------|
| 42 | `CreateCharacterRequest` strips whitespace from name | Trimmed correctly |
| 43 | `CreateCharacterRequest` validates template against allowed set | Invalid template raises ValidationError |
| 44 | `CreateCharacterRequest` requires description for custom | Missing description raises ValidationError |
| 45 | `CreateCharacterRequest` rejects description for non-custom | Provided description raises ValidationError |
| 46 | `UpdateCharacterRequest` requires at least one field | All-null raises ValidationError |
| 47 | `CharacterListItem` coerces UUID id to string | UUID input produces string output |
| 48 | `CharacterDetail` maps from ORM object with from_attributes | All fields correctly mapped |

### How to Mock Claude Haiku

```python
from unittest.mock import AsyncMock, patch, MagicMock

mock_response = MagicMock()
mock_response.content = [MagicMock(text="Generated system prompt...")]

with patch("app.services.character_service.AsyncAnthropic") as mock_cls:
    mock_client = AsyncMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)
    mock_cls.return_value = mock_client
    # ... run test
```

Alternatively, if the service receives an LLM provider via dependency injection, mock the provider's `complete()` method directly.

### How to Mock the Database

Follow the same pattern as P01-04. Override `get_db` for route tests, pass mock `AsyncSession` directly for service tests. For the list endpoint, mock `db.execute()` to return rows with the expected `(Character, last_message_at)` shape.

---

## 7. File Manifest

Every file to be created or modified, grouped by purpose.

### Route Handler

```
Backend:
  CREATE  backend/app/routes/characters.py
```

Contains four route functions: `list_characters`, `create_character`, `update_character`, `delete_character`. Each delegates to `CharacterService`.

### Service Layer

```
Backend:
  CREATE  backend/app/services/character_service.py
```

Contains the `CharacterService` class with `list_characters()`, `create_character()`, `update_character()`, and `delete_character()` methods. Contains the template role descriptions and the meta-prompt builder for Claude Haiku.

### Pydantic Schemas

```
Backend:
  CREATE  backend/app/schemas/character.py
```

Contains `CreateCharacterRequest`, `UpdateCharacterRequest`, `CharacterListItem`, `CharacterListResponse`, `CharacterDetail`.

### Application Wiring

```
Backend:
  MODIFY  backend/app/main.py
```

Add `from app.routes import characters` and register the characters router:

```python
app.include_router(characters.router, prefix="/api/v1/characters", tags=["characters"])
```

### Configuration

```
Backend:
  MODIFY  backend/app/config.py
```

Add `claude_haiku_model: str = "claude-haiku-4-5"` to the `Settings` class.

### Tests

```
Backend:
  CREATE  backend/tests/test_character_routes.py
  CREATE  backend/tests/test_character_service.py
  CREATE  backend/tests/test_character_schemas.py
```

### Documentation (Pipeline)

```
Shared:
  CREATE  shared/feature-specs/character-crud.md          (this file)
  CREATE  docs/pipeline/character-crud-architect.handoff.md
```

### Summary

| Action | Count |
|--------|-------|
| CREATE | 6 |
| MODIFY | 2 |
| DELETE | 0 |
| **Total** | **8** |

### Files NOT Modified

- `backend/app/dependencies.py` -- Uses the existing `get_current_user` and `get_db`. No changes needed.
- `backend/app/core/auth.py` -- JWT verification is handled by the existing middleware. No changes needed.
- `backend/app/models/` -- No model changes. Existing Character and Conversation models from P01-02 are used as-is.
- `backend/app/schemas/__init__.py` -- Not modified (follow direct import pattern from route files).
- `backend/app/services/__init__.py` -- Not modified (follow direct import pattern).
- `backend/requirements.txt` -- Already includes `anthropic>=0.43.0,<1.0.0`. No new dependencies needed.
- `backend/.env.example` -- Already has `ANTHROPIC_API_KEY`. No changes needed.

---

## 8. Acceptance Criteria

1. Given an authenticated user with one default character and one additional character (with a conversation that has messages), when the client sends `GET /api/v1/characters`, then the response is HTTP 200 with a `characters` array containing both characters, each with `id`, `name`, `template`, `description`, `avatar_style`, `is_default`, `last_message_at`, and `created_at` fields.

2. Given an authenticated user with characters that have different `last_message_at` values, when the client sends `GET /api/v1/characters`, then the characters are sorted by `last_message_at` descending with nulls last.

3. Given an authenticated user who has soft-deleted a character, when the client sends `GET /api/v1/characters`, then the deleted character does not appear in the response.

4. Given valid name and template (`english_teacher`), when the client sends `POST /api/v1/characters`, then the response is HTTP 201 with a character object containing a non-empty `system_prompt` generated by Claude Haiku.

5. Given template `custom` with a valid description, when the client sends `POST /api/v1/characters`, then the response is HTTP 201 and the generated `system_prompt` reflects the user's description.

6. Given a successful character creation, when the database is inspected, then both a `characters` row and a `conversations` row exist, linked by `character_id`.

7. Given a successful character creation, when the database is inspected, then the `mem0_agent_id` follows the pattern `{template}_{user_id}`.

8. Given template `custom` without a description, when the client sends `POST /api/v1/characters`, then the response is HTTP 422 with a validation error about the missing description.

9. Given an invalid template value, when the client sends `POST /api/v1/characters`, then the response is HTTP 422 with a validation error about the invalid template.

10. Given a character belonging to the authenticated user, when the client sends `PUT /api/v1/characters/:id` with a new `name`, then the response is HTTP 200 with the updated character and the name is changed.

11. Given a character belonging to another user, when the client sends `PUT /api/v1/characters/:id`, then the response is HTTP 403 with detail "Character does not belong to user".

12. Given a non-existent character ID, when the client sends `PUT /api/v1/characters/:id`, then the response is HTTP 404 with detail "Character not found".

13. Given a normal (non-default) character, when the client sends `DELETE /api/v1/characters/:id`, then the response is HTTP 204 and the character's `is_active` is set to `false` in the database.

14. Given the default character (`is_default = true`), when the client sends `DELETE /api/v1/characters/:id`, then the response is HTTP 403 with detail "Default character cannot be deleted".

15. Given any character CRUD endpoint, when the request has no `Authorization` header, then the response is HTTP 401 (or 403 from HTTPBearer scheme).

16. Given the route handler code for all four endpoints, when a developer inspects the code, then all business logic is in `CharacterService` and route handlers only call service methods, validate input (Pydantic), and return responses.

17. Given the Claude Haiku call in `CharacterService.create_character()`, when the Claude API returns an error, then the response is HTTP 503 with detail "AI service unavailable, please try again" and the error is logged.

18. Given the GET /characters response, when a developer inspects the response fields, then `system_prompt` and `mem0_agent_id` are NOT included (they are backend-internal).

19. Given the `config.py` Settings class, when a developer inspects it, then there is a `claude_haiku_model` field with default value `"claude-haiku-4-5"`.

20. Given the backend test suite, when a developer runs `pytest` on the new test files, then all tests pass with exit code 0.

---

## 9. Design Decisions and Rationale

### Why Claude Haiku for system prompt generation (not Sonnet)

System prompt generation is a one-time operation per character creation. It produces short text (100-300 words). Claude Haiku is significantly cheaper and faster than Sonnet for this use case. Per `docs/05-ai-bellek.md`, Haiku is the designated model for "simple JSON output, cheap and fast" operations. Prompt generation fits this category.

### Why the list endpoint is NOT cursor-paginated

Users are expected to have at most a few dozen characters, not thousands. Cursor pagination adds complexity for no benefit at this scale. If the character count grows significantly in the future, pagination can be added. The performance target for `GET /characters` is under 500ms (per `docs/standards/common.md` Section 9), which is achievable without pagination for reasonable character counts.

### Why `system_prompt` is excluded from the list response

The system prompt can be hundreds of words long. Including it in every character list item would bloat the response unnecessarily. The mobile client needs the prompt only when editing a character (PUT flow), not when displaying the character grid. The POST response includes the prompt so the user can review it immediately after creation.

### Why soft delete instead of hard delete

Per `docs/04-veri-api.md`: "Characters with conversation history are deactivated, not physically deleted." Soft delete preserves data integrity (foreign keys from messages), allows potential reactivation, and simplifies the deletion logic. The `is_active` flag is the standard mechanism defined in the schema.

### Why `template` is immutable after creation

The `template` determines the `mem0_agent_id`, which is the key for Mem0 memory isolation. Changing the template after creation would either require migrating all Mem0 memories to a new agent_id (complex and error-prone) or leave the agent_id inconsistent with the template (confusing). Per `docs/16-karakterler.md`: "mem0_agent_id cannot be changed after creation (memory loss would occur)."

### Why description validation differs between custom and non-custom templates

Built-in templates have predefined role descriptions. Allowing a `description` for non-custom templates would create ambiguity about whether the description or the built-in role should drive the prompt generation. Requiring description only for custom templates keeps the contract clear.

### Why `mem0_agent_id` needs a uniqueness fallback

The UNIQUE constraint on `mem0_agent_id` means a user cannot have two characters with the same template without a disambiguation mechanism. While rare (most users will have one character per template), the system must handle it gracefully. The `{template}_{short_uuid}_{user_id}` fallback preserves the template-first naming convention while ensuring uniqueness.

---

## 10. Notes for Developers

### For backend-dev

- **Start with schemas** (`app/schemas/character.py`), then the service (`app/services/character_service.py`), then the route (`app/routes/characters.py`), then wire up in `main.py`.

- **Anthropic client usage**: Use `AsyncAnthropic` from the `anthropic` package (already in `requirements.txt`). The `create()` call is NOT streaming -- use `client.messages.create()` not `client.messages.stream()`.

- **Config change**: Add `claude_haiku_model` to `Settings`. Use `settings.claude_haiku_model` in the service instead of hardcoding `"claude-haiku-4-5"`.

- **Router prefix**: Register with `prefix="/api/v1/characters"` in `main.py`. Route functions use relative paths: `@router.get("")`, `@router.post("")`, `@router.put("/{character_id}")`, `@router.delete("/{character_id}")`.

- **Path parameter type**: Use `character_id: uuid.UUID` in route signatures. FastAPI will automatically parse the UUID from the path and return 422 if invalid.

- **Ownership pattern**: The ownership check (`character.user_id == current_user.id`) is a common pattern that will be reused in many features. Consider extracting it to a helper, or keep it inline for now and refactor later.

- **Transaction scope**: For POST, both the Character and Conversation rows are added in the same session before a single `commit()`. If either fails, both roll back.

- **Defensive coding for list query**: Use `outerjoin` (LEFT JOIN) when joining conversations, even though every character should have a conversation. This prevents the query from silently dropping characters that somehow lack a conversation row.

- **The `system_prompt` field on the Character model is `TEXT NOT NULL`**. The Claude Haiku call must succeed for the character to be created. If Claude is unavailable, the entire creation fails with 503 -- do not create a character with an empty or placeholder prompt.

### For backend-tester

- **Mock the Anthropic client**: Patch `AsyncAnthropic` or the service's internal client. Return a mock response with `.content[0].text = "Generated system prompt..."`.

- **Test the join**: For list endpoint tests, seed the database with characters that have conversations with different `last_message_at` values (including null). Verify the ordering.

- **Test ownership**: Create characters owned by different users and verify that one user cannot update or delete another user's characters.

- **Test the default character protection**: Create a character with `is_default=True` and verify that DELETE returns 403.

- **Test soft delete**: After deleting, verify that the character's `is_active` field is `false` and that it no longer appears in the list response.
