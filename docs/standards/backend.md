# Ember Backend Coding Standards

Python 3.12 / FastAPI / SQLAlchemy 2 / Pydantic v2

This document is the authoritative reference for all backend development on the Ember project.
Zero-memory sessions must follow every rule here without exception.

---

## Table of Contents

1. Project Structure
2. FastAPI Route Patterns
3. SQLAlchemy Async Patterns
4. Pydantic v2 Models
5. Authentication — JWT / Cognito
6. Cursor-Based Pagination (mandatory)
7. Parallel Operations with asyncio.gather
8. SSE Streaming
9. Mem0 Memory Layer
10. Claude / Multi-Provider LLM
11. Error Handling
12. Environment Variables and Secrets
13. Dependency Injection
14. Alembic Migrations
15. Testing Patterns
16. Code Style

---

## 1. Project Structure

```
backend/
  app/
    main.py                  # FastAPI app factory, lifespan, CORS, middleware
    config.py                # Settings (pydantic-settings), reads env/secrets
    dependencies.py          # Shared FastAPI Depends functions (get_db, get_current_user)
    core/
      __init__.py
      auth.py                # CognitoJWKSProvider, verify_cognito_token
      circuit_breaker.py     # Mem0 circuit breaker
      logging.py             # Structured logging setup
      rate_limit.py          # RateLimiter (grouped: chat/write/read)
      sentry.py              # Sentry init
    middleware/
      __init__.py
      activity_tracking.py   # ActivityTrackingMiddleware (user activity upsert)
      rate_limit.py          # RateLimitMiddleware (ASGI)
      request_id.py          # RequestIDMiddleware (X-Request-ID header)
    routes/
      __init__.py
      auth.py
      characters.py
      chat.py
      health.py
      media.py
      memories.py
      notifications.py
      onboarding.py
      profile.py
      # voice.py — planned for Phase 3
    services/
      __init__.py
      activity_service.py     # Background user activity upserts
      auth_service.py
      character_service.py
      chat_service.py        # Message send + streaming + history
      content_moderation.py  # Content moderation pipeline
      health_service.py
      media_service.py
      memory_service.py
      notification_scheduler.py  # APScheduler cron jobs for proactive notifications
      notification_sender.py     # Firebase FCM push notification delivery
      notification_service.py    # High-level notification service (user lookup + send)
      onboarding_service.py
      profile_service.py
      llm/                   # Multi-provider LLM package
        __init__.py
        provider.py          # LLMProvider ABC
        anthropic_provider.py
        openai_provider.py
        router.py            # LLMRouter singleton
        exceptions.py        # LLMProviderError
      # voice_service.py — planned for Phase 3
    models/
      __init__.py
      base.py                # DeclarativeBase, TimestampMixin
      profile.py
      character.py
      conversation.py
      message.py
      moderation_event.py    # Content moderation audit log
      user_moderation_state.py  # Per-user abuse escalation
    schemas/
      __init__.py
      auth.py
      character.py           # Request/Response Pydantic models
      chat.py                # SendMessageRequest, MessageItem, SSE events
      memory.py
      onboarding.py
      media.py
      health.py              # Health check response schemas
      profile.py             # Profile CRUD schemas
    utils/
      __init__.py
      cursor.py              # Cursor encode/decode helpers
      timing.py              # log_external_call context manager
    db/
      session.py             # AsyncEngine, AsyncSessionLocal
      migrations/            # Alembic env + versions
  tests/
    conftest.py
    infra/                   # config, models, docker, health
    auth/                    # cognito, auth dependency
    routes/                  # API endpoint tests
    services/                # service layer tests
    schemas/                 # schema validation tests
  pyproject.toml
  alembic.ini
```

---

## 2. FastAPI Route Patterns

