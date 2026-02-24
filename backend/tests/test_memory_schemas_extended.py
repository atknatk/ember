"""Extended unit tests for memory Pydantic schemas.

Covers edge cases not in the base test_memory_schemas.py:
- MemoryItem with ISO string created_at (Pydantic auto-coercion)
- MemoryItem model_dump(mode="json") for API serialization
- JSON round-trip (serialize then deserialize back)
- Validation errors for missing required fields
- MemoryListResponse with a mix of items (some with created_at, some without)
- MemoryItem from_dict-like construction from Mem0 response
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import json  # noqa: E402
from datetime import UTC, datetime, timezone  # noqa: E402

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.schemas.memory import MemoryItem, MemoryListResponse  # noqa: E402


# ---------------------------------------------------------------------------
# MemoryItem extended tests
# ---------------------------------------------------------------------------


class TestMemoryItemExtended:
    """Extended tests for the MemoryItem schema."""

    def test_iso_string_created_at_coerced_to_datetime(self) -> None:
        """ISO 8601 string for created_at is automatically parsed to datetime."""
        item = MemoryItem(
            id="mem-1",
            memory="Test",
            created_at="2026-02-20T10:00:00Z",  # type: ignore[arg-type]
        )
        assert isinstance(item.created_at, datetime)
        assert item.created_at.year == 2026
        assert item.created_at.month == 2
        assert item.created_at.day == 20

    def test_iso_string_with_offset_parsed(self) -> None:
        """ISO 8601 string with timezone offset is parsed correctly."""
        item = MemoryItem(
            id="mem-1",
            memory="Test",
            created_at="2026-02-20T10:00:00+03:00",  # type: ignore[arg-type]
        )
        assert isinstance(item.created_at, datetime)
        assert item.created_at is not None
        assert item.created_at.tzinfo is not None

    def test_model_dump_json_mode(self) -> None:
        """model_dump(mode='json') produces JSON-serializable dict."""
        now = datetime.now(tz=UTC)
        item = MemoryItem(id="mem-1", memory="Test", created_at=now)
        data = item.model_dump(mode="json")
        # created_at should be a string in JSON mode
        assert isinstance(data["created_at"], str)
        assert isinstance(data["id"], str)
        assert isinstance(data["memory"], str)

    def test_model_dump_json_mode_null_created_at(self) -> None:
        """model_dump(mode='json') with None created_at returns None (not string)."""
        item = MemoryItem(id="mem-1", memory="Test", created_at=None)
        data = item.model_dump(mode="json")
        assert data["created_at"] is None

    def test_json_round_trip(self) -> None:
        """MemoryItem survives JSON serialization and deserialization."""
        now = datetime.now(tz=UTC)
        original = MemoryItem(id="mem-round", memory="Round trip test", created_at=now)
        json_str = original.model_dump_json()
        restored = MemoryItem.model_validate_json(json_str)
        assert restored.id == original.id
        assert restored.memory == original.memory
        # Allow small rounding differences in datetime comparison
        assert restored.created_at is not None
        assert original.created_at is not None
        assert abs((restored.created_at - original.created_at).total_seconds()) < 1

    def test_json_round_trip_null_created_at(self) -> None:
        """MemoryItem with None created_at survives JSON round-trip."""
        original = MemoryItem(id="mem-null", memory="Null date", created_at=None)
        json_str = original.model_dump_json()
        restored = MemoryItem.model_validate_json(json_str)
        assert restored.id == "mem-null"
        assert restored.memory == "Null date"
        assert restored.created_at is None

    def test_missing_id_raises_validation_error(self) -> None:
        """Missing 'id' field raises a validation error."""
        with pytest.raises(ValidationError) as exc_info:
            MemoryItem(memory="Missing id")  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("id",) for e in errors)

    def test_missing_memory_raises_validation_error(self) -> None:
        """Missing 'memory' field raises a validation error."""
        with pytest.raises(ValidationError) as exc_info:
            MemoryItem(id="mem-1")  # type: ignore[call-arg]
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("memory",) for e in errors)

    def test_empty_string_id_is_valid(self) -> None:
        """Empty string for id is technically valid (no min_length constraint)."""
        item = MemoryItem(id="", memory="Test")
        assert item.id == ""

    def test_empty_string_memory_is_valid(self) -> None:
        """Empty string for memory is technically valid (no min_length constraint)."""
        item = MemoryItem(id="mem-1", memory="")
        assert item.memory == ""

    def test_very_long_memory_text(self) -> None:
        """Very long memory text is accepted (no max_length constraint)."""
        long_text = "x" * 10000
        item = MemoryItem(id="mem-long", memory=long_text)
        assert len(item.memory) == 10000


# ---------------------------------------------------------------------------
# MemoryListResponse extended tests
# ---------------------------------------------------------------------------


class TestMemoryListResponseExtended:
    """Extended tests for the MemoryListResponse schema."""

    def test_mixed_created_at_items(self) -> None:
        """Response with mix of items (some with created_at, some without)."""
        items = [
            MemoryItem(id="mem-1", memory="Has date", created_at=datetime.now(tz=UTC)),
            MemoryItem(id="mem-2", memory="No date"),
            MemoryItem(id="mem-3", memory="Also has date", created_at=datetime.now(tz=UTC)),
        ]
        response = MemoryListResponse(memories=items)
        data = response.model_dump()
        assert data["memories"][0]["created_at"] is not None
        assert data["memories"][1]["created_at"] is None
        assert data["memories"][2]["created_at"] is not None

    def test_json_round_trip(self) -> None:
        """MemoryListResponse survives JSON round-trip."""
        items = [
            MemoryItem(id="mem-1", memory="First"),
            MemoryItem(id="mem-2", memory="Second", created_at=datetime.now(tz=UTC)),
        ]
        original = MemoryListResponse(memories=items)
        json_str = original.model_dump_json()
        restored = MemoryListResponse.model_validate_json(json_str)
        assert len(restored.memories) == 2
        assert restored.memories[0].id == "mem-1"
        assert restored.memories[1].id == "mem-2"

    def test_model_dump_json_produces_valid_json(self) -> None:
        """model_dump_json output can be parsed by standard json library."""
        response = MemoryListResponse(
            memories=[
                MemoryItem(id="mem-1", memory="Test"),
            ],
        )
        json_str = response.model_dump_json()
        parsed = json.loads(json_str)
        assert "memories" in parsed
        assert len(parsed["memories"]) == 1

    def test_empty_response_json(self) -> None:
        """Empty response serializes to {"memories": []} in JSON."""
        response = MemoryListResponse(memories=[])
        json_str = response.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed == {"memories": []}

    def test_response_from_dict_list(self) -> None:
        """MemoryListResponse can be constructed from a list of dicts (model_validate)."""
        data = {
            "memories": [
                {"id": "mem-1", "memory": "Test", "created_at": None},
                {"id": "mem-2", "memory": "Test 2", "created_at": "2026-01-01T00:00:00Z"},
            ],
        }
        response = MemoryListResponse.model_validate(data)
        assert len(response.memories) == 2
        assert response.memories[0].created_at is None
        assert response.memories[1].created_at is not None
