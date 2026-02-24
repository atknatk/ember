"""Tests for Dockerfile and docker-compose.yml validity.

Basic structural checks to verify the Docker files match the spec:
multi-stage build, non-root user, health check, correct services, etc.
"""

from __future__ import annotations

from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).parent.parent


@pytest.mark.asyncio
async def test_dockerfile_exists() -> None:
    """Dockerfile must exist in the backend directory."""
    assert (BACKEND_DIR / "Dockerfile").exists()


@pytest.mark.asyncio
async def test_dockerfile_uses_multistage_build() -> None:
    """Dockerfile must use a multi-stage build (FROM ... AS builder)."""
    content = (BACKEND_DIR / "Dockerfile").read_text()
    assert "AS builder" in content or "as builder" in content


@pytest.mark.asyncio
async def test_dockerfile_uses_python_312_slim() -> None:
    """Dockerfile must use python:3.12-slim base image."""
    content = (BACKEND_DIR / "Dockerfile").read_text()
    assert "python:3.12-slim" in content


@pytest.mark.asyncio
async def test_dockerfile_creates_nonroot_user() -> None:
    """Dockerfile must create a non-root 'ember' user."""
    content = (BACKEND_DIR / "Dockerfile").read_text()
    assert "ember" in content
    assert "USER ember" in content or "USER ember" in content


@pytest.mark.asyncio
async def test_dockerfile_exposes_port_8000() -> None:
    """Dockerfile must EXPOSE port 8000."""
    content = (BACKEND_DIR / "Dockerfile").read_text()
    assert "EXPOSE 8000" in content


@pytest.mark.asyncio
async def test_dockerfile_has_health_check() -> None:
    """Dockerfile must include a HEALTHCHECK directive hitting /api/v1/health."""
    content = (BACKEND_DIR / "Dockerfile").read_text()
    assert "HEALTHCHECK" in content
    assert "/api/v1/health" in content


@pytest.mark.asyncio
async def test_dockerfile_entrypoint_uses_uvicorn() -> None:
    """Dockerfile ENTRYPOINT must use uvicorn with app.main:app."""
    content = (BACKEND_DIR / "Dockerfile").read_text()
    assert "uvicorn" in content
    assert "app.main:app" in content


@pytest.mark.asyncio
async def test_dockerfile_contains_no_secrets() -> None:
    """Dockerfile must not contain any API keys or hardcoded secrets."""
    content = (BACKEND_DIR / "Dockerfile").read_text()
    forbidden = ["API_KEY=", "api_key=", "SECRET=", "PASSWORD="]
    for pattern in forbidden:
        assert pattern not in content, f"Dockerfile must not contain '{pattern}'"


@pytest.mark.asyncio
async def test_docker_compose_exists() -> None:
    """docker-compose.yml must exist in the backend directory."""
    assert (BACKEND_DIR / "docker-compose.yml").exists()


@pytest.mark.asyncio
async def test_docker_compose_has_db_service() -> None:
    """docker-compose.yml must define a 'db' service with postgres:16-alpine."""
    content = (BACKEND_DIR / "docker-compose.yml").read_text()
    assert "db:" in content
    assert "postgres:16-alpine" in content


@pytest.mark.asyncio
async def test_docker_compose_has_backend_service() -> None:
    """docker-compose.yml must define a 'backend' service."""
    content = (BACKEND_DIR / "docker-compose.yml").read_text()
    assert "backend:" in content


@pytest.mark.asyncio
async def test_docker_compose_db_uses_named_volume() -> None:
    """docker-compose.yml must use a named volume for PostgreSQL data."""
    content = (BACKEND_DIR / "docker-compose.yml").read_text()
    assert "ember_pgdata" in content


@pytest.mark.asyncio
async def test_docker_compose_backend_depends_on_db() -> None:
    """docker-compose.yml backend service must depend on db."""
    content = (BACKEND_DIR / "docker-compose.yml").read_text()
    assert "depends_on" in content
    assert "service_healthy" in content


@pytest.mark.asyncio
async def test_docker_compose_db_healthcheck() -> None:
    """docker-compose.yml db service must have a health check with pg_isready."""
    content = (BACKEND_DIR / "docker-compose.yml").read_text()
    assert "pg_isready" in content


@pytest.mark.asyncio
async def test_docker_compose_backend_hot_reload() -> None:
    """docker-compose.yml backend must use --reload for hot reload in dev."""
    content = (BACKEND_DIR / "docker-compose.yml").read_text()
    assert "--reload" in content
