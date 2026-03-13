# Doc-Code Sync

> Resolves 26 documentation-code contradictions accumulated during Phase 1 development and adds a CI script to prevent future drift.

**Status**: Released
**Added in**: Phase 1.5 (P1.5-07)
**Platforms**: Backend
**GitHub Issue**: #89

---

## Overview

As the Ember backend evolved through Phase 1, several documentation files fell out of sync with the actual implementation. By the end of P01-10 (media-upload), there were 28 catalogued discrepancies between the docs in `docs/standards/`, `docs/04-veri-api.md`, `docs/05-ai-bellek.md`, and `CLAUDE.md` and the working codebase. These ranged from references to a non-existent `app.models.user` module, to stale SSE event formats, to incorrect Mem0 API call signatures.

P1.5-07 is a docs-only and CI-tooling feature: no application logic was changed. The spec audited every affected doc file, catalogued each contradiction with an ID (C-01 through C-28), declared the authoritative source (in all cases, the working code), and prescribed the exact fix. C-12 turned out to be a non-contradiction (both sources were already consistent), leaving 26 real fixes applied across 8 files.

To prevent recurrence, a Python CI script (`backend/scripts/check_doc_code_sync.py`) was created with 7 mechanically verifiable checks. It runs in `.github/workflows/backend-ci.yml` after the pytest suite on every backend change. The script targets only assertions that can be checked programmatically — file and class existence, known-bad import strings, config field coverage — rather than attempting to parse prose.

---

## Architecture

### Scope of Changes

This feature modified 8 files and created 2 new files:

| File | Type | Contradictions Fixed |
|------|------|---------------------|
| `docs/standards/backend.md` | Modified | C-01, C-03, C-04, C-06, C-07, C-10, C-11, C-15, C-18, C-19, C-20, C-21, C-24, C-27 (14 fixes) |
| `docs/standards/testing.md` | Modified | C-01, C-02 (2 fixes) |
| `docs/standards/common.md` | Modified | C-06, C-09, C-26, C-28 (4 fixes) |
| `docs/04-veri-api.md` | Modified | C-08, C-13, C-16, C-17, C-23, C-25 (6 fixes) |
| `docs/05-ai-bellek.md` | Modified | C-05, C-22 (2 fixes) |
| `docs/08-guvenlik-performans.md` | Modified | C-14 (1 fix) |
| `CLAUDE.md` | Modified | C-05, C-14 (2 fixes) |
| `backend/scripts/check_doc_code_sync.py` | Created | CI check script |
| `.github/workflows/backend-ci.yml` | Modified | Added doc-code sync step |

### How the CI Script Works

`backend/scripts/check_doc_code_sync.py` runs 7 checks:

**Check 1 — Model class existence (FAIL)**
Scans `docs/standards/backend.md` and `docs/standards/testing.md` for `from app.models.{x} import {Y}` patterns using regex. For each match, verifies that `backend/app/models/{x}.py` exists and contains `class {Y}`. This was the highest-priority check: the `app.models.user` module never existed.

**Check 2 — Route file existence (FAIL)**
Extracts `.py` filenames from the project-structure tree block in `backend.md` under `routes/`. Compares against actual files in `backend/app/routes/`. Fails if any code route file is absent from the docs listing.

**Check 3 — Config field coverage (WARN only)**
Parses the `Settings` class from `backend/app/config.py` via AST. Extracts the same fields from the `Settings` code block in `backend.md` via regex. Produces warnings (not failures) on mismatches — config fields are added frequently and a hard failure would be too noisy.

**Check 4 — Service file existence (FAIL)**
Same as Check 2 but for `backend/app/services/`. Fails if any service `.py` file is in code but not listed in `backend.md`.

**Check 5 — AsyncMemoryClient reference (FAIL)**
Greps `backend.md` and `testing.md` for the literal string `AsyncMemoryClient`. Fails if found, with an explanatory message directing to `MemoryClient + asyncio.to_thread()`.

**Check 6 — User model reference (FAIL)**
Greps all `.md` files in `docs/standards/` for `from app.models.user import`. Fails if found, explaining that the model is `Profile` in `app.models.profile`.

