# Onboarding Endpoint

> Completes the first-launch onboarding flow by converting 7 Q&A answers into structured Mem0 memories via Claude Haiku, seeding them as global memories visible to all characters, and marking the user profile as onboarded.

**Status**: Released
**Added in**: Phase 1 (P01-09)
**Platforms**: Backend
**GitHub Issue**: #11

---

## Overview

When a new user registers with Ember, the AI companion has zero knowledge about them. The first few conversations would be generic and impersonal. The onboarding endpoint solves this by collecting answers to 7 predefined questions during first launch and converting those answers into structured, third-person memory statements that Mem0 can index and search. This way, every character -- not just the default General Friend -- can personalize conversations from the very first message.

The mobile client presents the onboarding questions after registration and submits all 7 answers in a single `POST /api/v1/onboarding/complete` request. The backend uses Claude Haiku to transform raw user answers (e.g., "I wake up at 6:30, love morning runs") into concise factual statements (e.g., "Morning person, wakes up at 6:30"). These structured memories are seeded into Mem0 as global memories (no `agent_id`), making them visible to all characters through the two-layer memory search in the chat flow. The profile's `onboarding_completed` flag is then set to `true` so the client does not show the onboarding flow again.

If Claude Haiku is temporarily unavailable or returns malformed output, a deterministic fallback formatter generates functional memories without blocking the user. The endpoint is retry-safe: if Mem0 or Haiku fails, the `onboarding_completed` flag stays `false` and the client can resubmit.

---

## Architecture

### How It Works (Data Flow)

1. The mobile client presents 7 onboarding questions to the user after registration and collects their answers.
2. The client sends `POST /api/v1/onboarding/complete` with all 7 Q&A pairs in the request body, along with `Authorization: Bearer <jwt>`.
3. The route handler resolves the authenticated user via the `get_current_user` dependency, providing the `Profile` with `onboarding_completed`, `mem0_user_id`, and `name`.
4. The service checks `profile.onboarding_completed`. If already `true`, it returns HTTP 409 Conflict immediately (no external calls are made).
5. The service builds a prompt containing all 7 Q&A pairs and sends a single request to Claude Haiku via `AsyncAnthropic` (native async, no thread wrapping).
6. Haiku returns a JSON array of 7 third-person memory statements. The service strips any markdown code block delimiters and parses the JSON.
7. If Haiku returns unparseable output, the service falls back to deterministic template-based formatting (see Fallback Memory Formatting below).
8. The service seeds the memory statements into Mem0 by calling `client.add()` with `user_id` only (no `agent_id`), wrapped in `asyncio.to_thread()` because the Mem0 SDK is synchronous. This stores them as global memories.
9. The service updates `profile.onboarding_completed = True`. If the `preferred_name` answer differs from `profile.name` (case-insensitive comparison), the profile name is updated as well.
10. The service commits the DB transaction and returns `{"onboarding_completed": true, "memories_seeded": N}`.

### Memory Seeding Strategy

Onboarding memories are seeded as **global memories** (`user_id` only, no `agent_id`). This is a deliberate design decision based on `docs/05-ai-bellek.md`:

- Global memories contain "basic user information visible to all characters" -- name, profession, goals, sleep schedule, etc.
- Onboarding answers are exactly this category of information.
- If memories were scoped to the companion character's `agent_id`, other characters (English Teacher, Fitness Coach, etc.) would not see them in their character-scoped search.
- The two-layer memory search in the chat flow (P01-06) searches both global (`user_id` only) and character-scoped (`user_id` + `agent_id`). Global memories are found by the global search path for all characters.

The memories are passed to Mem0 as a list of `{"role": "user", "content": text}` dicts. The Mem0 SDK extracts and stores individual memory entries from this content.

### Retry Safety (Operation Ordering)

The order of operations is designed for safe retries:

1. **Claude Haiku call** (stateless) -- can be retried any number of times with no side effects.
2. **Mem0 seeding** (idempotent) -- Mem0 deduplicates, so reseeding the same memories is harmless.
3. **DB flag update** (`onboarding_completed = true`) -- only set after both external calls succeed.

If Mem0 fails at step 2, the flag stays `false` and the client retries the entire flow. If the DB commit fails at step 3, Mem0 already has the memories (harmless duplicates on retry) and the next retry sets the flag.

### Claude Haiku Memory Conversion

A single Haiku call converts all 7 answers at once (not 7 separate calls). This reduces latency, cost, and gives Haiku the full context. The prompt instructs Haiku to output a JSON array of 7 third-person factual statements, each under 100 characters.

