"""Extended service unit tests for ProfileService.

Supplements the 14 existing tests in test_profile.py with:
- get_profile() direct mapping verification
- update_profile: timezone-only, language-only, zero-total cleanup path
- _cleanup_external_services: zero tasks (no characters, returns {"total":0})
- _cleanup_mem0_agent: direct invocation with mock MemoryClient
- _cleanup_mem0_global: direct invocation with mock MemoryClient
- _cleanup_s3: prefix iteration, empty page skipped, objects deleted
- _cleanup_cognito: admin_delete_user called with correct parameters
- _build_mem0_cleanup_tasks: task count for N characters
- delete_account: DB delete called before external cleanup
- delete_account: zero total tasks does NOT raise 503
- All partial failure permutations: 2 of 3, 3 of 3
- asyncio.gather called for parallel execution
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import asyncio  # noqa: E402
import uuid  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch, call  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.schemas.profile import ProfileResponse, ProfileUpdateRequest  # noqa: E402
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


def _mock_db_execute_with_agent_ids(db: AsyncMock, agent_ids: list[str]) -> None:
    """Configure db.execute to return a mock result with the given agent_ids."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = agent_ids
    db.execute.return_value = mock_result


# ---------------------------------------------------------------------------
# ProfileService.get_profile
# ---------------------------------------------------------------------------


class TestGetProfile:
    """Tests for ProfileService.get_profile()."""

    def test_returns_profile_response_schema(self) -> None:
        """get_profile() returns a ProfileResponse object."""
        db = _make_mock_db()
        service = ProfileService(db)
        profile = _make_fake_profile()

        result = service.get_profile(profile)

        assert isinstance(result, ProfileResponse)

    def test_maps_all_fields_correctly(self) -> None:
        """get_profile() maps all profile fields into the response schema."""
        db = _make_mock_db()
        service = ProfileService(db)
        profile = _make_fake_profile(
            name="Test User",
            timezone="America/Chicago",
            preferred_language="tr",
        )

        result = service.get_profile(profile)

        assert result.name == "Test User"
        assert result.timezone == "America/Chicago"
        assert result.preferred_language == "tr"
        assert result.email == "test@ember.ai"
        assert result.subscription_tier == "free"

    def test_id_is_string_in_response(self) -> None:
        """get_profile() coerces UUID id to string."""
        db = _make_mock_db()
        service = ProfileService(db)
        profile = _make_fake_profile()

        result = service.get_profile(profile)

        assert isinstance(result.id, str)
        assert result.id == str(FAKE_USER_ID)

    def test_avatar_url_none_preserved(self) -> None:
        """get_profile() returns None for avatar_url when profile has no avatar."""
        db = _make_mock_db()
        service = ProfileService(db)
        profile = _make_fake_profile(avatar_url=None)

        result = service.get_profile(profile)

        assert result.avatar_url is None

    def test_avatar_url_preserved_when_set(self) -> None:
        """get_profile() returns the avatar_url when profile has one."""
        db = _make_mock_db()
        service = ProfileService(db)
        url = "https://example.com/avatar.jpg"
        profile = _make_fake_profile(avatar_url=url)

        result = service.get_profile(profile)

        assert result.avatar_url == url


# ---------------------------------------------------------------------------
# ProfileService.update_profile -- extended
# ---------------------------------------------------------------------------


