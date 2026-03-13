"""TTS service — text-to-speech using ElevenLabs Flash v2.5 (primary) and AWS Polly (fallback).

Handles text-to-speech conversion, audio caching in S3, and circuit breaker
for ElevenLabs failures. Generated audio is stored as MP3 in S3 with
hash-based keys for deduplication.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

import boto3
import httpx
from botocore.exceptions import ClientError
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.character import Character
from app.schemas.tts import TTSResponse
from app.utils.timing import log_external_call

logger = logging.getLogger("ember")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# ElevenLabs API
_ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"
_ELEVENLABS_MODEL_ID = "eleven_flash_v2_5"
_ELEVENLABS_DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel (default)

# AWS Polly
_POLLY_VOICE_MAP: dict[str, str] = {
    "tr": "Burcu",
    "en": "Joanna",
    "de": "Vicki",
    "fr": "Lea",
    "es": "Lucia",
}
_POLLY_ENGINE = "neural"

# Short text threshold: texts < 150 chars go to Polly (cheaper/faster)
_SHORT_TEXT_THRESHOLD = 150

# S3 TTS audio path prefix
_S3_TTS_PREFIX = "tts"

# Module-level AWS clients (reused across requests)
_s3_client = boto3.client("s3", region_name=settings.aws_region)
_polly_client = boto3.client("polly", region_name=settings.aws_region)


# ---------------------------------------------------------------------------
# Circuit Breaker for ElevenLabs
# ---------------------------------------------------------------------------


class ElevenLabsCircuitState(StrEnum):
    """Possible states for the ElevenLabs circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class ElevenLabsCircuitOpenError(Exception):
    """Raised when a call is attempted while the ElevenLabs circuit is open."""


