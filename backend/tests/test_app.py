"""Smoke tests for the FastAPI application.

Verifies the app factory works, CORS is configured, unknown routes return 404,
global exception handler works, and app metadata is correct.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import app, create_app


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


@pytest.mark.asyncio
async def test_app_title_and_version() -> None:
    """App title must be 'Ember API' and version '1.0.0'."""
    application = create_app()
    assert application.title == "Ember API"
    assert application.version == "1.0.0"


@pytest.mark.asyncio
async def test_cors_allows_all_methods(client: AsyncClient) -> None:
    """CORS should allow all HTTP methods via Access-Control-Allow-Methods."""
    response = await client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    allow_methods = response.headers.get("access-control-allow-methods", "")
    # Wildcard "*" or explicit list including POST
    assert "POST" in allow_methods or "*" in allow_methods


@pytest.mark.asyncio
async def test_cors_allows_all_headers(client: AsyncClient) -> None:
    """CORS should allow the Authorization header."""
    response = await client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    allow_headers = response.headers.get("access-control-allow-headers", "")
    assert "authorization" in allow_headers.lower() or "*" in allow_headers


@pytest.mark.asyncio
async def test_cors_allows_credentials(client: AsyncClient) -> None:
    """CORS should set allow-credentials to true."""
    response = await client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_health_router_registered_under_api_v1(client: AsyncClient) -> None:
    """Health route must be at /api/v1/health, not /health."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200

    # /health without prefix should not exist
    response_no_prefix = await client.get("/health")
    assert response_no_prefix.status_code == 404


@pytest.mark.asyncio
async def test_module_level_app_is_fastapi() -> None:
    """The module-level `app` object must be a FastAPI instance."""
    assert isinstance(app, FastAPI)


@pytest.mark.asyncio
async def test_global_exception_handler_returns_500() -> None:
    """Unhandled exceptions must return 500 with {"detail": "Internal server error"}."""
    # Create a fresh app to avoid polluting the shared app with test routes
    test_app = create_app()

    @test_app.get("/api/v1/_test_error")
    async def _raise_error() -> None:
        raise RuntimeError("Intentional test error")

    transport = ASGITransport(app=test_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/v1/_test_error")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}


@pytest.mark.asyncio
async def test_lifespan_calls_setup_logging() -> None:
    """The lifespan context manager should call setup_logging on startup."""
    from unittest.mock import AsyncMock, patch

    from app.main import lifespan

    test_app = FastAPI()
    with patch("app.main.setup_logging") as mock_setup, \
         patch("app.main.engine") as mock_engine:
        mock_engine.dispose = AsyncMock()
        async with lifespan(test_app):
            mock_setup.assert_called_once()

        # engine.dispose should be called on shutdown
        mock_engine.dispose.assert_called_once()


@pytest.mark.asyncio
async def test_lifespan_disposes_engine_on_shutdown() -> None:
    """The lifespan must call engine.dispose() during shutdown."""
    from unittest.mock import AsyncMock, patch

    from app.main import lifespan

    test_app = FastAPI()
    with patch("app.main.setup_logging"), \
         patch("app.main.engine") as mock_engine:
        mock_engine.dispose = AsyncMock()
        async with lifespan(test_app):
            pass
        mock_engine.dispose.assert_awaited_once()
