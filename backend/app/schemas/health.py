"""Pydantic schemas for the health endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class DependencyStatus(BaseModel):
    """Status of upstream dependencies."""

    database: str  # "ok" | "degraded" | "unavailable"
    mem0: str  # "ok" | "degraded" | "unavailable"
    claude: str  # "ok" | "degraded" | "unavailable"


class HealthResponse(BaseModel):
    """Response schema for GET /api/v1/health."""

    status: str
    version: str
    dependencies: DependencyStatus | None = None
