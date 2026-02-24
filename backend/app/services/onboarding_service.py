"""Onboarding service -- business logic for completing user onboarding.

Converts onboarding Q&A answers into structured memory statements using
Claude Haiku, seeds those memories into Mem0 (global scope), and updates
the user profile's onboarding_completed flag.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from anthropic import AsyncAnthropic
from fastapi import HTTPException, status
from mem0 import MemoryClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.profile import Profile
from app.schemas.onboarding import OnboardingAnswer, OnboardingResponse

logger = logging.getLogger("ember")

# ---------------------------------------------------------------------------
# Prompt template for Claude Haiku memory conversion
# ---------------------------------------------------------------------------

_MEMORY_CONVERSION_PROMPT = """\
You are a memory extraction system. Convert the following onboarding Q&A answers \
into concise, factual memory statements about the user. Each statement should be a \
single sentence that an AI companion can use to personalize conversations.

Rules:
- Output ONLY a JSON array of strings. No other text.
- Each string is one factual memory statement.
- Use third person ("Prefers to be called Alex", not "I prefer to be called Alex").
- Keep each statement under 100 characters.
- Generate exactly one memory statement per Q&A pair.
- Do not add information that is not in the answers.

Q&A Pairs:
1. Preferred name: {preferred_name}
2. Occupation: {occupation}
3. Daily rhythm: {daily_rhythm}
4. Health/fitness goal: {health_goal}
5. Stress management: {stress_management}
6. Sleep schedule: {sleep_schedule}
7. Communication preference: {communication_style}

Output the JSON array now:"""

# ---------------------------------------------------------------------------
# Fallback templates when Haiku returns unparseable output
# ---------------------------------------------------------------------------

_FALLBACK_TEMPLATES: dict[str, str] = {
    "preferred_name": "Prefers to be called {answer}",
    "occupation": "Works as {answer}",
    "daily_rhythm": "Daily rhythm: {answer}",
    "health_goal": "Health/fitness goal: {answer}",
    "stress_management": "Stress management: {answer}",
    "sleep_schedule": "Sleep schedule: {answer}",
    "communication_style": "Communication preference: {answer}",
}


class OnboardingService:
    """Encapsulates all onboarding business logic."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def complete_onboarding(
        self,
        profile: Profile,
        answers: list[OnboardingAnswer],
    ) -> OnboardingResponse:
        """Process onboarding answers: convert to memories, seed Mem0, update profile.

        Steps (ordered for retry safety):
        1. Check if already onboarded -> 409
        2. Call Claude Haiku to convert Q&A -> structured memory strings
        3. Seed memories into Mem0 (global scope, user_id only)
        4. Update profile.onboarding_completed = True (and name if different)
        5. Commit DB transaction
        """
        # Step 1: Idempotency guard
        if profile.onboarding_completed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Onboarding already completed",
            )

        # Build a lookup dict for easy access by question_key
        answers_map: dict[str, str] = {a.question_key: a.answer for a in answers}

        # Step 2: Convert answers to structured memories via Haiku
        memories = await self._convert_answers_to_memories(answers_map)

        # Step 3: Seed memories into Mem0 (global scope)
        await self._seed_memories(
            memories=memories,
            mem0_user_id=profile.mem0_user_id,
        )

        # Step 4: Update profile
        profile.onboarding_completed = True

        # Update preferred name if different (case-insensitive comparison)
        preferred_name = answers_map.get("preferred_name", "").strip()
        current_name = (profile.name or "").strip()
        if preferred_name and preferred_name.lower() != current_name.lower():
            profile.name = preferred_name

        # Step 5: Commit DB changes
        await self.db.commit()

        return OnboardingResponse(
            onboarding_completed=True,
            memories_seeded=len(memories),
        )

    async def _convert_answers_to_memories(
        self,
        answers_map: dict[str, str],
    ) -> list[str]:
        """Call Claude Haiku to convert Q&A pairs into structured memory statements.

        Falls back to deterministic formatting if Haiku fails or returns
        unparseable output.
        """
        prompt = _MEMORY_CONVERSION_PROMPT.format(**answers_map)

        try:
            client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            response = await client.messages.create(
                model=settings.claude_haiku_model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = response.content[0].text.strip()

            return self._parse_haiku_response(raw_text, answers_map)

        except HTTPException:
            raise
        except Exception:
            logger.exception("Claude Haiku API error during onboarding memory conversion")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service temporarily unavailable",
            ) from None

    def _parse_haiku_response(
        self,
        raw_text: str,
        answers_map: dict[str, str],
    ) -> list[str]:
        """Parse Haiku JSON response; fallback to deterministic format on failure."""
        try:
            # Strip markdown code block delimiters if present
            cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text)
            cleaned = re.sub(r"\s*```$", "", cleaned)

            parsed = json.loads(cleaned)

            # Validate: must be a list of strings
            if (
                isinstance(parsed, list)
                and all(isinstance(item, str) for item in parsed)
                and len(parsed) > 0
            ):
                return parsed

            # Unexpected format -- fall back
            logger.warning(
                "Haiku returned valid JSON but unexpected format; using fallback",
            )
            return self._fallback_memories(answers_map)

        except (json.JSONDecodeError, ValueError):
            logger.warning(
                "Haiku returned non-JSON response; using fallback memories",
            )
            return self._fallback_memories(answers_map)

    @staticmethod
    def _fallback_memories(answers_map: dict[str, str]) -> list[str]:
        """Generate deterministic memory strings from onboarding answers."""
        memories: list[str] = []
        for key, template in _FALLBACK_TEMPLATES.items():
            answer = answers_map.get(key, "")
            if answer:
                memories.append(template.format(answer=answer))
        return memories

    async def _seed_memories(
        self,
        memories: list[str],
        mem0_user_id: str,
    ) -> None:
        """Seed structured memory statements into Mem0 (global scope).

        Memories are seeded with user_id only (no agent_id) so they are
        visible to all characters via the global memory search path.

        The Mem0 SDK is synchronous, so calls are wrapped in asyncio.to_thread().
        """
        try:
            client = MemoryClient(api_key=settings.mem0_api_key)
            # Pass memories as a list of user messages for Mem0 to extract and store
            messages = [{"role": "user", "content": m} for m in memories]
            await asyncio.to_thread(
                client.add,
                messages,
                user_id=mem0_user_id,
            )
        except Exception:
            logger.exception(
                "Mem0 add failed during onboarding for user_id=%s",
                mem0_user_id,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service temporarily unavailable",
            ) from None
