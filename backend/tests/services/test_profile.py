"""Unit tests for ProfileService business logic.

Tests the service layer directly with mocked database session, Mem0,
S3, and Cognito. Does not go through HTTP/FastAPI.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import uuid  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.schemas.profile import ProfileUpdateRequest  # noqa: E402
from app.services.profile_service import ProfileService  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")


def _make_fake_profile(
    name: str = "Alex",
    timezone: str = "UTC",
    avatar_url: str | None = None,
    preferred_language: str = "en",
) -> MagicMock:
    """Create a fake Profile-like object."""
    profile = MagicMock()
    profile.id = FAKE_USER_ID
    profile.email = "test@ember.ai"
    profile.name = name
    profile.mem0_user_id = f"user_{FAKE_USER_ID}"
    profile.fcm_token = None
    profile.timezone = timezone
    profile.avatar_url = avatar_url
    profile.preferred_language = preferred_language
    profile.onboarding_completed = True
    profile.subscription_tier = "free"
    profile.subscription_expires_at = None
    profile.created_at = datetime.now(tz=UTC)
    profile.updated_at = datetime.now(tz=UTC)
    return profile


def _make_mock_db() -> AsyncMock:
    """Create a mock AsyncSession."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    db.execute = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# ProfileService.update_profile
# ---------------------------------------------------------------------------


class TestUpdateProfile:
    """Tests for ProfileService.update_profile()."""

    @pytest.mark.asyncio
    async def test_partial_update_name_only(self) -> None:
        """Only name provided, other fields untouched."""
        db = _make_mock_db()
        profile = _make_fake_profile(name="OldName")
        service = ProfileService(db)

        body = ProfileUpdateRequest(name="NewName")
        await service.update_profile(user=profile, body=body)

        assert profile.name == "NewName"
        assert profile.timezone == "UTC"  # unchanged
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_avatar_clear(self) -> None:
        """avatar_url explicitly set to None clears the field."""
        db = _make_mock_db()
        profile = _make_fake_profile(avatar_url="https://old.com/img.jpg")
        service = ProfileService(db)

        # Create body with avatar_url explicitly set to None
        body = ProfileUpdateRequest.model_validate({"avatar_url": None})
        await service.update_profile(user=profile, body=body)

        assert profile.avatar_url is None

    @pytest.mark.asyncio
    async def test_avatar_not_provided(self) -> None:
        """avatar_url not in request, existing value preserved."""
        db = _make_mock_db()
        profile = _make_fake_profile(avatar_url="https://old.com/img.jpg")
        service = ProfileService(db)

        # Create body without avatar_url field
        body = ProfileUpdateRequest(name="NewName")
        await service.update_profile(user=profile, body=body)

        # avatar_url should remain unchanged
        assert profile.avatar_url == "https://old.com/img.jpg"

    @pytest.mark.asyncio
    async def test_all_fields_update(self) -> None:
        """All four fields provided, all updated."""
        db = _make_mock_db()
        profile = _make_fake_profile()
        service = ProfileService(db)

        body = ProfileUpdateRequest(
            name="Updated",
            timezone="America/New_York",
            avatar_url="https://new.com/avatar.jpg",
            preferred_language="tr",
        )
        await service.update_profile(user=profile, body=body)

        assert profile.name == "Updated"
        assert profile.timezone == "America/New_York"
        assert profile.avatar_url == "https://new.com/avatar.jpg"
        assert profile.preferred_language == "tr"

    @pytest.mark.asyncio
    async def test_empty_body_no_changes(self) -> None:
        """Empty body results in no field changes."""
        db = _make_mock_db()
        profile = _make_fake_profile(name="Alex", timezone="UTC")
        service = ProfileService(db)

        body = ProfileUpdateRequest()
        await service.update_profile(user=profile, body=body)

        assert profile.name == "Alex"
        assert profile.timezone == "UTC"
        db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# ProfileService.delete_account
# ---------------------------------------------------------------------------


