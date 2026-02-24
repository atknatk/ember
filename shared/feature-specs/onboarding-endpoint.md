# Feature Spec: P01-09 -- Onboarding Endpoint

**Feature ID**: P01-09
**Phase**: 1
**Layer**: backend
**GitHub Issue**: #11
**Date**: 2026-02-24
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature implements a single endpoint that completes the user onboarding flow:

**POST /api/v1/onboarding/complete** -- Receives answers to 7 onboarding questions, uses Claude Haiku to convert the raw Q&A pairs into structured memory statements, seeds those memories into Mem0 for the user's default General Friend character (`agent_id = companion_{user_id}`), and sets `profiles.onboarding_completed = true` in the database.

The 7 onboarding questions are defined in `docs/05-ai-bellek.md` Section "Onboarding Memory Seed":

1. "What should I call you?" (preferred name)
2. "What do you do for work?" (profession)
3. "Are you a morning person or a night owl?" (daily rhythm)
4. "What are your health/fitness goals?" (goals)
5. "What do you do for stress management?" (coping)
6. "What is your sleep schedule like?" (sleep pattern)
7. "What kind of friendship do you expect from me?" (communication preference)

The mobile client presents these questions during first launch (after registration) and submits all 7 answers in a single request.

### Why It Exists

Without onboarding, the AI companion starts every relationship with zero knowledge about the user. The first few conversations would be generic and impersonal. By seeding Mem0 with structured memories from onboarding answers, the General Friend character can be immediately personalized from the very first chat message. This directly supports Ember's core value proposition: a memory-first AI companion that "knows" the user.

### Dependencies

- **Requires**: P01-04 (auth-endpoints -- `get_current_user` dependency, Profile model with `onboarding_completed` column, default Character with `companion` template and `mem0_agent_id`)
- **Requires**: P01-01 (project-setup -- FastAPI scaffold, config with `anthropic_api_key`, `mem0_api_key`, `claude_haiku_model`)
- **Requires**: P01-02 (database-schema -- Profile and Character models)
- **Requires**: P01-03 (cognito-auth-middleware -- JWT verification)
- **Uses patterns from**: P01-06 (chat-streaming -- Claude Haiku calls via `AsyncAnthropic`, Mem0 `MemoryClient` with `asyncio.to_thread()`)

### What This Feature Does NOT Do

- It does not present the onboarding questions to the user. The mobile client owns the question UI and sends the collected answers.
- It does not create new characters or conversations. The default "Ember" companion character already exists from registration (P01-04).
- It does not allow partial onboarding. All 7 answers must be submitted together. There is no "save progress" endpoint.
- It does not allow re-onboarding. Once `onboarding_completed` is `true`, calling the endpoint again returns 409 Conflict.

---

## 2. Data Models

### No New Tables

This feature does not create any new database tables.

### No New Columns

All required columns already exist:

| Table | Column | Usage in This Feature |
|-------|--------|----------------------|
| `profiles.id` | UUID PK | Identifies the authenticated user |
| `profiles.onboarding_completed` | BOOLEAN DEFAULT FALSE | Updated to `true` after successful memory seeding |
| `profiles.mem0_user_id` | TEXT UNIQUE | Passed to Mem0 SDK as `user_id` for memory seeding |
| `profiles.name` | TEXT | Potentially updated if the user provides a different preferred name |
| `characters.user_id` | UUID FK -> profiles | Used to find the default character |
| `characters.template` | TEXT | Filtered to `"companion"` to find the General Friend character |
| `characters.is_default` | BOOLEAN | Filtered to `true` to find the General Friend character |
| `characters.mem0_agent_id` | TEXT UNIQUE | Passed to Mem0 SDK as `agent_id` for memory seeding |
| `characters.is_active` | BOOLEAN | Only active characters are used |

### Mem0 Operations

This feature performs a single Mem0 `add()` call to seed onboarding memories:

```
client.add(
    messages=structured_memories,  # list of memory strings from Haiku
    user_id=profile.mem0_user_id,
    agent_id=character.mem0_agent_id,   # companion_{user_id}
)
```

The memories are seeded to the General Friend character's memory space (scoped by `agent_id`). Per `docs/05-ai-bellek.md`, these are character-specific memories, not global memories, because they were generated in the context of the companion character.

