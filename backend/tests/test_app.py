"""Smoke tests for the FastAPI application.

Verifies the app factory works, CORS is configured, and unknown routes return 404.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.main import create_app


@pytest.mark.asyncio
async def test_create_app_returns_fastapi_instance() -> None:
    """create_app() should return a FastAPI instance."""
    application = create_app()
    assert isinstance(application, FastAPI)


@pytest.mark.asyncio
async def test_cors_middleware_present(client: AsyncClient) -> None:
    """CORS headers should be present in responses to preflight requests."""
    response = await client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" in response.headers


@pytest.mark.asyncio
async def test_unknown_route_returns_404(client: AsyncClient) -> None:
    """GET /api/v1/nonexistent should return 404."""
    response = await client.get("/api/v1/nonexistent")
    assert response.status_code == 404
