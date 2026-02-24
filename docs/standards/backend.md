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
    main.py                  # FastAPI app factory, lifespan, CORS
    config.py                # Settings (pydantic-settings), reads env/secrets
    dependencies.py          # Shared FastAPI Depends functions
    routes/
      __init__.py
      auth.py
      characters.py
      chat.py
      memories.py
      voice.py
    services/
      __init__.py
      character_service.py
      message_service.py
      memory_service.py
      llm_service.py
      voice_service.py
    models/
      __init__.py
      base.py                # DeclarativeBase, TimestampMixin
      profile.py
      character.py
      conversation.py
      message.py
    schemas/
      __init__.py
      character.py           # Request/Response Pydantic models
      message.py
      pagination.py
    utils/
      __init__.py
      cursor.py              # Cursor encode/decode helpers
      streaming.py           # SSE helpers
      cognito.py             # Token verification
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
from app.db.session import engine
from app.models.base import Base
from app.routes import auth, characters, chat, health, memories, voice


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Ember API", version="1.0.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # tighten in prod via config
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(characters.router, prefix="/api/v1/characters", tags=["characters"])
    app.include_router(chat.router, prefix="/api/v1/characters", tags=["messages"])
    app.include_router(memories.router, prefix="/api/v1", tags=["memories"])
    app.include_router(voice.router, prefix="/api/v1/voice", tags=["voice"])

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
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/{character_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    character_id: str,
    body: MessageRequest,
    current_user: User = Depends(get_current_user),
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
    limit: int = 30,
    current_user: User = Depends(get_current_user),
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
# app/schemas/message.py
from pydantic import BaseModel, Field, field_validator
from typing import Literal


class MessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)
    modality: Literal["text", "voice"] = "text"

    @field_validator("content")
    @classmethod
    def strip_content(cls, v: str) -> str:
        return v.strip()
```

### Response Schema

```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
```

### Pagination Schema

```python
from pydantic import BaseModel


class MessagePage(BaseModel):
    items: list[MessageResponse]
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
# app/utils/cognito.py
import httpx
from jose import JWTError, jwk, jwt
from jose.utils import base64url_decode
from fastapi import HTTPException, status
from app.config import settings

_jwks_cache: dict | None = None


async def get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is None:
        url = (
            f"https://cognito-idp.{settings.aws_region}.amazonaws.com/"
            f"{settings.cognito_user_pool_id}/.well-known/jwks.json"
        )
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=5)
            resp.raise_for_status()
            _jwks_cache = resp.json()
    return _jwks_cache


async def verify_token(token: str) -> dict:
    try:
        jwks = await get_jwks()
        header = jwt.get_unverified_header(token)
        key = next(k for k in jwks["keys"] if k["kid"] == header["kid"])
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.cognito_app_client_id,
        )
        return claims
    except (JWTError, StopIteration) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
```

```python
# app/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal
from app.utils.cognito import verify_token
from app.models.profile import Profile
from sqlalchemy import select

bearer_scheme = HTTPBearer()


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    claims = await verify_token(credentials.credentials)
    cognito_sub = claims["sub"]
    result = await db.execute(select(Profile).where(Profile.id == cognito_sub))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
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
# app/routes/messages.py (streaming variant)
import asyncio
import json
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.dependencies import get_current_user, get_db
from app.services.message_service import MessageService

router = APIRouter()


