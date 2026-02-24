# Architect Agent Memory

## Project Structure Observations

- The `backend/` directory was scaffolded with empty subdirectories: `app/routes/`, `app/services/`, `app/models/`, `app/utils/`, and `tests/`. Missing from initial scaffold: `app/core/`, `app/schemas/`, `app/db/`.
- `docs/standards/backend.md` Section 1 is the authoritative directory layout. It specifies `schemas/` and `db/` which the GitHub issue descriptions sometimes omit. Always cross-reference the standard.
- `shared/feature-specs/` and `docs/pipeline/` start with only `.gitkeep` files.
- `shared/api-contracts/` is empty -- no OpenAPI specs exist yet.

## Spec Writing Patterns

- Backend-only features (layer: backend) do not need iOS or Android sections. Skip sections 5 and 6 from the full template.
- For scaffold/infra features with no business logic, the "API Changes" section is minimal (just health endpoint), and "DB Changes" is "no new tables."
- The File Manifest should count every `__init__.py` file explicitly.
- Always include `.env.example`, `.gitignore`, `.dockerignore` in the file manifest for scaffold features.

## Spec Writing Patterns (continued)

- For DB schema features, the "API Changes" section is "no new endpoints" -- state this explicitly.
- TimestampMixin is not always appropriate. `messages` is append-only (no updated_at), `user_activity` has no created_at. Document WHY each table does or does not use the mixin.
- The existing `models/__init__.py` is nearly empty. Each new model feature must update it with imports.
- The existing `env.py` imports Base but not model modules. The wildcard `from app.models import *` must be added.
- CHECK constraints are preferred over PostgreSQL ENUM types (easier to modify, no ALTER TYPE needed).
- NUMERIC over FLOAT for health/measurement data (exact decimal storage).

## Key Decisions Log

- P01-01: Health endpoint is public, does not touch DB. Rationale: ECS health checks must not fail during DB failover.
- P01-01: `get_current_user` stubbed as 501 -- auth is a separate feature (P01-03).
- P01-01: Alembic configured but zero migrations -- first migration comes with P01-02.
- P01-02: Messages table omits TimestampMixin (append-only, no updated_at needed).
- P01-02: user_activity omits TimestampMixin (has updated_at but no created_at per docs/04-veri-api.md).
- P01-02: CHECK constraints over PG ENUMs for subscription_tier, role, partner status.
- P01-02: ON DELETE SET NULL for partners.user_id_2, CASCADE for user_id_1.
- P01-02: Single initial migration for all 7 tables.
- P01-03: Auth module in `core/auth.py` (not `utils/cognito.py`) -- consistent with `core/logging.py` from P01-01.
- P01-03: CognitoJWKSProvider class with TTL cache, not simple module-level dict -- needs timestamp + force-refresh logic.
- P01-03: Validate `token_use=id` (not access) -- Ember uses Cognito ID tokens.
- P01-03: Stale JWKS cache preferred over hard failure when endpoint unreachable.
- P01-03: Force JWKS refresh on kid miss (key rotation handling).
- P01-03: config.py already has cognito_user_pool_id, cognito_app_client_id, aws_region -- no changes needed.

## Key Decisions Log (continued)

- P01-04: Auto-confirm via admin_confirm_sign_up -- email verification deferred to Phase 2.
- P01-04: USER_PASSWORD_AUTH (not SRP) -- backend-to-Cognito is HTTPS, SRP is for client-side SDKs.
- P01-04: asyncio.to_thread() for boto3 calls -- standard library over aioboto3.
- P01-04: Default character named "Ember" with template "companion".
- P01-04: mem0_user_id = "user_{sub}" with lazy Mem0 user creation (no explicit API call).
- P01-04: Single DB transaction for Profile + Character + Conversation.
- P01-04: Idempotent registration handles Cognito-DB split-brain edge case.
- P01-04: email-validator package needed for Pydantic EmailStr.

## Implementation State After P01-04

- `backend/app/models/` has all 7 model files + populated `__init__.py` with all imports.
- `backend/app/dependencies.py` has `get_db` (real) + `get_current_user` (real -- JWT verification + Profile lookup).
- `backend/app/core/auth.py` has CognitoJWKSProvider + verify_cognito_token.
- `backend/app/config.py` Settings class has cognito fields. Does NOT have `claude_haiku_model` yet.
- `backend/app/core/` has `__init__.py` + `logging.py` + `auth.py`.
- `backend/app/schemas/` has `__init__.py` (empty) + `health.py` + `auth.py`.
- `backend/app/services/` has `__init__.py` (empty) + `auth_service.py`.
- `backend/requirements.txt` includes python-jose[cryptography], httpx, boto3, anthropic, email-validator.
- `backend/app/routes/` has `__init__.py` + `health.py` + `auth.py`.
- `backend/app/main.py` registers health and auth routers.

