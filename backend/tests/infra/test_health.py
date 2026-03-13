"""Tests for the health check endpoint.

Verifies GET /api/v1/health returns correct status and requires no auth.
Also verifies the enhanced dependency check functionality.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from app.services.health_service import HealthService


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


class TestHealthServiceProbes:
    """Unit tests for HealthService probe methods, testing each path directly."""

    @pytest.fixture
    def service(self) -> "HealthService":
        from app.services.health_service import HealthService
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock())
        return HealthService(db=mock_db)

    @pytest.mark.asyncio
    async def test_probe_database_returns_ok_on_fast_response(self, service: "HealthService") -> None:
        """Fast DB response (< degraded_threshold) returns 'ok'."""
        result = await service._probe_database(check_timeout=3.0, degraded_threshold=1.0)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_probe_database_returns_unavailable_on_exception(self, service: "HealthService") -> None:
        """DB connection exception returns 'unavailable'."""
        service.db.execute = AsyncMock(side_effect=Exception("DB connection refused"))
        result = await service._probe_database(check_timeout=3.0, degraded_threshold=1.0)
        assert result == "unavailable"

    @pytest.mark.asyncio
    async def test_probe_database_returns_unavailable_on_timeout(self, service: "HealthService") -> None:
        """DB timeout (asyncio.TimeoutError) returns 'unavailable'."""
        async def _slow() -> None:
            await asyncio.sleep(10)

        service.db.execute = AsyncMock(side_effect=asyncio.TimeoutError)
        result = await service._probe_database(check_timeout=0.01, degraded_threshold=1.0)
        assert result == "unavailable"

    @pytest.mark.asyncio
    async def test_probe_database_returns_degraded_on_slow_response(self, service: "HealthService") -> None:
        """DB response slower than degraded_threshold returns 'degraded'."""
        import time

        original_execute = service.db.execute

        async def _slow_execute(*args, **kwargs):  # type: ignore[no-untyped-def]
            await asyncio.sleep(0.05)
            return MagicMock()

        service.db.execute = _slow_execute

        # Set degraded_threshold very low so any real response is "degraded"
        result = await service._probe_database(check_timeout=3.0, degraded_threshold=0.001)
        assert result == "degraded"

    @pytest.mark.asyncio
    async def test_probe_mem0_returns_unavailable_on_exception(self, service: "HealthService") -> None:
        """Mem0 probe exception (e.g., import error, API error) returns 'unavailable'."""
        # Patch wait_for to raise before any coroutine is created to avoid RuntimeWarning
        with patch("app.services.health_service.asyncio.wait_for", side_effect=Exception("mem0 api error")):
            result = await service._probe_mem0(check_timeout=3.0, degraded_threshold=1.0)
        assert result == "unavailable"

    @pytest.mark.asyncio
    async def test_probe_mem0_returns_unavailable_on_timeout(self, service: "HealthService") -> None:
        """Mem0 probe that times out returns 'unavailable'."""
        with patch("app.services.health_service.asyncio.wait_for", side_effect=asyncio.TimeoutError):
            result = await service._probe_mem0(check_timeout=0.001, degraded_threshold=1.0)
        assert result == "unavailable"

    @pytest.mark.asyncio
    async def test_probe_claude_returns_unavailable_on_exception(self, service: "HealthService") -> None:
        """Claude probe exception returns 'unavailable'."""
        # Patch wait_for to raise before any coroutine is created to avoid RuntimeWarning
        with patch("app.services.health_service.asyncio.wait_for", side_effect=Exception("claude api error")):
            result = await service._probe_claude(check_timeout=3.0, degraded_threshold=1.0)
        assert result == "unavailable"

    @pytest.mark.asyncio
    async def test_probe_claude_returns_unavailable_on_timeout(self, service: "HealthService") -> None:
        """Claude probe that times out returns 'unavailable'."""
        with patch("app.services.health_service.asyncio.wait_for", side_effect=asyncio.TimeoutError):
            result = await service._probe_claude(check_timeout=0.001, degraded_threshold=1.0)
        assert result == "unavailable"

    @pytest.mark.asyncio
    async def test_check_dependencies_treats_gather_exception_as_unavailable(
        self, service: "HealthService"
    ) -> None:
        """If a probe raises inside gather(return_exceptions=True), it maps to 'unavailable'."""
        # Patch probes to raise so asyncio.gather returns Exception objects
        with (
            patch.object(
                service.__class__,
                "_probe_database",
                new_callable=AsyncMock,
                return_value=Exception("probe exploded"),
            ),
            patch.object(
                service.__class__,
                "_probe_mem0",
                new_callable=AsyncMock,
                return_value=Exception("probe exploded"),
            ),
            patch.object(
                service.__class__,
                "_probe_claude",
                new_callable=AsyncMock,
                return_value=Exception("probe exploded"),
            ),
        ):
            # Directly test the isinstance check by calling check_dependencies
            # with probes returning raw Exception instances (what gather does on error)
            from app.services.health_service import HealthService

            real_service = HealthService(db=service.db)

            async def _raise_db(timeout, threshold):  # type: ignore[no-untyped-def]
                raise RuntimeError("db exploded")

            async def _raise_mem0(timeout, threshold):  # type: ignore[no-untyped-def]
                raise RuntimeError("mem0 exploded")

            async def _raise_claude(timeout, threshold):  # type: ignore[no-untyped-def]
                raise RuntimeError("claude exploded")

            with (
                patch.object(real_service, "_probe_database", _raise_db),
                patch.object(real_service, "_probe_mem0", _raise_mem0),
                patch.object(real_service, "_probe_claude", _raise_claude),
            ):
                result = await real_service.check_dependencies()

            assert result.database == "unavailable"
            assert result.mem0 == "unavailable"
            assert result.claude == "unavailable"

    @pytest.mark.asyncio
    async def test_probe_mem0_returns_ok_on_fast_response(self, service: "HealthService") -> None:
        """Mem0 probe that responds quickly returns 'ok'."""
        # Mock wait_for to return immediately (success path)
        async def _fast_wait_for(coro, timeout):  # type: ignore[no-untyped-def]
            return None  # simulate fast return

        with patch("app.services.health_service.asyncio.wait_for", _fast_wait_for):
            result = await service._probe_mem0(check_timeout=3.0, degraded_threshold=1.0)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_probe_mem0_returns_degraded_on_slow_response(self, service: "HealthService") -> None:
        """Mem0 probe that responds slowly returns 'degraded'."""
        async def _slow_wait_for(coro, timeout):  # type: ignore[no-untyped-def]
            await asyncio.sleep(0.05)
            return None

        with patch("app.services.health_service.asyncio.wait_for", _slow_wait_for):
            result = await service._probe_mem0(check_timeout=3.0, degraded_threshold=0.001)
        assert result == "degraded"

    @pytest.mark.asyncio
    async def test_probe_claude_returns_ok_on_fast_response(self, service: "HealthService") -> None:
        """Claude probe that responds quickly returns 'ok'."""
        async def _fast_wait_for(coro, timeout):  # type: ignore[no-untyped-def]
            return None  # simulate fast return

        with patch("app.services.health_service.asyncio.wait_for", _fast_wait_for):
            result = await service._probe_claude(check_timeout=3.0, degraded_threshold=1.0)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_probe_claude_returns_degraded_on_slow_response(self, service: "HealthService") -> None:
        """Claude probe that responds slowly returns 'degraded'."""
        async def _slow_wait_for(coro, timeout):  # type: ignore[no-untyped-def]
            await asyncio.sleep(0.05)
            return None

        with patch("app.services.health_service.asyncio.wait_for", _slow_wait_for):
            result = await service._probe_claude(check_timeout=3.0, degraded_threshold=0.001)
        assert result == "degraded"

    @pytest.mark.asyncio
    async def test_parallel_response_within_5_seconds(self, service: "HealthService") -> None:
        """Even with all probes taking ~3s, parallel gather completes well under 9s total."""
        import time as _time

        async def _slow_probe(timeout, threshold):  # type: ignore[no-untyped-def]
            await asyncio.sleep(0.05)
            return "ok"

        with (
            patch.object(service, "_probe_database", _slow_probe),
            patch.object(service, "_probe_mem0", _slow_probe),
            patch.object(service, "_probe_claude", _slow_probe),
        ):
            start = _time.monotonic()
            result = await service.check_dependencies()
            elapsed = _time.monotonic() - start

        # Three probes each sleep 0.05s — parallel should finish in ~0.05s, not 0.15s
        assert elapsed < 0.12
        assert result.database == "ok"
        assert result.mem0 == "ok"
        assert result.claude == "ok"