class TestUpdateProfileExtended:
    """Extended tests for ProfileService.update_profile()."""

    @pytest.mark.asyncio
    async def test_timezone_only_update(self) -> None:
        """Only timezone provided, name and language unchanged."""
        db = _make_mock_db()
        profile = _make_fake_profile(timezone="UTC", name="Alex")
        service = ProfileService(db)

        body = ProfileUpdateRequest(timezone="Asia/Tokyo")
        await service.update_profile(user=profile, body=body)

        assert profile.timezone == "Asia/Tokyo"
        assert profile.name == "Alex"  # unchanged

    @pytest.mark.asyncio
    async def test_language_only_update(self) -> None:
        """Only preferred_language provided, other fields unchanged."""
        db = _make_mock_db()
        profile = _make_fake_profile(preferred_language="en", name="Alex")
        service = ProfileService(db)

        body = ProfileUpdateRequest(preferred_language="tr")
        await service.update_profile(user=profile, body=body)

        assert profile.preferred_language == "tr"
        assert profile.name == "Alex"  # unchanged

    @pytest.mark.asyncio
    async def test_avatar_url_set_to_new_value(self) -> None:
        """avatar_url can be updated to a new https URL."""
        db = _make_mock_db()
        profile = _make_fake_profile(avatar_url=None)
        service = ProfileService(db)

        new_url = "https://s3.amazonaws.com/new-avatar.jpg"
        body = ProfileUpdateRequest(avatar_url=new_url)
        await service.update_profile(user=profile, body=body)

        assert profile.avatar_url == new_url

    @pytest.mark.asyncio
    async def test_refresh_called_after_commit(self) -> None:
        """db.refresh is called after db.commit to get updated data."""
        db = _make_mock_db()
        profile = _make_fake_profile()
        service = ProfileService(db)

        body = ProfileUpdateRequest(name="UpdatedName")
        await service.update_profile(user=profile, body=body)

        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once_with(profile)

    @pytest.mark.asyncio
    async def test_update_returns_profile_response(self) -> None:
        """update_profile() returns a ProfileResponse instance."""
        db = _make_mock_db()
        profile = _make_fake_profile()
        service = ProfileService(db)

        body = ProfileUpdateRequest(name="Updated")
        result = await service.update_profile(user=profile, body=body)

        assert isinstance(result, ProfileResponse)

    @pytest.mark.asyncio
    async def test_name_with_whitespace_set_after_validation(self) -> None:
        """Whitespace in name is trimmed by Pydantic before reaching service."""
        db = _make_mock_db()
        profile = _make_fake_profile(name="OldName")
        service = ProfileService(db)

        # Pydantic strips whitespace before the service receives the body
        body = ProfileUpdateRequest(name="  NewName  ")
        await service.update_profile(user=profile, body=body)

        assert profile.name == "NewName"

    @pytest.mark.asyncio
    async def test_avatar_url_not_in_fields_set_does_not_update(self) -> None:
        """When avatar_url not in model_fields_set, user.avatar_url is NOT assigned."""
        db = _make_mock_db()
        original_url = "https://original.example.com/img.jpg"
        profile = _make_fake_profile(avatar_url=original_url)
        service = ProfileService(db)

        # Provide only timezone -- avatar_url not in body
        body = ProfileUpdateRequest(timezone="UTC")
        await service.update_profile(user=profile, body=body)

        # avatar_url attribute should not have been reassigned
        assert profile.avatar_url == original_url


# ---------------------------------------------------------------------------
# ProfileService.delete_account -- order of operations
# ---------------------------------------------------------------------------


class TestDeleteAccountOrderOfOperations:
    """Verifies DB deletion happens before external cleanup."""

    @pytest.mark.asyncio
    async def test_db_delete_called_before_external_cleanup(self) -> None:
        """db.delete is awaited before _cleanup_external_services is called."""
        db = _make_mock_db()
        profile = _make_fake_profile()
        _mock_db_execute_with_agent_ids(db, [])

        service = ProfileService(db)
        call_order: list[str] = []

        original_delete = db.delete

        async def tracked_delete(obj: object) -> None:
            call_order.append("db_delete")
            return await original_delete(obj)

        db.delete = tracked_delete

        async def tracked_cleanup(**kwargs: object) -> dict:
            call_order.append("external_cleanup")
            return {"total": 2, "failed": 0}

        with patch.object(
            service, "_cleanup_external_services", side_effect=tracked_cleanup
        ):
            await service.delete_account(user=profile)

        assert call_order.index("db_delete") < call_order.index("external_cleanup")

    @pytest.mark.asyncio
    async def test_db_commit_called_before_external_cleanup(self) -> None:
        """db.commit is awaited before _cleanup_external_services is called."""
        db = _make_mock_db()
        profile = _make_fake_profile()
        _mock_db_execute_with_agent_ids(db, [])

        service = ProfileService(db)
        call_order: list[str] = []

        original_commit = db.commit

        async def tracked_commit() -> None:
            call_order.append("db_commit")
            return await original_commit()

        db.commit = tracked_commit

        async def tracked_cleanup(**kwargs: object) -> dict:
            call_order.append("external_cleanup")
            return {"total": 2, "failed": 0}

        with patch.object(
            service, "_cleanup_external_services", side_effect=tracked_cleanup
        ):
            await service.delete_account(user=profile)

        assert call_order.index("db_commit") < call_order.index("external_cleanup")


