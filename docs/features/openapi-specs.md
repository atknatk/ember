# OpenAPI Specs

> Machine-readable OpenAPI 3.1 contracts for all 19 Ember API endpoints, with a drift-detection validation script that fails CI whenever the hand-written YAML diverges from the FastAPI implementation.

**Status**: Released
**Added in**: Phase 1.5 (P1.5-06)
**Platforms**: Backend
**GitHub Issue**: #88

---

## Overview

Before this feature, mobile developers (iOS and Android) had to read Python route handlers and Pydantic schemas to understand the API contract. This was error-prone and time-consuming. P1.5-06 introduces a complete set of OpenAPI 3.1 YAML specification files in `shared/api-contracts/` that document every implemented endpoint with request/response schemas, authentication requirements, error codes, path and query parameters, and SSE streaming event formats.

The specs are hand-written rather than generated from FastAPI's auto-generated schema. FastAPI's built-in OpenAPI output lacks SSE event documentation, meaningful descriptions, and mobile-developer-friendly organization. Hand-written specs can document the SSE event sequence with full type definitions and can be organized by domain group so a mobile developer can open only the file they need.

To prevent the hand-written specs from drifting as the backend evolves, a validation script at `backend/scripts/validate_openapi.py` is run in CI after every backend change. It imports the live FastAPI app, calls `app.openapi()`, and compares the result against the YAML files structurally — field names, status codes, query parameters, path parameters. If any endpoint in either direction is undocumented or mismatched, CI fails with a clear per-endpoint error message. This creates a continuous guarantee: the YAML files always describe what the API actually does.

---

## Architecture

### File Organization

```
shared/api-contracts/
  ember-api.yaml              Root spec: openapi version, servers, global security, $ref composition
  paths/
    auth.yaml                 POST /auth/register, /auth/login, /auth/refresh
    characters.yaml           GET+POST /characters, PUT+DELETE /characters/{character_id}
    chat.yaml                 POST /characters/{character_id}/messages (SSE), GET (cursor pagination)
    health.yaml               GET /health
    media.yaml                POST /media/upload-url
    memories.yaml             GET /memories, GET+DELETE /characters/{id}/memories, DELETE /{id}/memories/{mid}
    onboarding.yaml           POST /onboarding/complete
    profile.yaml              GET+PUT /profile, DELETE /profile/account
  schemas/
    auth.yaml                 RegisterRequest, LoginRequest, RefreshRequest, AuthResponse, UserResponse, RefreshResponse
    character.yaml            CreateCharacterRequest, UpdateCharacterRequest, CharacterListItem, CharacterListResponse, CharacterDetail
    chat.yaml                 SendMessageRequest, MessageItem, MessageListResponse, ChunkEvent, ActionEvent, DoneEvent, ErrorEvent
    common.yaml               ErrorResponse, RateLimitError
    health.yaml               HealthResponse, DependencyStatus, CircuitBreakerReport, CircuitBreakerStatus
    media.yaml                UploadUrlRequest, UploadUrlResponse
    memory.yaml               MemoryItem, MemoryListResponse
    onboarding.yaml           OnboardingAnswer, OnboardingRequest, OnboardingResponse
    profile.yaml              ProfileResponse, ProfileUpdateRequest, AccountDeleteRequest
```

A monolithic YAML file would exceed 1000 lines. Split files let a mobile developer open only the path group they are working on. The root `ember-api.yaml` uses `$ref` to compose everything into a single logical spec. Path references use JSON pointer encoding (e.g., `/characters/{character_id}` becomes `~1characters~1{character_id}` in the `$ref` fragment).

### Security Model

Global security is set at the root level: `security: [{bearerAuth: []}]`. Every endpoint inherits Bearer JWT auth by default. The four public endpoints — `GET /health`, `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh` — override this with `security: []`. This means adding a new authenticated endpoint requires no security configuration: the global default applies automatically.

The `bearerAuth` security scheme is defined in `ember-api.yaml` components:

```yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
      description: AWS Cognito ID token
```

### SSE Documentation Pattern

OpenAPI 3.1 cannot natively model Server-Sent Events. The chat streaming endpoint (`POST /characters/{character_id}/messages`) is documented with `content-type: text/event-stream` and a prose description of the event sequence. The individual SSE event schemas (`ChunkEvent`, `ActionEvent`, `DoneEvent`, `ErrorEvent`) are defined separately in `schemas/chat.yaml` for reference and potential mobile client code generation, even though they are not directly wired to the response schema.

This is an explicit design decision: the `text/event-stream` response body is modelled as `type: string` with a `description` block that explains each event type. The validation script skips response body comparison for the SSE endpoint (`POST /api/v1/characters/{character_id}/messages`) because FastAPI exposes `StreamingResponse` which produces no usable schema for comparison.

