# Feature Spec: P1.5-06 -- OpenAPI Specs

**Feature ID**: P1.5-06
**Phase**: 1.5
**Layer**: backend
**GitHub Issue**: #88
**Date**: 2026-03-13
**Author**: architect

---

## 1. Overview

### What This Feature Does

This feature creates OpenAPI 3.1 YAML specification files in `shared/api-contracts/` that document every implemented API endpoint. These files become the single source of truth for mobile clients when building their networking layers. Each spec file covers request/response schemas, authentication requirements, error codes, path parameters, query parameters, and SSE streaming behavior.

Additionally, a validation script is added that compares the hand-written YAML specs against the FastAPI auto-generated OpenAPI JSON schema. This ensures the YAML specs never drift from the actual implementation. The validation runs in CI on every backend change.

### Why It Exists

Mobile developers (iOS and Android) currently must read Python route handlers and Pydantic schemas to understand the API contract. This is error-prone and slow. A well-structured OpenAPI spec provides:

1. A language-agnostic, machine-readable contract that mobile developers can reference without reading Python.
2. An input for future code generation (Retrofit interfaces for Android, URLSession clients for iOS).
3. A drift-detection mechanism: if a backend developer changes an endpoint without updating the spec, CI fails.
4. A foundation for API documentation (Swagger UI, Redoc) that can be exposed for debugging.

### Dependencies

- **Requires**: P01-10 (media-upload) -- the last Phase 1 endpoint. All endpoints must be implemented before they can be documented.
- **Requires**: P1.5-01 (rate-limiting-middleware) -- 429 responses and rate limit headers must be documented.

### What This Feature Does NOT Do

