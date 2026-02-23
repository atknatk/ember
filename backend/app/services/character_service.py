"""Character service — business logic for character CRUD operations.

Handles listing, creating, updating, and soft-deleting AI characters.
Claude Haiku is used for automatic system prompt generation on creation.
"""

from __future__ import annotations

import logging
import uuid

from anthropic import AsyncAnthropic
from fastapi import HTTPException, status
from sqlalchemy import select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.character import Character
from app.models.conversation import Conversation
from app.schemas.character import CharacterDetail, CharacterListItem

logger = logging.getLogger("ember")

# Template role descriptions for the meta-prompt sent to Claude Haiku.
TEMPLATE_ROLES: dict[str, str] = {
    "companion": (
        "A personal AI companion and holistic life friend covering fitness, "
        "nutrition, work, stress, and relationships. Warm, honest, genuine "
        "but not overly positive."
    ),
    "english_teacher": (
        "An English language teacher who teaches through conversation. "
        "Corrects mistakes gently but stays motivating. Adapts to the "
        "user's level."
    ),
    "therapist": (
        "An emotional support assistant. Listens, reflects, does not judge. "
        "Never diagnoses or prescribes medication. Recommends professional "
        "help when needed. Uses CBT-based approaches."
    ),
    "fitness_coach": (
        "A fitness and nutrition coach. Provides workout programming, form "
        "advice, and nutrition support. Tracks progress and is mindful of "
        "injuries."
    ),
    "career_coach": (
        "A career development coach. Helps with goal setting, negotiation, "
        "leadership, and work-life balance. Pragmatic and honest."
    ),
}


def _build_meta_prompt(
    character_name: str,
    user_name: str,
    template: str,
    description: str | None,
) -> str:
    """Build the meta-prompt sent to Claude Haiku for system prompt generation."""
    if template == "custom":
        return (
            "Generate a system prompt for a custom AI character with the "
            "following specifications:\n\n"
            f"Character name: {character_name}\n"
            f"User's name: {user_name}\n"
            f"Character description (provided by the user): {description}\n\n"
            "The system prompt should:\n"
            "- Faithfully implement the user's description\n"
            "- Address the user by name naturally\n"
            "- Define the character's personality, tone, and expertise "
            "based on the description\n"
            "- Include instructions to remember things naturally "
            "(never say 'I remember that...')\n"
            "- Keep responses concise and conversational\n"
            "- Be written in second person ('You are...')\n"
            "- Be between 100-300 words\n\n"
            "Output ONLY the system prompt text, nothing else."
        )

    role = TEMPLATE_ROLES[template]
    return (
        "Generate a system prompt for an AI character with the "
        "following specifications:\n\n"
        f"Character name: {character_name}\n"
        f"User's name: {user_name}\n"
        f"Role: {role}\n\n"
        "The system prompt should:\n"
        "- Address the user by name naturally\n"
        "- Define the character's personality, tone, and expertise\n"
        "- Include instructions to remember things naturally "
        "(never say 'I remember that...')\n"
        "- Keep responses concise and conversational\n"
        "- Be written in second person ('You are...')\n"
        "- Be between 100-300 words\n\n"
        "Output ONLY the system prompt text, nothing else."
    )


