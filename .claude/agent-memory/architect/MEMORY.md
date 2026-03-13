# Architect Agent Memory

## Project Structure Observations

- [project_structure.md](project_structure.md) — if it exists, otherwise inline below:
- `shared/api-contracts/` is empty -- no OpenAPI specs exist yet.
- `docs/standards/backend.md` Section 1 is the authoritative directory layout.

## Spec Writing Patterns

- Backend-only features (layer: backend) skip iOS/Android sections 5 and 6.
- For scaffold/infra features, "API Changes" is minimal. For DB-only features, "API Changes" is "no new endpoints."
- The File Manifest should count every `__init__.py` file explicitly (for scaffold features).
- For MODIFY-only features, the file manifest is small but still list every modified file.
- When docs/standards/common.md and issue description conflict, note the discrepancy and state which takes precedence.
- For external-API wrappers (Mem0, etc.), list which existing DB columns are READ.
- For S3/storage features, document presigned URL approach (PUT vs POST).
- TimestampMixin: not for append-only tables (messages) or tables with non-standard timestamp columns (user_activity).
- CHECK constraints preferred over PG ENUMs.
- NUMERIC over FLOAT for health/measurement data.

## Key Decisions Log (P01-01 through P01-04)

- P01-01: Health endpoint public, no DB. Alembic configured, zero migrations.
- P01-02: CASCADE on profile FKs. SET NULL for partners.user_id_2.
- P01-03: Auth in core/auth.py. CognitoJWKSProvider with TTL cache. Validate token_use=id.
- P01-04: USER_PASSWORD_AUTH. asyncio.to_thread() for boto3. mem0_user_id = "user_{sub}". Single DB txn for Profile+Character+Conversation. email-validator needed.

## Key Decisions Log (P01-05 through P01-10)

- P01-05: Haiku for system prompt gen. No pagination on character list. Soft delete. mem0_agent_id uniqueness fallback.
- P01-06: SSE over WebSocket. Background task persistence. Separate Haiku for intent. 50 msgs context. Mem0 SDK synchronous, wrapped in to_thread().
- P01-07: Composite cursor (created_at, id). Base64 URL-safe JSON. tuple_() comparison. Default limit 20.
- P01-08: No pagination on memory list. Idempotent delete. 503 for Mem0 failures. Field named `memory`.
- P01-09: Onboarding memories global. Single Haiku call for all Q&A. Deterministic fallback. 409 for re-onboarding.
- P01-10: Presigned PUT. UUID in S3 key. Per-type content_type whitelist. 5-minute expiration.

## Key Decisions Log (P1.5-01 through P1.5-02)

- P1.5-01: In-memory token bucket. Three groups (chat=10, write=20, read=60). Fail-open. Lightweight JWT parsing in middleware.
- P1.5-02: DB cascade handles all relational cleanup on profile delete. DB deletion first, then best-effort Mem0/S3/Cognito cleanup.
- P1.5-02: Return 204 if partial external cleanup fails; 503 only if ALL external cleanups fail.
- P1.5-02: "DELETE MY ACCOUNT" confirmation string required for account deletion.
- P1.5-02: Pydantic model_fields_set to distinguish "field not sent" vs "field sent as null" for avatar_url.
- P1.5-02: New ProfileResponse schema (not modifying existing UserResponse in auth.py).
- P1.5-02: IANA timezone validation via stdlib zoneinfo.ZoneInfo. Supported languages: en, tr.
- P1.5-02: Cognito deletion via admin_delete_user (not delete_user) -- does not require user's access token.
- P1.5-02: Parallel Mem0 delete_all calls via asyncio.gather with return_exceptions=True.
- P1.5-02: No new config values needed.

## Key Decisions Log (P02-01 through P02-02)

- P02-01: Activity tracking middleware using Starlette BaseHTTPMiddleware + BackgroundTask. Upsert via raw SQL INSERT ON CONFLICT. Reuses _extract_sub_from_jwt from request_id middleware. Registered as innermost middleware (before rate limiter in code, after in execution).
- P02-02: APScheduler in-process (not Celery). Sequential user processing. Hourly midnight reset job. Deterministic fallback messages when Claude/Mem0 down. evaluate_notification_triggers is pure function. Firebase init in lifespan. Invalid FCM token -> set fcm_token=NULL. notification_preferences not checked yet (separate feature). goal_followup deferred.

## Implementation State

See [implementation_state.md](implementation_state.md) for full per-feature file tracking.

Current backend routes: health, auth, characters, chat, memories (2 routers), media, onboarding (8 include_router calls).
After P1.5-02: adds profile router (9 include_router calls).
