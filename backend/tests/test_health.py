"""Tests for the health check endpoint.

Verifies GET /api/v1/health returns correct status and requires no auth.
Also verifies response schema shape and content-type.
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


@pytest.mark.asyncio
async def test_health_response_schema_shape(client: AsyncClient) -> None:
    """Health response body must contain exactly 'status' and 'version' keys."""
    response = await client.get("/api/v1/health")
    data = response.json()
    assert set(data.keys()) == {"status", "version"}


@pytest.mark.asyncio
async def test_health_response_content_type(client: AsyncClient) -> None:
    """Health endpoint must return application/json content type."""
    response = await client.get("/api/v1/health")
    assert "application/json" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_health_head_method_not_allowed(client: AsyncClient) -> None:
    """POST to health endpoint should return 405 Method Not Allowed."""
    response = await client.post("/api/v1/health")
    assert response.status_code == 405