However, because the General Friend is the primary character and these are basic user facts (name, profession, goals), they will also be found by global memory searches that use `user_id` without `agent_id`. This is the correct behavior: all characters should be able to see basic user information from onboarding.

**Important Mem0 behavior note**: When `client.add()` is called with both `user_id` and `agent_id`, Mem0 stores the memories as character-scoped. The parallel two-layer search in the chat flow (from P01-06) searches both global (`user_id` only) and character-scoped (`user_id` + `agent_id`). Onboarding memories will be found by the character-scoped search for the companion character. For other characters, these memories will NOT appear in their character-scoped search. To ensure all characters can access basic user facts, we seed onboarding memories WITHOUT an `agent_id` (global scope). This makes them visible to all characters' global memory search.

**Decision**: Seed onboarding memories as global memories (`user_id` only, no `agent_id`). This aligns with `docs/05-ai-bellek.md` Section "Memory Isolation" which states that global memories contain "basic user information visible to all characters" -- name, profession, goals, etc. Onboarding answers are exactly this category of information.

---

## 3. API Endpoints

All endpoints are under the `/api/v1` prefix.

---

### POST /api/v1/onboarding/complete

Completes the user onboarding by converting Q&A answers into structured Mem0 memories and marking the profile as onboarded.

```
Auth: Bearer JWT required
Content-Type: application/json
```

**Request Body:**

```json
{
  "answers": [
    {
      "question_key": "preferred_name",
      "answer": "Alex"
    },
    {
      "question_key": "occupation",
      "answer": "Software engineer at a startup"
    },
    {
      "question_key": "daily_rhythm",
      "answer": "Morning person, I wake up at 6:30"
    },
    {
      "question_key": "health_goal",
      "answer": "Lose 10 kg and run a half marathon"
    },
    {
      "question_key": "stress_management",
      "answer": "I go for walks and listen to podcasts"
    },
    {
      "question_key": "sleep_schedule",
      "answer": "Usually 11 PM to 6:30 AM"
    },
    {
      "question_key": "communication_style",
      "answer": "I want someone who checks in on me but doesn't overwhelm me"
    }
  ]
}
```

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `answers` | array | yes | Exactly 7 items |
| `answers[].question_key` | string | yes | Must be one of the 7 valid keys (see below) |
| `answers[].answer` | string | yes | Min 1 char, max 500 chars, whitespace-trimmed |

**Valid `question_key` values:**

| Key | Maps to Onboarding Question |
|-----|----------------------------|
| `preferred_name` | "What should I call you?" |
| `occupation` | "What do you do for work?" |
| `daily_rhythm` | "Are you a morning person or a night owl?" |
| `health_goal` | "What are your health/fitness goals?" |
| `stress_management` | "What do you do for stress management?" |
| `sleep_schedule` | "What is your sleep schedule like?" |
| `communication_style` | "What kind of friendship do you expect from me?" |

**Validation rules:**
- All 7 question keys must be present (no duplicates, no missing keys).
- Each answer must be a non-empty string after trimming.
- Order of answers in the array does not matter.

**Response 200 OK:**

```json
{
  "onboarding_completed": true,
  "memories_seeded": 7
}
```

| Response Field | Type | Notes |
|----------------|------|-------|
| `onboarding_completed` | boolean | Always `true` on success |
| `memories_seeded` | integer | Number of memory statements seeded to Mem0. May differ from 7 if Haiku generates fewer or more statements per answer. |

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 401 | Missing or invalid JWT | `{"detail": "Invalid or expired token"}` |
| 409 | `profiles.onboarding_completed` is already `true` | `{"detail": "Onboarding already completed"}` |
| 422 | Pydantic validation failure (missing keys, invalid answer length, duplicate keys) | Standard FastAPI 422 response |
| 503 | Claude Haiku or Mem0 API unavailable | `{"detail": "AI service temporarily unavailable"}` |

**Notes:**
- This endpoint is idempotent in the error case: if Claude or Mem0 fails, the client can retry. The `onboarding_completed` flag is only set to `true` after successful memory seeding.
- If the `preferred_name` answer is different from `profiles.name`, the profile name is updated. This allows the user to choose a nickname during onboarding that overrides the name they entered during registration.

---

## 4. Backend Logic

### OnboardingService Class

A new `OnboardingService` class in `backend/app/services/onboarding_service.py` encapsulates all onboarding business logic. Route handlers delegate to this service.

