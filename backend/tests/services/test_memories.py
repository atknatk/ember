"""Unit tests for MemoryService.

Tests the MemoryService class with mocked database sessions and Mem0 client.
All Mem0 calls are wrapped in asyncio.to_thread() so MagicMock is sufficient.
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
from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.services.memory_service import MemoryService  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
OTHER_USER_ID = uuid.UUID("770e8400-e29b-41d4-a716-446655440099")
FAKE_CHARACTER_ID = uuid.UUID("660e8400-e29b-41d4-a716-446655440001")
FAKE_MEM0_USER_ID = f"user_{FAKE_USER_ID}"
FAKE_MEM0_AGENT_ID = f"english_teacher_{FAKE_USER_ID}"


def _make_mock_character(
    character_id: uuid.UUID = FAKE_CHARACTER_ID,
    user_id: uuid.UUID = FAKE_USER_ID,
) -> MagicMock:
    """Create a mock Character ORM object."""
    char = MagicMock()
    char.id = character_id
    char.user_id = user_id
    char.name = "Sarah"
    char.template = "english_teacher"
    char.mem0_agent_id = f"english_teacher_{user_id}"
    char.is_active = True
    char.created_at = datetime.now(tz=UTC)
    return char


def _make_mock_db(character: MagicMock | None = None) -> MagicMock:
    """Create a mock AsyncSession that returns the given character from execute()."""
    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = character

    # Make execute awaitable
    async def _mock_execute(*args: object, **kwargs: object) -> MagicMock:
        return mock_result

    mock_db.execute = _mock_execute
    return mock_db


MEM0_RESULTS = [
    {"id": "mem-1", "memory": "Likes morning workouts", "created_at": "2026-02-20T10:00:00Z"},
    {"id": "mem-2", "memory": "Left knee is sensitive", "created_at": "2026-02-18T15:30:00Z"},
]


# ---------------------------------------------------------------------------
# get_character_memories tests
# ---------------------------------------------------------------------------


class TestGetCharacterMemories:
    """Tests for MemoryService.get_character_memories()."""

    @pytest.mark.asyncio
    async def test_calls_mem0_with_correct_params(self) -> None:
        """S1: get_all() is called with correct user_id and agent_id."""
        char = _make_mock_character()
        mock_db = _make_mock_db(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = MEM0_RESULTS
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            await service.get_character_memories(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
                mem0_user_id=FAKE_MEM0_USER_ID,
            )

            mock_client.get_all.assert_called_once_with(
                user_id=FAKE_MEM0_USER_ID,
                agent_id=FAKE_MEM0_AGENT_ID,
            )

    @pytest.mark.asyncio
    async def test_maps_mem0_response_to_memory_items(self) -> None:
        """S2: Mem0 response is correctly mapped to MemoryItem list."""
        char = _make_mock_character()
        mock_db = _make_mock_db(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = MEM0_RESULTS
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            items = await service.get_character_memories(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
                mem0_user_id=FAKE_MEM0_USER_ID,
            )

            assert len(items) == 2
            assert items[0].id == "mem-1"
            assert items[0].memory == "Likes morning workouts"
            assert items[1].id == "mem-2"
            assert items[1].memory == "Left knee is sensitive"

    @pytest.mark.asyncio
    async def test_handles_missing_created_at(self) -> None:
        """S3: created_at is None when Mem0 does not return it."""
        char = _make_mock_character()
        mock_db = _make_mock_db(char)

        results_no_date = [
            {"id": "mem-1", "memory": "Test memory"},
        ]

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = results_no_date
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            items = await service.get_character_memories(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
                mem0_user_id=FAKE_MEM0_USER_ID,
            )

            assert len(items) == 1
            assert items[0].created_at is None

    @pytest.mark.asyncio
    async def test_raises_404_for_nonexistent_character(self) -> None:
        """S4: Raises 404 when character is not found."""
        mock_db = _make_mock_db(None)

        service = MemoryService(mock_db)
        with pytest.raises(HTTPException) as exc_info:
            await service.get_character_memories(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
                mem0_user_id=FAKE_MEM0_USER_ID,
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Character not found"

    @pytest.mark.asyncio
    async def test_raises_403_for_wrong_user(self) -> None:
        """S5: Raises 403 when character belongs to different user."""
        char = _make_mock_character(user_id=OTHER_USER_ID)
        mock_db = _make_mock_db(char)

        service = MemoryService(mock_db)
        with pytest.raises(HTTPException) as exc_info:
            await service.get_character_memories(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
                mem0_user_id=FAKE_MEM0_USER_ID,
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Character does not belong to user"

    @pytest.mark.asyncio
    async def test_raises_503_when_mem0_fails(self) -> None:
        """S6: Raises 503 when Mem0 API fails."""
        char = _make_mock_character()
        mock_db = _make_mock_db(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.side_effect = Exception("Mem0 connection refused")
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await service.get_character_memories(
                    character_id=FAKE_CHARACTER_ID,
                    user_id=FAKE_USER_ID,
                    mem0_user_id=FAKE_MEM0_USER_ID,
                )

            assert exc_info.value.status_code == 503
            assert exc_info.value.detail == "Memory service unavailable"


# ---------------------------------------------------------------------------
# delete_character_memory tests
# ---------------------------------------------------------------------------


class TestDeleteCharacterMemory:
    """Tests for MemoryService.delete_character_memory()."""

    @pytest.mark.asyncio
    async def test_calls_mem0_delete_with_correct_id(self) -> None:
        """S7: Mem0 delete() is called with correct memory_id."""
        char = _make_mock_character()
        mock_db = _make_mock_db(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.delete.return_value = None
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            await service.delete_character_memory(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
                memory_id="mem-1",
            )

            mock_client.delete.assert_called_once_with("mem-1")

    @pytest.mark.asyncio
    async def test_verifies_ownership_before_mem0_call(self) -> None:
        """S8: Ownership check happens before calling Mem0."""
        char = _make_mock_character(user_id=OTHER_USER_ID)
        mock_db = _make_mock_db(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await service.delete_character_memory(
                    character_id=FAKE_CHARACTER_ID,
                    user_id=FAKE_USER_ID,
                    memory_id="mem-1",
                )

            assert exc_info.value.status_code == 403
            # Mem0 should NOT have been called
            mock_client.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_treats_mem0_not_found_as_success(self) -> None:
        """S9: Mem0 'not found' error is treated as success (idempotent)."""
        char = _make_mock_character()
        mock_db = _make_mock_db(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.delete.side_effect = Exception("Memory not found")
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            # Should not raise
            await service.delete_character_memory(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
                memory_id="nonexistent-mem",
            )

    @pytest.mark.asyncio
    async def test_raises_503_on_mem0_failure(self) -> None:
        """S10: Raises 503 on Mem0 failure (non 'not found')."""
        char = _make_mock_character()
        mock_db = _make_mock_db(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.delete.side_effect = Exception("Connection timeout")
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await service.delete_character_memory(
                    character_id=FAKE_CHARACTER_ID,
                    user_id=FAKE_USER_ID,
                    memory_id="mem-1",
                )

            assert exc_info.value.status_code == 503
            assert exc_info.value.detail == "Memory service unavailable"


# ---------------------------------------------------------------------------
# delete_all_character_memories tests
# ---------------------------------------------------------------------------


class TestDeleteAllCharacterMemories:
    """Tests for MemoryService.delete_all_character_memories()."""

    @pytest.mark.asyncio
    async def test_calls_mem0_delete_all_with_correct_params(self) -> None:
        """S11: Mem0 delete_all() called with correct user_id and agent_id."""
        char = _make_mock_character()
        mock_db = _make_mock_db(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.delete_all.return_value = None
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            await service.delete_all_character_memories(
                character_id=FAKE_CHARACTER_ID,
                user_id=FAKE_USER_ID,
                mem0_user_id=FAKE_MEM0_USER_ID,
            )

            mock_client.delete_all.assert_called_once_with(
                user_id=FAKE_MEM0_USER_ID,
                agent_id=FAKE_MEM0_AGENT_ID,
            )

    @pytest.mark.asyncio
    async def test_verifies_ownership_before_mem0_call(self) -> None:
        """S12: Ownership check happens before calling Mem0."""
        char = _make_mock_character(user_id=OTHER_USER_ID)
        mock_db = _make_mock_db(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await service.delete_all_character_memories(
                    character_id=FAKE_CHARACTER_ID,
                    user_id=FAKE_USER_ID,
                    mem0_user_id=FAKE_MEM0_USER_ID,
                )

            assert exc_info.value.status_code == 403
            mock_client.delete_all.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_503_when_mem0_fails(self) -> None:
        """S13: Raises 503 when Mem0 fails."""
        char = _make_mock_character()
        mock_db = _make_mock_db(char)

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.delete_all.side_effect = Exception("Mem0 error")
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await service.delete_all_character_memories(
                    character_id=FAKE_CHARACTER_ID,
                    user_id=FAKE_USER_ID,
                    mem0_user_id=FAKE_MEM0_USER_ID,
                )

            assert exc_info.value.status_code == 503
            assert exc_info.value.detail == "Memory service unavailable"


# ---------------------------------------------------------------------------
# get_global_memories tests
# ---------------------------------------------------------------------------


class TestGetGlobalMemories:
    """Tests for MemoryService.get_global_memories()."""

    @pytest.mark.asyncio
    async def test_calls_mem0_without_agent_id(self) -> None:
        """S14: get_all() is called with user_id only (no agent_id)."""
        mock_db = MagicMock()

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = MEM0_RESULTS
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            await service.get_global_memories(mem0_user_id=FAKE_MEM0_USER_ID)

            mock_client.get_all.assert_called_once_with(
                user_id=FAKE_MEM0_USER_ID,
            )

    @pytest.mark.asyncio
    async def test_maps_mem0_response_correctly(self) -> None:
        """S15: Mem0 response is correctly mapped to MemoryItem list."""
        mock_db = MagicMock()

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.return_value = MEM0_RESULTS
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            items = await service.get_global_memories(
                mem0_user_id=FAKE_MEM0_USER_ID,
            )

            assert len(items) == 2
            assert items[0].id == "mem-1"
            assert items[0].memory == "Likes morning workouts"
            assert items[1].id == "mem-2"

    @pytest.mark.asyncio
    async def test_raises_503_when_mem0_fails(self) -> None:
        """S16: Raises 503 when Mem0 fails."""
        mock_db = MagicMock()

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get_all.side_effect = Exception("Mem0 error")
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await service.get_global_memories(
                    mem0_user_id=FAKE_MEM0_USER_ID,
                )

            assert exc_info.value.status_code == 503
            assert exc_info.value.detail == "Memory service unavailable"
