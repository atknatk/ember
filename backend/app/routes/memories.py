"""Memory route handlers.

Provides endpoints for reading and deleting Mem0 memories.
Two routers are defined:
  - global_router: for GET /memories (global/General Friend memories)
  - character_router: for character-scoped memory operations

All endpoints require JWT authentication. Business logic is delegated
to MemoryService.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.profile import Profile
from app.schemas.memory import MemoryListResponse
from app.services.memory_service import MemoryService

# ---------------------------------------------------------------------------
# Global memories router — registered under /api/v1
# ---------------------------------------------------------------------------

global_router = APIRouter()


@global_router.get(
    "/memories",
    response_model=MemoryListResponse,
)
async def get_global_memories(
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryListResponse:
    """Retrieve global (non-character-scoped) memories from Mem0.

    Returns memories stored without an agent_id, visible to all characters.
    """
    service = MemoryService(db)
    items = await service.get_global_memories(
        mem0_user_id=current_user.mem0_user_id,
    )
    return MemoryListResponse(memories=items)


@global_router.delete(
    "/memories/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_global_memory(
    memory_id: str,
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a single global memory from Mem0.

    Validates that the memory belongs to the authenticated user.
    Idempotent: returns 204 even if the memory_id does not exist.
    """
    service = MemoryService(db)
    await service.delete_global_memory(
        mem0_user_id=current_user.mem0_user_id,
        memory_id=memory_id,
    )


# ---------------------------------------------------------------------------
# Character-scoped memories router — registered under /api/v1/characters
# ---------------------------------------------------------------------------

character_router = APIRouter()


@character_router.get(
    "/{character_id}/memories",
    response_model=MemoryListResponse,
)
async def get_character_memories(
    character_id: uuid.UUID,
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MemoryListResponse:
    """Retrieve all memories stored in Mem0 for a specific character."""
    service = MemoryService(db)
    items = await service.get_character_memories(
        character_id=character_id,
        user_id=current_user.id,
        mem0_user_id=current_user.mem0_user_id,
    )
    return MemoryListResponse(memories=items)


@character_router.delete(
    "/{character_id}/memories/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_character_memory(
    character_id: uuid.UUID,
    memory_id: str,
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a single memory from Mem0.

    Idempotent: returns 204 even if the memory_id does not exist in Mem0.
    """
    service = MemoryService(db)
    await service.delete_character_memory(
        character_id=character_id,
        user_id=current_user.id,
        memory_id=memory_id,
    )


@character_router.delete(
    "/{character_id}/memories",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_all_character_memories(
    character_id: uuid.UUID,
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete ALL memories for a specific character from Mem0.

    Only deletes memories scoped to this character's mem0_agent_id.
    Does not affect global memories.
    """
    service = MemoryService(db)
    await service.delete_all_character_memories(
        character_id=character_id,
        user_id=current_user.id,
        mem0_user_id=current_user.mem0_user_id,
    )