```
class OnboardingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def complete_onboarding(
        self,
        profile: Profile,
        answers: list[OnboardingAnswer],
    ) -> OnboardingResponse:
        """Process onboarding answers: convert to memories, seed Mem0, update profile."""
```

### Complete Onboarding Flow (Step-by-Step)

```
Client sends: POST /api/v1/onboarding/complete
Authorization: Bearer <jwt>
    { answers: [ {question_key, answer}, ... ] }
    |
    v
1. get_current_user extracts Profile from JWT
    |
    v
2. Check profile.onboarding_completed
    |
    +--> true --> 409 "Onboarding already completed"
    |
    v
3. Validate answers: all 7 keys present, no duplicates, all non-empty
    |   (Pydantic model handles this validation)
    |
    v
4. Build a prompt for Claude Haiku with Q&A pairs
    |
    v
5. Call Claude Haiku to convert raw Q&A answers into structured memory statements
    |
    +--> Claude API error --> 503 "AI service temporarily unavailable"
    |
    v
6. Parse Haiku's response (expect a JSON array of memory strings)
    |
    +--> Parse failure --> use fallback memory formatting (see below)
    |
    v
7. Seed memories to Mem0 (global scope):
    client = MemoryClient(api_key=settings.mem0_api_key)
    for memory_text in structured_memories:
        client.add(memory_text, user_id=profile.mem0_user_id)
    |
    +--> Mem0 API error --> 503 "AI service temporarily unavailable"
    |
    v
8. Update profile:
    profile.onboarding_completed = true
    If preferred_name != profile.name:
        profile.name = preferred_name
    |
    v
9. Commit DB transaction
    |
    v
10. Return 200 { onboarding_completed: true, memories_seeded: N }
```

### Claude Haiku Prompt for Memory Conversion

The service sends a structured prompt to Claude Haiku that includes all 7 Q&A pairs and asks for structured memory statements. This is a single Haiku call (not 7 separate calls).

```
MEMORY_CONVERSION_PROMPT = """\
You are a memory extraction system. Convert the following onboarding Q&A answers \
into concise, factual memory statements about the user. Each statement should be a \
single sentence that an AI companion can use to personalize conversations.

Rules:
- Output ONLY a JSON array of strings. No other text.
- Each string is one factual memory statement.
- Use third person ("Prefers to be called Alex", not "I prefer to be called Alex").
- Keep each statement under 100 characters.
- Generate exactly one memory statement per Q&A pair.
- Do not add information that is not in the answers.

Q&A Pairs:
1. Preferred name: {preferred_name}
2. Occupation: {occupation}
3. Daily rhythm: {daily_rhythm}
4. Health/fitness goal: {health_goal}
5. Stress management: {stress_management}
6. Sleep schedule: {sleep_schedule}
7. Communication preference: {communication_style}

Output the JSON array now:"""
```

**Expected Haiku response:**

```json
[
  "Prefers to be called Alex",
  "Works as a software engineer at a startup",
  "Morning person, wakes up at 6:30",
  "Goal: lose 10 kg and run a half marathon",
  "Manages stress by going for walks and listening to podcasts",
  "Sleeps from 11 PM to 6:30 AM",
  "Wants an AI friend who checks in regularly but doesn't overwhelm"
]
```

### Fallback Memory Formatting

If Claude Haiku returns a response that cannot be parsed as a JSON array of strings (malformed JSON, unexpected format), the service falls back to a deterministic mapping:

| Question Key | Fallback Format |
|-------------|----------------|
| `preferred_name` | `"Prefers to be called {answer}"` |
| `occupation` | `"Works as {answer}"` |
| `daily_rhythm` | `"Daily rhythm: {answer}"` |
| `health_goal` | `"Health/fitness goal: {answer}"` |
| `stress_management` | `"Stress management: {answer}"` |
| `sleep_schedule` | `"Sleep schedule: {answer}"` |
| `communication_style` | `"Communication preference: {answer}"` |

This ensures onboarding always succeeds even if Haiku returns unexpected output. The fallback memories are less natural-sounding but still functional for Mem0 search.

### Mem0 Seeding Strategy

The service calls `client.add()` once with the full list of memory statements:

```python
client = MemoryClient(api_key=settings.mem0_api_key)
await asyncio.to_thread(
    client.add,
    structured_memories,   # list of memory text strings
    user_id=profile.mem0_user_id,
)
```

