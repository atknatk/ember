"""Unit tests for memory Pydantic schemas.

Tests MemoryItem and MemoryListResponse serialization and defaults.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402

from app.schemas.memory import MemoryItem, MemoryListResponse  # noqa: E402


class TestMemoryItem:
    """Tests for the MemoryItem schema."""

    def test_all_fields_populated(self) -> None:
        """T1: MemoryItem with all fields populated has correct values."""
        now = datetime.now(tz=UTC)
        item = MemoryItem(id="mem-1", memory="Likes morning workouts", created_at=now)
        assert item.id == "mem-1"
        assert item.memory == "Likes morning workouts"
        assert item.created_at == now

    def test_created_at_defaults_to_none(self) -> None:
        """T2: MemoryItem without created_at defaults to None."""
        item = MemoryItem(id="mem-2", memory="Left knee is sensitive")
        assert item.id == "mem-2"
        assert item.memory == "Left knee is sensitive"
        assert item.created_at is None

    def test_serialization(self) -> None:
        """MemoryItem serializes correctly to dict."""
        item = MemoryItem(id="mem-3", memory="Prefers short corrections", created_at=None)
        data = item.model_dump()
        assert data["id"] == "mem-3"
        assert data["memory"] == "Prefers short corrections"
        assert data["created_at"] is None


class TestMemoryListResponse:
    """Tests for the MemoryListResponse schema."""

    def test_empty_memories_list(self) -> None:
        """T3: MemoryListResponse with empty memories list serializes correctly."""
        response = MemoryListResponse(memories=[])
        data = response.model_dump()
        assert data == {"memories": []}

    def test_multiple_items(self) -> None:
        """T4: MemoryListResponse with multiple items serializes correctly."""
        now = datetime.now(tz=UTC)
        items = [
            MemoryItem(id="mem-1", memory="Likes morning workouts", created_at=now),
            MemoryItem(id="mem-2", memory="Left knee is sensitive"),
        ]
        response = MemoryListResponse(memories=items)
        data = response.model_dump()
        assert len(data["memories"]) == 2
        assert data["memories"][0]["id"] == "mem-1"
        assert data["memories"][0]["memory"] == "Likes morning workouts"
        assert data["memories"][0]["created_at"] is not None
        assert data["memories"][1]["id"] == "mem-2"
        assert data["memories"][1]["memory"] == "Left knee is sensitive"
        assert data["memories"][1]["created_at"] is None

    @pytest.mark.asyncio
    async def test_json_serialization(self) -> None:
        """MemoryListResponse produces valid JSON."""
        response = MemoryListResponse(
            memories=[
                MemoryItem(id="mem-1", memory="Test memory", created_at=None),
            ],
        )
        json_str = response.model_dump_json()
        assert '"mem-1"' in json_str
        assert '"Test memory"' in json_str
