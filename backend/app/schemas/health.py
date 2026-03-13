"""Pydantic schemas for the health endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class DependencyStatus(BaseModel):
    """Status of upstream dependencies."""

    database: str  # "ok" | "degraded" | "unavailable"
    mem0: str  # "ok" | "degraded" | "unavailable"
    claude: str  # "ok" | "degraded" | "unavailable"


class CircuitBreakerStatus(BaseModel):
    """Status of a single circuit breaker."""

    state: str  # "closed" | "open" | "half_open"
    failure_count: int
    last_failure_at: str | None = None
    last_success_at: str | None = None
    retry_queue_size: int
    cache_entries: int


class CircuitBreakerReport(BaseModel):
    """Report of all circuit breakers in the system."""

    mem0: CircuitBreakerStatus


class HealthResponse(BaseModel):
    """Response schema for GET /api/v1/health."""

    status: str
    version: str
    dependencies: DependencyStatus | None = None
    circuit_breaker: CircuitBreakerReport | None = None