**Key details:**
- The call uses `user_id` only (no `agent_id`). This seeds them as global memories visible to all characters.
- The `client.add()` method accepts either a string or a list of message dicts. For seeding, we pass the formatted memory strings as a single joined text or as a list of `{"role": "user", "content": text}` dicts. The Mem0 SDK will extract and store memories from the content.
- All Mem0 SDK calls are synchronous and must be wrapped in `asyncio.to_thread()`.
- On Mem0 failure, the service raises 503. The DB flag is NOT set, allowing the client to retry.

### Profile Name Update

If the `preferred_name` answer differs from the current `profiles.name`, the profile name is updated in the same transaction. This handles the case where a user registers as "Alexander" but wants to be called "Alex".

The comparison is case-insensitive and stripped: `preferred_name.strip().lower() != profile.name.strip().lower()`.

### Error Handling

| Failure Point | Behavior |
|--------------|----------|
| Pydantic validation (missing keys, empty answers) | 422 -- standard FastAPI validation error |
| `onboarding_completed` already `true` | 409 -- "Onboarding already completed" |
| Claude Haiku API error | 503 -- "AI service temporarily unavailable"; DB not modified |
| Claude Haiku returns unparseable response | Use fallback formatting; continue normally |
| Mem0 `add()` failure | 503 -- "AI service temporarily unavailable"; DB not modified |
| DB commit failure | 500 -- handled by global exception handler; Mem0 memories may already be written (acceptable -- they are harmless without the flag, and the client will retry) |

### Transaction Safety

The order of operations matters for idempotency:
1. First, call Claude Haiku (stateless -- can be retried safely)
2. Then, seed Mem0 (idempotent -- adding duplicate memories is harmless; Mem0 deduplicates)
3. Finally, update `onboarding_completed` flag in the DB

If step 2 fails, the flag stays `false` and the client can retry. If step 3 fails, Mem0 has the memories but the flag is `false`; on retry, Mem0 will deduplicate and the flag will be set. This ordering ensures the endpoint is retry-safe.

---

## 5. Pydantic Schemas

All schemas are defined in `backend/app/schemas/onboarding.py`.

### Request Schemas

```
VALID_QUESTION_KEYS = frozenset({
    "preferred_name",
    "occupation",
    "daily_rhythm",
    "health_goal",
    "stress_management",
    "sleep_schedule",
    "communication_style",
})


class OnboardingAnswer(BaseModel):
    """A single Q&A pair from the onboarding flow."""

    question_key: str
    answer: str = Field(..., min_length=1, max_length=500)

    @field_validator("answer")
    @classmethod
    def strip_answer(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Answer must not be blank")
        return stripped

    @field_validator("question_key")
    @classmethod
    def validate_key(cls, v: str) -> str:
        if v not in VALID_QUESTION_KEYS:
            raise ValueError(f"Invalid question_key: {v}")
        return v


class OnboardingRequest(BaseModel):
    """Request body for POST /onboarding/complete."""

    answers: list[OnboardingAnswer] = Field(..., min_length=7, max_length=7)

    @model_validator(mode="after")
    def validate_all_keys_present(self) -> Self:
        keys = {a.question_key for a in self.answers}
        if keys != VALID_QUESTION_KEYS:
            missing = VALID_QUESTION_KEYS - keys
            raise ValueError(f"Missing question keys: {', '.join(sorted(missing))}")
        return self
```

### Response Schemas

```
class OnboardingResponse(BaseModel):
    """Response for POST /onboarding/complete."""

    onboarding_completed: bool
    memories_seeded: int
```

---

## 6. Router Registration

### Onboarding Router

A new router in `backend/app/routes/onboarding.py`, registered under `/api/v1/onboarding`:

```python
router = APIRouter()

@router.post("/complete", response_model=OnboardingResponse)
async def complete_onboarding(
    body: OnboardingRequest,
    profile: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingResponse:
    service = OnboardingService(db)
    return await service.complete_onboarding(profile=profile, answers=body.answers)
```

In `main.py`:

```python
from app.routes import onboarding

app.include_router(onboarding.router, prefix="/api/v1/onboarding", tags=["onboarding"])
```

---

## 7. Test Requirements

### Route Tests (`backend/tests/test_onboarding_routes.py`)

These tests use the FastAPI test client. The `get_current_user` dependency is overridden to return a fake Profile. Claude and Mem0 calls are mocked.

