"""Memory service — business logic for reading and deleting Mem0 memories.

Handles listing character-scoped memories, deleting single or all memories
for a character, and listing global (non-character-scoped) memories.
All Mem0 SDK calls are synchronous and wrapped in asyncio.to_thread().

When the Mem0 circuit breaker is OPEN, user-facing memory management
endpoints return HTTP 503 immediately (see shared/feature-specs/mem0-circuit-breaker.md).
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import HTTPException, status
from mem0 import MemoryClient
from sqlalchemy import select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.circuit_breaker import (
    CircuitOpenError,
    CircuitState,
    get_mem0_circuit_breaker,
)
from app.models.character import Character
from app.schemas.memory import MemoryItem
from app.utils.timing import log_external_call

logger = logging.getLogger("ember")


class MemoryService:
    """Encapsulates all Mem0 memory read and delete operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def get_character_memories(
        self,
        character_id: uuid.UUID,
        user_id: uuid.UUID,
        mem0_user_id: str,
    ) -> list[MemoryItem]:
        """Get all Mem0 memories for a specific character.

        Raises:
            HTTPException(404): Character not found or inactive.
            HTTPException(403): Character does not belong to user.
            HTTPException(503): Mem0 API unavailable or circuit breaker open.
        """
        character = await self._get_owned_character(character_id, user_id)
        self._check_circuit()

        try:
            breaker = get_mem0_circuit_breaker()

            async def _do_get_all() -> list[dict[str, object]]:
                client = MemoryClient(api_key=settings.mem0_api_key)
                async with log_external_call("mem0", "get_all"):
                    return await asyncio.to_thread(
                        client.get_all,
                        user_id=mem0_user_id,
                        agent_id=character.mem0_agent_id,
                    )

            results = await breaker.call_with_breaker(_do_get_all)
        except CircuitOpenError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Memory service temporarily unavailable",
            ) from None
        except Exception:
            logger.exception(
                "Mem0 get_all failed for agent_id=%s", character.mem0_agent_id,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Memory service unavailable",
            ) from None

        return self._map_memories(results)

    async def delete_character_memory(
        self,
        character_id: uuid.UUID,
        user_id: uuid.UUID,
        memory_id: str,
    ) -> None:
        """Delete a single memory from Mem0.

        Idempotent: returns successfully even if memory_id does not exist.

        Raises:
            HTTPException(404): Character not found or inactive.
            HTTPException(403): Character does not belong to user.
            HTTPException(503): Mem0 API unavailable or circuit breaker open.
        """
        await self._get_owned_character(character_id, user_id)
        self._check_circuit()

        try:
            breaker = get_mem0_circuit_breaker()

            async def _do_delete() -> None:
                client = MemoryClient(api_key=settings.mem0_api_key)
                async with log_external_call("mem0", "delete"):
                    await asyncio.to_thread(client.delete, memory_id)

            await breaker.call_with_breaker(_do_delete)
        except CircuitOpenError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Memory service temporarily unavailable",
            ) from None
        except Exception as exc:
            # Treat "not found" from Mem0 as success (idempotent delete)
            exc_str = str(exc).lower()
            if "not found" in exc_str or "404" in exc_str:
                logger.debug(
                    "Mem0 delete memory_id=%s not found (treated as success)", memory_id,
                )
                return
            logger.exception(
                "Mem0 delete failed for memory_id=%s", memory_id,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Memory service unavailable",
            ) from None

    async def delete_all_character_memories(
        self,
        character_id: uuid.UUID,
        user_id: uuid.UUID,
        mem0_user_id: str,
    ) -> None:
        """Delete all Mem0 memories for a specific character.

        Raises:
            HTTPException(404): Character not found or inactive.
            HTTPException(403): Character does not belong to user.
            HTTPException(503): Mem0 API unavailable or circuit breaker open.
        """
        character = await self._get_owned_character(character_id, user_id)
        self._check_circuit()

        try:
            breaker = get_mem0_circuit_breaker()

            async def _do_delete_all() -> None:
                client = MemoryClient(api_key=settings.mem0_api_key)
                async with log_external_call("mem0", "delete_all"):
                    await asyncio.to_thread(
                        client.delete_all,
                        user_id=mem0_user_id,
                        agent_id=character.mem0_agent_id,
                    )

            await breaker.call_with_breaker(_do_delete_all)
        except CircuitOpenError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Memory service temporarily unavailable",
            ) from None
        except Exception:
            logger.exception(
                "Mem0 delete_all failed for agent_id=%s", character.mem0_agent_id,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Memory service unavailable",
            ) from None

    async def get_global_memories(
        self,
        mem0_user_id: str,
    ) -> list[MemoryItem]:
        """Get all global (non-character-scoped) Mem0 memories.

        Raises:
            HTTPException(503): Mem0 API unavailable or circuit breaker open.
        """
        self._check_circuit()

        try:
            breaker = get_mem0_circuit_breaker()

            async def _do_get_all() -> list[dict[str, object]]:
                client = MemoryClient(api_key=settings.mem0_api_key)
                async with log_external_call("mem0", "get_all"):
                    return await asyncio.to_thread(
                        client.get_all,
                        user_id=mem0_user_id,
                    )

            results = await breaker.call_with_breaker(_do_get_all)
        except CircuitOpenError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Memory service temporarily unavailable",
            ) from None
        except Exception:
            logger.exception(
                "Mem0 get_all (global) failed for user_id=%s", mem0_user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Memory service unavailable",
            ) from None

        return self._map_memories(results)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_circuit(self) -> None:
        """Raise 503 immediately if the circuit breaker is OPEN.

        HALF_OPEN state is allowed through as a probe opportunity.
        """
        breaker = get_mem0_circuit_breaker()
        if breaker.state == CircuitState.OPEN:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Memory service temporarily unavailable",
            )

    async def _get_owned_character(
        self,
        character_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Character:
        """Look up an active character and verify ownership.

        Raises:
            HTTPException(404): Character not found or inactive.
            HTTPException(403): Character does not belong to user.
        """
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
        if character.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Character does not belong to user",
            )
        return character

    @staticmethod
    def _map_memories(results: list[dict[str, object]]) -> list[MemoryItem]:
        """Map Mem0 SDK response dicts to MemoryItem schema objects."""
        items: list[MemoryItem] = []
        for r in results:
            items.append(
                MemoryItem(
                    id=str(r["id"]),
                    memory=str(r["memory"]),
                    created_at=r.get("created_at"),  # type: ignore[arg-type]
                ),
            )
        return items
