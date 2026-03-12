"""Profile service -- business logic for profile CRUD operations.

Handles profile retrieval, updates, and GDPR-compliant account deletion
with cascade cleanup across DB, Mem0, S3, and Cognito.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import HTTPException, status
from mem0 import MemoryClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.character import Character
from app.models.profile import Profile
from app.schemas.profile import ProfileResponse, ProfileUpdateRequest

logger = logging.getLogger("ember")


class ProfileService:
    """Encapsulates all profile-related business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def get_profile(self, user: Profile) -> ProfileResponse:
        """Map an ORM Profile object to the response schema.

        The ``get_current_user`` dependency already performs the DB lookup,
        so this method only maps the result to the response schema.
        """
        return ProfileResponse.model_validate(user)

    async def update_profile(
        self,
        user: Profile,
        body: ProfileUpdateRequest,
    ) -> ProfileResponse:
        """Apply partial updates to the user's profile.

        Only fields present in ``body.model_fields_set`` are applied.
        For ``avatar_url``, explicit ``null`` clears the field; omission
        preserves the current value.
        """
        fields_set = body.model_fields_set

        if "name" in fields_set and body.name is not None:
            user.name = body.name

        if "timezone" in fields_set and body.timezone is not None:
            user.timezone = body.timezone

        if "preferred_language" in fields_set and body.preferred_language is not None:
            user.preferred_language = body.preferred_language

        # avatar_url: distinguish "not sent" vs "sent as null" vs "sent as string"
        if "avatar_url" in fields_set:
            user.avatar_url = body.avatar_url  # None clears, string sets

        await self.db.commit()
        await self.db.refresh(user)

        return ProfileResponse.model_validate(user)

    async def delete_account(
        self,
        user: Profile,
    ) -> None:
        """GDPR-compliant full account deletion.

        Phase 1: Gather data needed for external cleanup.
        Phase 2: Delete DB rows (cascades via ON DELETE CASCADE).
        Phase 3: Best-effort external cleanup (Mem0, S3, Cognito).

        Raises:
            HTTPException(503): When ALL external cleanup operations fail.
        """
        # Phase 1 -- Gather data before DB deletion
        user_id = str(user.id)
        mem0_user_id = user.mem0_user_id
        user_email = user.email

        # Collect all character mem0_agent_ids (including inactive)
        result = await self.db.execute(
            select(Character.mem0_agent_id).where(
                Character.user_id == user.id,
            ),
        )
        agent_ids: list[str] = list(result.scalars().all())

        # Phase 2 -- Delete DB rows (point of no return)
        await self.db.delete(user)
        await self.db.commit()

        # Phase 3 -- External cleanup (best-effort)
        cleanup_results = await self._cleanup_external_services(
            user_id=user_id,
            mem0_user_id=mem0_user_id,
            user_email=user_email,
            agent_ids=agent_ids,
        )

        # If ALL external cleanups failed, raise 503
        if cleanup_results["total"] > 0 and cleanup_results["failed"] == cleanup_results["total"]:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Account deletion partially failed. Please contact support.",
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _cleanup_external_services(
        self,
        user_id: str,
        mem0_user_id: str,
        user_email: str,
        agent_ids: list[str],
    ) -> dict[str, int]:
        """Run external cleanup tasks in parallel. Returns success/failure counts."""
        tasks: list[tuple[str, object]] = []

        # Mem0 cleanup tasks
        mem0_tasks = self._build_mem0_cleanup_tasks(
            mem0_user_id=mem0_user_id,
            agent_ids=agent_ids,
        )
        tasks.extend(mem0_tasks)

        # S3 cleanup
        tasks.append(("s3", self._cleanup_s3(user_id)))

        # Cognito cleanup
        tasks.append(("cognito", self._cleanup_cognito(user_email)))

        if not tasks:
            return {"total": 0, "failed": 0}

        # Run all cleanup tasks in parallel
        coros = [t[1] for t in tasks]
        labels = [t[0] for t in tasks]
        results = await asyncio.gather(*coros, return_exceptions=True)  # type: ignore[arg-type]

        failed = 0
        for label, result in zip(labels, results, strict=True):
            if isinstance(result, Exception):
                failed += 1
                logger.error(
                    "External cleanup failed [%s] for user_id=%s: %s",
                    label,
                    user_id,
                    result,
                    exc_info=result,
                )

        return {"total": len(tasks), "failed": failed}

    def _build_mem0_cleanup_tasks(
        self,
        mem0_user_id: str,
        agent_ids: list[str],
    ) -> list[tuple[str, object]]:
        """Build Mem0 delete_all coroutines for each agent_id plus global."""
        tasks: list[tuple[str, object]] = []

        # Per-character memory deletion
        for agent_id in agent_ids:
            tasks.append((
                f"mem0:{agent_id}",
                self._cleanup_mem0_agent(mem0_user_id, agent_id),
            ))

        # Global memory deletion (no agent_id)
        tasks.append(("mem0:global", self._cleanup_mem0_global(mem0_user_id)))

        return tasks

    async def _cleanup_mem0_agent(
        self,
        mem0_user_id: str,
        agent_id: str,
    ) -> None:
        """Delete all Mem0 memories for a specific agent_id."""
        client = MemoryClient(api_key=settings.mem0_api_key)
        await asyncio.to_thread(
            client.delete_all,
            user_id=mem0_user_id,
            agent_id=agent_id,
        )

    async def _cleanup_mem0_global(
        self,
        mem0_user_id: str,
    ) -> None:
        """Delete all global Mem0 memories (no agent_id)."""
        client = MemoryClient(api_key=settings.mem0_api_key)
        await asyncio.to_thread(
            client.delete_all,
            user_id=mem0_user_id,
        )

    async def _cleanup_s3(self, user_id: str) -> None:
        """Delete all S3 objects under the user's prefixes."""
        import boto3

        s3 = boto3.client("s3", region_name=settings.aws_region)
        bucket = settings.s3_bucket_name

        for prefix in [f"photos/{user_id}/", f"audio/{user_id}/"]:
            await asyncio.to_thread(
                self._delete_s3_prefix, s3, bucket, prefix,
            )

    @staticmethod
    def _delete_s3_prefix(
        s3: object,
        bucket: str,
        prefix: str,
    ) -> None:
        """Delete all objects under a given S3 prefix (synchronous)."""
        paginator = s3.get_paginator("list_objects_v2")  # type: ignore[union-attr]
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            objects = page.get("Contents", [])
            if not objects:
                continue
            delete_keys = [{"Key": obj["Key"]} for obj in objects]
            s3.delete_objects(  # type: ignore[union-attr]
                Bucket=bucket,
                Delete={"Objects": delete_keys},
            )

    async def _cleanup_cognito(self, user_email: str) -> None:
        """Delete the Cognito user by email."""
        import boto3

        cognito = boto3.client("cognito-idp", region_name=settings.aws_region)
        await asyncio.to_thread(
            cognito.admin_delete_user,
            UserPoolId=settings.cognito_user_pool_id,
            Username=user_email,
        )
