"""Media upload route handlers.

Provides a single endpoint for generating S3 presigned PUT URLs for
file uploads. All endpoints require JWT authentication. Business logic
is delegated to MediaService.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.models.profile import Profile
from app.schemas.media import UploadUrlRequest, UploadUrlResponse
from app.services.media_service import MediaService

router = APIRouter()


@router.post("/upload-url", response_model=UploadUrlResponse)
async def create_upload_url(
    body: UploadUrlRequest,
    current_user: Profile = Depends(get_current_user),
) -> UploadUrlResponse:
    """Generate a presigned S3 PUT URL for the client to upload a file.

    The client sends a filename, content type, and media type (photo/audio/tts).
    The backend validates the content type, generates an S3 key, creates a
    5-minute presigned PUT URL, and returns both the upload URL and the
    permanent file URL.
    """
    service = MediaService()
    return await service.generate_upload_url(
        user_id=current_user.id,
        filename=body.filename,
        content_type=body.content_type,
        media_type=body.type,
    )
