"""Pydantic response schemas for memory endpoints.

Covers the response models for listing and individual memory items
returned from Mem0. No request schemas are needed as all endpoints
use path parameters only.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class MemoryItem(BaseModel):
    """A single memory entry from Mem0."""

    id: str
    memory: str
    created_at: datetime | None = None


class MemoryListResponse(BaseModel):
    """Response for memory list endpoints (character-scoped and global)."""

    memories: list[MemoryItem]