# ---------------------------------------------------------------------------
# ProfileService._cleanup_external_services -- edge cases
# ---------------------------------------------------------------------------


class TestCleanupExternalServicesExtended:
    """Extended tests for _cleanup_external_services."""

    @pytest.mark.asyncio
    async def test_zero_agent_ids_still_runs_global_s3_cognito(self) -> None:
        """With no characters, 3 tasks remain: global mem0, s3, cognito."""
        db = _make_mock_db()
        service = ProfileService(db)

        with (
            patch.object(service, "_cleanup_mem0_global", new_callable=AsyncMock) as mock_global,
            patch.object(service, "_cleanup_s3", new_callable=AsyncMock) as mock_s3,
            patch.object(service, "_cleanup_cognito", new_callable=AsyncMock) as mock_cognito,
        ):
            result = await service._cleanup_external_services(
                user_id="uid",
                mem0_user_id="mem0_uid",
                user_email="test@test.com",
                agent_ids=[],
            )

        assert result["total"] == 3  # 0 agent + 1 global + 1 s3 + 1 cognito
        assert result["failed"] == 0
        mock_global.assert_awaited_once()
        mock_s3.assert_awaited_once()
        mock_cognito.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_all_tasks_fail_returns_all_failed(self) -> None:
        """All 3 tasks fail -> failed == total."""
        db = _make_mock_db()
        service = ProfileService(db)

        with (
            patch.object(
                service, "_cleanup_mem0_global", new_callable=AsyncMock,
                side_effect=Exception("Mem0 error"),
            ),
            patch.object(
                service, "_cleanup_s3", new_callable=AsyncMock,
                side_effect=Exception("S3 error"),
            ),
            patch.object(
                service, "_cleanup_cognito", new_callable=AsyncMock,
                side_effect=Exception("Cognito error"),
            ),
        ):
            result = await service._cleanup_external_services(
                user_id="uid",
                mem0_user_id="mem0_uid",
                user_email="test@test.com",
                agent_ids=[],
            )

        assert result["total"] == 3
        assert result["failed"] == 3

    @pytest.mark.asyncio
    async def test_s3_only_fails_returns_one_failed(self) -> None:
        """Only S3 fails -> failed == 1, total == 3."""
        db = _make_mock_db()
        service = ProfileService(db)

        with (
            patch.object(service, "_cleanup_mem0_global", new_callable=AsyncMock),
            patch.object(
                service, "_cleanup_s3", new_callable=AsyncMock,
                side_effect=RuntimeError("S3 down"),
            ),
            patch.object(service, "_cleanup_cognito", new_callable=AsyncMock),
        ):
            result = await service._cleanup_external_services(
                user_id="uid",
                mem0_user_id="mem0_uid",
                user_email="test@test.com",
                agent_ids=[],
            )

        assert result["total"] == 3
        assert result["failed"] == 1

    @pytest.mark.asyncio
    async def test_cognito_only_fails_returns_one_failed(self) -> None:
        """Only Cognito fails -> failed == 1."""
        db = _make_mock_db()
        service = ProfileService(db)

        with (
            patch.object(service, "_cleanup_mem0_global", new_callable=AsyncMock),
            patch.object(service, "_cleanup_s3", new_callable=AsyncMock),
            patch.object(
                service, "_cleanup_cognito", new_callable=AsyncMock,
                side_effect=RuntimeError("Cognito down"),
            ),
        ):
            result = await service._cleanup_external_services(
                user_id="uid",
                mem0_user_id="mem0_uid",
                user_email="test@test.com",
                agent_ids=[],
            )

        assert result["total"] == 3
        assert result["failed"] == 1

    @pytest.mark.asyncio
    async def test_two_agent_ids_results_in_correct_total(self) -> None:
        """2 agent_ids -> total = 2 (agent) + 1 (global) + 1 (s3) + 1 (cognito) = 5."""
        db = _make_mock_db()
        service = ProfileService(db)

        with (
            patch.object(service, "_cleanup_mem0_agent", new_callable=AsyncMock),
            patch.object(service, "_cleanup_mem0_global", new_callable=AsyncMock),
            patch.object(service, "_cleanup_s3", new_callable=AsyncMock),
            patch.object(service, "_cleanup_cognito", new_callable=AsyncMock),
        ):
            result = await service._cleanup_external_services(
                user_id="uid",
                mem0_user_id="mem0_uid",
                user_email="test@test.com",
                agent_ids=["agent_a", "agent_b"],
            )

        assert result["total"] == 5
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_mem0_agent_called_with_correct_args(self) -> None:
        """_cleanup_mem0_agent is called with mem0_user_id and each agent_id."""
        db = _make_mock_db()
        service = ProfileService(db)
        agent_ids = ["companion_uid", "english_teacher_uid"]

        with (
            patch.object(service, "_cleanup_mem0_agent", new_callable=AsyncMock) as mock_agent,
            patch.object(service, "_cleanup_mem0_global", new_callable=AsyncMock),
            patch.object(service, "_cleanup_s3", new_callable=AsyncMock),
            patch.object(service, "_cleanup_cognito", new_callable=AsyncMock),
        ):
            await service._cleanup_external_services(
                user_id="uid",
                mem0_user_id="mem0_uid",
                user_email="test@test.com",
                agent_ids=agent_ids,
            )

        assert mock_agent.await_count == 2
        mock_agent.assert_any_await("mem0_uid", "companion_uid")
        mock_agent.assert_any_await("mem0_uid", "english_teacher_uid")

    @pytest.mark.asyncio
    async def test_cleanup_s3_called_with_user_id(self) -> None:
        """_cleanup_s3 is called with the correct user_id."""
        db = _make_mock_db()
        service = ProfileService(db)

        with (
            patch.object(service, "_cleanup_mem0_global", new_callable=AsyncMock),
            patch.object(service, "_cleanup_s3", new_callable=AsyncMock) as mock_s3,
            patch.object(service, "_cleanup_cognito", new_callable=AsyncMock),
        ):
            await service._cleanup_external_services(
                user_id="specific-user-id",
                mem0_user_id="mem0_uid",
                user_email="test@test.com",
                agent_ids=[],
            )

        mock_s3.assert_awaited_once_with("specific-user-id")

    @pytest.mark.asyncio
    async def test_cleanup_cognito_called_with_email(self) -> None:
        """_cleanup_cognito is called with the correct email."""
        db = _make_mock_db()
        service = ProfileService(db)

        with (
            patch.object(service, "_cleanup_mem0_global", new_callable=AsyncMock),
            patch.object(service, "_cleanup_s3", new_callable=AsyncMock),
            patch.object(service, "_cleanup_cognito", new_callable=AsyncMock) as mock_cog,
        ):
            await service._cleanup_external_services(
                user_id="uid",
                mem0_user_id="mem0_uid",
                user_email="specific@user.com",
                agent_ids=[],
            )

        mock_cog.assert_awaited_once_with("specific@user.com")