class TestDeleteAccount:
    """Tests for ProfileService.delete_account()."""

    @pytest.mark.asyncio
    async def test_full_deletion_flow(self) -> None:
        """Verify all external cleanup calls are made with correct parameters."""
        db = _make_mock_db()
        profile = _make_fake_profile()

        # Mock character query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            "companion_550e8400-e29b-41d4-a716-446655440000",
        ]
        db.execute.return_value = mock_result

        service = ProfileService(db)

        with (
            patch.object(
                service, "_cleanup_external_services", new_callable=AsyncMock,
                return_value={"total": 3, "failed": 0},
            ) as mock_cleanup,
        ):
            await service.delete_account(user=profile)

        # Verify DB deletion
        db.delete.assert_awaited_once_with(profile)
        db.commit.assert_awaited_once()

        # Verify external cleanup was called
        mock_cleanup.assert_awaited_once()
        call_kwargs = mock_cleanup.call_args.kwargs
        assert call_kwargs["user_id"] == str(FAKE_USER_ID)
        assert call_kwargs["mem0_user_id"] == f"user_{FAKE_USER_ID}"
        assert call_kwargs["user_email"] == "test@ember.ai"
        assert call_kwargs["agent_ids"] == [
            "companion_550e8400-e29b-41d4-a716-446655440000",
        ]

    @pytest.mark.asyncio
    async def test_mem0_failure_still_returns(self) -> None:
        """Mem0 failure doesn't raise (some services succeed)."""
        db = _make_mock_db()
        profile = _make_fake_profile()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result

        service = ProfileService(db)

        # 1 out of 3 failed -> not all failed -> should succeed
        with patch.object(
            service, "_cleanup_external_services", new_callable=AsyncMock,
            return_value={"total": 3, "failed": 1},
        ):
            # Should not raise
            await service.delete_account(user=profile)

    @pytest.mark.asyncio
    async def test_s3_failure_still_returns(self) -> None:
        """S3 failure doesn't raise (some services succeed)."""
        db = _make_mock_db()
        profile = _make_fake_profile()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result

        service = ProfileService(db)

        with patch.object(
            service, "_cleanup_external_services", new_callable=AsyncMock,
            return_value={"total": 3, "failed": 1},
        ):
            await service.delete_account(user=profile)

    @pytest.mark.asyncio
    async def test_cognito_failure_still_returns(self) -> None:
        """Cognito failure doesn't raise (some services succeed)."""
        db = _make_mock_db()
        profile = _make_fake_profile()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result

        service = ProfileService(db)

        with patch.object(
            service, "_cleanup_external_services", new_callable=AsyncMock,
            return_value={"total": 3, "failed": 1},
        ):
            await service.delete_account(user=profile)

    @pytest.mark.asyncio
    async def test_all_external_failures_raises_503(self) -> None:
        """All three external services fail -> raises 503."""
        db = _make_mock_db()
        profile = _make_fake_profile()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result

        service = ProfileService(db)

        with (
            patch.object(
                service, "_cleanup_external_services", new_callable=AsyncMock,
                return_value={"total": 3, "failed": 3},
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            await service.delete_account(user=profile)

        assert exc_info.value.status_code == 503
        assert "partially failed" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_multiple_characters_mem0_calls(self) -> None:
        """User has 3 characters -- verify all agent_ids collected."""
        db = _make_mock_db()
        profile = _make_fake_profile()

        agent_ids = [
            "companion_user1",
            "english_teacher_user1",
            "therapist_user1",
        ]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = agent_ids
        db.execute.return_value = mock_result

        service = ProfileService(db)

        with patch.object(
            service, "_cleanup_external_services", new_callable=AsyncMock,
            return_value={"total": 6, "failed": 0},
        ) as mock_cleanup:
            await service.delete_account(user=profile)

        call_kwargs = mock_cleanup.call_args.kwargs
        assert call_kwargs["agent_ids"] == agent_ids

    @pytest.mark.asyncio
    async def test_no_characters_only_global_mem0(self) -> None:
        """User has no characters -- only global Mem0 deletion attempted."""
        db = _make_mock_db()
        profile = _make_fake_profile()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result

        service = ProfileService(db)

        with patch.object(
            service, "_cleanup_external_services", new_callable=AsyncMock,
            return_value={"total": 3, "failed": 0},
        ) as mock_cleanup:
            await service.delete_account(user=profile)

        call_kwargs = mock_cleanup.call_args.kwargs
        assert call_kwargs["agent_ids"] == []


# ---------------------------------------------------------------------------
# _cleanup_external_services (integration-style)
# ---------------------------------------------------------------------------


class TestCleanupExternalServices:
    """Tests for the external cleanup orchestration."""

    @pytest.mark.asyncio
    async def test_mem0_per_agent_plus_global(self) -> None:
        """Verify Mem0 delete_all is called for each agent_id plus global."""
        db = _make_mock_db()
        service = ProfileService(db)

        agent_ids = ["companion_user1", "english_teacher_user1"]

        with (
            patch.object(
                service, "_cleanup_mem0_agent", new_callable=AsyncMock,
            ) as mock_agent,
            patch.object(
                service, "_cleanup_mem0_global", new_callable=AsyncMock,
            ) as mock_global,
            patch.object(
                service, "_cleanup_s3", new_callable=AsyncMock,
            ),
            patch.object(
                service, "_cleanup_cognito", new_callable=AsyncMock,
            ),
        ):
            result = await service._cleanup_external_services(
                user_id="uid",
                mem0_user_id="mem0_uid",
                user_email="test@test.com",
                agent_ids=agent_ids,
            )

        assert mock_agent.await_count == 2
        mock_global.assert_awaited_once_with("mem0_uid")
        assert result["total"] == 5  # 2 agent + 1 global + 1 s3 + 1 cognito
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_partial_failure_counts_correctly(self) -> None:
        """One failure out of several is counted correctly."""
        db = _make_mock_db()
        service = ProfileService(db)

        with (
            patch.object(
                service, "_cleanup_mem0_agent", new_callable=AsyncMock,
            ),
            patch.object(
                service, "_cleanup_mem0_global", new_callable=AsyncMock,
                side_effect=Exception("Mem0 error"),
            ),
            patch.object(
                service, "_cleanup_s3", new_callable=AsyncMock,
            ),
            patch.object(
                service, "_cleanup_cognito", new_callable=AsyncMock,
            ),
        ):
            result = await service._cleanup_external_services(
                user_id="uid",
                mem0_user_id="mem0_uid",
                user_email="test@test.com",
                agent_ids=["agent_1"],
            )

        assert result["failed"] == 1
        assert result["total"] == 4  # 1 agent + 1 global + 1 s3 + 1 cognito