| # | Scenario | Expected |
|---|----------|----------|
| R1 | POST /onboarding/complete with all 7 valid answers | 200, `{"onboarding_completed": true, "memories_seeded": 7}` |
| R2 | POST /onboarding/complete when onboarding already completed | 409, `{"detail": "Onboarding already completed"}` |
| R3 | POST /onboarding/complete with missing question keys (only 5 of 7) | 422 (Pydantic validation) |
| R4 | POST /onboarding/complete with duplicate question keys | 422 (Pydantic validation) |
| R5 | POST /onboarding/complete with invalid question key | 422 (Pydantic validation) |
| R6 | POST /onboarding/complete with empty answer string | 422 (Pydantic validation) |
| R7 | POST /onboarding/complete with answer exceeding 500 chars | 422 (Pydantic validation) |
| R8 | POST /onboarding/complete without auth header | 401 |
| R9 | POST /onboarding/complete when Claude Haiku fails | 503, `{"detail": "AI service temporarily unavailable"}` |
| R10 | POST /onboarding/complete when Mem0 fails | 503, `{"detail": "AI service temporarily unavailable"}` |
| R11 | POST /onboarding/complete updates profile name when preferred_name differs | 200, profile.name updated to preferred_name |
| R12 | POST /onboarding/complete does not update profile name when preferred_name matches | 200, profile.name unchanged |
| R13 | POST /onboarding/complete when Claude returns unparseable response | 200, fallback memories used, `memories_seeded: 7` |
| R14 | POST /onboarding/complete with answer that is only whitespace | 422 (Pydantic validation -- blank after strip) |

### Service Tests (`backend/tests/test_onboarding_service.py`)

These tests unit-test the `OnboardingService` class directly. The database session, Claude, and Mem0 are mocked.

| # | Scenario | Expected |
|---|----------|----------|
| S1 | `complete_onboarding()` raises 409 when `profile.onboarding_completed` is true | HTTPException(409) raised before any external calls |
| S2 | `complete_onboarding()` calls Claude Haiku with the correct prompt containing all 7 answers | AsyncAnthropic called once with model=settings.claude_haiku_model |
| S3 | `complete_onboarding()` parses Haiku JSON response into memory list | Correct list of 7 strings extracted |
| S4 | `complete_onboarding()` falls back to deterministic format when Haiku returns invalid JSON | 7 fallback-formatted memories generated |
| S5 | `complete_onboarding()` calls Mem0 add() with user_id only (no agent_id) | Mem0 called with correct user_id, no agent_id parameter |
| S6 | `complete_onboarding()` sets `profile.onboarding_completed = True` after Mem0 success | Profile attribute updated |
| S7 | `complete_onboarding()` updates `profile.name` when preferred_name differs | Profile name changed |
| S8 | `complete_onboarding()` does NOT update `profile.name` when preferred_name matches (case-insensitive) | Profile name unchanged |
| S9 | `complete_onboarding()` calls `db.commit()` exactly once on success | Commit called once |
| S10 | `complete_onboarding()` raises 503 when Claude Haiku fails | HTTPException(503), no DB changes |
| S11 | `complete_onboarding()` raises 503 when Mem0 add() fails | HTTPException(503), no DB changes |
| S12 | `complete_onboarding()` does NOT set onboarding_completed if Mem0 fails | Profile.onboarding_completed remains False |
| S13 | `_convert_answers_to_memories()` sends correct prompt format to Haiku | Prompt contains all 7 answer values in the correct format |
| S14 | `_fallback_memories()` generates 7 correctly formatted strings | Each string matches the fallback template |

### Schema Tests (`backend/tests/test_onboarding_schemas.py`)

| # | Scenario | Expected |
|---|----------|----------|
| T1 | `OnboardingRequest` with all 7 valid keys and non-empty answers | Valid, no errors |
| T2 | `OnboardingRequest` with 6 answers (missing one key) | ValidationError |
| T3 | `OnboardingRequest` with 8 answers (duplicate key) | ValidationError |
| T4 | `OnboardingRequest` with an invalid question_key | ValidationError |
| T5 | `OnboardingAnswer` with answer that is whitespace only | ValidationError |
| T6 | `OnboardingAnswer` with answer exceeding 500 chars | ValidationError |
| T7 | `OnboardingAnswer.strip_answer()` trims whitespace | "  Alex  " becomes "Alex" |
| T8 | `OnboardingResponse` serializes correctly | `{"onboarding_completed": true, "memories_seeded": 7}` |

