"""Tests for Pydantic response schemas.

Verifies HealthResponse schema validation and serialization.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.schemas.health import HealthResponse


@pytest.mark.asyncio
async def test_health_response_is_pydantic_model() -> None:
    """HealthResponse must be a Pydantic BaseModel subclass."""
    assert issubclass(HealthResponse, BaseModel)


@pytest.mark.asyncio
async def test_health_response_has_required_fields() -> None:
    """HealthResponse must have 'status' and 'version' fields."""
    fields = set(HealthResponse.model_fields.keys())
    assert "status" in fields
    assert "version" in fields


@pytest.mark.asyncio
async def test_health_response_serialization() -> None:
    """HealthResponse should serialize to dict with correct keys."""
    response = HealthResponse(status="ok", version="1.0.0")
    data = response.model_dump()
    assert data == {"status": "ok", "version": "1.0.0"}