### Drift Detection: How the Validation Script Works

`backend/scripts/validate_openapi.py` performs a structural comparison in five dimensions:

1. **Path coverage (YAML → FastAPI)**: Every path in the YAML specs must exist in the FastAPI routing table. Missing paths are reported as errors.
2. **Path coverage (FastAPI → YAML)**: Every path FastAPI exposes (with the `/api/v1` prefix stripped) must appear in the YAML. Undocumented endpoints are reported as errors. Routes containing `/_test` are excluded — these are injected by the auth dependency test suite and are not real endpoints.
3. **Request body fields**: For each path+method, the JSON schema field names in the YAML `requestBody` are compared against the FastAPI-generated schema (resolving `$ref` pointers). Missing or extra fields are reported.
4. **Response status codes**: The set of documented status codes is compared. FastAPI auto-generates `422` for all POST/PUT endpoints; if the YAML omits `422`, the validator drops `422` from the FastAPI set before comparing, treating the omission as tolerated.
5. **Query and path parameters**: Parameter names (and types for query params) are compared between YAML and FastAPI.

The script exits with code 0 on success, code 1 on any difference. Output identifies every mismatch by `METHOD /path`.

`jsonref` (mentioned as a potential dependency in the original spec) was not needed. The script resolves `$ref` pointers manually inside `resolve_ref()`, which is simpler and avoids an extra dependency.

### CI Integration

The validation step runs in `.github/workflows/backend-ci.yml` after the pytest suite passes:

```yaml
- name: Validate OpenAPI specs
  run: python scripts/validate_openapi.py
```

The step requires the same environment variables as the test suite (database URL, Cognito IDs, AWS region) because it imports the FastAPI app to call `app.openapi()`.

### FastAPI Tags

`backend/app/main.py` was updated to add `openapi_tags` to the `FastAPI` constructor. This populates the tag descriptions visible in FastAPI's built-in `/docs` (Swagger UI) and `/redoc` routes:

| Tag | Description |
|-----|-------------|
| `health` | Health check and dependency status |
| `auth` | Authentication (register, login, refresh) |
| `characters` | Character CRUD |
| `chat` | Message sending (SSE) and history |
| `memories` | Mem0 memory retrieval and deletion |
| `media` | S3 presigned URL generation |
| `onboarding` | Onboarding flow completion |
| `profile` | User profile management |

---

## Endpoint Catalog

All 19 endpoint+method combinations are documented. The table below is the authoritative inventory:

| # | Method | Path | Auth | Tags |
|---|--------|------|------|------|
| 1 | GET | `/health` | No | health |
| 2 | POST | `/auth/register` | No | auth |
| 3 | POST | `/auth/login` | No | auth |
| 4 | POST | `/auth/refresh` | No | auth |
| 5 | GET | `/characters` | Yes | characters |
| 6 | POST | `/characters` | Yes | characters |
| 7 | PUT | `/characters/{character_id}` | Yes | characters |
| 8 | DELETE | `/characters/{character_id}` | Yes | characters |
| 9 | POST | `/characters/{character_id}/messages` | Yes | chat |
| 10 | GET | `/characters/{character_id}/messages` | Yes | chat |
| 11 | GET | `/memories` | Yes | memories |
| 12 | GET | `/characters/{character_id}/memories` | Yes | memories |
| 13 | DELETE | `/characters/{character_id}/memories/{memory_id}` | Yes | memories |
| 14 | DELETE | `/characters/{character_id}/memories` | Yes | memories |
| 15 | POST | `/media/upload-url` | Yes | media |
| 16 | POST | `/onboarding/complete` | Yes | onboarding |
| 17 | GET | `/profile` | Yes | profile |
| 18 | PUT | `/profile` | Yes | profile |
| 19 | DELETE | `/profile/account` | Yes | profile |

All endpoints use the base URL `https://api.ember.com/api/v1` in production and `http://localhost:8000/api/v1` locally.

---

## API Reference

This feature documents existing endpoints — it does not introduce new ones. The YAML specs are the machine-readable source of truth. The key behaviors documented are described below.

### Common Response Headers (All Authenticated Endpoints)

| Header | Type | Description |
|--------|------|-------------|
| `X-RateLimit-Limit` | integer | Maximum requests per minute for this endpoint group |
| `X-RateLimit-Remaining` | integer | Remaining requests in the current window |
| `X-RateLimit-Reset` | integer | Unix timestamp when the limit window resets |

### 429 Too Many Requests

All authenticated endpoints include a `429` response code in their spec:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 4
Content-Type: application/json