**Check 7 — Route prefix consistency (WARN only)**
Extracts `prefix=` values from `include_router(...)` calls in both `main.py` and the `create_app` example in `backend.md`. Warns (not fails) on any set difference, since the docs example may intentionally simplify.

**Exit codes**: 0 if all checks pass (warnings are acceptable), 1 if any FAIL-level check triggers.

### Decision: Code Always Wins

Every one of the 26 contradictions was resolved by updating docs to match the working code, never the reverse. No contradiction described behavior that should have been implemented but was not. The docs simply lagged behind implementation decisions. This principle is enshrined in the script: it validates that docs reflect code, not that code conforms to docs.

### Decision: Warnings vs. Failures

Two checks (config field coverage, route prefix consistency) are warnings only. Config fields are added regularly during feature development and a CI failure on every new field would create friction. Route prefix consistency is a warn because the docs example may show a simplified version for readability. The four structural checks (model existence, route/service file existence, known-bad import strings) are hard failures because they cause runtime import errors if a developer follows the docs literally.

---

## Contradiction Catalog Summary

The 26 resolved contradictions fell into these categories:

**Naming and module path errors (8 fixes)**
- C-01/C-02: `app.models.user.User` → `app.models.profile.Profile`; `cognito_sub` column does not exist — `Profile.id` is the Cognito sub UUID
- C-04: Cognito verification at `app/utils/cognito.py::verify_token` → `app/core/auth.py::verify_cognito_token` with `CognitoJWKSProvider` and TTL caching
- C-09: Agent names `backend-agent`, `ios-agent` → `backend-dev`, `ios-dev`, `backend-tester`, etc.
- C-11: LLM service single file `app/services/llm_service.py` with `ClaudeProvider` → package `app/services/llm/` with `AnthropicProvider`, `LLMRouter`, `get_llm_router()`

**Numeric value errors (2 fixes)**
- C-05: Context window "last 20 messages" → "last 50 messages" (controlled by `settings.max_context_messages = 50`)
- C-06: Default pagination limit 30 → 20 (`Query(default=20, ge=1, le=100)` in `routes/chat.py`)

**API contract errors (8 fixes)**
- C-08: Error response format `{"error": {"code": ..., "message": ...}}` → `{"detail": "..."}`
- C-13: Memory item field `"content"` → `"memory"` (Mem0 SDK returns `memory`)
- C-16: Message cursor `?cursor={created_at_iso}` → opaque base64 composite cursor `{"ts": "...", "id": "..."}`
- C-17: GET messages response schema not documented → added `{"items": [...], "next_cursor": "...", "has_more": true}`
- C-23: Character list field `last_conversation_at` → `last_message_at`
- C-25: SSE docs missing `ErrorEvent` → added `data: {"type": "error", "message": "..."}`

**Implementation pattern errors (5 fixes)**
- C-03: `AsyncMemoryClient` (non-existent) → sync `MemoryClient` wrapped in `asyncio.to_thread()`
- C-19: SSE event format `{"delta": chunk}` / `data: [DONE]` → typed JSON events `{"type": "chunk", "content": "..."}` / `{"type": "done", ...}`
- C-20: Services injected via `Depends(get_memory_service)` → services instantiated directly in route handlers: `service = ChatService(db)`
- C-22: Mem0 API dict-style params → keyword-style params; `mem0.search_async()` → `asyncio.to_thread(client.search, ...)`
- C-28: Conversation created on first message → conversation created at character creation time

**Structure / completeness errors (3 fixes)**
- C-07: Single memories router → dual routers: `global_router` and `character_router`
- C-10: Project structure missing `core/`, `middleware/`, `services/llm/`, onboarding/media/profile/health routes and services
- C-15: `create_app` example missing media, onboarding, profile routers and `RateLimitMiddleware`/`RequestIDMiddleware`