## Key Decisions Log (P01-05)

- P01-05: Claude Haiku for system prompt generation (not Sonnet) -- cheap/fast for short one-time text.
- P01-05: No cursor pagination on character list -- users have at most dozens of characters.
- P01-05: system_prompt excluded from list response, included in POST/PUT responses only.
- P01-05: Soft delete (is_active=false) per docs/04-veri-api.md.
- P01-05: Template and mem0_agent_id are immutable after creation.
- P01-05: mem0_agent_id uniqueness fallback: {template}_{uuid[:8]}_{user_id} for duplicate templates.
- P01-05: New config field: claude_haiku_model = "claude-haiku-4-5".
- P01-05: No Mem0 API calls during character CRUD -- agent_id stored for future messaging use.

## Key Decisions Log (P01-06)

- P01-06: SSE over WebSocket for chat streaming -- request-response, not bidirectional.
- P01-06: Background task persistence (after stream) -- minimizes TTFT (<1s target).
- P01-06: Background tasks use separate AsyncSessionLocal() -- request session closes with StreamingResponse.
- P01-06: Separate Haiku call for intent extraction -- keeps Sonnet response natural, cheaper.
- P01-06: 50 messages context (configurable via max_context_messages) -- CLAUDE.md says 30-50.
- P01-06: 3 parallel fetches in asyncio.gather(): global Mem0, character Mem0, DB last 50 messages.
- P01-06: Mem0 SDK is synchronous -- all calls wrapped in asyncio.to_thread().
- P01-06: Chat router registered under /api/v1/characters prefix -- routes use /{character_id}/messages, no conflict with character CRUD router.
- P01-06: Auto-create conversation if missing (defensive).
- P01-06: Action metadata stored on assistant message's JSONB metadata_ column.
- P01-06: SSE format: data: {json}\n\n with type field in JSON (no event: header).

## Key Decisions Log (P01-07)

- P01-07: Composite cursor (created_at, id) over plain ISO timestamp -- fixes correctness bug with same-timestamp messages.
- P01-07: Base64 URL-safe JSON cursor encoding per docs/standards/common.md Section 6.
- P01-07: No backward compatibility for old plain-ISO cursors -- no mobile client has shipped yet.
- P01-07: No index changes needed -- existing idx_messages_conv_time is sufficient, id tiebreaker operates on small result set.
- P01-07: SQLAlchemy tuple_() for row-value comparison: (created_at, id) < ($ts, $id).
- P01-07: Default limit stays at 20 (matches issue description; common.md says 30 but issue takes precedence).
- P01-07: Single HTTPException(400) for all cursor parse failures -- do not expose internal error details.
- P01-07: MODIFY-only feature -- no new files created in backend, only updates to 4 existing files.

## Implementation State After P01-06

- `backend/app/config.py` now has `claude_haiku_model`, `claude_model`, `max_context_messages: int = 50`.
- `backend/app/routes/` has `__init__.py` + `health.py` + `auth.py` + `characters.py` + `chat.py`.
- `backend/app/services/` has `__init__.py` (empty) + `auth_service.py` + `character_service.py` + `chat_service.py`.
- `backend/app/schemas/` has `__init__.py` (empty) + `health.py` + `auth.py` + `character.py` + `chat.py`.
- `backend/app/main.py` registers health, auth, characters, and chat routers.
- `backend/app/db/session.py` has AsyncSessionLocal (used by background tasks).
- Tests: `test_chat_routes.py` (989 lines) and `test_chat_service.py` (1947 lines) with comprehensive coverage.

## Implementation State After P01-05

- `backend/app/config.py` now has `claude_haiku_model: str = "claude-haiku-4-5"`.
- `backend/app/routes/` has `__init__.py` + `health.py` + `auth.py` + `characters.py`.
- `backend/app/services/` has `__init__.py` (empty) + `auth_service.py` + `character_service.py`.
- `backend/app/schemas/` has `__init__.py` (empty) + `health.py` + `auth.py` + `character.py`.
- `backend/app/main.py` registers health, auth, and characters routers.

## Spec Writing Patterns (P01-07 lesson)

- When a feature mostly enhances an existing implementation, clearly document "What Already Exists" vs "What Changes" in a comparison table.
- For MODIFY-only features with no new files, the file manifest is small. Still list every modified file explicitly.
- When docs/standards/common.md and the issue description conflict on specifics (e.g., default limit 30 vs 20), note the discrepancy and state which takes precedence and why.
