"""Tests for the health check endpoint.

Verifies GET /api/v1/health returns correct status and requires no auth.
Also verifies the enhanced dependency check functionality.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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
async def test_health_without_check_dependencies_has_null_dependencies(
    client: AsyncClient,
) -> None:
    """Without check_dependencies param, dependencies should be null."""
    response = await client.get("/api/v1/health")
    data = response.json()
    assert data.get("dependencies") is None


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


@pytest.mark.asyncio
async def test_health_check_dependencies_all_healthy(client: AsyncClient) -> None:
    """With check_dependencies=true and all deps healthy, all should be 'ok'."""
    with (
        patch(
            "app.services.health_service.HealthService._probe_database",
            new_callable=AsyncMock,
            return_value="ok",
        ),
        patch(
            "app.services.health_service.HealthService._probe_mem0",
            new_callable=AsyncMock,
            return_value="ok",
        ),
        patch(
            "app.services.health_service.HealthService._probe_claude",
            new_callable=AsyncMock,
            return_value="ok",
        ),
    ):
        response = await client.get("/api/v1/health?check_dependencies=true")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        deps = data["dependencies"]
        assert deps is not None
        assert deps["database"] == "ok"
        assert deps["mem0"] == "ok"
        assert deps["claude"] == "ok"


@pytest.mark.asyncio
async def test_health_check_db_unavailable(client: AsyncClient) -> None:
    """With database down, database should be 'unavailable' but status still 200."""
    with (
        patch(
            "app.services.health_service.HealthService._probe_database",
            new_callable=AsyncMock,
            return_value="unavailable",
        ),
        patch(
            "app.services.health_service.HealthService._probe_mem0",
            new_callable=AsyncMock,
            return_value="ok",
        ),
        patch(
            "app.services.health_service.HealthService._probe_claude",
            new_callable=AsyncMock,
            return_value="ok",
        ),
    ):
        response = await client.get("/api/v1/health?check_dependencies=true")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["dependencies"]["database"] == "unavailable"


@pytest.mark.asyncio
async def test_health_check_db_degraded(client: AsyncClient) -> None:
    """With slow DB (>1s), database should be 'degraded'."""
    with (
        patch(
            "app.services.health_service.HealthService._probe_database",
            new_callable=AsyncMock,
            return_value="degraded",
        ),
        patch(
            "app.services.health_service.HealthService._probe_mem0",
            new_callable=AsyncMock,
            return_value="ok",
        ),
        patch(
            "app.services.health_service.HealthService._probe_claude",
            new_callable=AsyncMock,
            return_value="ok",
        ),
    ):
        response = await client.get("/api/v1/health?check_dependencies=true")
        assert response.status_code == 200
        assert response.json()["dependencies"]["database"] == "degraded"


@pytest.mark.asyncio
async def test_health_returns_200_even_when_all_deps_down(client: AsyncClient) -> None:
    """Health check must always return 200 regardless of dependency status."""
    with (
        patch(
            "app.services.health_service.HealthService._probe_database",
            new_callable=AsyncMock,
            return_value="unavailable",
        ),
        patch(
            "app.services.health_service.HealthService._probe_mem0",
            new_callable=AsyncMock,
            return_value="unavailable",
        ),
        patch(
            "app.services.health_service.HealthService._probe_claude",
            new_callable=AsyncMock,
            return_value="unavailable",
        ),
    ):
        response = await client.get("/api/v1/health?check_dependencies=true")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
