"""Pydantic schemas for the health endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response schema for GET /api/v1/health."""

    status: str
    version: str
