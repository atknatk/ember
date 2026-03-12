---
name: implementation_state
description: Tracks which files exist in backend after each feature is implemented - used to know what to MODIFY vs CREATE in new specs
type: project
---

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

## Implementation State After P01-05

- `backend/app/config.py` now has `claude_haiku_model: str = "claude-haiku-4-5"`.
- `backend/app/routes/` adds `characters.py`.
- `backend/app/services/` adds `character_service.py`.
- `backend/app/schemas/` adds `character.py`.

## Implementation State After P01-06

- `backend/app/config.py` now has `claude_haiku_model`, `claude_model`, `max_context_messages: int = 50`.
- `backend/app/routes/` adds `chat.py`.
- `backend/app/services/` adds `chat_service.py`.
- `backend/app/schemas/` adds `chat.py`.
- `backend/app/db/session.py` has AsyncSessionLocal (used by background tasks).

## Implementation State After P01-07

- `backend/app/services/chat_service.py` has MessageCursor dataclass, _encode_cursor, _decode_cursor, tuple_ pagination.
- No new files. MODIFY-only feature.

## Implementation State After P01-08

- `backend/app/routes/` adds `memories.py`.
- `backend/app/services/` adds `memory_service.py`.
- `backend/app/schemas/` adds `memory.py`.

## Implementation State After P01-09

- `backend/app/routes/` adds `onboarding.py`.
- `backend/app/services/` adds `onboarding_service.py`.
- `backend/app/schemas/` adds `onboarding.py`.

## Implementation State After P01-10

- `backend/app/routes/` adds `media.py`.
- No new service file (presigned URL logic inline or in media service).
- `backend/app/main.py` registers 8 include_router calls: health, auth, characters, chat, memories (global + character), media, onboarding.

## Implementation State After P1.5-01

- `backend/app/middleware/` created with `rate_limit.py`.
- `backend/app/core/rate_limit.py` has RateLimiter + TokenBucket + extract_user_key.
- `backend/app/config.py` adds rate_limit_chat, rate_limit_write, rate_limit_read.
- `backend/app/main.py` adds RateLimitMiddleware.

## Current State (as of P1.5-02 spec)

Full file listing for `backend/app/routes/`:
`__init__.py`, `health.py`, `auth.py`, `characters.py`, `chat.py`, `memories.py`, `onboarding.py`, `media.py`

Full file listing for `backend/app/services/`:
`__init__.py` (empty), `auth_service.py`, `character_service.py`, `chat_service.py`, `memory_service.py`, `onboarding_service.py`

Full file listing for `backend/app/schemas/`:
`__init__.py` (empty), `health.py`, `auth.py`, `character.py`, `chat.py`, `memory.py`, `onboarding.py`
