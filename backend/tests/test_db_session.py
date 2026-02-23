"""Tests for the database session factory.

Verifies engine configuration (pool_size, pool_pre_ping) and
session factory settings (expire_on_commit, autoflush).
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.session import AsyncSessionLocal, engine


@pytest.mark.asyncio
async def test_engine_is_async_engine() -> None:
    """The module-level engine must be an AsyncEngine instance."""
    assert isinstance(engine, AsyncEngine)


@pytest.mark.asyncio
async def test_engine_pool_size_is_20() -> None:
    """Engine pool_size must be 20 as specified in the spec."""
    # pool_size is set on the sync engine underneath
    assert engine.pool.size() == 20


@pytest.mark.asyncio
async def test_engine_pool_pre_ping_enabled() -> None:
    """Engine must have pool_pre_ping=True for connection health checks."""
    assert engine.pool._pre_ping is True


@pytest.mark.asyncio
async def test_session_factory_is_async_sessionmaker() -> None:
    """AsyncSessionLocal must be an async_sessionmaker instance."""
    assert isinstance(AsyncSessionLocal, async_sessionmaker)


@pytest.mark.asyncio
async def test_session_factory_expire_on_commit_false() -> None:
    """Session factory must have expire_on_commit=False."""
    assert AsyncSessionLocal.kw.get("expire_on_commit") is False


@pytest.mark.asyncio
async def test_session_factory_autoflush_false() -> None:
    """Session factory must have autoflush=False."""
    assert AsyncSessionLocal.kw.get("autoflush") is False


@pytest.mark.asyncio
async def test_session_factory_class_is_async_session() -> None:
    """Session factory must produce AsyncSession instances."""
    assert AsyncSessionLocal.class_ is AsyncSession