{"detail": "Rate limit exceeded"}
```

The `Retry-After` header is always present and is an integer (seconds until the next request is accepted).

### Common Error Schema

All error responses use `ErrorResponse`, defined in `schemas/common.yaml`. The `detail` field is either a string (application-raised `HTTPException`) or an array of Pydantic validation error objects (422 responses):

```json
{"detail": "Character not found"}
```

or

```json
{
  "detail": [
    {"loc": ["body", "content"], "msg": "field required", "type": "value_error.missing"}
  ]
}
```

### SSE Streaming Endpoint

`POST /api/v1/characters/{character_id}/messages` returns `text/event-stream`. The event sequence is:

```
data: {"type": "chunk", "content": "Hello"}
data: {"type": "chunk", "content": " there!"}
data: {"type": "action", "action": "SET_ALARM", "payload": {"time": "07:00", "label": "Wake up"}}
data: {"type": "done", "message_id": "uuid-string"}
```

On error mid-stream:
```
data: {"type": "error", "message": "description"}
```

The stream always ends with either a `done` or `error` event. The response also carries `Cache-Control: no-cache` and `X-Accel-Buffering: no` headers.

SSE event type schemas (defined in `schemas/chat.yaml`):

| Schema | Fields |
|--------|--------|
| `ChunkEvent` | `type: const "chunk"`, `content: string` |
| `ActionEvent` | `type: const "action"`, `action: string`, `payload: object` |
| `DoneEvent` | `type: const "done"`, `message_id: string (uuid)` |
| `ErrorEvent` | `type: const "error"`, `message: string` |

The `type` field uses `const` as a discriminator, which allows mobile clients to generate discriminated union types from these schemas.

---

## Validation Script Reference

### Running Locally

```bash
cd backend && python scripts/validate_openapi.py
```

Output on success:
```
Loading YAML specs from .../shared/api-contracts
Found 14 paths in YAML specs
Loading FastAPI auto-generated schema
Found N paths in FastAPI schema

Comparing specs...

OK: All YAML specs match the FastAPI schema.
```

Note: `14 paths` is correct — the YAML has 14 path keys. The 19 count refers to endpoint+method combinations, since some paths (e.g., `/characters`) define both GET and POST.

Output on drift:
```
FAILED: 2 difference(s) found:

  1. PUT /characters/{character_id}: request body fields in FastAPI but missing from YAML: ['new_field']
  2. GET /profile: response fields in YAML but missing from FastAPI: ['old_field']