### How to Mock Claude Haiku

```python
from unittest.mock import AsyncMock, patch, MagicMock

mock_response = MagicMock()
mock_response.content = [MagicMock(text='["Prefers to be called Alex", "Works as a software engineer"]')]

mock_client = AsyncMock()
mock_client.messages.create = AsyncMock(return_value=mock_response)

with patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls:
    mock_cls.return_value = mock_client
    # ... run test
```

### How to Mock Mem0

```python
from unittest.mock import patch, MagicMock

mock_client = MagicMock()
mock_client.add.return_value = None  # add() returns None on success

with patch("app.services.onboarding_service.MemoryClient") as mock_cls:
    mock_cls.return_value = mock_client
    # ... run test

# For Mem0 failure:
mock_client.add.side_effect = Exception("Mem0 connection refused")
```

All Mem0 calls are wrapped in `asyncio.to_thread()`. The mock's methods are called synchronously within the thread pool, so standard `MagicMock` is sufficient.

### How to Mock the Database

Follow the same pattern as P01-04 and P01-08. Override `get_current_user` for route tests to return a Profile with `onboarding_completed=False`. For service tests, pass a mock `AsyncSession` directly to `OnboardingService(db=mock_db)`.

---

## 8. File Manifest

Every file to be created or modified, grouped by purpose.

### Route Handler

```
Backend:
  CREATE  backend/app/routes/onboarding.py
```

Contains a single router with one route function (`complete_onboarding`). Delegates to `OnboardingService`.

### Service Layer

```
Backend:
  CREATE  backend/app/services/onboarding_service.py
```

Contains the `OnboardingService` class with `complete_onboarding()` and private helpers: `_convert_answers_to_memories()` (Claude Haiku call), `_fallback_memories()` (deterministic fallback), `_seed_memories()` (Mem0 add call).

### Pydantic Schemas

```
Backend:
  CREATE  backend/app/schemas/onboarding.py
```

Contains `OnboardingAnswer`, `OnboardingRequest`, `OnboardingResponse`, and the `VALID_QUESTION_KEYS` constant.

### Application Wiring

```
Backend:
  MODIFY  backend/app/main.py
```

Add import for `onboarding` module and register the router:

```python
from app.routes import auth, characters, chat, health, memories, onboarding

app.include_router(onboarding.router, prefix="/api/v1/onboarding", tags=["onboarding"])
```

### Tests

```
Backend:
  CREATE  backend/tests/test_onboarding_routes.py
  CREATE  backend/tests/test_onboarding_service.py
  CREATE  backend/tests/test_onboarding_schemas.py
```

### Documentation (Pipeline)

```
Shared:
  CREATE  shared/feature-specs/onboarding-endpoint.md          (this file)
  CREATE  docs/pipeline/onboarding-endpoint-architect.handoff.md
```

### Summary

| Action | Count |
|--------|-------|
| CREATE | 6 |
| MODIFY | 1 |
| DELETE | 0 |
| **Total** | **7** |

### Files NOT Modified

- `backend/app/config.py` -- `anthropic_api_key`, `claude_haiku_model`, and `mem0_api_key` already exist. No new config values needed.
- `backend/app/dependencies.py` -- Uses the existing `get_current_user` and `get_db`. No changes needed.
- `backend/app/models/` -- No model changes. Existing Profile and Character models are used as-is.
- `backend/app/schemas/__init__.py` -- Not modified (follows direct import pattern from existing code).
- `backend/app/services/__init__.py` -- Not modified (follows direct import pattern from existing code).
- `backend/requirements.txt` -- `anthropic` and `mem0ai` are already dependencies.
- `backend/app/db/session.py` -- No changes. The endpoint uses the request-scoped session from `get_db`, not `AsyncSessionLocal`.
- `backend/app/routes/auth.py` -- Not modified. Registration still sets `onboarding_completed=false`.
- `backend/app/services/auth_service.py` -- Not modified. The default companion character and profile are created during registration unchanged.
- `backend/app/services/chat_service.py` -- Not modified. Claude and Mem0 patterns are referenced but the code is not changed.

---

## 9. Acceptance Criteria

1. Given an authenticated user with `onboarding_completed=false` and all 7 valid Q&A answers, when the client sends `POST /api/v1/onboarding/complete`, then the response is HTTP 200 with `{"onboarding_completed": true, "memories_seeded": N}` where N is a positive integer.