@router.post("/{character_id}/messages/stream")
async def stream_message(
    character_id: str,
    body: MessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = MessageService(db)

    async def event_generator():
        async for chunk in service.stream(
            user_id=current_user.id,
            character_id=character_id,
            content=body.content,
        ):
            yield f"data: {json.dumps({'delta': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

```python
# app/services/llm_service.py — streaming from Claude
from anthropic import AsyncAnthropic
from app.config import settings

client = AsyncAnthropic(api_key=settings.anthropic_api_key)


async def stream_completion(messages: list[dict], system: str):
    async with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system,
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text
```

**Rules:**
- Always set `Cache-Control: no-cache` and `X-Accel-Buffering: no`.
- Terminate the stream with `data: [DONE]\n\n`.
- Each SSE message: `data: <json>\n\n` (double newline).
- Clients must handle partial JSON — always send complete JSON objects per chunk.

---

## 9. Mem0 Memory Layer

```python
# app/services/memory_service.py
from mem0 import AsyncMemoryClient
from app.config import settings

_client: AsyncMemoryClient | None = None


def get_mem0_client() -> AsyncMemoryClient:
    global _client
    if _client is None:
        _client = AsyncMemoryClient(api_key=settings.mem0_api_key)
    return _client


def agent_id(template_id: str, user_id: str) -> str:
    """Canonical format: {template_id}_{user_id}"""
    return f"{template_id}_{user_id}"


class MemoryService:
    def __init__(self):
        self.client = get_mem0_client()

    async def add(self, messages: list[dict], user_id: str, template_id: str) -> None:
        await self.client.add(
            messages=messages,
            user_id=user_id,
            agent_id=agent_id(template_id, user_id),
        )

    async def search(
        self,
        query: str,
        user_id: str,
        template_id: str,
        limit: int = 10,
    ) -> list[dict]:
        results = await self.client.search(
            query=query,
            user_id=user_id,
            agent_id=agent_id(template_id, user_id),
            limit=limit,
        )
        return results

    async def get_all(self, user_id: str, template_id: str) -> list[dict]:
        return await self.client.get_all(
            user_id=user_id,
            agent_id=agent_id(template_id, user_id),
        )
```

**Rules:**
- `agent_id` format is always `{template_id}_{user_id}` — never deviate.
- Always pass both `user_id` and `agent_id` for per-character isolation.
- Prefer `AsyncMemoryClient` if available. The sync `MemoryClient` with `asyncio.to_thread()` is acceptable as fallback.
- Memory is searched before building the LLM prompt, in parallel with history retrieval.

---

## 10. Claude / Multi-Provider LLM

> **Status:** The `LLMProvider` abstraction is defined below but not yet implemented in the codebase.
> Current code uses `AsyncAnthropic` directly. Implementation planned in P1.5-05.

```python
# app/services/llm_service.py
from abc import ABC, abstractmethod
from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from app.config import settings


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, system: str, messages: list[dict]) -> str: ...

    @abstractmethod
    async def stream(self, system: str, messages: list[dict]):
        yield ""  # async generator


class ClaudeProvider(LLMProvider):
    def __init__(self):
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model  # e.g. "claude-sonnet-4-6"

    async def complete(self, system: str, messages: list[dict]) -> str:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system,
            messages=messages,
        )
        return response.content[0].text

    async def stream(self, system: str, messages: list[dict]):
        async with self.client.messages.stream(
            model=self.model,
            max_tokens=1024,
            system=system,
            messages=messages,
        ) as s:
            async for chunk in s.text_stream:
                yield chunk


class OpenAIProvider(LLMProvider):
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model  # e.g. "gpt-4o"

    async def complete(self, system: str, messages: list[dict]) -> str:
        all_messages = [{"role": "system", "content": system}] + messages
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=all_messages,
        )
        return response.choices[0].message.content

    async def stream(self, system: str, messages: list[dict]):
        all_messages = [{"role": "system", "content": system}] + messages
        async with await self.client.chat.completions.create(
            model=self.model,
            messages=all_messages,
            stream=True,
        ) as s:
            async for chunk in s:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content


def get_llm_provider() -> LLMProvider:
    provider = settings.llm_provider  # "claude" | "openai" | "gemini"
    if provider == "claude":
        return ClaudeProvider()
    elif provider == "openai":
        return OpenAIProvider()
    raise ValueError(f"Unknown LLM provider: {provider}")
```

**Rules:**
- All LLM calls go through the `LLMProvider` abstraction.
- Default provider is `claude`. Config drives switching.
- Use `claude-haiku` for fast/cheap ops (classification, short summaries).
- Use `claude-sonnet` for main conversations.
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
import boto3
import json
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_secret(secret_name: str) -> dict:
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response["SecretString"])


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

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
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Mem0
    mem0_api_key: str = ""

    # App
    debug: bool = False

    def model_post_init(self, __context) -> None:
        if not self.debug and self.aws_secret_name:
            secrets = _load_secret(self.aws_secret_name)
            for key, value in secrets.items():
                if hasattr(self, key):
                    object.__setattr__(self, key, value)


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

```python
# app/dependencies.py
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import AsyncSessionLocal
from app.services.memory_service import MemoryService
from app.services.llm_service import LLMProvider, get_llm_provider


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


def get_memory_service() -> MemoryService:
    return MemoryService()


def get_llm() -> LLMProvider:
    return get_llm_provider()


# Usage in route:
@router.post("/{character_id}/messages")
async def send_message(
    character_id: str,
    body: MessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    memory: MemoryService = Depends(get_memory_service),
    llm: LLMProvider = Depends(get_llm),
):
    ...
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
# tests/conftest.py
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.main import app
from app.dependencies import get_db, get_current_user
from app.models.base import Base
from app.models.user import User

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


@pytest_asyncio.fixture
async def client(db):
    fake_user = User(id="test-user-id", cognito_sub="test-sub", email="test@ember.ai")

    async def override_db():
        yield db

    async def override_user():
        return fake_user

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
```

```python
# tests/routes/test_messages.py
import pytest


@pytest.mark.asyncio
async def test_send_message_returns_201(client, db):
    response = await client.post(
        "/characters/char-1/messages",
        json={"content": "Hello Ember"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["role"] == "assistant"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_messages_cursor_pagination(client, db):
    # seed messages
    for i in range(5):
        await client.post("/characters/char-1/messages", json={"content": f"msg {i}"})

    resp1 = await client.get("/characters/char-1/messages?limit=2")
    assert resp1.status_code == 200
    page1 = resp1.json()
    assert len(page1["items"]) == 2
    assert page1["has_more"] is True

    resp2 = await client.get(f"/characters/char-1/messages?limit=2&cursor={page1['next_cursor']}")
    assert resp2.status_code == 200
    page2 = resp2.json()
    assert len(page2["items"]) == 2
```

### Mocking External Services

```python
# tests/services/test_message_service.py
from unittest.mock import AsyncMock, patch
import pytest


@pytest.mark.asyncio
async def test_message_service_calls_mem0(db):
    with patch("app.services.memory_service.MemoryService.search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        with patch("app.services.llm_service.ClaudeProvider.complete", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Hello, I'm Ember!"
            from app.services.message_service import MessageService
            svc = MessageService(db)
            result = await svc.send(user_id="u1", character_id="c1", content="Hi")
            assert result.content == "Hello, I'm Ember!"
            mock_search.assert_called_once()
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
