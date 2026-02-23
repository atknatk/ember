"""Shared FastAPI dependency injection functions.

Provides get_db for database session management and get_current_user
for JWT authentication (stubbed until P01-03 auth feature).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import NoReturn

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session, ensuring cleanup on exit."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user() -> NoReturn:
    """Stub for JWT authentication. Implemented in P01-03 (user-auth).

    Raises:
        HTTPException: Always raises 501 Not Implemented.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Authentication not yet implemented",
    )