### App Factory

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.core.rate_limit import RateLimiter
from app.db.session import engine
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.routes import auth, characters, chat, health, media, memories, onboarding, profile


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup (Sentry, logging)
    yield
    # shutdown
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Ember API", version=settings.app_version, lifespan=lifespan)

    # Middleware (Starlette applies in reverse: last registered = outermost)
    rate_limiter = RateLimiter(
        group_limits={
            "chat": settings.rate_limit_chat,     # 10/min
            "write": settings.rate_limit_write,    # 20/min
            "read": settings.rate_limit_read,      # 60/min
        },
        exempt_paths={"/api/v1/health"},
    )
    app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)

    origins = [o.strip() for o in settings.cors_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)

    # Route registration
    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(characters.router, prefix="/api/v1/characters", tags=["characters"])
    app.include_router(chat.router, prefix="/api/v1/characters", tags=["chat"])
    app.include_router(memories.global_router, prefix="/api/v1", tags=["memories"])
    app.include_router(memories.character_router, prefix="/api/v1/characters", tags=["memories"])
    app.include_router(media.router, prefix="/api/v1/media", tags=["media"])
    app.include_router(onboarding.router, prefix="/api/v1/onboarding", tags=["onboarding"])
    app.include_router(profile.router, prefix="/api/v1", tags=["profile"])

    return app