2. Given a successful onboarding completion, when the profile is inspected in the database, then `onboarding_completed` is `true`.

3. Given a successful onboarding completion, when Mem0 is queried with the user's `mem0_user_id` (no agent_id), then the seeded memories are returned. Each memory is a structured, third-person factual statement derived from the onboarding answers.

4. Given an authenticated user with `onboarding_completed=true`, when the client sends `POST /api/v1/onboarding/complete`, then the response is HTTP 409 with detail "Onboarding already completed".

5. Given a request with fewer than 7 answers or missing question keys, when the client sends `POST /api/v1/onboarding/complete`, then the response is HTTP 422 with a Pydantic validation error indicating the missing keys.

6. Given a request with duplicate question keys, when the client sends `POST /api/v1/onboarding/complete`, then the response is HTTP 422.

7. Given a request with an invalid question_key value, when the client sends `POST /api/v1/onboarding/complete`, then the response is HTTP 422.

8. Given a request with an answer that is empty or whitespace-only, when the client sends `POST /api/v1/onboarding/complete`, then the response is HTTP 422.

9. Given a `preferred_name` answer that differs from the current `profiles.name`, when onboarding completes successfully, then `profiles.name` is updated to the preferred name value.

10. Given that Claude Haiku is unavailable, when the client sends `POST /api/v1/onboarding/complete`, then the response is HTTP 503 with detail "AI service temporarily unavailable" and `onboarding_completed` remains `false`.

11. Given that Mem0 is unavailable, when the client sends `POST /api/v1/onboarding/complete`, then the response is HTTP 503 with detail "AI service temporarily unavailable" and `onboarding_completed` remains `false`.

12. Given that Claude Haiku returns a non-JSON or malformed response, when the client sends `POST /api/v1/onboarding/complete`, then the service falls back to deterministic memory formatting and the endpoint returns 200 with the fallback memories seeded.

13. Given no `Authorization` header, when the client sends `POST /api/v1/onboarding/complete`, then the response is HTTP 401.

14. Given the `OnboardingService` code, when a developer inspects it, then all Claude Haiku calls use `AsyncAnthropic` and all Mem0 calls are wrapped in `asyncio.to_thread()`.

15. Given the route handler code, when a developer inspects it, then all business logic is in `OnboardingService` and the route handler only calls the service method and returns the response.

16. Given the backend test suite, when a developer runs `pytest` on the new test files, then all tests pass with exit code 0.

---

## 10. Design Decisions and Rationale

### Why Claude Haiku converts Q&A to structured memories

Raw user answers ("I wake up at 6:30, love morning runs") are not ideal for Mem0 storage. Claude Haiku converts them into concise, third-person factual statements ("Morning person, wakes up at 6:30") that Mem0 can index and search more effectively. Haiku is chosen over Sonnet because this is a simple text transformation task that does not require complex reasoning, and Haiku is significantly cheaper and faster.

### Why a single Haiku call (not 7 separate calls)

Sending all 7 Q&A pairs in one prompt is more efficient than 7 separate API calls. It reduces latency (one round-trip instead of 7), reduces cost (one prompt overhead instead of 7), and allows Haiku to see the full context of the user when generating memories.

### Why a deterministic fallback exists

If Claude Haiku is temporarily down or returns malformed output, the onboarding flow should not block the user. The deterministic fallback produces functional (if less polished) memories that still allow the AI companion to personalize conversations. The user is not aware of which path was used.

### Why onboarding memories are seeded as global (no agent_id)

Per `docs/05-ai-bellek.md`, global memories contain "basic user information visible to all characters" -- name, profession, goals, sleep schedule, etc. Onboarding answers are exactly this category. If we seeded them with the companion's `agent_id`, only the companion character would see them in character-scoped searches. By seeding globally, all characters (English Teacher, Fitness Coach, etc.) benefit from the onboarding information.

### Why the endpoint returns 409 for already-completed onboarding

Re-running onboarding would add duplicate memories to Mem0 (Mem0 may or may not deduplicate). More importantly, it would be confusing for the user experience. The mobile client checks `onboarding_completed` from the login/register response and only shows the onboarding flow when it is `false`. The 409 is a safety net for race conditions or misbehaving clients.

### Why the profile name is updated from preferred_name