**Configuration errors (3 fixes)**
- C-14: Flat "20 req/min" → grouped limits: 10/min chat, 20/min write, 60/min read
- C-18: Settings class example missing ~20 config fields including circuit breaker, Sentry, S3, Firebase, CORS settings
- C-26: `.env.example` missing LLM_PROVIDER, S3_BUCKET_NAME, FIREBASE_CREDENTIALS_JSON, rate limit and Sentry fields

---

## API Reference

This feature introduces no new API endpoints. See [`docs/04-veri-api.md`](../04-veri-api.md) for the full API contract, which was updated as part of this feature (C-08, C-13, C-16, C-17, C-23, C-25).

---

## Backend Implementation

**Files**:
- `backend/scripts/check_doc_code_sync.py` — CI drift detection script
- `.github/workflows/backend-ci.yml` — added `Check doc-code sync` step

**Running the CI script locally**:
```bash
cd backend && python scripts/check_doc_code_sync.py
```

Expected output on a clean repo:
```
Running doc-code sync checks...
Results: 0 failures, 0 warnings
All checks passed.
```

**Verifying regression detection**: To confirm a check works, temporarily introduce a known-bad pattern:
```bash
# In docs/standards/backend.md, add: from app.models.user import User
python scripts/check_doc_code_sync.py
# Expected: FAIL — exit code 1
```

---

## Testing

This feature has no application code changes and therefore no unit tests for business logic. The CI script itself was verified to:
- Pass (exit 0) against the repo after all doc fixes were applied
- Fail (exit 1) when known-bad patterns are injected (per acceptance criteria in the spec)

The backend pytest suite continued to pass throughout: 1883 passed, 13 skipped, 0 failed.

### Running the Check

```bash
cd backend && python scripts/check_doc_code_sync.py
```

---

## Known Limitations

- **Config field coverage is WARN-only**: Adding a new field to `config.py` will produce a CI warning but not a failure. The design is intentional to avoid blocking routine feature development with doc-update obligations.
- **Check 3 (config fields) uses regex parsing on the docs example**: The regex pattern `\s+(\w+)\s*:\s*\w+` on the `Settings` class block in `backend.md` may miss fields if the doc example uses multi-line annotations or complex type hints. The AST-based code parser is exact; the doc parser is approximate.
- **Service file check does not cover the `services/llm/` sub-package**: `check_service_files()` only scans `backend/app/services/*.py` (top-level files). The `services/llm/` package is not individually checked. LLM provider files added under that sub-package will not trigger a CI failure if undocumented.
- **Prose contradictions are not caught**: The script detects only mechanically verifiable assertions. A doc that correctly names a class but describes it doing the wrong thing will not be caught.

---

## Extending This Feature

**Adding a new check**: Add a function `check_{name}() -> None` that calls `fail()` or `warn()` as appropriate, then add a call to it inside `main()`. Follow the existing pattern: collect failures into the module-level `failures` list via the `fail()` helper, which also prints immediately.

**Promoting a warning to a failure**: Change the `warn(...)` call in the relevant check function to `fail(...)`. Do this only after verifying that the check is stable enough to not create false positives during routine development.

**Covering the `services/llm/` sub-package**: Extend `check_service_files()` to also walk `backend/app/services/llm/` and verify each file is listed in the `services/llm/` subtree in `backend.md`. Follow the same pattern as `check_route_files()`.

**Adding a new stale-import check**: Add a grep check inside a new function, following the pattern of `check_async_memory_client()` and `check_user_model_reference()`. Both use a simple string or regex scan across `DOCS_STANDARDS.glob("*.md")`.

---

## Related Documentation

- [Database Schema and API Endpoints](../04-veri-api.md) — updated by C-08, C-13, C-16, C-17, C-23, C-25
- [AI Memory System](../05-ai-bellek.md) — updated by C-05, C-22
- [Security and Performance](../08-guvenlik-performans.md) — updated by C-14
- [Backend Standards](../standards/backend.md) — updated by 14 contradictions
- [Testing Standards](../standards/testing.md) — updated by C-01, C-02
- [Common Standards](../standards/common.md) — updated by C-06, C-09, C-26, C-28
- [OpenAPI Specs](./openapi-specs.md) — P1.5-06, the companion feature that introduced machine-readable API contracts