app = create_app()
```

### Route File Pattern

```python
# app/routes/messages.py
from fastapi import APIRouter, Depends, HTTPException, status
from app.dependencies import get_current_user, get_db
from app.schemas.message import MessageRequest, MessageResponse, MessagePage
from app.services.message_service import MessageService
from app.models.profile import Profile
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/{character_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    character_id: str,
    body: MessageRequest,
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    service = MessageService(db)
    return await service.send(
        user_id=current_user.id,
        character_id=character_id,
        content=body.content,
    )


@router.get("/{character_id}/messages", response_model=MessagePage)
async def list_messages(
    character_id: str,
    cursor: str | None = None,
    limit: int = 20,
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessagePage:
    service = MessageService(db)
    return await service.list_messages(
        user_id=current_user.id,
        character_id=character_id,
        cursor=cursor,
        limit=min(limit, 100),
    )
```

**Rules:**
- Router prefix set in `create_app`, not in route file.
- Never put business logic in route functions — delegate to service layer.
- `status_code` must be explicit on POST (201) and DELETE (204).
- `response_model` always declared.

---

## 3. SQLAlchemy Async Patterns

### Session Setup

```python
# app/db/session.py
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.config import settings

engine = create_async_engine(
    settings.database_url,          # postgresql+asyncpg://...
    echo=settings.debug,
    pool_size=20,
    max_overflow=0,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)
```

### Base Model

```python
# app/models/base.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

### Query Pattern

```python
# app/services/message_service.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.message import Message


class MessageService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, message_id: str) -> Message | None:
        result = await self.db.execute(
            select(Message).where(Message.id == message_id)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> Message:
        msg = Message(**kwargs)
        self.db.add(msg)
        await self.db.commit()
        await self.db.refresh(msg)
        return msg
```

**Rules:**
- Always `await` every database call.
- Use `select()` from `sqlalchemy`, never `session.query()` (legacy style).
- `scalar_one_or_none()` for single rows; `scalars().all()` for lists.
- `expire_on_commit=False` prevents lazy-load errors after commit.
- Never use sync SQLAlchemy engines in async routes.

---

## 4. Pydantic v2 Models

### Request Schema

```python
# app/schemas/chat.py
from pydantic import BaseModel, Field, field_validator


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    media_url: str | None = Field(default=None, max_length=2048)

    @field_validator("content")
    @classmethod
    def strip_content(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Message content must not be empty after trimming whitespace")
        return stripped
```

### Response Schema

```python
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class MessageItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    media_url: str | None
    metadata: dict[str, Any] | None
    created_at: datetime
```

### Pagination Schema

```python
from pydantic import BaseModel


class MessageListResponse(BaseModel):
    items: list[MessageItem]
    next_cursor: str | None
    has_more: bool
```

**Rules:**
- Request schemas: use `Field(...)` with constraints.
- Response schemas: always `ConfigDict(from_attributes=True)` for ORM mapping.
- Never expose internal DB IDs where UUID strings are expected.
- Use `model_config` not deprecated `class Config`.

---

## 5. Authentication — JWT / Cognito

```python
# app/core/auth.py
import httpx
import time
import uuid
from jose import JWTError, jwt
from fastapi import HTTPException, status
from app.config import settings
from app.utils.timing import log_external_call


class CognitoJWKSProvider:
    """Fetches and caches JWKS keys with TTL-based caching (10 min)
    and key rotation handling."""

    def __init__(self, *, region: str, user_pool_id: str, cache_ttl: float = 600.0):
        self._jwks_cache: dict[str, object] | None = None
        self._cache_timestamp: float = 0.0
        self._cache_ttl = cache_ttl
        self._jwks_url = (
            f"https://cognito-idp.{region}.amazonaws.com/"
            f"{user_pool_id}/.well-known/jwks.json"
        )
        self._issuer_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"

    async def get_jwks(self, *, force_refresh: bool = False) -> dict[str, object]:
        if not force_refresh and self._cache_is_fresh():
            return self._jwks_cache
        async with log_external_call("cognito", "jwks_fetch"):
            async with httpx.AsyncClient() as client:
                resp = await client.get(self._jwks_url, timeout=5)
                resp.raise_for_status()
                self._jwks_cache = resp.json()
        self._cache_timestamp = time.monotonic()
        return self._jwks_cache

    async def get_signing_key(self, token: str) -> dict[str, object]:
        """Find the JWK matching the token's kid. Forces refresh on cache miss
        to handle key rotation."""
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        jwks = await self.get_jwks()
        key = self._find_key(jwks, kid)
        if key is None:
            jwks = await self.get_jwks(force_refresh=True)
            key = self._find_key(jwks, kid)
        if key is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, ...)
        return key


_jwks_provider = CognitoJWKSProvider(
    region=settings.aws_region,
    user_pool_id=settings.cognito_user_pool_id,
)


async def verify_cognito_token(token: str) -> dict[str, object]:
    key = await _jwks_provider.get_signing_key(token)
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.cognito_app_client_id,
            issuer=_jwks_provider.issuer_url,
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return claims
```

```python
# app/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal
from app.core.auth import verify_cognito_token
from app.models.profile import Profile
from sqlalchemy import select

_bearer_scheme = HTTPBearer()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    claims = await verify_cognito_token(credentials.credentials)
    cognito_sub = uuid.UUID(str(claims["sub"]))
    result = await db.execute(select(Profile).where(Profile.id == cognito_sub))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return profile
```

**Rules:**
- Extract `user_id` from JWT claims — NEVER accept `user_id` in request body.
- Cache JWKS; do not fetch on every request.
- All protected routes use `current_user: Profile = Depends(get_current_user)`.

---

## 6. Cursor-Based Pagination (Mandatory)

**OFFSET/LIMIT pagination is forbidden.** Every list endpoint must use cursor pagination.

```python
# app/utils/cursor.py
import base64
import json
from datetime import datetime


def encode_cursor(created_at: datetime, id: str) -> str:
    payload = {"ts": created_at.isoformat(), "id": id}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    payload = json.loads(base64.urlsafe_b64decode(cursor).decode())
    return datetime.fromisoformat(payload["ts"]), payload["id"]
```

```python
# In MessageService
from app.utils.cursor import encode_cursor, decode_cursor
from sqlalchemy import and_, or_, select, tuple_


async def list_messages(
    self,
    user_id: str,
    character_id: str,
    cursor: str | None,
    limit: int,
) -> MessagePage:
    stmt = (
        select(Message)
        .where(
            Message.user_id == user_id,
            Message.character_id == character_id,
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit + 1)
    )

    if cursor:
        ts, mid = decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Message.created_at < ts,
                and_(Message.created_at == ts, Message.id < mid),
            )
        )

    result = await self.db.execute(stmt)
    rows = result.scalars().all()

    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = encode_cursor(items[-1].created_at, items[-1].id) if has_more else None

    return MessagePage(
        items=[MessageResponse.model_validate(m) for m in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )
```

**Rules:**
- Cursor encodes `(created_at, id)` for stable ordering.
- Index on `(user_id, character_id, created_at DESC, id DESC)` is required.
- Never use `OFFSET`. Never use `page` query params.
- Return `next_cursor: null` when no more pages.

---

## 7. Parallel Operations with asyncio.gather

Use `asyncio.gather` when two or more independent async operations can run concurrently.

```python
import asyncio
from app.services.memory_service import MemoryService
from app.services.character_service import CharacterService


async def build_context(user_id: str, character_id: str, db):
    memory_svc = MemoryService()
    char_svc = CharacterService(db)

    memories, character, history = await asyncio.gather(
        memory_svc.search(user_id=user_id, character_id=character_id, query="..."),
        char_svc.get(character_id),
        char_svc.get_recent_messages(character_id, user_id, limit=30),
    )
    return memories, character, history
```

**Rules:**
- Never `await` sequentially when operations are independent.
- Use `asyncio.gather(*coros, return_exceptions=True)` when partial failure is acceptable; check each result individually.
- Do not mix sync blocking calls inside `gather` — wrap with `asyncio.to_thread` if needed.

---

## 8. SSE Streaming

```python
# app/routes/chat.py (streaming)
import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.dependencies import get_current_user, get_db
from app.models.profile import Profile
from app.schemas.chat import SendMessageRequest
from app.services.chat_service import ChatService

router = APIRouter()


@router.post("/{character_id}/messages")
async def send_message(
    character_id: uuid.UUID,
    body: SendMessageRequest,
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    service = ChatService(db)
    context = await service.validate_send_message(
        character_id=character_id,
        user_id=current_user.id,
        profile=current_user,
        content=body.content,
    )

    return StreamingResponse(
        service.stream_response(
            context=context,
            user_id=current_user.id,
            profile=current_user,
            content=body.content,
            media_url=body.media_url,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

### SSE Event Models

```python
# app/schemas/chat.py — SSE event types
from pydantic import BaseModel

class ChunkEvent(BaseModel):
    type: str = "chunk"
    content: str

class ActionEvent(BaseModel):
    type: str = "action"
    action: str
    payload: dict[str, Any]

class DoneEvent(BaseModel):
    type: str = "done"
    message_id: str

class ErrorEvent(BaseModel):
    type: str = "error"
    message: str
```

### SSE Event Wire Format

```
data: {"type": "chunk", "content": "Great"}
data: {"type": "chunk", "content": "! Let's start"}
data: {"type": "action", "action": "SET_ALARM", "payload": {"time": "07:00"}}
data: {"type": "done", "message_id": "uuid-here"}
data: {"type": "error", "message": "LLM service unavailable"}
```

**Rules:**
- Always set `Cache-Control: no-cache` and `X-Accel-Buffering: no`.
- Use typed JSON events (`ChunkEvent`, `ActionEvent`, `DoneEvent`, `ErrorEvent`).
- The `done` event is always the last event and contains the saved `message_id`.
- Each SSE message: `data: <json>\n\n` (double newline).
- Clients must handle partial JSON — always send complete JSON objects per chunk.

---

## 9. Mem0 Memory Layer

```python
# app/services/memory_service.py
import asyncio
from mem0 import MemoryClient
from app.config import settings
from app.core.circuit_breaker import get_mem0_circuit_breaker
from app.utils.timing import log_external_call


class MemoryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_character_memories(
        self,
        character_id: uuid.UUID,
        user_id: uuid.UUID,
        mem0_user_id: str,
    ) -> list[MemoryItem]:
        character = await self._get_owned_character(character_id, user_id)
        breaker = get_mem0_circuit_breaker()

        async def _do_get_all() -> list[dict[str, object]]:
            client = MemoryClient(api_key=settings.mem0_api_key)
            async with log_external_call("mem0", "get_all"):
                return await asyncio.to_thread(
                    client.get_all,
                    user_id=mem0_user_id,
                    agent_id=character.mem0_agent_id,
                )

        results = await breaker.call_with_breaker(_do_get_all)
        return self._map_memories(results)
```

**Rules:**
- `agent_id` format is always `{template_id}_{user_id}` — never deviate.
- Always pass both `user_id` and `agent_id` for per-character isolation.
- The mem0 SDK provides a sync `MemoryClient`. All calls must be wrapped in `asyncio.to_thread()` to avoid blocking the event loop.
- All Mem0 calls go through the circuit breaker (`get_mem0_circuit_breaker()`).
- Memory is searched before building the LLM prompt, in parallel with history retrieval.

---

## 10. Claude / Multi-Provider LLM

The LLM layer is a package at `app/services/llm/` with provider abstraction, an Anthropic
and OpenAI implementation, and a router singleton that selects the active provider.

```python
# app/services/llm/provider.py — ABC
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self, system: str, messages: list[dict[str, str]],
        model: str | None = None, max_tokens: int = 1024, temperature: float = 0.8,
    ) -> str: ...

    @abstractmethod
    def stream(
        self, system: str, messages: list[dict[str, str]],
        model: str | None = None, max_tokens: int = 1024, temperature: float = 0.8,
    ) -> AsyncIterator[str]: ...

    @abstractmethod
    async def complete_fast(
        self, system: str, messages: list[dict[str, str]],
        max_tokens: int = 256, temperature: float = 0.0,
    ) -> str:
        """Fast/cheap completion for classification tasks.
        Uses the provider's fast model automatically (e.g. claude-haiku)."""
```

```python
# app/services/llm/router.py — singleton
from app.services.llm.anthropic_provider import AnthropicProvider
from app.services.llm.openai_provider import OpenAIProvider
from app.services.llm.provider import LLMProvider


class LLMRouter:
    """Routes LLM requests to the configured provider."""

    def __init__(self, settings: Settings) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._default: str = settings.llm_provider
        if settings.anthropic_api_key:
            self._providers["claude"] = AnthropicProvider(settings)
        if settings.openai_api_key:
            self._providers["openai"] = OpenAIProvider(settings)

    def get(self, provider: str | None = None) -> LLMProvider:
        name = provider or self._default
        return self._providers[name]


_router_instance: LLMRouter | None = None

def get_llm_router() -> LLMRouter:
    global _router_instance
    if _router_instance is None:
        from app.config import settings
        _router_instance = LLMRouter(settings)
    return _router_instance
```

**Rules:**
- All LLM calls go through `get_llm_router().get()` to obtain a `LLMProvider`.
- Default provider is `claude`. Config drives switching via `LLM_PROVIDER` env var.
- Use `complete_fast()` for fast/cheap ops (classification, short summaries) — it auto-selects the haiku model.
- Use `complete()` or `stream()` for main conversations.
- Never import `anthropic` directly in route files — use service layer.

---

## 11. Error Handling

```python
# Consistent error responses
from fastapi import HTTPException, status

# 400 — Bad Request
raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="content cannot be empty")