@dataclass
class ElevenLabsCircuitBreaker:
    """Circuit breaker for ElevenLabs API calls.

    Thread-safe for asyncio (single-threaded event loop, no locks needed).
    """

    failure_threshold: int = 3
    recovery_timeout: float = 60.0
    state: ElevenLabsCircuitState = field(default=ElevenLabsCircuitState.CLOSED)
    failure_count: int = field(default=0)
    _opened_at: float | None = field(default=None)

    def is_available(self) -> bool:
        """Check if requests can be attempted."""
        if self.state == ElevenLabsCircuitState.CLOSED:
            return True
        if self.state == ElevenLabsCircuitState.OPEN:
            if self._opened_at is not None and (
                time.monotonic() - self._opened_at >= self.recovery_timeout
            ):
                self.state = ElevenLabsCircuitState.HALF_OPEN
                logger.warning("ElevenLabs circuit breaker half-open, probing...")
                return True
            return False
        # HALF_OPEN — allow a single probe
        return True

    def record_success(self) -> None:
        """Record a successful ElevenLabs call."""
        self.failure_count = 0
        if self.state == ElevenLabsCircuitState.HALF_OPEN:
            self.state = ElevenLabsCircuitState.CLOSED
            self._opened_at = None
            logger.warning("ElevenLabs circuit breaker closed")

    def record_failure(self) -> None:
        """Record a failed ElevenLabs call."""
        self.failure_count += 1
        if self.state == ElevenLabsCircuitState.HALF_OPEN:
            self.state = ElevenLabsCircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning("ElevenLabs circuit breaker probe failed, reopening")
        elif (
            self.state == ElevenLabsCircuitState.CLOSED
            and self.failure_count >= self.failure_threshold
        ):
            self.state = ElevenLabsCircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning(
                "ElevenLabs circuit breaker opened after %d consecutive failures",
                self.failure_count,
            )

    def get_status(self) -> dict[str, str | int | None]:
        """Return circuit breaker status for diagnostics."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
        }


# Module-level circuit breaker singleton
_elevenlabs_breaker: ElevenLabsCircuitBreaker | None = None


def get_elevenlabs_circuit_breaker() -> ElevenLabsCircuitBreaker:
    """Return the module-level ElevenLabs circuit breaker singleton."""
    global _elevenlabs_breaker  # noqa: PLW0603
    if _elevenlabs_breaker is None:
        _elevenlabs_breaker = ElevenLabsCircuitBreaker()
    return _elevenlabs_breaker


# ---------------------------------------------------------------------------
# TTS Service
# ---------------------------------------------------------------------------


def _compute_audio_hash(text: str, voice_id: str, language: str) -> str:
    """Compute a deterministic hash for audio caching."""
    key_material = f"{text}|{voice_id}|{language}"
    return hashlib.sha256(key_material.encode()).hexdigest()[:32]


class TTSService:
    """Text-to-Speech service with ElevenLabs primary and Polly fallback."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def synthesize(
        self,
        user_id: uuid.UUID,
        character_id: str,
        text: str,
        voice_id: str | None = None,
        language: str = "en",
    ) -> TTSResponse:
        """Convert text to speech audio and return an S3 URL.

        Flow:
        1. Validate character ownership.
        2. Check S3 cache for existing audio (hash-based key).
        3. If not cached, synthesize using ElevenLabs (primary) or Polly (fallback).
        4. Upload to S3 and return the URL.

        Args:
            user_id: The authenticated user's profile UUID.
            character_id: The character UUID.
            text: The text to convert to speech.
            voice_id: Optional ElevenLabs voice ID override.
            language: Language code (e.g., "en", "tr").

        Returns:
            TTSResponse with audio_url and optional duration.

        Raises:
            HTTPException(404): Character not found.
            HTTPException(403): Character does not belong to user.
            HTTPException(503): Both TTS providers unavailable.
        """
        # Validate character ownership
        character = await self._get_owned_character(character_id, user_id)

        # Determine voice ID
        effective_voice_id = voice_id or _ELEVENLABS_DEFAULT_VOICE_ID

        # Check S3 cache
        audio_hash = _compute_audio_hash(text, effective_voice_id, language)
        s3_key = f"{_S3_TTS_PREFIX}/{user_id}/{audio_hash}.mp3"

        cached_url = await self._check_s3_cache(s3_key)
        if cached_url is not None:
            logger.debug("TTS cache hit for hash=%s", audio_hash)
            return TTSResponse(audio_url=cached_url, duration_seconds=None)

        # Synthesize audio
        audio_data = await self._synthesize_audio(
            text=text,
            voice_id=effective_voice_id,
            language=language,
            character=character,
        )

        # Upload to S3
        audio_url = await self._upload_to_s3(
            audio_data=audio_data,
            s3_key=s3_key,
        )

        return TTSResponse(audio_url=audio_url, duration_seconds=None)

    async def _get_owned_character(
        self,
        character_id: str,
        user_id: uuid.UUID,
    ) -> Character:
        """Fetch a character and verify ownership."""
        try:
            char_uuid = uuid.UUID(character_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Character not found",
            ) from None

        result = await self.db.execute(
            select(Character).where(
                Character.id == char_uuid,
                Character.is_active.is_(True),
            ),
        )
        character = result.scalar_one_or_none()

        if character is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Character not found",
            )

        if character.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Character does not belong to user",
            )

        return character

    async def _check_s3_cache(self, s3_key: str) -> str | None:
        """Check if audio already exists in S3. Returns URL if found, None otherwise."""
        try:
            await asyncio.to_thread(
                _s3_client.head_object,
                Bucket=settings.s3_bucket_name,
                Key=s3_key,
            )
            return self._build_s3_url(s3_key)
        except ClientError:
            return None

    async def _synthesize_audio(
        self,
        text: str,
        voice_id: str,
        language: str,
        character: Character,
    ) -> bytes:
        """Synthesize audio using ElevenLabs (primary) or Polly (fallback).

        Uses hybrid strategy:
        - Short texts (< 150 chars) go to Polly directly (faster, cheaper).
        - Longer texts go to ElevenLabs; falls back to Polly on failure.
        """
        breaker = get_elevenlabs_circuit_breaker()

        # Short text optimization: go directly to Polly
        use_elevenlabs = (
            len(text) >= _SHORT_TEXT_THRESHOLD
            and settings.elevenlabs_api_key
            and breaker.is_available()
        )

        if use_elevenlabs:
            try:
                return await self._call_elevenlabs(text, voice_id, language)
            except Exception:
                logger.warning(
                    "ElevenLabs TTS failed, falling back to Polly",
                    exc_info=True,
                )
                breaker.record_failure()

        # Fallback to Polly
        return await self._call_polly(text, language)

    async def _call_elevenlabs(
        self,
        text: str,
        voice_id: str,
        language: str,
    ) -> bytes:
        """Call ElevenLabs text-to-speech API."""
        breaker = get_elevenlabs_circuit_breaker()
        url = f"{_ELEVENLABS_API_BASE}/text-to-speech/{voice_id}"

        headers = {
            "xi-api-key": settings.elevenlabs_api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }

        payload = {
            "text": text,
            "model_id": _ELEVENLABS_MODEL_ID,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        }

        # Add language hint for multilingual model
        if language and language != "en":
            payload["language_code"] = language

        async with log_external_call("elevenlabs", "text_to_speech"):
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            breaker.record_failure()
            msg = f"ElevenLabs API error: {response.status_code}"
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=msg,
            )

        breaker.record_success()
        return response.content

    async def _call_polly(self, text: str, language: str) -> bytes:
        """Call AWS Polly text-to-speech as fallback."""
        voice_id = _POLLY_VOICE_MAP.get(language, "Joanna")

        try:
            async with log_external_call("polly", "synthesize_speech"):
                response = await asyncio.to_thread(
                    _polly_client.synthesize_speech,
                    Text=text,
                    OutputFormat="mp3",
                    VoiceId=voice_id,
                    Engine=_POLLY_ENGINE,
                )
        except ClientError:
            logger.exception("Polly TTS failed for language=%s", language)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="TTS service unavailable",
            ) from None

        audio_stream = response.get("AudioStream")
        if audio_stream is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="TTS service returned empty audio",
            )

        return await asyncio.to_thread(audio_stream.read)

    async def _upload_to_s3(self, audio_data: bytes, s3_key: str) -> str:
        """Upload audio data to S3 and return the permanent URL."""
        try:
            async with log_external_call("s3", "put_object"):
                await asyncio.to_thread(
                    _s3_client.put_object,
                    Bucket=settings.s3_bucket_name,
                    Key=s3_key,
                    Body=audio_data,
                    ContentType="audio/mpeg",
                )
        except ClientError:
            logger.exception("S3 upload failed for key=%s", s3_key)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage service unavailable",
            ) from None

        return self._build_s3_url(s3_key)

    @staticmethod
    def _build_s3_url(s3_key: str) -> str:
        """Construct a permanent S3 URL."""
        return (
            f"https://{settings.s3_bucket_name}"
            f".s3.{settings.aws_region}.amazonaws.com/{s3_key}"
        )