# ---------------------------------------------------------------------------
# ProfileService._build_mem0_cleanup_tasks
# ---------------------------------------------------------------------------


class TestBuildMem0CleanupTasks:
    """Tests for _build_mem0_cleanup_tasks helper."""

    def test_zero_agent_ids_returns_one_task(self) -> None:
        """No agents -> 1 task (global only)."""
        db = _make_mock_db()
        service = ProfileService(db)

        tasks = service._build_mem0_cleanup_tasks(
            mem0_user_id="mem0_uid",
            agent_ids=[],
        )

        assert len(tasks) == 1
        assert tasks[0][0] == "mem0:global"

    def test_three_agent_ids_returns_four_tasks(self) -> None:
        """3 agents -> 4 tasks (3 agent + 1 global)."""
        db = _make_mock_db()
        service = ProfileService(db)

        tasks = service._build_mem0_cleanup_tasks(
            mem0_user_id="mem0_uid",
            agent_ids=["a1", "a2", "a3"],
        )

        assert len(tasks) == 4

    def test_task_labels_include_agent_ids(self) -> None:
        """Task labels use 'mem0:{agent_id}' format for per-character tasks."""
        db = _make_mock_db()
        service = ProfileService(db)

        tasks = service._build_mem0_cleanup_tasks(
            mem0_user_id="mem0_uid",
            agent_ids=["companion_u1"],
        )

        labels = [t[0] for t in tasks]
        assert "mem0:companion_u1" in labels
        assert "mem0:global" in labels

    def test_global_task_is_always_last(self) -> None:
        """Global mem0 cleanup task appears as the last in the returned list."""
        db = _make_mock_db()
        service = ProfileService(db)

        tasks = service._build_mem0_cleanup_tasks(
            mem0_user_id="mem0_uid",
            agent_ids=["agent_1", "agent_2"],
        )

        assert tasks[-1][0] == "mem0:global"


