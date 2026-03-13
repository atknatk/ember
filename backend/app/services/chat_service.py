"""Chat service — business logic for streaming chat and message history.

Handles sending messages via SSE streaming (Claude Sonnet), intent extraction
(Claude Haiku), Mem0 memory integration, background persistence, and cursor-based
message history retrieval.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from mem0 import MemoryClient
from sqlalchemy import select, true, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.models.character import Character
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.profile import Profile
from app.models.user_activity import UserActivity
from app.schemas.chat import (
    ActionEvent,
    ChunkEvent,
    DoneEvent,
    ErrorEvent,
    MessageItem,
    MessageListResponse,
    ModerationSSEEvent,
)
from app.services.content_moderation import ContentModerationService
from app.services.llm.exceptions import LLMProviderError
from app.services.llm.router import LLMRouter, get_llm_router
from app.utils.timing import log_external_call

logger = logging.getLogger("ember")

# Intent extraction prompt template for Claude Haiku
_INTENT_EXTRACTION_PROMPT = """\
Analyze the following AI assistant response and determine \
if it contains an intent to perform a device action.

Supported actions:
- SET_ALARM: Setting an alarm or reminder. Extract time and label.
- ADD_CALENDAR_EVENT: Adding a calendar event. Extract title, date, time, duration.

If the response contains a device action intent, respond with ONLY this JSON:
{{"action": "<ACTION_NAME>", "payload": {{<relevant fields>}}}}

If the response does NOT contain any device action intent, respond with ONLY:
none

The "time" field must be in ISO 8601 format. The "date" field must be YYYY-MM-DD format.

User's timezone: {timezone}
Current date: {current_date}

