"""TTS route handlers.

Provides a single endpoint for converting text to speech using ElevenLabs
(primary) or AWS Polly (fallback). All endpoints require JWT authentication.
Business logic is delegated to TTSService.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.profile import Profile
from app.schemas.tts import TTSRequest, TTSResponse
from app.services.tts_service import TTSService

router = APIRouter()


@router.post("/tts", response_model=TTSResponse)
async def synthesize_speech(
    body: TTSRequest,
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TTSResponse:
    """Convert text to speech and return an S3 audio URL.

    Uses ElevenLabs Flash v2.5 as the primary TTS provider with AWS Polly
    as fallback. Short texts (< 150 characters) are routed directly to
    Polly for lower latency and cost. Generated audio is cached in S3
    using hash-based keys for deduplication.
    """
    service = TTSService(db)
    return await service.synthesize(
        user_id=current_user.id,
        character_id=body.character_id,
        text=body.text,
        voice_id=body.voice_id,
        language=body.language,
    )