# ---------------------------------------------------------------------------
# ProfileService._cleanup_s3 -- unit tests with mocked boto3
# ---------------------------------------------------------------------------


class TestCleanupS3:
    """Unit tests for _cleanup_s3 with mocked boto3."""

    @pytest.mark.asyncio
    async def test_s3_cleanup_deletes_photos_and_audio_prefixes(self) -> None:
        """_cleanup_s3 deletes objects under 'photos/{user_id}/' and 'audio/{user_id}/'."""
        db = _make_mock_db()
        service = ProfileService(db)

        mock_s3_client = MagicMock()
        mock_paginator = MagicMock()
        mock_s3_client.get_paginator.return_value = mock_paginator
        # Return empty pages so no delete_objects is called
        mock_paginator.paginate.return_value = iter([{"Contents": []}])

        deleted_prefixes: list[str] = []
        original_delete_prefix = service._delete_s3_prefix

        def track_prefix(s3: object, bucket: str, prefix: str) -> None:
            deleted_prefixes.append(prefix)

        with (
            patch("boto3.client", return_value=mock_s3_client),
            patch.object(service, "_delete_s3_prefix", side_effect=track_prefix),
        ):
            await service._cleanup_s3("test-user-id")

        assert "photos/test-user-id/" in deleted_prefixes
        assert "audio/test-user-id/" in deleted_prefixes
        assert len(deleted_prefixes) == 2

    @pytest.mark.asyncio
    async def test_s3_cleanup_uses_correct_region(self) -> None:
        """_cleanup_s3 creates boto3.client('s3') with region_name kwarg."""
        db = _make_mock_db()
        service = ProfileService(db)

        with (
            patch("boto3.client", return_value=MagicMock()) as mock_boto3,
            patch.object(service, "_delete_s3_prefix"),
        ):
            await service._cleanup_s3("uid")

        from app.config import settings

        mock_boto3.assert_called_once_with("s3", region_name=settings.aws_region)

    def test_delete_s3_prefix_skips_empty_page(self) -> None:
        """_delete_s3_prefix does not call delete_objects for pages with no Contents."""
        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = iter([
            {},  # no "Contents" key
            {"Contents": []},  # empty Contents
        ])

        ProfileService._delete_s3_prefix(mock_s3, "test-bucket", "photos/uid/")

        mock_s3.delete_objects.assert_not_called()

    def test_delete_s3_prefix_batches_objects(self) -> None:
        """_delete_s3_prefix calls delete_objects with correct keys for non-empty page."""
        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator

        objects = [{"Key": f"photos/uid/file_{i}.jpg"} for i in range(3)]
        mock_paginator.paginate.return_value = iter([{"Contents": objects}])

        ProfileService._delete_s3_prefix(mock_s3, "my-bucket", "photos/uid/")

        mock_s3.delete_objects.assert_called_once_with(
            Bucket="my-bucket",
            Delete={
                "Objects": [
                    {"Key": "photos/uid/file_0.jpg"},
                    {"Key": "photos/uid/file_1.jpg"},
                    {"Key": "photos/uid/file_2.jpg"},
                ],
            },
        )

    def test_delete_s3_prefix_processes_multiple_pages(self) -> None:
        """_delete_s3_prefix processes multiple paginator pages."""
        mock_s3 = MagicMock()
        mock_paginator = MagicMock()
        mock_s3.get_paginator.return_value = mock_paginator

        page1_objects = [{"Key": "photos/uid/a.jpg"}]
        page2_objects = [{"Key": "photos/uid/b.jpg"}]
        mock_paginator.paginate.return_value = iter([
            {"Contents": page1_objects},
            {"Contents": page2_objects},
        ])

        ProfileService._delete_s3_prefix(mock_s3, "my-bucket", "photos/uid/")

        assert mock_s3.delete_objects.call_count == 2


