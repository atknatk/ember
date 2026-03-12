"""Profile route handlers -- GET, PUT /profile and DELETE /profile/account.

Provides endpoints for viewing and updating the user's profile, and for
GDPR-compliant full account deletion. All business logic is delegated
to ProfileService.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.profile import Profile
from app.schemas.profile import AccountDeleteRequest, ProfileResponse, ProfileUpdateRequest
from app.services.profile_service import ProfileService

router = APIRouter()


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    current_user: Profile = Depends(get_current_user),
) -> ProfileResponse:
    """Return the authenticated user's profile data."""
    service = ProfileService.__new__(ProfileService)
    return service.get_profile(current_user)


@router.put("/profile", response_model=ProfileResponse)
async def update_profile(
    body: ProfileUpdateRequest,
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Update mutable profile fields. Only provided fields are changed."""
    service = ProfileService(db)
    return await service.update_profile(user=current_user, body=body)


@router.delete(
    "/profile/account",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_account(
    body: AccountDeleteRequest,
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """GDPR-compliant full account deletion.

    Requires the confirmation text ``"DELETE MY ACCOUNT"`` in the request body.
    Permanently removes all user data across DB, Mem0, S3, and Cognito.
    """
    if body.confirmation != "DELETE MY ACCOUNT":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation text must be exactly 'DELETE MY ACCOUNT'",
        )

    service = ProfileService(db)
    await service.delete_account(user=current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