```

### Dev Dependencies

The validation script requires packages that are already in `backend/requirements-dev.txt`:

```
pyyaml>=6.0.0
openapi-spec-validator>=0.7.0
```

These are dev-only and must not be added to the production `requirements.txt`.

---

## Testing

### Coverage Summary

| File | Tests | Line Coverage |
|------|-------|--------------|
| `tests/test_openapi_yaml.py` | 69 | — |
| `tests/test_openapi_validation.py` | 62 | 91% on `scripts/validate_openapi.py` |
| **Total** | **131** | — |

Coverage target (>= 80%) is met. The only uncovered lines are 354–380: the `if __name__ == "__main__"` CLI entry block, which wraps already-tested functions. Testing it would require subprocess invocation, which adds flakiness for no benefit.

### Running Tests

OpenAPI tests only:

```bash
cd backend && python -m pytest tests/test_openapi_yaml.py tests/test_openapi_validation.py -v
```

Full backend suite:

```bash
cd backend && python -m pytest tests/ -v
```

### Test Coverage by Class

**`tests/test_openapi_yaml.py`** — YAML syntax, structure, and completeness (no FastAPI import required):

| Class | Tests | What it verifies |
|-------|-------|-----------------|
| `TestRootSpec` | +3 | Server URLs (production + local), global `bearerAuth` reference, `bearerFormat: JWT` |
| `TestOperationIds` | 2 | All `operationId`s are unique; every operation has one |
| `TestEndpointTags` | 1 | All 19 endpoint+tag pairs are correctly assigned |
| `TestUnauthorizedCoverage` | 1 | Every authenticated endpoint documents a `401` response |
| `TestRateLimitCoverage` | 2 | Every authenticated endpoint documents `429`; every `429` has `Retry-After` header |
| `TestPathParameters` | 1 | `character_id` path params declare `format: uuid` |
| `TestSchemaFieldCompleteness` | 23 | Every request/response schema has all required fields per spec |
| `TestSSEEventSchemas` | 4 | `ChunkEvent`, `ActionEvent`, `DoneEvent`, `ErrorEvent` field and `const` type values |
| `TestSchemaConstraints` | 10 | `minLength`, `maxLength`, `enum` values, and `format` constraints match spec |
| `TestCIWorkflow` | 3 | CI workflow file exists and includes a step that runs `validate_openapi.py` |

**`tests/test_openapi_validation.py`** — Structural comparison logic (imports FastAPI app):

| Class | Tests | What it verifies |
|-------|-------|-----------------|
| `TestHelperFunctions` | +13 | `get_query_params` edge cases, `extract_required_fields`, `get_path_params`, `resolve_ref`, `get_request_body_schema`, `anyOf`/`allOf`/`oneOf` field extraction |
| `TestDriftDetection` | 16 | `compare_schemas` catches: missing paths, missing methods, request body presence mismatch, missing/extra fields, response code drift, `422` tolerance, query/path param mismatches, `/_test` route exclusion, SSE endpoint skip, FastAPI paths without `/api/v1` prefix |
| `TestLoadYamlSpecs` | 5 | `sys.exit(1)` on missing root spec, correct path count (14 keys), warning on unresolvable pointer, inline (non-`$ref`) path handling, all endpoint groups present |

### Testing Drift Detection Manually

To verify the script catches drift, temporarily rename a field in any schema YAML and run the script:

```bash
# Edit shared/api-contracts/schemas/auth.yaml: rename "email" to "email_address" in RegisterRequest
python backend/scripts/validate_openapi.py
# Expected: FAILED with "POST /auth/register: request body fields in YAML but missing from FastAPI: ['email_address']"
```

---

## Known Limitations

- **SSE response body is not structurally validated**: The validation script skips response body comparison for `POST /characters/{character_id}/messages`. FastAPI's `StreamingResponse` produces no schema, so drift in SSE event field names cannot be caught automatically. Content accuracy relies on the manual review items in the test plan and the SSE event schema tests in `test_openapi_yaml.py`.
- **Response schema depth is limited to top-level fields**: `compare_schemas` compares field names at the top level of request/response schemas. Nested object schemas are not recursively compared. A change to a field type or a nested object's shape will not be caught automatically.
- **`jsonref` not used**: The architect spec listed `jsonref` as a required dependency. The implementation handles `$ref` resolution with a custom `resolve_ref()` function, which covers the FastAPI schema's internal `$ref`s. The YAML path files reference each other only through the root `ember-api.yaml` composition, which is resolved by `load_yaml_specs()`. The `jsonref` package was not added to `requirements-dev.txt`.
- **No Swagger UI or Redoc page exposed**: FastAPI's built-in `/docs` and `/redoc` are available in development mode only. This is a separate concern not addressed by this feature.

---

## Extending This Feature

**Adding a new endpoint**: When a new route is added to any file in `backend/app/routes/`, the validator will fail CI with `"FastAPI endpoint <path> not documented in YAML specs"`. To fix: add the path entry to the appropriate `paths/*.yaml` file and add any new request/response schemas to the corresponding `schemas/*.yaml` file. Reference the new path from `ember-api.yaml` using the `$ref` pattern already established there.

**Adding a new schema to an existing endpoint**: Update the relevant `schemas/*.yaml` file. If the new field is required in the Pydantic model, the validator will report it as missing from the YAML on the next CI run. Add the field with its type and constraints to match the Pydantic validator rules.

**Adding a new path file for a new domain**: Create `shared/api-contracts/paths/{domain}.yaml` and `shared/api-contracts/schemas/{domain}.yaml`, then add the `$ref` entries for each new path to `ember-api.yaml`. Follow the existing JSON pointer encoding pattern for URL characters: `/` encodes as `~1`, `{` and `}` are used literally in path templates.

**Documenting a new SSE endpoint**: Add the endpoint path to the `SSE_ENDPOINTS` set at the top of `validate_openapi.py` to prevent false response-body drift errors. Document the event schemas in the relevant schema YAML and describe the event sequence in prose in the path YAML, following the pattern in `paths/chat.yaml`.

**Upgrading the schema comparison depth**: To catch nested field drift, extend `extract_field_names()` to recurse into `properties` sub-objects and update `compare_schemas()` to call it recursively with a path prefix. Add corresponding tests to `TestDriftDetection`.

---

## Related Documentation

- [Database Schema and API Endpoints](../04-veri-api.md) — human-readable API contract in Turkish (this feature is the machine-readable English complement)
- [AI Memory System](../05-ai-bellek.md) — Mem0 integration referenced in memory endpoint schemas
- [Security and Performance](../08-guvenlik-performans.md) — auth and rate limit behavior documented in the specs
- [Chat Streaming](./chat-streaming.md) — P01-06, the SSE endpoint whose event format is documented here
- [Rate Limiting Middleware](./rate-limiting-middleware.md) — P1.5-01, the source of the 429 / `Retry-After` responses documented in every authenticated endpoint spec
- [Mem0 Circuit Breaker](./mem0-circuit-breaker.md) — P1.5-04, whose `CircuitBreakerStatus` schema is documented in `schemas/health.yaml`
