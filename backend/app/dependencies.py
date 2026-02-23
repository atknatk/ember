"""Shared FastAPI dependency injection functions.

Provides get_db for database session management and get_current_user
for JWT authentication via AWS Cognito.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import verify_cognito_token
from app.db.session import AsyncSessionLocal
from app.models.profile import Profile

_bearer_scheme = HTTPBearer()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session, ensuring cleanup on exit."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    """Authenticate the request and return the current user's Profile.

    Extracts the Bearer token from the Authorization header, verifies it
    against Cognito JWKS, and looks up the corresponding profile in the
    database.

    Args:
        credentials: The Bearer token extracted by FastAPI's HTTPBearer.
        db: The async database session.

    Returns:
        The authenticated user's Profile ORM object.

    Raises:
        HTTPException: 401 if the token is missing, invalid, expired,
            or the user is not found in the database.
    """
    claims = await verify_cognito_token(credentials.credentials)
    cognito_sub = uuid.UUID(str(claims["sub"]))

    result = await db.execute(
        select(Profile).where(Profile.id == cognito_sub),
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return profile
