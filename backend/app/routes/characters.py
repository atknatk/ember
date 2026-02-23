"""Character CRUD route handlers.

Provides endpoints for listing, creating, updating, and soft-deleting
AI characters. All endpoints require JWT authentication. Business logic
is delegated to CharacterService.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_db
from app.models.profile import Profile
from app.schemas.character import (
    CharacterDetail,
    CharacterListResponse,
    CreateCharacterRequest,
    UpdateCharacterRequest,
)
from app.services.character_service import CharacterService

router = APIRouter()


@router.get(
    "",
    response_model=CharacterListResponse,
)
async def list_characters(
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CharacterListResponse:
    """List all active characters for the authenticated user.

    Characters are ordered by last_message_at DESC (NULLS LAST),
    then by created_at DESC.
    """
    service = CharacterService(db)
    items = await service.list_characters(user_id=current_user.id)
    return CharacterListResponse(characters=items)


@router.post(
    "",
    response_model=CharacterDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_character(
    body: CreateCharacterRequest,
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CharacterDetail:
    """Create a new AI character with an auto-generated system prompt.

    Auto-creates the corresponding conversation row. Uses Claude Haiku
    for system prompt generation.
    """
    service = CharacterService(db)
    return await service.create_character(
        user_id=current_user.id,
        user_name=current_user.name,
        name=body.name,
        template=body.template,
        description=body.description,
    )


@router.put(
    "/{character_id}",
    response_model=CharacterDetail,
)
async def update_character(
    character_id: uuid.UUID,
    body: UpdateCharacterRequest,
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CharacterDetail:
    """Update a character's mutable fields (name, system_prompt, avatar_style).

    Enforces ownership: the character must belong to the authenticated user.
    """
    service = CharacterService(db)
    return await service.update_character(
        character_id=character_id,
        user_id=current_user.id,
        name=body.name,
        system_prompt=body.system_prompt,
        avatar_style=body.avatar_style,
    )


@router.delete(
    "/{character_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_character(
    character_id: uuid.UUID,
    current_user: Profile = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a character by setting is_active=false.

    The default character (General Friend) cannot be deleted and returns 403.
    Enforces ownership.
    """
    service = CharacterService(db)
    await service.delete_character(
        character_id=character_id,
        user_id=current_user.id,
    )