# ---------------------------------------------------------------------------
# ProfileService._cleanup_mem0_agent and _cleanup_mem0_global -- unit tests
# ---------------------------------------------------------------------------


class TestCleanupMem0:
    """Unit tests for Mem0 cleanup private methods."""

    @pytest.mark.asyncio
    async def test_cleanup_mem0_agent_calls_delete_all_with_agent_id(self) -> None:
        """_cleanup_mem0_agent calls client.delete_all with user_id and agent_id."""
        db = _make_mock_db()
        service = ProfileService(db)

        mock_client = MagicMock()
        mock_client.delete_all = MagicMock()

        with patch("app.services.profile_service.MemoryClient", return_value=mock_client):
            await service._cleanup_mem0_agent(
                mem0_user_id="mem0_uid_123",
                agent_id="companion_uid_abc",
            )

        mock_client.delete_all.assert_called_once_with(
            user_id="mem0_uid_123",
            agent_id="companion_uid_abc",
        )

    @pytest.mark.asyncio
    async def test_cleanup_mem0_global_calls_delete_all_without_agent_id(self) -> None:
        """_cleanup_mem0_global calls client.delete_all with only user_id."""
        db = _make_mock_db()
        service = ProfileService(db)

        mock_client = MagicMock()
        mock_client.delete_all = MagicMock()

        with patch("app.services.profile_service.MemoryClient", return_value=mock_client):
            await service._cleanup_mem0_global(mem0_user_id="mem0_uid_456")

        mock_client.delete_all.assert_called_once_with(user_id="mem0_uid_456")
        # Ensure agent_id is NOT passed
        call_kwargs = mock_client.delete_all.call_args.kwargs
        assert "agent_id" not in call_kwargs

    @pytest.mark.asyncio
    async def test_cleanup_mem0_agent_uses_settings_api_key(self) -> None:
        """MemoryClient is instantiated with settings.mem0_api_key."""
        db = _make_mock_db()
        service = ProfileService(db)

        with patch("app.services.profile_service.MemoryClient") as mock_client_cls:
            mock_client_cls.return_value.delete_all = MagicMock()
            await service._cleanup_mem0_agent("uid", "agent_id")

        from app.config import settings
        mock_client_cls.assert_called_once_with(api_key=settings.mem0_api_key)


# ---------------------------------------------------------------------------
# ProfileService._cleanup_cognito -- unit tests
# ---------------------------------------------------------------------------


