"""Async SQLAlchemy engine and session factory.

Creates the async engine with connection pooling and the session factory
used by the get_db dependency. When DATABASE_URL is not configured, a
placeholder URL is used so the module can be imported without error.
Actual database operations will fail with a clear connection error.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# Use a placeholder URL when database_url is not configured to allow
# module import without error (deferred connection pattern).
_database_url = settings.database_url or "postgresql+asyncpg://localhost/ember_placeholder"

engine = create_async_engine(
    _database_url,
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
