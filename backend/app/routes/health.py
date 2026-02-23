"""Health check endpoint for ECS Fargate and load balancer probes.

This endpoint is public (no auth required) and must not touch the database
or any external service. It must respond within 5 seconds.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return application health status and version."""
    return HealthResponse(status="ok", version=settings.app_version)
