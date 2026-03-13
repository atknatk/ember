"""Proactive message generator -- generates personalized notification messages.

Extracts message generation logic from notification_scheduler.py into a dedicated
service with per-user per-day caching, character personality integration, and
strict 100-character enforcement.

The cache is in-memory keyed by (user_id, notification_type, local_date). It is
cleared by the midnight reset job in notification_scheduler.py.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from mem0 import MemoryClient

from app.config import settings
from app.services.llm.router import get_llm_router

if TYPE_CHECKING:
    from app.models.character import Character
    from app.models.profile import Profile

logger = logging.getLogger("ember")

# ---------------------------------------------------------------------------
# Constants (moved from notification_scheduler.py)
# ---------------------------------------------------------------------------

TONE_MAP: dict[str, str] = {
    "morning_checkin": "warm and energetic",
    "afternoon_nudge": "curious and light",
    "evening_reflection": "calm and reflective",
    "sleep_reminder": "gentle and caring",
}

MEM0_QUERIES: dict[str, str] = {
    "morning_checkin": "morning routine, daily plans, habits",
    "afternoon_nudge": "hobbies, interests, current goals",
    "evening_reflection": "daily reflection, mood, feelings, evening routine",
    "sleep_reminder": "sleep schedule, wake up time, rest",
}

FALLBACK_MESSAGES: dict[str, dict[str, str]] = {
    "morning_checkin": {
        "en": "Good morning! How are you feeling today?",
        "tr": "Gunaydin! Bugun nasil hissediyorsun?",
    },
    "afternoon_nudge": {
        "en": "Hey! Haven't heard from you today. Everything okay?",
        "tr": "Selam! Bugun konusmadik, her sey yolunda mi?",
    },
    "evening_reflection": {
        "en": "How was your day? I'd love to hear about it.",
        "tr": "Gunun nasil gecti? Duymak isterim.",
    },
    "sleep_reminder": {
        "en": "It's getting late. Time to wind down?",
        "tr": "Gec oldu. Yatma vakti geldi mi?",
    },
}


# ---------------------------------------------------------------------------
# Mem0 helper (moved from notification_scheduler.py)
# ---------------------------------------------------------------------------


def _search_mem0(
    mem0_user_id: str,
    agent_id: str,
    query: str,
) -> list[dict[str, object]]:
    """Search Mem0 for relevant memories (synchronous, called via to_thread)."""
    client = MemoryClient(api_key=settings.mem0_api_key)
    return client.search(  # type: ignore[no-any-return]
        query,
        user_id=mem0_user_id,
        agent_id=agent_id,
        limit=5,
    )


# ---------------------------------------------------------------------------
# Fallback helper (moved from notification_scheduler.py)
# ---------------------------------------------------------------------------


def _get_fallback_message(notification_type: str, language: str) -> str:
    """Return a deterministic fallback message for the given type and language."""
    type_messages = FALLBACK_MESSAGES.get(notification_type, {})
    return type_messages.get(language, type_messages.get("en", "Hey! How are you?"))


# ---------------------------------------------------------------------------
# Truncation helper
# ---------------------------------------------------------------------------


def _truncate_to_limit(message: str, limit: int = 100) -> str:
    """Truncate message to limit characters at word boundary with ellipsis.

    If the message is at or under the limit, returns it unchanged.
    If over the limit, truncates at the last space before position (limit - 3)
    and appends '...'. If there is no space, hard-truncates at (limit - 3).
    """
    if len(message) <= limit:
        return message

    cutoff = limit - 3
    space_idx = message.rfind(" ", 0, cutoff)
    if space_idx > 0:
        return message[:space_idx] + "..."
    return message[:cutoff] + "..."


# ---------------------------------------------------------------------------
# ProactiveMessageGenerator
# ---------------------------------------------------------------------------


class ProactiveMessageGenerator:
    """Generates personalized push notification messages with caching.

    Each instance maintains an in-memory cache keyed by
    ``"{user_id}:{notification_type}:{local_date}"`` to avoid redundant
    Mem0 + Claude Haiku calls across scheduler cycles on the same day.
    """

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    async def generate(
        self,
        profile: Profile,
        character: Character,
        notification_type: str,
        local_now: datetime,
    ) -> str:
        """Generate a personalized notification message.

        Steps:
        1. Check cache -- return immediately if a cached message exists.
        2. Search Mem0 for relevant memories.
        3. Build prompt with character personality.
        4. Call Claude Haiku via complete_fast().
        5. Enforce 100-character limit with word-boundary truncation.
        6. Cache and return.

        Falls back to deterministic messages if either service fails.

        Args:
            profile: The user's Profile model.
            character: The user's default Character model.
            notification_type: One of the NOTIFICATION_TYPES.
            local_now: Current time in the user's local timezone.

        Returns:
            A notification message string (at most 100 characters).
        """
        # 1. Check cache
        cache_key = self._build_cache_key(profile.id, notification_type, local_now)
        if cache_key in self._cache:
            return self._cache[cache_key]

        language = profile.preferred_language or "en"

        # 2. Search Mem0
        memories_text = ""
        try:
            mem0_query = MEM0_QUERIES.get(notification_type, "")
            memories = await asyncio.to_thread(
                _search_mem0,
                mem0_user_id=profile.mem0_user_id,
                agent_id=character.mem0_agent_id,
                query=mem0_query,
            )
            if memories:
                memories_text = "\n".join(
                    f"- {m.get('memory', '')}" for m in memories if m.get("memory")
                )
        except Exception:
            logger.warning(
                "Mem0 search failed for notification %s, user_id=%s",
                notification_type,
                profile.id,
            )

        # 3. Build prompt with character personality
        personality_excerpt = ""
        if character.system_prompt:
            personality_excerpt = character.system_prompt[:200]

        tone = TONE_MAP.get(notification_type, "warm")
        system_prompt = (
            f"You are {character.name}, the user's personal AI companion.\n\n"
            f"Your personality:\n{personality_excerpt}\n\n"
            f"Generate a push notification message. Rules:\n"
            f"- Maximum 100 characters total\n"
            f"- Tone: {tone}\n"
            f"- Language: {language}\n"
            f"- 1-2 sentences max\n"
            f"- No quotes, no emoji\n"
            f"- Address the user by name if it fits naturally"
        )

        user_prompt = (
            f"Notification type: {notification_type}\n"
            f"User's name: {profile.name}\n"
            f"Current local time: {local_now.strftime('%H:%M')}\n"
            f"Day of week: {local_now.strftime('%A')}\n"
            f"Relevant memories:\n{memories_text or 'None'}\n\n"
            f"Generate a warm, personalized notification message."
        )

        # 4. Call Claude Haiku
        try:
            llm = get_llm_router().get()
            message = await llm.complete_fast(
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=100,
                temperature=0.7,
            )
            message = message.strip()

            # 5. Enforce 100-character limit
            message = _truncate_to_limit(message)

        except Exception:
            logger.warning(
                "Claude Haiku failed for notification %s, user_id=%s, using fallback",
                notification_type,
                profile.id,
            )
            message = _get_fallback_message(notification_type, language)

        # 6. Cache and return
        self._cache[cache_key] = message
        return message

    def clear_cache(self) -> None:
        """Clear the entire message cache.

        Called by the midnight reset job in notification_scheduler.py.
        """
        self._cache.clear()

    def _build_cache_key(
        self,
        user_id: uuid.UUID,
        notification_type: str,
        local_now: datetime,
    ) -> str:
        """Build a cache key string.

        Returns:
            A string in the format ``"{user_id}:{notification_type}:{YYYY-MM-DD}"``.
        """
        return f"{user_id}:{notification_type}:{local_now.strftime('%Y-%m-%d')}"
