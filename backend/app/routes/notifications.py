"""Notification route handlers -- PUT and DELETE /notifications/token.

Provides endpoints for registering and unregistering FCM device tokens
used for push notifications. All business logic for token persistence
is handled directly in the route handlers (simple CRUD, no service needed).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.profile import Profile
from app.schemas.notifications import FcmTokenRequest, FcmTokenResponse

router = APIRouter()


@router.put("/notifications/token", response_model=FcmTokenResponse)
async def register_fcm_token(
    body: FcmTokenRequest,
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FcmTokenResponse:
    """Register or update the authenticated user's FCM device token.

    Idempotent -- calling with the same token multiple times has the same effect.
    Each user has exactly one FCM token at a time (the latest device).
    """
    await db.execute(
        update(Profile)
        .where(Profile.id == current_user.id)
        .values(fcm_token=body.fcm_token),
    )
    await db.commit()
    return FcmTokenResponse(status="ok")


@router.delete(
    "/notifications/token",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unregister_fcm_token(
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Unregister the authenticated user's FCM token.

    Used when the user disables notifications or logs out.
    Idempotent -- returns 204 regardless of whether a token was previously stored.
    """
    await db.execute(
        update(Profile)
        .where(Profile.id == current_user.id)
        .values(fcm_token=None),
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