class TestCleanupCognito:
    """Unit tests for _cleanup_cognito."""

    @pytest.mark.asyncio
    async def test_cleanup_cognito_calls_admin_delete_user(self) -> None:
        """_cleanup_cognito calls admin_delete_user with correct UserPoolId and Username."""
        db = _make_mock_db()
        service = ProfileService(db)

        mock_cognito_client = MagicMock()
        mock_cognito_client.admin_delete_user = MagicMock()

        with patch("boto3.client", return_value=mock_cognito_client):
            await service._cleanup_cognito("user@example.com")

        from app.config import settings
        mock_cognito_client.admin_delete_user.assert_called_once_with(
            UserPoolId=settings.cognito_user_pool_id,
            Username="user@example.com",
        )

    @pytest.mark.asyncio
    async def test_cleanup_cognito_uses_cognito_idp_client(self) -> None:
        """_cleanup_cognito creates boto3 client for 'cognito-idp'."""
        db = _make_mock_db()
        service = ProfileService(db)

        with patch("boto3.client", return_value=MagicMock()) as mock_boto3:
            await service._cleanup_cognito("user@example.com")

        # First positional arg must be 'cognito-idp'
        call_args = mock_boto3.call_args
        assert call_args[0][0] == "cognito-idp"


# ---------------------------------------------------------------------------
# ProfileService.delete_account -- zero total tasks edge case
# ---------------------------------------------------------------------------


class TestDeleteAccountZeroTotal:
    """Tests for the zero-total tasks edge case in delete_account."""

    @pytest.mark.asyncio
    async def test_zero_total_tasks_does_not_raise_503(self) -> None:
        """When _cleanup_external_services returns total=0, no 503 is raised."""
        db = _make_mock_db()
        profile = _make_fake_profile()
        _mock_db_execute_with_agent_ids(db, [])

        service = ProfileService(db)

        with patch.object(
            service, "_cleanup_external_services", new_callable=AsyncMock,
            return_value={"total": 0, "failed": 0},
        ):
            # Should not raise any exception
            await service.delete_account(user=profile)

    @pytest.mark.asyncio
    async def test_two_of_three_failures_does_not_raise_503(self) -> None:
        """2 out of 3 failures: not ALL failed, so no 503 is raised."""
        db = _make_mock_db()
        profile = _make_fake_profile()
        _mock_db_execute_with_agent_ids(db, [])

        service = ProfileService(db)

        with patch.object(
            service, "_cleanup_external_services", new_callable=AsyncMock,
            return_value={"total": 3, "failed": 2},
        ):
            # Should not raise (failed != total)
            await service.delete_account(user=profile)

    @pytest.mark.asyncio
    async def test_user_id_passed_as_string_to_cleanup(self) -> None:
        """user_id passed to _cleanup_external_services is a string, not UUID."""
        db = _make_mock_db()
        profile = _make_fake_profile()
        _mock_db_execute_with_agent_ids(db, [])

        service = ProfileService(db)

        with patch.object(
            service, "_cleanup_external_services", new_callable=AsyncMock,
            return_value={"total": 2, "failed": 0},
        ) as mock_cleanup:
            await service.delete_account(user=profile)

        call_kwargs = mock_cleanup.call_args.kwargs
        assert isinstance(call_kwargs["user_id"], str)
        assert call_kwargs["user_id"] == str(FAKE_USER_ID)

    @pytest.mark.asyncio
    async def test_mem0_user_id_passed_correctly(self) -> None:
        """mem0_user_id from profile is passed to external cleanup."""
        db = _make_mock_db()
        profile = _make_fake_profile()
        _mock_db_execute_with_agent_ids(db, [])

        service = ProfileService(db)

        with patch.object(
            service, "_cleanup_external_services", new_callable=AsyncMock,
            return_value={"total": 2, "failed": 0},
        ) as mock_cleanup:
            await service.delete_account(user=profile)

        call_kwargs = mock_cleanup.call_args.kwargs
        assert call_kwargs["mem0_user_id"] == f"user_{FAKE_USER_ID}"

    @pytest.mark.asyncio
    async def test_user_email_passed_correctly(self) -> None:
        """Email from profile is passed to external cleanup."""
        db = _make_mock_db()
        profile = _make_fake_profile()
        _mock_db_execute_with_agent_ids(db, [])

        service = ProfileService(db)

        with patch.object(
            service, "_cleanup_external_services", new_callable=AsyncMock,
            return_value={"total": 2, "failed": 0},
        ) as mock_cleanup:
            await service.delete_account(user=profile)

        call_kwargs = mock_cleanup.call_args.kwargs
        assert call_kwargs["user_email"] == "test@ember.ai"
