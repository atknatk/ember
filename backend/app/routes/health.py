"""Health check endpoint for ECS Fargate and load balancer probes.

This endpoint is public (no auth required) and must respond within 5 seconds.
When check_dependencies=true, it probes upstream dependencies (database,
Mem0, Claude) in parallel and reports their status, along with the circuit
breaker state.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.circuit_breaker import get_mem0_circuit_breaker
from app.dependencies import get_db
from app.schemas.health import (
    CircuitBreakerReport,
    CircuitBreakerStatus,
    HealthResponse,
)
from app.services.health_service import HealthService

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check(
    check_dependencies: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> HealthResponse:
    """Return application health status, version, and optional dependency status.

    Without check_dependencies: fast response for ECS probes (no external calls).
    With check_dependencies=true: probes database, Mem0, and Claude (for dashboards).
    Also includes circuit breaker status when check_dependencies=true.
    """
    if not check_dependencies:
        return HealthResponse(status="ok", version=settings.app_version)

    service = HealthService(db)
    dependencies = await service.check_dependencies()

    # Circuit breaker status
    breaker = get_mem0_circuit_breaker()
    cb_status_raw = breaker.get_status()
    cb_status = CircuitBreakerStatus(**cb_status_raw)
    cb_report = CircuitBreakerReport(mem0=cb_status)

    return HealthResponse(
        status="ok",
        version=settings.app_version,
        dependencies=dependencies,
        circuit_breaker=cb_report,
    )