- It does not generate client code from the specs. Code generation is a future concern.
- It does not replace `docs/04-veri-api.md`. That document remains the human-readable architectural reference in Turkish. The OpenAPI specs are the machine-readable English contract.
- It does not add new endpoints or change existing endpoint behavior.
- It does not expose a Swagger UI or Redoc page in production. That is a separate concern (could be enabled in dev mode via FastAPI's built-in docs).

---

## 2. Data Models

### No New Tables

This feature does not create or alter any database tables. It is purely a documentation and validation concern.

### No Mem0 Operations

This feature does not interact with Mem0.

---

## 3. OpenAPI File Organization

### Directory Structure

```
shared/api-contracts/
  ember-api.yaml            # Root spec file: info, servers, security, references
  paths/
    auth.yaml               # /auth/register, /auth/login, /auth/refresh
    characters.yaml         # /characters (GET, POST), /characters/{id} (PUT, DELETE)
    chat.yaml               # /characters/{id}/messages (POST SSE, GET paginated)
    memories.yaml           # /memories (GET), /characters/{id}/memories (GET, DELETE, DELETE all)
    media.yaml              # /media/upload-url (POST)
    onboarding.yaml         # /onboarding/complete (POST)
    profile.yaml            # /profile (GET, PUT), /profile/account (DELETE)
    health.yaml             # /health (GET)
  schemas/
    auth.yaml               # RegisterRequest, LoginRequest, RefreshRequest, AuthResponse, etc.
    character.yaml          # CreateCharacterRequest, UpdateCharacterRequest, CharacterDetail, etc.
    chat.yaml               # SendMessageRequest, MessageItem, MessageListResponse, SSE events
    memory.yaml             # MemoryItem, MemoryListResponse
    media.yaml              # UploadUrlRequest, UploadUrlResponse
    onboarding.yaml         # OnboardingAnswer, OnboardingRequest, OnboardingResponse
    profile.yaml            # ProfileResponse, ProfileUpdateRequest, AccountDeleteRequest
    health.yaml             # HealthResponse, DependencyStatus, CircuitBreakerStatus
    common.yaml             # ErrorResponse (detail), pagination envelope
```

### Why Split Files

A single monolithic YAML becomes unreadable past 500 lines. Split files let mobile developers open only the path file they care about. The root `ember-api.yaml` uses `$ref` to compose everything.

---

## 4. Root Spec File: `ember-api.yaml`

The root file must contain the following sections.

### Info

```yaml
openapi: "3.1.0"
info:
  title: Ember API
  version: "1.0.0"
  description: >
    REST API for the Ember AI companion app. All endpoints are under /api/v1/.
    Authentication uses AWS Cognito JWTs (Bearer token).
  contact:
    name: Ember Engineering
servers:
  - url: https://api.ember.com/api/v1
    description: Production
  - url: http://localhost:8000/api/v1
    description: Local development
```

### Security Schemes

```yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: AWS Cognito ID token
```

### Global Security

Most endpoints require auth. The root file sets `security: [bearerAuth: []]` globally. Individual endpoints that do NOT require auth (register, login, refresh, health) override with `security: []`.

### Path References

The root file uses `$ref` to include each path file:

```yaml
paths:
  /auth/register:
    $ref: "paths/auth.yaml#/~1auth~1register"
  /auth/login:
    $ref: "paths/auth.yaml#/~1auth~1login"
  # ... etc.
```

---

## 5. Endpoint Catalog

This section documents every endpoint that must appear in the OpenAPI specs. The spec YAML files must faithfully represent these contracts.

### 5.1 Health

**GET /health**

- Auth: none (override global security with `security: []`)
- Query params: `check_dependencies` (boolean, default false)
- Response 200:
  ```
  { status: string, version: string, dependencies?: DependencyStatus, circuit_breaker?: CircuitBreakerReport }
  ```
- DependencyStatus: `{ database: string, mem0: string, claude: string }`
- CircuitBreakerReport: `{ mem0: CircuitBreakerStatus }`
- CircuitBreakerStatus: `{ state: string, failure_count: integer, last_failure_at: string|null, last_success_at: string|null, retry_queue_size: integer, cache_entries: integer }`

### 5.2 Auth

**POST /auth/register**

- Auth: none
- Request body: `{ email: string (email format), password: string (minLength 8), name: string (minLength 1, maxLength 100) }`
- Response 201: `AuthResponse { token: string, refresh_token: string, user: UserResponse }`
- UserResponse: `{ id: string (uuid), email: string, name: string, onboarding_completed: boolean, subscription_tier: string, preferred_language: string, timezone: string, avatar_url: string|null, created_at: string (date-time) }`
- Response 409: `{ detail: string }` -- email already exists
- Response 422: `{ detail: [...] }` -- Pydantic validation errors

**POST /auth/login**

- Auth: none
- Request body: `{ email: string (email format), password: string (minLength 1) }`
- Response 200: `AuthResponse`
- Response 401: `{ detail: string }` -- invalid credentials

**POST /auth/refresh**

- Auth: none
- Request body: `{ refresh_token: string (minLength 1) }`
- Response 200: `RefreshResponse { token: string }`
- Response 401: `{ detail: string }` -- invalid or expired refresh token

### 5.3 Characters

**GET /characters**

- Auth: Bearer JWT required
- Response 200: `CharacterListResponse { characters: CharacterListItem[] }`
- CharacterListItem: `{ id: string, name: string, template: string, description: string|null, avatar_style: string, is_default: boolean, last_message_at: string|null (date-time), created_at: string (date-time) }`

**POST /characters**

- Auth: Bearer JWT required
- Request body: `CreateCharacterRequest { name: string (1-100), template: string (enum: companion, english_teacher, therapist, fitness_coach, career_coach, custom), description: string|null (max 1000, required if template=custom, forbidden otherwise) }`
- Response 201: `CharacterDetail { id: string, name: string, template: string, description: string|null, system_prompt: string, avatar_style: string, is_default: boolean, created_at: string (date-time) }`
- Response 422: validation errors

**PUT /characters/{character_id}**

- Auth: Bearer JWT required
- Path params: `character_id` (string, uuid format)
- Request body: `UpdateCharacterRequest { name?: string (1-100), system_prompt?: string (1-10000), avatar_style?: string (max 50) }` -- at least one field required
- Response 200: `CharacterDetail`
- Response 403: `{ detail: string }` -- not owner
- Response 404: `{ detail: string }` -- character not found

**DELETE /characters/{character_id}**

- Auth: Bearer JWT required
- Path params: `character_id` (string, uuid format)
- Response 204: no content
- Response 403: `{ detail: string }` -- cannot delete default character, or not owner
- Response 404: `{ detail: string }` -- character not found

### 5.4 Chat

**POST /characters/{character_id}/messages**

- Auth: Bearer JWT required
- Path params: `character_id` (string, uuid format)
- Request body: `SendMessageRequest { content: string (1-4000), media_url?: string (max 2048, must be http/https URL) }`
- Response 200: `text/event-stream` (NOT JSON)
- SSE event sequence:
  ```
  data: {"type": "chunk", "content": "text fragment"}
  data: {"type": "chunk", "content": "more text"}
  data: {"type": "action", "action": "SET_ALARM", "payload": {"time": "07:00", "label": "Wake up"}}
  data: {"type": "done", "message_id": "uuid-string"}
  ```
  On error mid-stream:
  ```
  data: {"type": "error", "message": "description"}
  ```
- SSE event schemas:
  - ChunkEvent: `{ type: "chunk", content: string }`
  - ActionEvent: `{ type: "action", action: string, payload: object }`
  - DoneEvent: `{ type: "done", message_id: string }`
  - ErrorEvent: `{ type: "error", message: string }`
- Response 403: `{ detail: string }` -- not owner
- Response 404: `{ detail: string }` -- character not found
- Note: The SSE endpoint returns `Content-Type: text/event-stream` with `Cache-Control: no-cache` and `X-Accel-Buffering: no` headers. OpenAPI cannot fully model SSE, so the response content type is documented as `text/event-stream` with a description of the event format. The SSE event schemas are defined in the schemas section for reference.

**GET /characters/{character_id}/messages**

- Auth: Bearer JWT required
- Path params: `character_id` (string, uuid format)
- Query params: `cursor` (string, optional -- base64-encoded composite cursor), `limit` (integer, default 20, min 1, max 100)
- Response 200: `MessageListResponse { items: MessageItem[], next_cursor: string|null, has_more: boolean }`
- MessageItem: `{ id: string, role: string (enum: user, assistant), content: string, media_url: string|null, metadata: object|null, created_at: string (date-time) }`
- Response 400: `{ detail: string }` -- invalid cursor format
- Response 403: `{ detail: string }` -- not owner
- Response 404: `{ detail: string }` -- character not found

### 5.5 Memories

**GET /memories**

- Auth: Bearer JWT required
- Response 200: `MemoryListResponse { memories: MemoryItem[] }`
- MemoryItem: `{ id: string, memory: string, created_at: string|null (date-time) }`

**GET /characters/{character_id}/memories**

- Auth: Bearer JWT required
- Path params: `character_id` (string, uuid format)
- Response 200: `MemoryListResponse`
- Response 403: `{ detail: string }` -- not owner
- Response 404: `{ detail: string }` -- character not found

**DELETE /characters/{character_id}/memories/{memory_id}**

- Auth: Bearer JWT required
- Path params: `character_id` (string, uuid format), `memory_id` (string)
- Response 204: no content (idempotent)
- Response 403: not owner
- Response 404: character not found

**DELETE /characters/{character_id}/memories**

- Auth: Bearer JWT required
- Path params: `character_id` (string, uuid format)
- Response 204: no content
- Response 403: not owner
- Response 404: character not found

### 5.6 Media

**POST /media/upload-url**

- Auth: Bearer JWT required
- Request body: `UploadUrlRequest { filename: string (1-255, no path separators, no .., no null bytes), content_type: string (minLength 1), type: string (enum: photo, audio, tts) }`
- Response 200: `UploadUrlResponse { upload_url: string, file_url: string }`
- Response 400: `{ detail: string }` -- unsupported content type
- Response 422: validation errors

### 5.7 Onboarding

**POST /onboarding/complete**

- Auth: Bearer JWT required
- Request body: `OnboardingRequest { answers: OnboardingAnswer[7] }` -- exactly 7 items, all keys required
- OnboardingAnswer: `{ question_key: string (enum: preferred_name, occupation, daily_rhythm, health_goal, stress_management, sleep_schedule, communication_style), answer: string (1-500) }`
- Response 200: `OnboardingResponse { onboarding_completed: boolean, memories_seeded: integer }`
- Response 409: `{ detail: string }` -- onboarding already completed
- Response 503: `{ detail: string }` -- Claude or Mem0 unavailable

### 5.8 Profile

**GET /profile**

- Auth: Bearer JWT required
- Response 200: `ProfileResponse { id: string, email: string, name: string, timezone: string, avatar_url: string|null, preferred_language: string, onboarding_completed: boolean, subscription_tier: string, subscription_expires_at: string|null (date-time), created_at: string (date-time) }`

**PUT /profile**

- Auth: Bearer JWT required
- Request body: `ProfileUpdateRequest { name?: string (1-100), timezone?: string (IANA), avatar_url?: string (https://, max 2048), preferred_language?: string (enum: en, tr) }`
- Response 200: `ProfileResponse`
- Response 422: validation errors

**DELETE /profile/account**

- Auth: Bearer JWT required
- Request body: `AccountDeleteRequest { confirmation: string }` -- must be exactly "DELETE MY ACCOUNT"
- Response 204: no content
- Response 400: `{ detail: string }` -- incorrect confirmation text

### 5.9 Common Schemas

**ErrorResponse**

All error responses use:
```yaml
ErrorResponse:
  type: object
  required: [detail]
  properties:
    detail:
      oneOf:
        - type: string
        - type: array
          items:
            type: object
            properties:
              loc:
                type: array
                items:
                  oneOf:
                    - type: string
                    - type: integer
              msg:
                type: string
              type:
                type: string
```

The `detail` field is a string for application-raised errors (HTTPException) and an array of validation error objects for Pydantic 422 responses.

**Rate Limit Headers**

All endpoints may return 429 with:
- `Retry-After` header (integer, seconds until the rate limit window resets)
- Response body: `{ detail: string }`

This should be documented as a global response component that applies to all authenticated endpoints.

---

## 6. Backend Logic

### 6.1 Validation Script: `scripts/validate-openapi.py`

The script performs drift detection between the hand-written YAML specs and the FastAPI auto-generated schema.

**How it works:**

1. Import the FastAPI `app` object from `app.main`.
2. Call `app.openapi()` to get the auto-generated OpenAPI JSON schema.
3. Load and merge the hand-written YAML specs from `shared/api-contracts/` using a YAML parser with `$ref` resolution.
4. Compare the two schemas structurally:
   - Every path in the YAML must exist in the FastAPI schema.
   - Every path in the FastAPI schema must exist in the YAML (no undocumented endpoints).
   - For each path+method, compare: request body schema (field names, types, required fields), response status codes, response schema (field names, types), query parameters (names, types, required/optional), path parameters.
5. Report differences as errors. Exit with code 1 if any differences found, 0 if specs match.

**What it does NOT compare:**

- Description text, summary, examples -- these are documentation-only and may differ.
- `operationId` values -- FastAPI auto-generates these from function names.
- Server URLs -- these are environment-specific.
- The SSE streaming endpoint response body -- FastAPI models this as `StreamingResponse` which does not produce a schema. The YAML documents the SSE event format for human consumption.

**Tolerance rules:**

- The FastAPI schema may use `anyOf` where the YAML uses `type` with `nullable` -- these are semantically equivalent in OpenAPI 3.1 and the validator must treat them as equal.
- Field ordering differences are ignored.
- Extra `422` responses in the FastAPI schema (auto-generated for all POST/PUT endpoints) are expected and not flagged if the YAML also includes them.

### 6.2 CI Integration

The validation script runs in the existing `backend-ci.yml` GitHub Actions workflow as a new step after tests pass:

```yaml
- name: Validate OpenAPI specs
  run: python scripts/validate-openapi.py
```

This step only runs when files in `backend/**` or `shared/api-contracts/**` change.

### 6.3 FastAPI OpenAPI Customization

The `create_app()` function in `main.py` should be updated to customize the auto-generated schema title and version to match the YAML specs. This is not a functional change but ensures consistency:

```python
app = FastAPI(
    title="Ember API",
    version=settings.app_version,
    # ... existing config
    openapi_tags=[
        {"name": "health", "description": "Health check and dependency status"},
        {"name": "auth", "description": "Authentication (register, login, refresh)"},
        {"name": "characters", "description": "Character CRUD"},
        {"name": "chat", "description": "Message sending (SSE) and history"},
        {"name": "memories", "description": "Mem0 memory retrieval and deletion"},
        {"name": "media", "description": "S3 presigned URL generation"},
        {"name": "onboarding", "description": "Onboarding flow completion"},
        {"name": "profile", "description": "User profile management"},
    ],
)
```

---

## 7. Test Plan

### 7.1 Validation Script Tests

**File**: `backend/tests/test_openapi_validation.py`

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Run validation script against current codebase | Exit code 0, no differences reported |
| 2 | All FastAPI paths are present in the YAML specs | No "undocumented endpoint" warnings |
| 3 | All YAML paths exist in the FastAPI schema | No "spec references non-existent path" errors |
| 4 | Request body field names match between YAML and FastAPI | No field name mismatches |
| 5 | Response status codes match | No missing or extra status codes (except tolerated 422) |
| 6 | Query parameter names and types match | No parameter mismatches |

### 7.2 YAML Syntax Tests

**File**: `backend/tests/test_openapi_yaml.py`

| # | Scenario | Expected |
|---|----------|----------|
| 1 | All YAML files parse without syntax errors | Valid YAML |
| 2 | All `$ref` pointers resolve to existing definitions | No broken references |
| 3 | The merged spec is valid OpenAPI 3.1 | Passes `openapi-spec-validator` library check |
| 4 | Every path has at least one response defined | No empty responses |
| 5 | Every authenticated endpoint has `security: [{bearerAuth: []}]` (or inherits global) | Auth coverage complete |
| 6 | Every endpoint has a `description` field | No undescribed endpoints |

### 7.3 Content Accuracy Tests

These are manual review items, not automated tests:

- Every Pydantic schema field appears in the corresponding YAML schema
- Every field constraint (minLength, maxLength, enum values, format) matches the Pydantic validator
- The SSE event documentation matches the actual event models in `app/schemas/chat.py`

---

## 8. Acceptance Criteria

1. Given the `shared/api-contracts/` directory, when a developer reads `ember-api.yaml`, then they can find a `$ref` entry for every implemented endpoint (18 endpoint+method combinations total).

2. Given the `paths/auth.yaml` file, when a developer reads the POST /auth/register spec, then they see the exact request body schema (email, password, name) with correct types, constraints (minLength, maxLength), and format (email).

3. Given the `paths/chat.yaml` file, when a developer reads the POST /characters/{character_id}/messages spec, then they find documentation of the SSE event types (chunk, action, done, error) with their field definitions.

4. Given the `paths/chat.yaml` file, when a developer reads the GET /characters/{character_id}/messages spec, then they find cursor-based pagination query params (cursor, limit) and the response envelope (items, next_cursor, has_more).

5. Given the `schemas/common.yaml` file, when a developer reads the ErrorResponse schema, then they find both the string variant (HTTPException) and the array variant (Pydantic 422 validation errors).

6. Given a clean backend checkout, when `python scripts/validate-openapi.py` is run, then it exits with code 0 and prints no errors.

7. Given a backend developer changes an endpoint's response schema without updating the YAML spec, when CI runs the validation step, then it fails with a clear error message identifying which endpoint and which field drifted.

8. Given the YAML spec files, when they are loaded by an OpenAPI 3.1 validator library, then they pass validation with zero errors.

9. Given the `ember-api.yaml` root file, when a developer inspects the security section, then all endpoints except health, register, login, and refresh require Bearer JWT auth.

10. Given any path file, when a developer inspects an authenticated endpoint, then they find 401 listed as a possible response code with the error schema.

11. Given any path file, when a developer inspects an authenticated endpoint, then they find 429 listed as a possible response code with the rate-limit error schema and `Retry-After` header.

---

## 9. File Manifest

```
Backend:
  MODIFY backend/app/main.py                        (add openapi_tags to FastAPI constructor)
  CREATE backend/scripts/validate_openapi.py         (drift detection script)
  CREATE backend/tests/test_openapi_validation.py    (validation script tests)
  CREATE backend/tests/test_openapi_yaml.py          (YAML syntax and completeness tests)

Shared:
  CREATE shared/api-contracts/ember-api.yaml         (root OpenAPI spec)
  CREATE shared/api-contracts/paths/auth.yaml        (auth endpoint paths)
  CREATE shared/api-contracts/paths/characters.yaml  (character CRUD paths)
  CREATE shared/api-contracts/paths/chat.yaml        (chat SSE + message history paths)
  CREATE shared/api-contracts/paths/memories.yaml    (memory paths)
  CREATE shared/api-contracts/paths/media.yaml       (media upload path)
  CREATE shared/api-contracts/paths/onboarding.yaml  (onboarding path)
  CREATE shared/api-contracts/paths/profile.yaml     (profile paths)
  CREATE shared/api-contracts/paths/health.yaml      (health check path)
  CREATE shared/api-contracts/schemas/auth.yaml      (auth request/response schemas)
  CREATE shared/api-contracts/schemas/character.yaml (character schemas)
  CREATE shared/api-contracts/schemas/chat.yaml      (chat + SSE event schemas)
  CREATE shared/api-contracts/schemas/memory.yaml    (memory schemas)
  CREATE shared/api-contracts/schemas/media.yaml     (media schemas)
  CREATE shared/api-contracts/schemas/onboarding.yaml(onboarding schemas)
  CREATE shared/api-contracts/schemas/profile.yaml   (profile schemas)
  CREATE shared/api-contracts/schemas/health.yaml    (health schemas)
  CREATE shared/api-contracts/schemas/common.yaml    (ErrorResponse, pagination, rate limit)
  DELETE shared/api-contracts/.gitkeep               (no longer needed)

CI:
  MODIFY .github/workflows/backend-ci.yml            (add validate-openapi step)

Specs:
  CREATE shared/feature-specs/openapi-specs.md       (this file)
  CREATE docs/pipeline/openapi-specs-architect.handoff.md
```

---

## Appendix A: Complete Endpoint Inventory

This table enumerates every endpoint that must be documented. The backend developer should use this as a checklist.

| # | Method | Path | Auth | Router File | Tags |
|---|--------|------|------|-------------|------|
| 1 | GET | /health | No | health.py | health |
| 2 | POST | /auth/register | No | auth.py | auth |
| 3 | POST | /auth/login | No | auth.py | auth |
| 4 | POST | /auth/refresh | No | auth.py | auth |
| 5 | GET | /characters | Yes | characters.py | characters |
| 6 | POST | /characters | Yes | characters.py | characters |
| 7 | PUT | /characters/{character_id} | Yes | characters.py | characters |
| 8 | DELETE | /characters/{character_id} | Yes | characters.py | characters |
| 9 | POST | /characters/{character_id}/messages | Yes | chat.py | chat |
| 10 | GET | /characters/{character_id}/messages | Yes | chat.py | chat |
| 11 | GET | /memories | Yes | memories.py | memories |
| 12 | GET | /characters/{character_id}/memories | Yes | memories.py | memories |
| 13 | DELETE | /characters/{character_id}/memories/{memory_id} | Yes | memories.py | memories |
| 14 | DELETE | /characters/{character_id}/memories | Yes | memories.py | memories |
| 15 | POST | /media/upload-url | Yes | media.py | media |
| 16 | POST | /onboarding/complete | Yes | onboarding.py | onboarding |
| 17 | GET | /profile | Yes | profile.py | profile |
| 18 | PUT | /profile | Yes | profile.py | profile |
| 19 | DELETE | /profile/account | Yes | profile.py | profile |

Total: 19 endpoint+method combinations.

## Appendix B: SSE Documentation Pattern

OpenAPI 3.1 does not natively model Server-Sent Events. The recommended pattern for the POST /characters/{character_id}/messages endpoint is:

```yaml
responses:
  "200":
    description: AI response streamed as Server-Sent Events
    content:
      text/event-stream:
        schema:
          type: string
          description: |
            Stream of SSE events. Each event has `data:` prefix followed by JSON.

            Event types:
            - chunk: { "type": "chunk", "content": "text fragment" }
            - action: { "type": "action", "action": "SET_ALARM", "payload": { ... } }
            - done: { "type": "done", "message_id": "uuid" }
            - error: { "type": "error", "message": "description" }

            The stream always ends with either a "done" or "error" event.
    headers:
      Cache-Control:
        schema:
          type: string
          example: "no-cache"
      X-Accel-Buffering:
        schema:
          type: string
          example: "no"
```

The individual SSE event schemas (ChunkEvent, ActionEvent, DoneEvent, ErrorEvent) should also be defined in `schemas/chat.yaml` for reference, even though they are not directly referenced by the response schema. This allows mobile developers to generate data classes from them.

## Appendix C: Validation Script Dependencies

The validation script requires the following Python packages (add to `requirements-dev.txt` or equivalent):

- `pyyaml` -- YAML parsing
- `openapi-spec-validator` -- OpenAPI 3.1 schema validation
- `jsonref` -- JSON `$ref` resolution (works with YAML-loaded dicts)

These are dev-only dependencies and must not be added to the production `requirements.txt`.
