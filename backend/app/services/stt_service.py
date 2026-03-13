"""STT service — speech-to-text using OpenAI Whisper API.

Downloads audio from S3, validates format and size, sends to Whisper for
transcription, and returns transcript with detected language and confidence.
"""

from __future__ import annotations

import asyncio
import io
import logging
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError
from fastapi import HTTPException, status
from openai import OpenAI

from app.config import settings
from app.utils.timing import log_external_call

logger = logging.getLogger("ember")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum audio file size: 25MB (Whisper API limit)
_MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024

# Supported audio extensions
_SUPPORTED_EXTENSIONS = {".m4a", ".mp3", ".wav", ".ogg"}

# Extension to MIME type mapping for Whisper
_EXTENSION_MIME_MAP: dict[str, str] = {
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
}

# Module-level AWS S3 client (reused across requests)
_s3_client = boto3.client("s3", region_name=settings.aws_region)


# ---------------------------------------------------------------------------
# STT Service
# ---------------------------------------------------------------------------


class STTService:
    """Speech-to-Text service using OpenAI Whisper."""

    async def transcribe(self, audio_url: str) -> dict[str, object]:
        """Transcribe audio from an S3 URL using OpenAI Whisper.

        Flow:
        1. Parse the S3 URL to extract bucket and key.
        2. Download audio from S3.
        3. Validate file size (max 25MB).
        4. Send to Whisper API for transcription.
        5. Return transcript, language, confidence, and duration.

        Args:
            audio_url: S3 URL of the audio file.

        Returns:
            Dict with transcript, language, confidence, and duration_seconds.

        Raises:
            HTTPException(400): Unsupported audio format.
            HTTPException(413): File exceeds 25MB.
            HTTPException(503): S3 or Whisper API unavailable.
        """
        # Parse S3 URL
        bucket, key = self._parse_s3_url(audio_url)

        # Validate extension
        extension = self._get_extension(key)
        if extension not in _SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Unsupported audio format. "
                    "Supported formats: M4A, MP3, WAV, OGG"
                ),
            )

        # Download from S3
        audio_data = await self._download_from_s3(bucket, key)

        # Validate size
        if len(audio_data) > _MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Audio file exceeds maximum size of 25MB",
            )

        # Transcribe with Whisper
        result = await self._call_whisper(audio_data, key, extension)

        return result

    @staticmethod
    def _parse_s3_url(url: str) -> tuple[str, str]:
        """Parse an S3 URL into (bucket, key).

        Supports both virtual-hosted and path-style S3 URLs:
        - https://bucket.s3.region.amazonaws.com/key
        - https://s3.region.amazonaws.com/bucket/key
        """
        parsed = urlparse(url)
        host = parsed.hostname or ""

        if host.endswith(".amazonaws.com"):
            # Virtual-hosted style: bucket.s3.region.amazonaws.com/key
            parts = host.split(".")
            if parts[0] != "s3":
                bucket = parts[0]
                key = parsed.path.lstrip("/")
            else:
                # Path-style: s3.region.amazonaws.com/bucket/key
                path_parts = parsed.path.lstrip("/").split("/", 1)
                if len(path_parts) < 2:  # noqa: PLR2004
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid S3 URL format",
                    )
                bucket = path_parts[0]
                key = path_parts[1]
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid S3 URL: must be an amazonaws.com URL",
            )

        if not bucket or not key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid S3 URL format",
            )

        return bucket, key

    @staticmethod
    def _get_extension(key: str) -> str:
        """Extract the file extension from an S3 key, ignoring query params."""
        # Remove query string if present
        clean = key.split("?")[0]
        dot_idx = clean.rfind(".")
        if dot_idx == -1:
            return ""
        return clean[dot_idx:].lower()

    async def _download_from_s3(self, bucket: str, key: str) -> bytes:
        """Download audio file from S3."""
        try:
            async with log_external_call("s3", "get_object"):
                response = await asyncio.to_thread(
                    _s3_client.get_object,
                    Bucket=bucket,
                    Key=key,
                )
            body = response["Body"]
            audio_data: bytes = await asyncio.to_thread(body.read)
            return audio_data
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("NoSuchKey", "404"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Audio file not found at the provided URL",
                ) from None
            logger.exception("S3 download failed for bucket=%s key=%s", bucket, key)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage service unavailable",
            ) from None

    async def _call_whisper(
        self,
        audio_data: bytes,
        key: str,
        extension: str,
    ) -> dict[str, object]:
        """Send audio to OpenAI Whisper API for transcription."""
        if not settings.openai_api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="STT service not configured",
            )

        # Determine filename and content type
        filename = key.split("/")[-1]
        content_type = _EXTENSION_MIME_MAP.get(extension, "audio/mpeg")

        try:
            async with log_external_call("openai", "whisper_transcribe"):
                result = await asyncio.to_thread(
                    self._whisper_transcribe,
                    audio_data,
                    filename,
                    content_type,
                )
            return result
        except HTTPException:
            raise
        except Exception:
            logger.exception("Whisper transcription failed")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="STT service unavailable",
            ) from None

    @staticmethod
    def _whisper_transcribe(
        audio_data: bytes,
        filename: str,
        content_type: str,
    ) -> dict[str, object]:
        """Synchronous Whisper API call (run via asyncio.to_thread)."""
        client = OpenAI(api_key=settings.openai_api_key)

        audio_file = io.BytesIO(audio_data)
        audio_file.name = filename

        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
        )

        # Extract fields from the Whisper response
        transcript = getattr(transcription, "text", "") or ""
        language = getattr(transcription, "language", "unknown") or "unknown"
        duration = getattr(transcription, "duration", None)

        # Whisper verbose_json does not return a top-level confidence score.
        # We compute an average confidence from segment-level data if available.
        confidence = _compute_average_confidence(transcription)

        return {
            "transcript": transcript,
            "language": language,
            "confidence": confidence,
            "duration_seconds": float(duration) if duration is not None else None,
        }


def _compute_average_confidence(transcription: object) -> float:
    """Compute average confidence from Whisper segment-level data.

    Whisper verbose_json returns segments with avg_logprob. We convert
    logprob to a 0-1 confidence approximation. Returns 0.0 if no
    segment data is available.
    """
    segments = getattr(transcription, "segments", None)
    if not segments:
        return 0.0

    import math

    total = 0.0
    count = 0
    for segment in segments:
        avg_logprob = getattr(segment, "avg_logprob", None)
        if avg_logprob is None and isinstance(segment, dict):
            avg_logprob = segment.get("avg_logprob")
        if avg_logprob is not None:
            # Convert log probability to a 0-1 scale
            total += math.exp(avg_logprob)
            count += 1

    if count == 0:
        return 0.0

    return round(min(max(total / count, 0.0), 1.0), 4)
