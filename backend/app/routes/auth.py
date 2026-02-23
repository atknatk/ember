"""Authentication route handlers — register, login, refresh.

All three endpoints are public (no JWT required). Business logic is
delegated to AuthService; route handlers only validate input and
return responses.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
)
from app.services.auth_service import AuthService

router = APIRouter()


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Create a new user account.

    Registers the user in AWS Cognito, creates a profile row, initialises
    a default 'Ember' companion character, and returns tokens + user data.
    """
    service = AuthService(db)
    return await service.register(
        email=body.email,
        password=body.password,
        name=body.name,
    )


@router.post(
    "/login",
    response_model=AuthResponse,
)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    """Authenticate an existing user and return tokens + profile."""
    service = AuthService(db)
    return await service.login(
        email=body.email,
        password=body.password,
    )


@router.post(
    "/refresh",
    response_model=RefreshResponse,
)
async def refresh(
    body: RefreshRequest,
) -> RefreshResponse:
    """Exchange a refresh token for a new access (ID) token.

    The database is not needed for this endpoint since it only calls
    Cognito's REFRESH_TOKEN_AUTH flow.
    """
    service = AuthService(db=None)  # type: ignore[arg-type]
    return await service.refresh(refresh_token=body.refresh_token)
