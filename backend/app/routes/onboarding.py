"""Onboarding route handler -- POST /api/v1/onboarding/complete.

Receives 7 onboarding Q&A answers, converts them to Mem0 memories via
Claude Haiku, seeds global memories, and marks the profile as onboarded.
All business logic is delegated to OnboardingService.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.profile import Profile
from app.schemas.onboarding import OnboardingRequest, OnboardingResponse
from app.services.onboarding_service import OnboardingService

router = APIRouter()


@router.post("/complete", response_model=OnboardingResponse)
async def complete_onboarding(
    body: OnboardingRequest,
    profile: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingResponse:
    """Complete the user onboarding flow.

    Accepts 7 Q&A pairs, converts them to structured memory statements
    via Claude Haiku, seeds them into Mem0 as global memories, and sets
    ``profiles.onboarding_completed = true``.

    Returns 409 if onboarding has already been completed.
    Returns 503 if Claude Haiku or Mem0 is unavailable.
    """
    service = OnboardingService(db)
    return await service.complete_onboarding(
        profile=profile,
        answers=body.answers,
    )
