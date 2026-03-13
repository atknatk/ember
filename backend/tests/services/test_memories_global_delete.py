"""Unit tests for MemoryService.delete_global_memory().

Tests ownership validation, idempotent deletion, and error handling
with mocked Mem0 client.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import uuid  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.services.memory_service import MemoryService  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
FAKE_MEM0_USER_ID = f"user_{FAKE_USER_ID}"
OTHER_MEM0_USER_ID = "user_770e8400-e29b-41d4-a716-446655440099"

MEMORY_RESPONSE = {
    "id": "mem-1",
    "memory": "Works as a freelance engineer",
    "user_id": FAKE_MEM0_USER_ID,
    "created_at": "2026-02-15T08:00:00Z",
}


# ---------------------------------------------------------------------------
# delete_global_memory tests
# ---------------------------------------------------------------------------


class TestDeleteGlobalMemory:
    """Tests for MemoryService.delete_global_memory()."""

    @pytest.mark.asyncio
    async def test_calls_get_then_delete(self) -> None:
        """S1: client.get() then client.delete() are called in sequence."""
        mock_db = MagicMock()

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = MEMORY_RESPONSE
            mock_client.delete.return_value = None
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            await service.delete_global_memory(
                mem0_user_id=FAKE_MEM0_USER_ID,
                memory_id="mem-1",
            )

            mock_client.get.assert_called_once_with("mem-1")
            mock_client.delete.assert_called_once_with("mem-1")

    @pytest.mark.asyncio
    async def test_matching_user_id_succeeds(self) -> None:
        """S2: Matching user_id completes without exception."""
        mock_db = MagicMock()

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = MEMORY_RESPONSE
            mock_client.delete.return_value = None
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            # Should not raise
            await service.delete_global_memory(
                mem0_user_id=FAKE_MEM0_USER_ID,
                memory_id="mem-1",
            )

    @pytest.mark.asyncio
    async def test_mismatched_user_id_raises_403(self) -> None:
        """S3: Mismatched user_id raises HTTPException(403)."""
        mock_db = MagicMock()
        other_memory = {**MEMORY_RESPONSE, "user_id": OTHER_MEM0_USER_ID}

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = other_memory
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await service.delete_global_memory(
                    mem0_user_id=FAKE_MEM0_USER_ID,
                    memory_id="mem-1",
                )

            assert exc_info.value.status_code == 403
            assert exc_info.value.detail == "Memory does not belong to user"
            # delete should NOT have been called
            mock_client.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_not_found_is_idempotent(self) -> None:
        """S4: client.get() raising 'not found' is treated as success."""
        mock_db = MagicMock()

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.side_effect = Exception("Memory not found")
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            # Should not raise
            await service.delete_global_memory(
                mem0_user_id=FAKE_MEM0_USER_ID,
                memory_id="nonexistent",
            )

            # delete should NOT have been called
            mock_client.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_other_error_raises_503(self) -> None:
        """S5: client.get() raising non-'not found' error raises 503."""
        mock_db = MagicMock()

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.side_effect = Exception("Connection timeout")
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await service.delete_global_memory(
                    mem0_user_id=FAKE_MEM0_USER_ID,
                    memory_id="mem-1",
                )

            assert exc_info.value.status_code == 503
            assert exc_info.value.detail == "Memory service temporarily unavailable"

    @pytest.mark.asyncio
    async def test_delete_not_found_is_idempotent(self) -> None:
        """S6: client.delete() raising 'not found' is treated as success (race condition)."""
        mock_db = MagicMock()

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = MEMORY_RESPONSE
            mock_client.delete.side_effect = Exception("Memory not found")
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            # Should not raise
            await service.delete_global_memory(
                mem0_user_id=FAKE_MEM0_USER_ID,
                memory_id="mem-1",
            )

    @pytest.mark.asyncio
    async def test_delete_other_error_raises_503(self) -> None:
        """S7: client.delete() raising non-'not found' error raises 503."""
        mock_db = MagicMock()

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.return_value = MEMORY_RESPONSE
            mock_client.delete.side_effect = Exception("Connection timeout")
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await service.delete_global_memory(
                    mem0_user_id=FAKE_MEM0_USER_ID,
                    memory_id="mem-1",
                )

            assert exc_info.value.status_code == 503
            assert exc_info.value.detail == "Memory service temporarily unavailable"

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_raises_503(self) -> None:
        """S8: Circuit breaker OPEN state raises 503 immediately."""
        mock_db = MagicMock()

        with patch("app.services.memory_service.get_mem0_circuit_breaker") as mock_cb:
            mock_breaker = MagicMock()
            mock_breaker.state = "open"
            mock_cb.return_value = mock_breaker

            service = MemoryService(mock_db)
            with pytest.raises(HTTPException) as exc_info:
                await service.delete_global_memory(
                    mem0_user_id=FAKE_MEM0_USER_ID,
                    memory_id="mem-1",
                )

            assert exc_info.value.status_code == 503
            assert exc_info.value.detail == "Memory service temporarily unavailable"

    @pytest.mark.asyncio
    async def test_get_404_string_is_idempotent(self) -> None:
        """S4b: client.get() raising error with '404' is treated as success."""
        mock_db = MagicMock()

        with patch("app.services.memory_service.MemoryClient") as mock_cls:
            mock_client = MagicMock()
            mock_client.get.side_effect = Exception("HTTP 404 error")
            mock_cls.return_value = mock_client

            service = MemoryService(mock_db)
            # Should not raise
            await service.delete_global_memory(
                mem0_user_id=FAKE_MEM0_USER_ID,
                memory_id="nonexistent",
            )