# 401 — Unauthorized
raise HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid token",
    headers={"WWW-Authenticate": "Bearer"},
)

# 403 — Forbidden (authenticated but not allowed)
raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Character does not belong to user")

# 404 — Not Found
raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")

# 429 — Rate Limited
raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")

# 503 — External Service Down
raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="LLM service unavailable")
```

### Global Exception Handler

```python
# app/main.py
from fastapi import Request
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
```

**Error response format** (always):
```json
{"detail": "Human-readable message"}
```

---

## 12. Environment Variables and Secrets

```python
# app/config.py
import json
import logging
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("ember")


def _load_secret(secret_name: str, region: str) -> dict[str, object]:
    import boto3
    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response["SecretString"])


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # App
    app_name: str = "Ember"
    app_version: str = "1.0.0"
    debug: bool = False
    log_level: str = "INFO"

    # AWS
    aws_region: str = "us-east-1"
    aws_secret_name: str = "ember/prod/secrets"

    # Database
    database_url: str = ""

    # Cognito
    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""

    # LLM
    llm_provider: str = "claude"
    claude_model: str = "claude-sonnet-4-6"
    claude_haiku_model: str = "claude-haiku-4-5"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_fast_model: str = "gpt-4o-mini"

    # Memory
    mem0_api_key: str = ""

    # Circuit Breaker
    mem0_circuit_failure_threshold: int = 3
    mem0_circuit_recovery_timeout: float = 60.0
    mem0_cache_ttl: float = 300.0
    mem0_retry_queue_max_size: int = 100

    # Chat context
    max_context_messages: int = 50

    # Voice
    elevenlabs_api_key: str = ""

    # Storage
    s3_bucket_name: str = ""

    # Push Notifications
    firebase_credentials_json: str = ""

    # Notification Scheduler
    notification_scheduler_enabled: bool = True
    notification_scheduler_interval_minutes: int = 30
    notification_batch_size: int = 100

    # Rate Limiting (requests per minute per user)
    rate_limit_chat: int = 10
    rate_limit_write: int = 20
    rate_limit_read: int = 60

    # CORS
    cors_origins: str = "*"

    # Observability — Sentry
    sentry_dsn: str = ""
    sentry_environment: str = "development"
    sentry_traces_sample_rate: float = 0.1

    # Observability — Health Check
    health_check_timeout: float = 3.0
    health_check_degraded_threshold: float = 1.0

    # Observability — Logging
    log_request_body: bool = False

    # Content Moderation
    moderation_enabled: bool = True
    moderation_fail_open: bool = True
    moderation_abuse_window_hours: int = 24
    moderation_block_duration_short_minutes: int = 15
    moderation_block_duration_long_minutes: int = 60

    def model_post_init(self, __context: object) -> None:
        if not self.debug and self.aws_secret_name:
            try:
                secrets = _load_secret(self.aws_secret_name, self.aws_region)
                for key, value in secrets.items():
                    if hasattr(self, key):
                        object.__setattr__(self, key, value)
            except Exception:
                logger.warning(
                    "Failed to load secrets from AWS Secrets Manager. "
                    "Falling back to environment variables.",
                    exc_info=True,
                )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
