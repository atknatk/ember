"""Tests for the health check endpoint.

Verifies GET /api/v1/health returns correct status and requires no auth.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    """GET /api/v1/health should return 200 with status and version."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_health_requires_no_auth(client: AsyncClient) -> None:
    """GET /api/v1/health should succeed without an Authorization header."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert "status" in response.json()
