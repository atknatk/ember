"""STT route handlers.

Provides a single endpoint for transcribing audio to text using OpenAI
Whisper API. All endpoints require JWT authentication. Business logic
is delegated to STTService.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.models.profile import Profile
from app.schemas.stt import STTRequest, STTResponse
from app.services.stt_service import STTService

router = APIRouter()


@router.post("/stt", response_model=STTResponse)
async def transcribe_audio(
    body: STTRequest,
    current_user: Profile = Depends(get_current_user),
) -> STTResponse:
    """Transcribe audio from an S3 URL to text.

    Downloads audio from S3, validates format (M4A, MP3, WAV, OGG) and
    size (max 25MB), sends to OpenAI Whisper API for transcription, and
    returns the transcript with detected language and confidence score.
    """
    service = STTService()
    result = await service.transcribe(audio_url=body.audio_url)

    return STTResponse(
        transcript=str(result["transcript"]),
        language=str(result["language"]),
        confidence=float(result["confidence"]),  # type: ignore[arg-type]
        duration_seconds=(
            float(result["duration_seconds"])
            if result.get("duration_seconds") is not None
            else None
        ),
    )