The service uses `AsyncAnthropic` (the Anthropic SDK's native async client) with `max_tokens=512` and `model=settings.claude_haiku_model`.

### Fallback Memory Formatting

If Haiku returns a response that cannot be parsed as a JSON array of non-empty strings, the service uses a deterministic template-based fallback:

| Question Key | Fallback Format |
|-------------|----------------|
| `preferred_name` | `"Prefers to be called {answer}"` |
| `occupation` | `"Works as {answer}"` |
| `daily_rhythm` | `"Daily rhythm: {answer}"` |
| `health_goal` | `"Health/fitness goal: {answer}"` |
| `stress_management` | `"Stress management: {answer}"` |
| `sleep_schedule` | `"Sleep schedule: {answer}"` |
| `communication_style` | `"Communication preference: {answer}"` |

The fallback memories are less natural-sounding but fully functional for Mem0 search. The user is not aware of which path was used.

### Database Tables Involved

| Table | Operation | Notes |
|-------|-----------|-------|
| `profiles` | UPDATE | Sets `onboarding_completed = true`; optionally updates `name` if preferred name differs |
| `characters` | (none) | Not accessed by this feature. The default companion character already exists from registration (P01-04). |

No new tables or columns are created by this feature.

---

## API Reference

### POST /api/v1/onboarding/complete

Completes the user onboarding by converting Q&A answers into structured Mem0 memories and marking the profile as onboarded.

**Auth**: Bearer JWT required
**Content-Type**: `application/json`

**Request Body**:

```json
{
  "answers": [
    { "question_key": "preferred_name", "answer": "Alex" },
    { "question_key": "occupation", "answer": "Software engineer at a startup" },
    { "question_key": "daily_rhythm", "answer": "Morning person, I wake up at 6:30" },
    { "question_key": "health_goal", "answer": "Lose 10 kg and run a half marathon" },
    { "question_key": "stress_management", "answer": "I go for walks and listen to podcasts" },
    { "question_key": "sleep_schedule", "answer": "Usually 11 PM to 6:30 AM" },
    { "question_key": "communication_style", "answer": "I want someone who checks in on me but doesn't overwhelm me" }
  ]
}
```

**Request Fields**:

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `answers` | array | yes | Exactly 7 items |
| `answers[].question_key` | string | yes | Must be one of the 7 valid keys (see below) |
| `answers[].answer` | string | yes | Min 1 char, max 500 chars; whitespace-trimmed; blank-after-trim is rejected |

**Valid `question_key` values**:

| Key | Onboarding Question |
|-----|---------------------|
| `preferred_name` | "What should I call you?" |
| `occupation` | "What do you do for work?" |
| `daily_rhythm` | "Are you a morning person or a night owl?" |
| `health_goal` | "What are your health/fitness goals?" |
| `stress_management` | "What do you do for stress management?" |
| `sleep_schedule` | "What is your sleep schedule like?" |
| `communication_style` | "What kind of friendship do you expect from me?" |

**Validation rules**:
- All 7 question keys must be present. No duplicates, no missing keys. Order does not matter.
- Each answer must be non-empty after whitespace trimming.
- Pydantic validates `max_length=500` on the raw input string before the `strip()` field validator runs. An answer of 498 chars + 2 trailing spaces (500 total) is accepted, but 499 chars + 2 trailing spaces (501 total) is rejected before stripping.

**Response 200 OK**:

```json
{
  "onboarding_completed": true,
  "memories_seeded": 7
}
```

| Response Field | Type | Notes |
|----------------|------|-------|
| `onboarding_completed` | boolean | Always `true` on success |
| `memories_seeded` | integer | Number of memory statements seeded to Mem0. Typically 7 but may vary if Haiku generates more or fewer statements. |

**Error Responses**:

| Status | Detail | When |
|--------|--------|------|
| 401 | `"Invalid or expired token"` | Missing or invalid JWT |
| 409 | `"Onboarding already completed"` | `profiles.onboarding_completed` is already `true` |
| 422 | Standard FastAPI validation error | Missing keys, duplicate keys, invalid key, empty/blank answer, answer > 500 chars |
| 503 | `"AI service temporarily unavailable"` | Claude Haiku or Mem0 API error |

**Notes**:
- This endpoint is retry-safe. If Claude or Mem0 fails (503), the `onboarding_completed` flag remains `false` and the client can retry.
- If the `preferred_name` answer differs from `profiles.name` (case-insensitive, whitespace-trimmed comparison), the profile name is updated in the same transaction. This lets a user who registered as "Alexander" be called "Alex" by the companion.
- The 409 response is a safety net for race conditions or misbehaving clients. The mobile client checks `onboarding_completed` from the login/register response and only shows the onboarding flow when it is `false`.

---

## Configuration

No new configuration values were introduced for this feature. All required settings already exist from prior features (P01-01, P01-06).

| Setting | Source | Description |
|---------|--------|-------------|
| `anthropic_api_key` | `app/config.py` (AWS Secrets Manager) | API key for the Anthropic Claude API. Used by `AsyncAnthropic`. |
| `claude_haiku_model` | `app/config.py` | Model identifier for Claude Haiku (e.g., `claude-haiku-4-5-20241022`). |
| `mem0_api_key` | `app/config.py` (AWS Secrets Manager) | API key for Mem0.ai cloud. Used by `MemoryClient`. |

No new packages were added. The `anthropic` and `mem0ai` Python packages were already dependencies from P01-06 (chat-streaming).

---

## Files

| File | Role |
|------|------|
| `backend/app/routes/onboarding.py` | Route handler. Defines a single router with one endpoint (`POST /complete`). Delegates all business logic to `OnboardingService`. |
| `backend/app/services/onboarding_service.py` | `OnboardingService` class with 5 methods: `complete_onboarding()` (public entry point), `_convert_answers_to_memories()` (Haiku call), `_parse_haiku_response()` (JSON parsing + fallback trigger), `_fallback_memories()` (deterministic formatter), `_seed_memories()` (Mem0 add call). |
| `backend/app/schemas/onboarding.py` | `OnboardingAnswer`, `OnboardingRequest`, `OnboardingResponse` Pydantic models, plus the `VALID_QUESTION_KEYS` frozenset constant. |
| `backend/app/main.py` | Modified to import `onboarding` module and register the router at `/api/v1/onboarding`. |

### Router Registration

```python
# In main.py:
from app.routes import auth, characters, chat, health, memories, onboarding

app.include_router(onboarding.router, prefix="/api/v1/onboarding", tags=["onboarding"])
```

---

## Testing

### Coverage Summary

| File | Tests (original + extended) | Line Coverage | Branch Coverage |
|------|----------------------------|---------------|-----------------|
| `test_onboarding_schemas.py` + `_extended.py` | 15 + 31 = 46 | 100% | 100% |
| `test_onboarding_service.py` + `_extended.py` | 18 + 33 = 51 | 100% | 100% |
| `test_onboarding_routes.py` + `_extended.py` | 16 + 18 = 34 | 100% | 100% |
| **Total** | **131 passed, 0 failed** | **100%** (all 3 source files) | **100%** |

Full backend suite after this feature: 1193 passed, 0 failed, 0 skipped.

### Key Test Scenarios

**Route tests** cover the complete HTTP integration: successful onboarding (200), already-completed guard (409), all Pydantic validation edge cases (422), missing auth (401), Claude Haiku failure (503), Mem0 failure (503), fallback on unparseable Haiku response (200), profile name update behavior, response content-type verification, and method-not-allowed (405 for GET).

**Service tests** verify the business logic in isolation: idempotency guard (409 before external calls), correct Haiku prompt construction, JSON parsing of Haiku response, fallback trigger on malformed JSON, Mem0 called with `user_id` only (no `agent_id`), profile flag and name updates, DB commit ordering, 503 on Haiku/Mem0 failures, and the `HTTPException` re-raise path (line 148) that ensures HTTP errors from the Haiku call path are not wrapped as 503.

**Schema tests** verify Pydantic validation: all 7 keys required, duplicate key detection, invalid keys, whitespace-only answers, boundary lengths (1 char, 500 chars, 501 chars), Unicode/CJK characters, special characters, and the `VALID_QUESTION_KEYS` constant.

### Running Tests

Onboarding tests only:

```bash
cd backend && python -m pytest tests/test_onboarding_schemas.py tests/test_onboarding_service.py tests/test_onboarding_routes.py -v
```

All onboarding tests (including extended edge cases):

```bash
cd backend && python -m pytest tests/test_onboarding_schemas.py tests/test_onboarding_schemas_extended.py tests/test_onboarding_service.py tests/test_onboarding_service_extended.py tests/test_onboarding_routes.py tests/test_onboarding_routes_extended.py -v
```

Full backend suite:

```bash
cd backend && python -m pytest tests/ -v --ignore=tests/test_migration.py
```

---

## Known Limitations

- **No partial onboarding**: All 7 answers must be submitted together in a single request. There is no "save progress" endpoint. If the user closes the app mid-onboarding, answers are lost and must be re-entered.
- **No re-onboarding**: Once `onboarding_completed` is `true`, the endpoint returns 409. There is no way to re-do onboarding or update the seeded memories through this endpoint. Users can manage individual memories via the memory endpoints (P01-08).
- **No mobile UI in this feature**: The mobile client owns the question presentation UI. This feature only provides the backend endpoint that the client submits answers to.
- **Mem0 deduplication is assumed**: On retry after a DB commit failure, the same memories may be submitted to Mem0 again. The implementation assumes Mem0 deduplicates or handles duplicates gracefully.
- **Pydantic max_length applies before strip**: The `max_length=500` constraint on answers is validated on the raw input string before the `strip()` field validator runs. This means an answer of 499 visible characters plus 2 trailing spaces (501 total) is rejected, even though the stripped content is only 499 characters.
- **Haiku "not found" detection on HTTPException re-raise**: The service re-raises `HTTPException` instances from the Haiku call path without wrapping them as 503. If a rate-limit (429) or other HTTP error propagates from the Anthropic SDK as an `HTTPException`, it is passed through with its original status code rather than being normalized to 503.

---

## Design Decisions

### Why Claude Haiku converts Q&A to structured memories

Raw user answers are conversational and not ideal for Mem0 storage and retrieval. Claude Haiku converts them into concise, third-person factual statements that Mem0 can index and search more effectively. Haiku is chosen over Sonnet because this is a simple text transformation task that does not require complex reasoning, and Haiku is significantly cheaper and faster.

### Why a single Haiku call (not 7 separate calls)

Sending all 7 Q&A pairs in one prompt reduces latency (one round-trip instead of 7), reduces cost (one prompt overhead instead of 7), and allows Haiku to see the full context of the user when generating memories.

### Why onboarding memories are seeded as global (no agent_id)

Basic user facts from onboarding -- name, profession, goals, sleep schedule -- should be available to all characters, not just the companion. Global memories are found by every character's global memory search path.

### Why onboarding runs in the foreground (not a background task)

Unlike the chat flow (P01-06) where memory persistence happens in a background task so the user does not wait, onboarding is a one-time operation where the user expects a brief loading state. Running in the foreground allows the endpoint to report success or failure accurately and keeps the retry logic simple.

### Why the profile name is updated from preferred_name

During registration, users provide their full name. During onboarding, they may answer "What should I call you?" with a nickname. Updating `profiles.name` ensures the AI uses the preferred name consistently, not just in Mem0 memories.

---

## Extending This Feature

**Adding more onboarding questions**: Add the new question key to the `VALID_QUESTION_KEYS` frozenset in `backend/app/schemas/onboarding.py`. Add a corresponding fallback template to `_FALLBACK_TEMPLATES` in `backend/app/services/onboarding_service.py`. Update the `_MEMORY_CONVERSION_PROMPT` to include the new Q&A pair. Update the `min_length` and `max_length` constraints on the `answers` field in `OnboardingRequest`. Update all tests that assert on the count of required keys.

**Allowing re-onboarding**: Remove or modify the 409 guard in `OnboardingService.complete_onboarding()`. Consider clearing existing onboarding-related memories from Mem0 before reseeding to avoid duplicates.

**Seeding character-scoped memories**: To seed memories that are visible only to a specific character, pass `agent_id=character.mem0_agent_id` in the `_seed_memories()` call alongside `user_id`. This would change the memory scope from global to character-specific.

**Adding onboarding status to the profile API**: The mobile client currently checks `onboarding_completed` from the login/register response. If a separate profile endpoint is added, include this flag in the response schema.

---

## Related Documentation

- [AI Memory System](../05-ai-bellek.md) -- Mem0 integration design, memory isolation, and the 7 onboarding questions
- [Chat Streaming](./chat-streaming.md) -- P01-06, where the two-layer memory search uses the global memories seeded here
- [Memory Endpoints](./memory-endpoints.md) -- P01-08, where users can view and delete the memories created by onboarding
- [Auth Endpoints](./auth-endpoints.md) -- P01-04, where registration creates the default companion character and profile
- [Database Schema and API Endpoints](../04-veri-api.md) -- profiles and characters table definitions