class CharacterService:
    """Encapsulates all character CRUD business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    async def list_characters(
        self,
        user_id: uuid.UUID,
    ) -> list[CharacterListItem]:
        """List all active characters for a user with last_message_at from conversations."""
        stmt = (
            select(Character, Conversation.last_message_at)
            .outerjoin(Conversation, Conversation.character_id == Character.id)
            .where(Character.user_id == user_id, Character.is_active == true())
            .order_by(
                Conversation.last_message_at.desc().nulls_last(),
                Character.created_at.desc(),
            )
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        items: list[CharacterListItem] = []
        for character, last_message_at in rows:
            items.append(
                CharacterListItem(
                    id=str(character.id),
                    name=character.name,
                    template=character.template,
                    description=character.description,
                    avatar_style=character.avatar_style,
                    is_default=character.is_default,
                    last_message_at=last_message_at,
                    created_at=character.created_at,
                ),
            )
        return items

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_character(
        self,
        user_id: uuid.UUID,
        user_name: str,
        name: str,
        template: str,
        description: str | None,
    ) -> CharacterDetail:
        """Create a new character with auto-generated system prompt and conversation."""
        # Generate system prompt via Claude Haiku
        system_prompt = await self._generate_system_prompt(
            character_name=name,
            user_name=user_name,
            template=template,
            description=description,
        )

        # Compute mem0_agent_id with uniqueness handling
        character_id = uuid.uuid4()
        mem0_agent_id = await self._compute_mem0_agent_id(
            template=template,
            user_id=user_id,
            character_id=character_id,
        )

        # Create Character row
        character = Character(
            id=character_id,
            user_id=user_id,
            name=name,
            template=template,
            description=description,
            system_prompt=system_prompt,
            mem0_agent_id=mem0_agent_id,
            avatar_style="default",
            is_default=False,
            is_active=True,
        )
        self.db.add(character)

        # Create Conversation row
        conversation = Conversation(
            id=uuid.uuid4(),
            user_id=user_id,
            character_id=character_id,
            last_message_at=None,
        )
        self.db.add(conversation)

        # Commit both in a single transaction
        await self.db.commit()
        await self.db.refresh(character)

        return CharacterDetail.model_validate(character)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_character(
        self,
        character_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str | None,
        system_prompt: str | None,
        avatar_style: str | None,
    ) -> CharacterDetail:
        """Update mutable fields on an existing character."""
        character = await self._get_active_character(character_id)

        # Ownership check
        if character.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Character does not belong to user",
            )

        # Apply updates
        if name is not None:
            character.name = name
        if system_prompt is not None:
            character.system_prompt = system_prompt
        if avatar_style is not None:
            character.avatar_style = avatar_style

        await self.db.commit()
        await self.db.refresh(character)

        return CharacterDetail.model_validate(character)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_character(
        self,
        character_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Soft-delete a character by setting is_active=false."""
        character = await self._get_active_character(character_id)

        # Ownership check
        if character.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Character does not belong to user",
            )

        # Default character protection
        if character.is_default:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Default character cannot be deleted",
            )

        character.is_active = False
        await self.db.commit()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _get_active_character(self, character_id: uuid.UUID) -> Character:
        """Look up an active character by id, raising 404 if not found."""
        result = await self.db.execute(
            select(Character).where(
                Character.id == character_id,
                Character.is_active == true(),
            ),
        )
        character = result.scalar_one_or_none()
        if character is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Character not found",
            )
        return character

    async def _generate_system_prompt(
        self,
        character_name: str,
        user_name: str,
        template: str,
        description: str | None,
    ) -> str:
        """Call Claude Haiku to generate a system prompt for the character."""
        meta_prompt = _build_meta_prompt(
            character_name=character_name,
            user_name=user_name,
            template=template,
            description=description,
        )

        try:
            client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            response = await client.messages.create(
                model=settings.claude_haiku_model,
                max_tokens=512,
                messages=[{"role": "user", "content": meta_prompt}],
            )
            return response.content[0].text
        except Exception:
            logger.exception("Claude Haiku API error during system prompt generation")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service unavailable, please try again",
            ) from None

    async def _compute_mem0_agent_id(
        self,
        template: str,
        user_id: uuid.UUID,
        character_id: uuid.UUID,
    ) -> str:
        """Compute a unique mem0_agent_id for the character.

        Default format: ``{template}_{user_id}``.
        Fallback (if a character with the same template exists for this user):
        ``{template}_{character_uuid[:8]}_{user_id}``.
        """
        default_agent_id = f"{template}_{user_id}"

        # Check if any character (active or inactive) already uses this agent_id
        result = await self.db.execute(
            select(Character.id).where(Character.mem0_agent_id == default_agent_id),
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            return default_agent_id

        # Uniqueness conflict: append short UUID discriminator
        short_uuid = str(character_id)[:8]
        return f"{template}_{short_uuid}_{user_id}"
