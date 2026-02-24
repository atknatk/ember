"""Unit tests for OnboardingService business logic.

Tests the service layer directly with mocked database session, Claude Haiku,
and Mem0 client. Does not go through HTTP/FastAPI.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import json  # noqa: E402
import uuid  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.schemas.onboarding import OnboardingAnswer  # noqa: E402
from app.services.onboarding_service import (  # noqa: E402
    _FALLBACK_TEMPLATES,
    OnboardingService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")


def _make_fake_profile(
    onboarding_completed: bool = False,
    name: str = "Alexander",
) -> MagicMock:
    """Create a fake Profile-like object."""
    profile = MagicMock()
    profile.id = FAKE_USER_ID
    profile.name = name
    profile.mem0_user_id = f"user_{FAKE_USER_ID}"
    profile.onboarding_completed = onboarding_completed
    return profile


def _build_answers() -> list[OnboardingAnswer]:
    """Return a valid list of 7 OnboardingAnswer objects."""
    return [
        OnboardingAnswer(question_key="preferred_name", answer="Alex"),
        OnboardingAnswer(question_key="occupation", answer="Software engineer"),
        OnboardingAnswer(question_key="daily_rhythm", answer="Morning person"),
        OnboardingAnswer(question_key="health_goal", answer="Lose 10 kg"),
        OnboardingAnswer(question_key="stress_management", answer="Walks and podcasts"),
        OnboardingAnswer(question_key="sleep_schedule", answer="11 PM to 6:30 AM"),
        OnboardingAnswer(question_key="communication_style", answer="Check in regularly"),
    ]


def _mock_haiku_response(memories: list[str]) -> MagicMock:
    """Create a mock Claude Haiku response with a JSON array."""
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = json.dumps(memories)
    mock_response.content = [mock_content]
    return mock_response


def _mock_haiku_response_text(text: str) -> MagicMock:
    """Create a mock Claude Haiku response with arbitrary text."""
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = text
    mock_response.content = [mock_content]
    return mock_response


STANDARD_MEMORIES = [
    "Prefers to be called Alex",
    "Works as a software engineer",
    "Morning person",
    "Goal: lose 10 kg",
    "Manages stress with walks and podcasts",
    "Sleeps from 11 PM to 6:30 AM",
    "Wants regular check-ins without being overwhelmed",
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCompleteOnboarding:
    """Tests for OnboardingService.complete_onboarding()."""

    @pytest.mark.asyncio
    async def test_s1_raises_409_when_already_completed(self) -> None:
        """S1: Raises 409 when onboarding_completed is already true."""
        db = AsyncMock()
        profile = _make_fake_profile(onboarding_completed=True)
        service = OnboardingService(db)

        with pytest.raises(HTTPException) as exc_info:
            await service.complete_onboarding(profile=profile, answers=_build_answers())

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "Onboarding already completed"

    @pytest.mark.asyncio
    async def test_s1_no_external_calls_when_already_completed(self) -> None:
        """S1: No Claude or Mem0 calls when already onboarded."""
        db = AsyncMock()
        profile = _make_fake_profile(onboarding_completed=True)
        service = OnboardingService(db)

        with (
            patch("app.services.onboarding_service.AsyncAnthropic") as mock_claude,
            patch("app.services.onboarding_service.MemoryClient") as mock_mem0,
            pytest.raises(HTTPException),
        ):
            await service.complete_onboarding(profile=profile, answers=_build_answers())

        mock_claude.assert_not_called()
        mock_mem0.assert_not_called()

    @pytest.mark.asyncio
    async def test_s2_calls_haiku_with_correct_model(self) -> None:
        """S2: Calls Claude Haiku with the correct model setting."""
        db = AsyncMock()
        profile = _make_fake_profile()
        service = OnboardingService(db)

        mock_response = _mock_haiku_response(STANDARD_MEMORIES)

        with (
            patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls,
            patch("app.services.onboarding_service.MemoryClient"),
        ):
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            await service.complete_onboarding(profile=profile, answers=_build_answers())

            # Verify Haiku was called with the configured model
            call_kwargs = mock_client.messages.create.call_args
            assert call_kwargs.kwargs["model"] == "claude-haiku-4-5"

    @pytest.mark.asyncio
    async def test_s3_parses_haiku_json_response(self) -> None:
        """S3: Parses Haiku JSON response into a list of 7 memory strings."""
        db = AsyncMock()
        profile = _make_fake_profile()
        service = OnboardingService(db)

        mock_response = _mock_haiku_response(STANDARD_MEMORIES)

        with (
            patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls,
            patch("app.services.onboarding_service.MemoryClient") as mock_mem0_cls,
        ):
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            mock_mem0 = MagicMock()
            mock_mem0.add.return_value = None
            mock_mem0_cls.return_value = mock_mem0

            result = await service.complete_onboarding(
                profile=profile, answers=_build_answers(),
            )

            assert result.memories_seeded == 7

    @pytest.mark.asyncio
    async def test_s4_fallback_on_invalid_json(self) -> None:
        """S4: Falls back to deterministic format when Haiku returns invalid JSON."""
        db = AsyncMock()
        profile = _make_fake_profile()
        service = OnboardingService(db)

        # Return non-JSON text
        mock_response = _mock_haiku_response_text(
            "Here are the memories:\n- Prefers to be called Alex",
        )

        with (
            patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls,
            patch("app.services.onboarding_service.MemoryClient") as mock_mem0_cls,
        ):
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            mock_mem0 = MagicMock()
            mock_mem0.add.return_value = None
            mock_mem0_cls.return_value = mock_mem0

            result = await service.complete_onboarding(
                profile=profile, answers=_build_answers(),
            )

            assert result.onboarding_completed is True
            assert result.memories_seeded == 7

    @pytest.mark.asyncio
    async def test_s5_mem0_called_with_user_id_only(self) -> None:
        """S5: Mem0 add() is called with user_id only (no agent_id)."""
        db = AsyncMock()
        profile = _make_fake_profile()
        service = OnboardingService(db)

        mock_response = _mock_haiku_response(STANDARD_MEMORIES)

        with (
            patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls,
            patch("app.services.onboarding_service.MemoryClient") as mock_mem0_cls,
            patch("app.services.onboarding_service.asyncio") as mock_asyncio,
        ):
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            mock_mem0 = MagicMock()
            mock_mem0.add.return_value = None
            mock_mem0_cls.return_value = mock_mem0

            # Make to_thread call the function synchronously
            async def fake_to_thread(func: object, *args: object, **kwargs: object) -> object:
                return func(*args, **kwargs)  # type: ignore[operator]

            mock_asyncio.to_thread = AsyncMock(side_effect=fake_to_thread)

            await service.complete_onboarding(profile=profile, answers=_build_answers())

            # Verify Mem0 add was called
            mock_mem0.add.assert_called_once()
            call_args = mock_mem0.add.call_args

            # Verify user_id is passed
            assert call_args.kwargs["user_id"] == profile.mem0_user_id

            # Verify agent_id is NOT passed
            assert "agent_id" not in call_args.kwargs

    @pytest.mark.asyncio
    async def test_s6_sets_onboarding_completed(self) -> None:
        """S6: Sets profile.onboarding_completed = True after Mem0 success."""
        db = AsyncMock()
        profile = _make_fake_profile()
        service = OnboardingService(db)

        mock_response = _mock_haiku_response(STANDARD_MEMORIES)

        with (
            patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls,
            patch("app.services.onboarding_service.MemoryClient") as mock_mem0_cls,
        ):
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            mock_mem0 = MagicMock()
            mock_mem0.add.return_value = None
            mock_mem0_cls.return_value = mock_mem0

            await service.complete_onboarding(profile=profile, answers=_build_answers())

            assert profile.onboarding_completed is True

    @pytest.mark.asyncio
    async def test_s7_updates_name_when_different(self) -> None:
        """S7: Updates profile.name when preferred_name differs."""
        db = AsyncMock()
        profile = _make_fake_profile(name="Alexander")
        service = OnboardingService(db)

        mock_response = _mock_haiku_response(STANDARD_MEMORIES)

        with (
            patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls,
            patch("app.services.onboarding_service.MemoryClient") as mock_mem0_cls,
        ):
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            mock_mem0 = MagicMock()
            mock_mem0.add.return_value = None
            mock_mem0_cls.return_value = mock_mem0

            # preferred_name in _build_answers() is "Alex" != "Alexander"
            await service.complete_onboarding(profile=profile, answers=_build_answers())

            assert profile.name == "Alex"

    @pytest.mark.asyncio
    async def test_s8_does_not_update_name_when_same(self) -> None:
        """S8: Does NOT update profile.name when it matches (case-insensitive)."""
        db = AsyncMock()
        profile = _make_fake_profile(name="Alex")
        service = OnboardingService(db)

        mock_response = _mock_haiku_response(STANDARD_MEMORIES)

        with (
            patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls,
            patch("app.services.onboarding_service.MemoryClient") as mock_mem0_cls,
        ):
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            mock_mem0 = MagicMock()
            mock_mem0.add.return_value = None
            mock_mem0_cls.return_value = mock_mem0

            await service.complete_onboarding(profile=profile, answers=_build_answers())

            # Name should remain "Alex" (set on mock, not changed)
            assert profile.name == "Alex"

    @pytest.mark.asyncio
    async def test_s9_commits_once_on_success(self) -> None:
        """S9: Calls db.commit() exactly once on success."""
        db = AsyncMock()
        profile = _make_fake_profile()
        service = OnboardingService(db)

        mock_response = _mock_haiku_response(STANDARD_MEMORIES)

        with (
            patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls,
            patch("app.services.onboarding_service.MemoryClient") as mock_mem0_cls,
        ):
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            mock_mem0 = MagicMock()
            mock_mem0.add.return_value = None
            mock_mem0_cls.return_value = mock_mem0

            await service.complete_onboarding(profile=profile, answers=_build_answers())

            db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_s10_raises_503_when_haiku_fails(self) -> None:
        """S10: Raises 503 when Claude Haiku API fails."""
        db = AsyncMock()
        profile = _make_fake_profile()
        service = OnboardingService(db)

        with patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=Exception("Claude API connection error"),
            )
            mock_cls.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                await service.complete_onboarding(
                    profile=profile, answers=_build_answers(),
                )

            assert exc_info.value.status_code == 503
            assert exc_info.value.detail == "AI service temporarily unavailable"

    @pytest.mark.asyncio
    async def test_s11_raises_503_when_mem0_fails(self) -> None:
        """S11: Raises 503 when Mem0 add() fails."""
        db = AsyncMock()
        profile = _make_fake_profile()
        service = OnboardingService(db)

        mock_response = _mock_haiku_response(STANDARD_MEMORIES)

        with (
            patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls,
            patch("app.services.onboarding_service.MemoryClient") as mock_mem0_cls,
            patch(
                "app.services.onboarding_service.asyncio.to_thread",
                new_callable=AsyncMock,
                side_effect=Exception("Mem0 connection refused"),
            ),
        ):
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            mock_mem0 = MagicMock()
            mock_mem0_cls.return_value = mock_mem0

            with pytest.raises(HTTPException) as exc_info:
                await service.complete_onboarding(
                    profile=profile, answers=_build_answers(),
                )

            assert exc_info.value.status_code == 503
            assert exc_info.value.detail == "AI service temporarily unavailable"

    @pytest.mark.asyncio
    async def test_s12_onboarding_not_set_when_mem0_fails(self) -> None:
        """S12: onboarding_completed remains False when Mem0 fails."""
        db = AsyncMock()
        profile = _make_fake_profile()
        service = OnboardingService(db)

        mock_response = _mock_haiku_response(STANDARD_MEMORIES)

        with (
            patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls,
            patch("app.services.onboarding_service.MemoryClient") as mock_mem0_cls,
            patch(
                "app.services.onboarding_service.asyncio.to_thread",
                new_callable=AsyncMock,
                side_effect=Exception("Mem0 failure"),
            ),
        ):
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            mock_mem0 = MagicMock()
            mock_mem0_cls.return_value = mock_mem0

            with pytest.raises(HTTPException):
                await service.complete_onboarding(
                    profile=profile, answers=_build_answers(),
                )

            assert profile.onboarding_completed is False


class TestConvertAnswersToMemories:
    """Tests for the private _convert_answers_to_memories method."""

    @pytest.mark.asyncio
    async def test_s13_prompt_contains_all_answers(self) -> None:
        """S13: The prompt sent to Haiku contains all 7 answer values."""
        db = AsyncMock()
        service = OnboardingService(db)

        answers_map = {
            "preferred_name": "Alex",
            "occupation": "Software engineer",
            "daily_rhythm": "Morning person",
            "health_goal": "Lose 10 kg",
            "stress_management": "Walks and podcasts",
            "sleep_schedule": "11 PM to 6:30 AM",
            "communication_style": "Check in regularly",
        }

        mock_response = _mock_haiku_response(STANDARD_MEMORIES)

        with patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            await service._convert_answers_to_memories(answers_map)

            # Verify the prompt contains all answer values
            call_kwargs = mock_client.messages.create.call_args
            prompt_content = call_kwargs.kwargs["messages"][0]["content"]
            for answer_value in answers_map.values():
                assert answer_value in prompt_content


class TestFallbackMemories:
    """Tests for the static _fallback_memories method."""

    def test_s14_generates_7_formatted_strings(self) -> None:
        """S14: Generates 7 correctly formatted fallback memories."""
        answers_map = {
            "preferred_name": "Alex",
            "occupation": "Software engineer",
            "daily_rhythm": "Morning person",
            "health_goal": "Lose 10 kg",
            "stress_management": "Walks and podcasts",
            "sleep_schedule": "11 PM to 6:30 AM",
            "communication_style": "Check in regularly",
        }

        memories = OnboardingService._fallback_memories(answers_map)
        assert len(memories) == 7

        # Verify each memory matches the fallback template
        for key, template in _FALLBACK_TEMPLATES.items():
            expected = template.format(answer=answers_map[key])
            assert expected in memories

    def test_fallback_with_empty_answer(self) -> None:
        """Fallback skips keys with empty answers."""
        answers_map = {
            "preferred_name": "Alex",
            "occupation": "",
            "daily_rhythm": "Morning person",
            "health_goal": "Lose 10 kg",
            "stress_management": "Walks",
            "sleep_schedule": "11 PM to 7 AM",
            "communication_style": "Regular check-ins",
        }
        memories = OnboardingService._fallback_memories(answers_map)
        # Empty occupation should be skipped
        assert len(memories) == 6


class TestParseHaikuResponse:
    """Tests for _parse_haiku_response edge cases."""

    def test_markdown_code_block_stripped(self) -> None:
        """JSON wrapped in markdown code blocks is parsed correctly."""
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = {"preferred_name": "Alex"}

        raw = '```json\n["Prefers to be called Alex"]\n```'
        result = service._parse_haiku_response(raw, answers_map)
        assert result == ["Prefers to be called Alex"]

    def test_plain_json_parsed(self) -> None:
        """Plain JSON array is parsed correctly."""
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = {"preferred_name": "Alex"}

        raw = '["Prefers to be called Alex"]'
        result = service._parse_haiku_response(raw, answers_map)
        assert result == ["Prefers to be called Alex"]

    def test_non_json_triggers_fallback(self) -> None:
        """Non-JSON text triggers fallback."""
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = {
            "preferred_name": "Alex",
            "occupation": "Engineer",
            "daily_rhythm": "Morning",
            "health_goal": "Lose weight",
            "stress_management": "Walking",
            "sleep_schedule": "11-7",
            "communication_style": "Friendly",
        }

        result = service._parse_haiku_response("Not JSON at all", answers_map)
        assert len(result) == 7
        assert result[0] == "Prefers to be called Alex"

    def test_empty_array_triggers_fallback(self) -> None:
        """Empty JSON array triggers fallback."""
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = {
            "preferred_name": "Alex",
            "occupation": "Engineer",
            "daily_rhythm": "Morning",
            "health_goal": "Lose weight",
            "stress_management": "Walking",
            "sleep_schedule": "11-7",
            "communication_style": "Friendly",
        }

        result = service._parse_haiku_response("[]", answers_map)
        assert len(result) == 7
