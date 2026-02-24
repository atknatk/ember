"""Media service -- business logic for S3 presigned URL generation.

Handles content type validation, filename sanitization, S3 key construction,
and presigned PUT URL generation via boto3. All S3 interactions are
contained in this module; route handlers never import boto3 directly.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, status

from app.config import settings
from app.schemas.media import UploadUrlResponse

logger = logging.getLogger("ember")

# Content type whitelist per media type
ALLOWED_CONTENT_TYPES: dict[str, frozenset[str]] = {
    "photo": frozenset({"image/jpeg", "image/png", "image/heic"}),
    "audio": frozenset({"audio/m4a", "audio/mp3", "audio/mpeg"}),
    "tts": frozenset({"audio/mp3", "audio/mpeg"}),
}

# Presigned URL expiration in seconds
_PRESIGNED_URL_EXPIRATION = 300

# Module-level S3 client (reused across requests)
_s3_client = boto3.client("s3", region_name=settings.aws_region)


def _sanitize_filename(filename: str) -> str:
    """Sanitize a filename for safe use in S3 keys.

    - Strips path separators (/, \\) and null bytes.
    - Replaces spaces with underscores.
    - Removes characters that are not alphanumeric, hyphens, underscores, or dots.
    - Truncates the name portion (excluding extension) to 100 characters.
    - Falls back to "upload" if the filename becomes empty after sanitization.
    """
    # Strip path separators and null bytes
    sanitized = filename.replace("/", "").replace("\\", "").replace("\x00", "")

    # Replace spaces with underscores
    sanitized = sanitized.replace(" ", "_")

    # Remove unsafe characters, keeping only alphanumeric, hyphens, underscores, dots
    sanitized = re.sub(r"[^\w\-.]", "", sanitized)

    # Split into name and extension for truncation
    dot_idx = sanitized.rfind(".")
    if dot_idx > 0:
        name = sanitized[:dot_idx]
        ext = sanitized[dot_idx:]
        name = name[:100]
        sanitized = name + ext
    else:
        sanitized = sanitized[:100]

    # Fall back to "upload" if empty
    if not sanitized or sanitized.startswith("."):
        sanitized = "upload"

    return sanitized


class MediaService:
    """Encapsulates presigned URL generation for S3 file uploads."""

    async def generate_upload_url(
        self,
        user_id: uuid.UUID,
        filename: str,
        content_type: str,
        media_type: str,
    ) -> UploadUrlResponse:
        """Generate a presigned S3 PUT URL for file upload.

        Args:
            user_id: The authenticated user's profile UUID.
            filename: Original filename from the client (already Pydantic-validated).
            content_type: MIME type of the file.
            media_type: Media category (photo, audio, tts).

        Returns:
            UploadUrlResponse with presigned upload_url and permanent file_url.

        Raises:
            HTTPException(400): Content type not allowed for the given media type.
            HTTPException(503): S3 presigned URL generation failed.
        """
        # Validate content type against whitelist
        allowed = ALLOWED_CONTENT_TYPES.get(media_type)
        if allowed is None or content_type not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Content type '{content_type}' is not allowed for type '{media_type}'",
            )

        # Sanitize filename
        sanitized_filename = _sanitize_filename(filename)

        # Construct S3 key
        file_uuid = uuid.uuid4()
        s3_key = f"{media_type}/{user_id}/{file_uuid}_{sanitized_filename}"

        # Generate presigned PUT URL via boto3 (wrapped in asyncio.to_thread for safety)
        try:
            upload_url = await asyncio.to_thread(
                _s3_client.generate_presigned_url,
                "put_object",
                Params={
                    "Bucket": settings.s3_bucket_name,
                    "Key": s3_key,
                    "ContentType": content_type,
                },
                ExpiresIn=_PRESIGNED_URL_EXPIRATION,
                HttpMethod="PUT",
            )
        except (ClientError, Exception):
            logger.exception(
                "S3 presigned URL generation failed for user_id=%s, s3_key=%s",
                user_id,
                s3_key,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage service unavailable",
            ) from None

        # Construct permanent file URL
        file_url = (
            f"https://{settings.s3_bucket_name}"
            f".s3.{settings.aws_region}.amazonaws.com/{s3_key}"
        )

        return UploadUrlResponse(upload_url=upload_url, file_url=file_url)