During registration, the user provides their full name. During onboarding, the "What should I call you?" question may yield a nickname ("Alex" instead of "Alexander"). Updating `profiles.name` ensures the AI uses the preferred name everywhere, not just in Mem0 memories.

### Why Mem0 seeding happens before the DB flag update

If Mem0 fails, the flag stays `false` and the client can retry. If the DB flag update fails after Mem0 succeeds, the memories are already in Mem0 (harmless duplicates on retry thanks to Mem0's deduplication) and the next retry will succeed in setting the flag. This ordering maximizes retry safety.

### Why not use a background task for Mem0 seeding

Unlike the chat flow (P01-06) where the user should not wait for memory persistence, the onboarding flow is a one-time operation where the user expects to wait briefly. The mobile client shows a loading state during onboarding. Running Mem0 seeding in the foreground ensures we can report success/failure accurately and keeps the retry logic simple.

---

## 11. Notes for Developers

### For backend-dev

- **Start with schemas** (`app/schemas/onboarding.py`), then the service (`app/services/onboarding_service.py`), then the route (`app/routes/onboarding.py`), then wire up in `main.py`.

- **Claude Haiku call pattern**: Follow the same pattern as `ChatService._extract_intent()` in `chat_service.py` (lines 473-517). Use `AsyncAnthropic` (not `asyncio.to_thread` for Claude -- the Anthropic SDK has native async support via `AsyncAnthropic`). Set `max_tokens=512` (the response is a small JSON array).

- **Mem0 add() call pattern**: Follow the pattern in `chat_service.py` `_persist_exchange()` (lines 584-596). Use `MemoryClient` wrapped in `asyncio.to_thread()`. The key difference: pass `user_id` only (no `agent_id`) for global scope.

- **Mem0 add() input format**: The `client.add()` method can accept a string or a list of message dicts. For onboarding, the simplest approach is to pass the list of memory strings joined with newlines as a single string, or pass each memory as a separate `{"role": "user", "content": text}` dict in a list. Test both approaches to see which produces better Mem0 memory entries. The recommended approach is to pass each memory as a separate add() call or concatenate them into one add() call -- verify with the Mem0 SDK docs which approach produces distinct, searchable memories.

- **Haiku JSON parsing**: Use `json.loads()` on the Haiku response text. Strip any markdown code block delimiters (` ```json ` and ` ``` `) before parsing -- LLMs sometimes wrap JSON in code blocks. If parsing fails, log a warning and use `_fallback_memories()`.

- **Profile update for preferred_name**: Extract the answer with `question_key == "preferred_name"` before the Haiku call. Compare case-insensitively with `profile.name`. If different, update `profile.name` in the same DB transaction.

- **Router prefix**: Register the router with `prefix="/api/v1/onboarding"` in `main.py`. The route function uses the relative path: `@router.post("/complete")`.

- **Existing import in main.py**: The current `from app.routes import auth, characters, chat, health, memories` line needs to be extended with `onboarding`.

- **No new config values needed**: `anthropic_api_key`, `claude_haiku_model`, and `mem0_api_key` all exist in `config.py`. Use `settings.claude_haiku_model` for the Haiku model name.

### For backend-tester

- **Mock Claude at the import level**: Patch `app.services.onboarding_service.AsyncAnthropic` to return a mock client with a mock `messages.create()` method that returns a mock response containing a JSON array of 7 strings.

- **Mock Mem0 at the import level**: Patch `app.services.onboarding_service.MemoryClient` to return a mock client. Verify `add()` is called with the correct `user_id` parameter and no `agent_id` parameter.

- **Test the 409 path**: Set `profile.onboarding_completed = True` in the mock profile and verify the endpoint returns 409 without making any Claude or Mem0 calls.

- **Test the fallback path**: Make the mock Haiku response return non-JSON text (e.g., `"Here are the memories:\n- Prefers to be called Alex"`) and verify the service uses fallback formatting and still returns 200.

- **Test profile name update**: Provide a `preferred_name` answer that differs from `profile.name` and verify `profile.name` is updated in the DB.

- **Test Pydantic validation thoroughly**: Test missing keys, duplicate keys, invalid keys, empty answers, whitespace-only answers, and answers exceeding 500 characters.

- **Verify ordering**: Ensure that when Mem0 fails, `onboarding_completed` is NOT set to `true`. Use mock side effects to simulate Mem0 failure after successful Haiku response.
