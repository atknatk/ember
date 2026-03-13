# Backend Dev Handoff: OpenAPI Specs

**Date**: 2026-03-13
**Agent**: backend-dev
**Status**: COMPLETE

## Implemented Files

### Shared (YAML specs)
- `shared/api-contracts/ember-api.yaml` -- root OpenAPI 3.1 spec with $ref composition
- `shared/api-contracts/paths/auth.yaml` -- 3 auth endpoint paths
- `shared/api-contracts/paths/characters.yaml` -- 4 character CRUD paths
- `shared/api-contracts/paths/chat.yaml` -- 2 chat paths (SSE + history)
- `shared/api-contracts/paths/health.yaml` -- 1 health check path
- `shared/api-contracts/paths/media.yaml` -- 1 media upload path
- `shared/api-contracts/paths/memories.yaml` -- 4 memory paths
- `shared/api-contracts/paths/onboarding.yaml` -- 1 onboarding path
- `shared/api-contracts/paths/profile.yaml` -- 3 profile paths
- `shared/api-contracts/schemas/auth.yaml` -- RegisterRequest, LoginRequest, RefreshRequest, AuthResponse, UserResponse, RefreshResponse
- `shared/api-contracts/schemas/character.yaml` -- CreateCharacterRequest, UpdateCharacterRequest, CharacterListItem, CharacterListResponse, CharacterDetail
- `shared/api-contracts/schemas/chat.yaml` -- SendMessageRequest, MessageItem, MessageListResponse, ChunkEvent, ActionEvent, DoneEvent, ErrorEvent
- `shared/api-contracts/schemas/common.yaml` -- ErrorResponse, RateLimitError
- `shared/api-contracts/schemas/health.yaml` -- HealthResponse, DependencyStatus, CircuitBreakerReport, CircuitBreakerStatus
- `shared/api-contracts/schemas/media.yaml` -- UploadUrlRequest, UploadUrlResponse
- `shared/api-contracts/schemas/memory.yaml` -- MemoryItem, MemoryListResponse
- `shared/api-contracts/schemas/onboarding.yaml` -- OnboardingAnswer, OnboardingRequest, OnboardingResponse
- `shared/api-contracts/schemas/profile.yaml` -- ProfileResponse, ProfileUpdateRequest, AccountDeleteRequest

### Backend
- `backend/app/main.py` -- added openapi_tags to FastAPI constructor
- `backend/scripts/validate_openapi.py` -- drift detection script (compares YAML vs FastAPI)
- `backend/tests/test_openapi_yaml.py` -- 15 tests (YAML syntax, $ref resolution, completeness, security)
- `backend/tests/test_openapi_validation.py` -- 11 tests (validation against current codebase, helper unit tests)
- `backend/requirements-dev.txt` -- added pyyaml, openapi-spec-validator

### CI
- `.github/workflows/backend-ci.yml` -- added "Validate OpenAPI specs" step after tests

## Endpoints Documented (19 total)
- `GET /health` -- health check (public)
- `POST /auth/register` -- user registration (public)
- `POST /auth/login` -- user login (public)
- `POST /auth/refresh` -- token refresh (public)
- `GET /characters` -- list characters
- `POST /characters` -- create character
- `PUT /characters/{character_id}` -- update character
- `DELETE /characters/{character_id}` -- delete character
- `POST /characters/{character_id}/messages` -- send message (SSE streaming)
- `GET /characters/{character_id}/messages` -- message history (cursor pagination)
- `GET /memories` -- global memories
- `GET /characters/{character_id}/memories` -- character memories
- `DELETE /characters/{character_id}/memories/{memory_id}` -- delete single memory
- `DELETE /characters/{character_id}/memories` -- delete all character memories
- `POST /media/upload-url` -- presigned upload URL
- `POST /onboarding/complete` -- complete onboarding
- `GET /profile` -- get profile
- `PUT /profile` -- update profile
- `DELETE /profile/account` -- delete account

## Test Results
- pytest: 1792 passed, 13 skipped, 0 failed
- ruff: clean
- validation script: exit code 0 (all specs match)

## Known Issues / Deviations from Spec
- Test routes (e.g., `_test_protected`) injected by auth dependency tests are excluded from validation via `/_test` path filter. This is expected and intentional.
- The spec mentions `jsonref` as a dependency but it was not needed -- YAML $ref resolution is handled manually in the validation script, which is simpler and avoids an extra dependency.

## Notes for Backend Tester
- The validation script at `backend/scripts/validate_openapi.py` can be run standalone: `python scripts/validate_openapi.py`
- YAML spec tests in `tests/test_openapi_yaml.py` do not require the FastAPI app -- they only parse YAML files
- Validation tests in `tests/test_openapi_validation.py` import the FastAPI app to compare schemas
- To test drift detection: temporarily rename a field in a YAML schema and verify the validation script catches it