Assistant response to analyze:
{assistant_response}"""

_SUPPORTED_ACTIONS = frozenset({"SET_ALARM", "ADD_CALENDAR_EVENT"})


# ---------------------------------------------------------------------------
# Cursor helpers for composite (created_at, id) pagination
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MessageCursor:
    """Decoded composite cursor for keyset pagination."""

    ts: datetime
    id: uuid.UUID


def _encode_cursor(ts: datetime, msg_id: uuid.UUID) -> str:
    """Encode a (created_at, id) pair into an opaque base64 URL-safe cursor string."""
    payload = {"ts": ts.isoformat(), "id": str(msg_id)}
    raw = json.dumps(payload).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> MessageCursor:
    """Decode a base64 URL-safe cursor string into a MessageCursor.

    Raises HTTPException(400) for any malformed input.
    """
    try:
        # Restore base64 padding
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded)
        payload = json.loads(raw)
        ts = datetime.fromisoformat(payload["ts"])
        msg_id = uuid.UUID(payload["id"])
        return MessageCursor(ts=ts, id=msg_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid cursor format",
        )


class ChatService:
    """Encapsulates all messaging business logic."""

    def __init__(
        self,
        db: AsyncSession,
        llm_router: LLMRouter | None = None,
    ) -> None:
        self.db = db
        self._llm_router_override = llm_router

    @property
    def _llm_router(self) -> LLMRouter:
        """Lazy-initialize the LLM router on first access."""
        if self._llm_router_override is not None:
            return self._llm_router_override
        return get_llm_router()

    # ------------------------------------------------------------------
    # Send Message (Streaming)
    # ------------------------------------------------------------------

    async def validate_send_message(
        self,
        character_id: uuid.UUID,
        user_id: uuid.UUID,
        profile: Profile,
        content: str,
    ) -> dict[str, Any]:
        """Validate and prepare context for streaming. Raises HTTPException on failure.

        This method runs BEFORE the StreamingResponse is created, so
        HTTPExceptions are properly caught and returned as JSON errors.

        Returns a context dict with character, conversation, system_prompt,
        and formatted_messages for use in the streaming generator.
        """
        # Step 1: Look up character (active, ownership check)
        character = await self._get_active_character(character_id)
        if character.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Character does not belong to user",
            )

        # Step 2: Content moderation check
        moderation_service = ContentModerationService()
        moderation_result = await moderation_service.check_message(
            content=content,
            user_id=user_id,
            character_id=character_id,
            character_template=character.template,
            db=self.db,
        )

        if not moderation_result.allowed:
            if moderation_result.blocked_until is not None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "detail": moderation_result.reason,
                        "blocked_until": moderation_result.blocked_until.isoformat(),
                    },
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=moderation_result.reason,
            )

        # Step 3: Look up (or auto-create) conversation
        conversation = await self._get_or_create_conversation(
            character_id=character_id,
            user_id=user_id,
        )

        # Step 4: Parallel fetch — Mem0 memories + recent messages
        global_memories, character_memories, recent_messages = await asyncio.gather(
            self._search_memories(content, profile.mem0_user_id, agent_id=None),
            self._search_memories(
                content, profile.mem0_user_id, agent_id=character.mem0_agent_id,
            ),
            self._get_recent_messages(conversation.id),
            return_exceptions=True,
        )

        # Handle Mem0 search failures gracefully
        if isinstance(global_memories, BaseException):
            logger.error("Global Mem0 search failed: %s", global_memories)
            global_memories = []
        if isinstance(character_memories, BaseException):
            logger.error("Character Mem0 search failed: %s", character_memories)
            character_memories = []
        if isinstance(recent_messages, BaseException):
            logger.error("Recent messages fetch failed: %s", recent_messages)
            recent_messages = []

        # Step 5: Build LLM prompt
        system_prompt = self._build_system_prompt(
            character_system_prompt=character.system_prompt,
            global_memories=global_memories,
            character_memories=character_memories,
            profile=profile,
        )

        # Step 5b: Append moderation augmentation if present
        if moderation_result.augment_system_prompt:
            system_prompt = f"{system_prompt}\n\n{moderation_result.augment_system_prompt}"

        formatted_messages = self._format_messages(recent_messages, content)

        return {
            "character": character,
            "conversation": conversation,
            "system_prompt": system_prompt,
            "formatted_messages": formatted_messages,
            "moderation_result": moderation_result,
        }

    async def stream_response(  # noqa: ANN201
        self,
        context: dict[str, Any],
        user_id: uuid.UUID,
        profile: Profile,
        content: str,
        media_url: str | None,
    ):
        """Yield SSE events for the AI response.

        This async generator runs inside a StreamingResponse.
        Validation has already been performed by validate_send_message().

        Yields SSE-formatted strings: 'data: {"type":"chunk","content":"..."}\n\n'
        """
        character: Character = context["character"]
        conversation: Conversation = context["conversation"]
        system_prompt: str = context["system_prompt"]
        formatted_messages: list[dict[str, str]] = context["formatted_messages"]
        moderation_result = context.get("moderation_result")

        full_response = ""
        assistant_message_id = uuid.uuid4()

        # Emit moderation SSE event for therapist crisis augmentation
        if (
            moderation_result is not None
            and moderation_result.augment_system_prompt is not None
            and character.template == "therapist"
        ):
            mod_event = ModerationSSEEvent(
                message=(
                    "I need to be careful here. If you're in crisis, please contact "
                    "988 (Suicide & Crisis Lifeline) or text HOME to 741741."
                ),
            )
            yield f"data: {mod_event.model_dump_json()}\n\n"

        try:
            provider = self._llm_router.get()
            async for text in provider.stream(
                system=system_prompt,
                messages=formatted_messages,
                max_tokens=2048,
            ):
                full_response += text
                event = ChunkEvent(content=text)
                yield f"data: {event.model_dump_json()}\n\n"

        except LLMProviderError:
            logger.exception(
                "LLM provider error for character_id=%s",
                character.id,
            )
            error_event = ErrorEvent(
                message="AI service temporarily unavailable",
            )
            yield f"data: {error_event.model_dump_json()}\n\n"
            return
        except Exception:
            logger.exception(
                "Claude streaming error for character_id=%s",
                character.id,
            )
            error_event = ErrorEvent(
                message="AI service temporarily unavailable",
            )
            yield f"data: {error_event.model_dump_json()}\n\n"
            return

        # Intent extraction via Haiku
        action_metadata = await self._extract_intent(
            full_response, profile.timezone,
        )
        if action_metadata is not None:
            action_event = ActionEvent(
                action=action_metadata["action"],
                payload=action_metadata["payload"],
            )
            yield f"data: {action_event.model_dump_json()}\n\n"

        # Done event
        done_event = DoneEvent(message_id=str(assistant_message_id))
        yield f"data: {done_event.model_dump_json()}\n\n"

        # Background tasks (fire-and-forget)
        asyncio.create_task(  # noqa: RUF006
            _persist_exchange(
                user_id=user_id,
                conversation_id=conversation.id,
                user_content=content,
                user_media_url=media_url,
                assistant_content=full_response,
                assistant_message_id=assistant_message_id,
                action_metadata=action_metadata,
                mem0_user_id=profile.mem0_user_id,
                mem0_agent_id=character.mem0_agent_id,
            ),
        )

    # ------------------------------------------------------------------
    # Get Messages (Paginated)
    # ------------------------------------------------------------------

    async def get_messages(
        self,
        character_id: uuid.UUID,
        user_id: uuid.UUID,
        cursor: MessageCursor | None,
        limit: int,
    ) -> MessageListResponse:
        """Retrieve paginated message history for a character's conversation."""
        # Validate character access
        character = await self._get_active_character(character_id)
        if character.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Character does not belong to user",
            )

        # Look up conversation
        result = await self.db.execute(
            select(Conversation).where(Conversation.character_id == character_id),
        )
        conversation = result.scalar_one_or_none()
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        # Cursor-based query with composite (created_at, id) cursor
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit + 1)
        )
        if cursor is not None:
            stmt = stmt.where(
                tuple_(Message.created_at, Message.id)
                < tuple_(cursor.ts, cursor.id),
            )

        result = await self.db.execute(stmt)
        rows = result.scalars().all()

        has_more = len(rows) > limit
        items = list(rows[:limit])

        next_cursor: str | None = None
        if has_more and items:
            next_cursor = _encode_cursor(items[-1].created_at, items[-1].id)

        return MessageListResponse(
            items=[
                MessageItem(
                    id=str(msg.id),
                    role=msg.role,
                    content=msg.content,
                    media_url=msg.media_url,
                    metadata=msg.metadata_,
                    created_at=msg.created_at,
                )
                for msg in items
            ],
            next_cursor=next_cursor,
            has_more=has_more,
        )

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

    async def _get_or_create_conversation(
        self,
        character_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Conversation:
        """Find the conversation for a character, auto-creating if missing."""
        result = await self.db.execute(
            select(Conversation).where(Conversation.character_id == character_id),
        )
        conversation = result.scalar_one_or_none()
        if conversation is not None:
            return conversation

        # Defensive: auto-create if missing
        conversation = Conversation(
            id=uuid.uuid4(),
            user_id=user_id,
            character_id=character_id,
            last_message_at=None,
        )
        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)
        return conversation

    async def _search_memories(
        self,
        query: str,
        mem0_user_id: str,
        agent_id: str | None,
        limit: int = 5,
    ) -> list[str]:
        """Search Mem0 for relevant memories. Returns a list of memory text strings.

        Uses the circuit breaker to avoid calling Mem0 when it is down.
        Falls back to cached results or empty list on failure.
        """
        from app.core.circuit_breaker import (
            CircuitOpenError,
            get_mem0_circuit_breaker,
        )

        breaker = get_mem0_circuit_breaker()

        # Build cache key
        cache_key = agent_id if agent_id is not None else f"global:{mem0_user_id}"

        # Check if circuit is open — serve from cache or return empty
        if breaker.state.value == "open":
            cached = breaker.get_cached_memories(cache_key)
            return cached if cached is not None else []

        try:
            async def _do_search() -> list[dict[str, Any]]:
                client = MemoryClient(api_key=settings.mem0_api_key)
                kwargs: dict[str, Any] = {
                    "user_id": mem0_user_id,
                    "limit": limit,
                }
                if agent_id is not None:
                    kwargs["agent_id"] = agent_id

                async with log_external_call("mem0", "search"):
                    return await asyncio.to_thread(
                        client.search,
                        query,
                        **kwargs,
                    )

            results = await breaker.call_with_breaker(_do_search)
            memories = [r["memory"] for r in results]

            # Cache the successful result
            breaker.set_cached_memories(cache_key, memories)
            return memories

        except CircuitOpenError:
            # Circuit just opened — try cache
            cached = breaker.get_cached_memories(cache_key)
            return cached if cached is not None else []
        except Exception:
            logger.exception(
                "Mem0 search failed (agent_id=%s)", agent_id,
            )
            # Try cache as fallback
            cached = breaker.get_cached_memories(cache_key)
            return cached if cached is not None else []

    async def _get_recent_messages(
        self,
        conversation_id: uuid.UUID,
    ) -> list[Message]:
        """Fetch the last N messages for context, ordered by created_at ASC."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(settings.max_context_messages)
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        # Reverse to chronological order for the LLM prompt
        return list(reversed(rows))

    def _build_system_prompt(
        self,
        character_system_prompt: str,
        global_memories: list[str],
        character_memories: list[str],
        profile: Profile,
    ) -> str:
        """Build the full system prompt from 3 blocks per docs/05-ai-bellek.md."""
        blocks: list[str] = []

        # Block 1: Character definition
        blocks.append(character_system_prompt)

        # Block 2: Learned knowledge (Mem0 memories)
        all_memories = _deduplicate_memories(global_memories, character_memories)
        if all_memories:
            memory_lines = "\n".join(f"- {m}" for m in all_memories)
            blocks.append(f"What you know about this user:\n{memory_lines}")

        # Block 3: Daily context
        try:
            import zoneinfo
            tz = zoneinfo.ZoneInfo(profile.timezone or "UTC")
        except Exception:
            import zoneinfo
            tz = zoneinfo.ZoneInfo("UTC")

        now = datetime.now(tz=tz)
        date_str = now.strftime("%A, %Y-%m-%d %H:%M")
        blocks.append(
            f"Current date and time: {date_str}\n"
            f"Timezone: {profile.timezone}\n"
            f"User's preferred language: {profile.preferred_language}"
        )

        return "\n\n".join(blocks)

    def _format_messages(
        self,
        recent_messages: list[Message],
        new_content: str,
    ) -> list[dict[str, str]]:
        """Format message history + new user message for the Claude API."""
        formatted: list[dict[str, str]] = []
        for msg in recent_messages:
            formatted.append({"role": msg.role, "content": msg.content})

        # Append the new user message
        formatted.append({"role": "user", "content": new_content})
        return formatted

    async def _extract_intent(
        self,
        assistant_response: str,
        user_timezone: str,
    ) -> dict[str, Any] | None:
        """Extract device action intent from the assistant response via Claude Haiku."""
        try:
            now = datetime.now(tz=UTC)
            prompt = _INTENT_EXTRACTION_PROMPT.format(
                timezone=user_timezone,
                current_date=now.strftime("%Y-%m-%d"),
                assistant_response=assistant_response,
            )

            provider = self._llm_router.get()
            raw_text = await provider.complete_fast(
                system="",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=256,
                temperature=0.0,
            )
            raw_text = raw_text.strip()

            if raw_text.lower() == "none":
                return None

            parsed = json.loads(raw_text)
            if (
                isinstance(parsed, dict)
                and "action" in parsed
                and parsed["action"] in _SUPPORTED_ACTIONS
            ):
                return {
                    "action": parsed["action"],
                    "payload": parsed.get("payload", {}),
                }

            logger.debug("Haiku returned unsupported action: %s", raw_text)
            return None

        except json.JSONDecodeError:
            logger.debug("Haiku returned non-JSON response: %s", raw_text)
            return None
        except Exception:
            logger.exception("Intent extraction via Haiku failed")
            return None


# ---------------------------------------------------------------------------
# Background task (module-level function for testability)
# ---------------------------------------------------------------------------


async def _persist_exchange(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    user_content: str,
    user_media_url: str | None,
    assistant_content: str,
    assistant_message_id: uuid.UUID,
    action_metadata: dict[str, Any] | None,
    mem0_user_id: str,
    mem0_agent_id: str,
) -> None:
    """Background task: persist messages, update timestamps, add to Mem0."""
    try:
        async with AsyncSessionLocal() as db:
            # Save user message
            user_msg = Message(
                id=uuid.uuid4(),
                conversation_id=conversation_id,
                user_id=user_id,
                role="user",
                content=user_content,
                media_url=user_media_url,
            )
            db.add(user_msg)

            # Save assistant message
            assistant_msg = Message(
                id=assistant_message_id,
                conversation_id=conversation_id,
                user_id=user_id,
                role="assistant",
                content=assistant_content,
                metadata_=action_metadata,
            )
            db.add(assistant_msg)

            # Update conversation timestamp
            await db.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id)
                .values(last_message_at=datetime.now(tz=UTC)),
            )

            # Update user activity
            await db.execute(
                update(UserActivity)
                .where(UserActivity.user_id == user_id)
                .values(last_chat_at=datetime.now(tz=UTC)),
            )

            await db.commit()

    except Exception:
        logger.exception(
            "Background persist failed for conversation_id=%s",
            conversation_id,
        )

    # Mem0 add (outside DB transaction) — routed through circuit breaker
    from app.core.circuit_breaker import (
        CircuitOpenError,
        CircuitState,
        get_mem0_circuit_breaker,
    )

    breaker = get_mem0_circuit_breaker()
    mem0_messages = [
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": assistant_content},
    ]

    if breaker.state == CircuitState.OPEN:
        # Queue for later retry
        breaker.enqueue_retry(mem0_messages, mem0_user_id, mem0_agent_id)
        logger.debug(
            "Mem0 add queued (circuit open) for agent_id=%s", mem0_agent_id,
        )
    else:
        try:
            async def _do_add() -> None:
                client = MemoryClient(api_key=settings.mem0_api_key)
                async with log_external_call("mem0", "add"):
                    await asyncio.to_thread(
                        client.add,
                        mem0_messages,
                        user_id=mem0_user_id,
                        agent_id=mem0_agent_id,
                    )

            await breaker.call_with_breaker(_do_add)
        except CircuitOpenError:
            breaker.enqueue_retry(mem0_messages, mem0_user_id, mem0_agent_id)
            logger.debug(
                "Mem0 add queued (circuit opened during call) for agent_id=%s",
                mem0_agent_id,
            )
        except Exception:
            logger.exception("Mem0 add failed for agent_id=%s", mem0_agent_id)
            breaker.enqueue_retry(mem0_messages, mem0_user_id, mem0_agent_id)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


def _deduplicate_memories(
    global_memories: list[str],
    character_memories: list[str],
) -> list[str]:
    """De-duplicate memories by exact string match, preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for memory in [*character_memories, *global_memories]:
        if memory not in seen:
            seen.add(memory)
            result.append(memory)
    return result