```

**Rules:**
- Never hardcode secrets in source code.
- Local development: `.env` file (gitignored).
- Production: AWS Secrets Manager.
- Never commit `.env` files. `.env.example` (empty values) is allowed.

---

## 13. Dependency Injection Pattern

The `dependencies.py` module exports exactly two dependencies: `get_db` and `get_current_user`.
Service classes are instantiated directly in route handlers, not via `Depends()`.

```python
# app/dependencies.py — only two exports
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    ...
```

```python
# Usage in route handlers — services constructed directly
@router.post("/{character_id}/messages")
async def send_message(
    character_id: uuid.UUID,
    body: SendMessageRequest,
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    service = ChatService(db)
    context = await service.validate_send_message(...)
    return StreamingResponse(service.stream_response(...), ...)
```

---

## 14. Alembic Migrations

```
alembic revision --autogenerate -m "add messages table"
alembic upgrade head
alembic downgrade -1
```

```python
# db/migrations/env.py — async pattern
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from app.models.base import Base
from app.models import *  # ensure all models are imported

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


async def run_migrations_online():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
```

**Rules:**
- Every schema change requires a migration.
- Never `ALTER TABLE` manually in production.
- Migration files are committed to git.
- Always test `upgrade` and `downgrade` before merging.

---

## 15. Testing Patterns

```python
# tests/conftest.py — default mock-based conftest (unit tests)
import os
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://ember:ember@localhost:5432/ember_test")

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.dependencies import get_db
from app.main import app


async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
    yield AsyncMock()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
```

**Integration test conftest pattern** (for tests needing a real database):

```python
# tests/integration/conftest.py — real-DB integration tests
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.dependencies import get_db, get_current_user
from app.models.base import Base
from app.models.profile import Profile

TEST_DB_URL = "postgresql+asyncpg://ember:ember@localhost/ember_test"
test_engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db():
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()
```

```python
# tests/routes/test_chat.py
import pytest


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_returns_sse_stream_with_valid_body(self, client):
        # Mock auth + service layers as needed per test
        ...

    @pytest.mark.asyncio
    async def test_returns_422_with_empty_content(self, client):
        response = await client.post(
            "/api/v1/characters/char-1/messages",
            json={"content": ""},
        )
        assert response.status_code == 422


class TestListMessages:
    @pytest.mark.asyncio
    async def test_returns_200_with_pagination_shape(self, client):
        response = await client.get("/api/v1/characters/char-1/messages?limit=2")
        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert "has_more" in body
        assert "next_cursor" in body
```

### Mocking External Services

```python
# tests/services/test_chat_service.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.mark.asyncio
async def test_chat_service_calls_mem0(db):
    with patch("app.services.memory_service.MemoryClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.search.return_value = []
        mock_client_cls.return_value = mock_client

        with patch("app.services.llm.router.get_llm_router") as mock_router:
            mock_provider = AsyncMock()
            mock_provider.stream.return_value = AsyncMock()
            mock_router.return_value.get.return_value = mock_provider

            from app.services.chat_service import ChatService
            svc = ChatService(db)
            # ... test logic
```

---

## 16. Code Style

```toml
# pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py312"
select = ["E", "F", "I", "N", "UP", "ANN", "ASYNC"]
ignore = ["ANN101", "ANN102"]

[tool.black]
line-length = 100
target-version = ["py312"]

[tool.mypy]
strict = true
python_version = "3.12"
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

**Rules:**
- All code passes `ruff check`, `black --check`, and `mypy --strict`.
- Type annotations required on all functions (including return type).
- No `Any` unless absolutely unavoidable — document why.
- Max line length: 100.
- Imports: stdlib, third-party, local — separated by blank lines (ruff `I` enforces this).
- No `print()` in production code — use `logging`.
