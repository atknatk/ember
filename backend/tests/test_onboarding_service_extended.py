"""Extended unit tests for OnboardingService.

Covers edge cases not in the original test_onboarding_service.py:
- Haiku response parsing edge cases (dict, list of non-strings, mixed types,
  code block without json qualifier, nested JSON, number in list)
- Fallback memory generation with special characters / unicode
- HTTPException re-raise in _convert_answers_to_memories (line 148)
- Mem0 messages format verification
- Profile name is None
- Profile name case-insensitive comparison variations
- DB commit NOT called on Haiku failure
- DB commit NOT called on Mem0 failure
- Haiku called with max_tokens=512
- Answer order invariance at service level
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
    OnboardingService,
    _FALLBACK_TEMPLATES,
    _MEMORY_CONVERSION_PROMPT,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")

STANDARD_MEMORIES = [
    "Prefers to be called Alex",
    "Works as a software engineer",
    "Morning person",
    "Goal: lose 10 kg",
    "Manages stress with walks and podcasts",
    "Sleeps from 11 PM to 6:30 AM",
    "Wants regular check-ins without being overwhelmed",
]


def _make_fake_profile(
    onboarding_completed: bool = False,
    name: str | None = "Alexander",
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


def _build_answers_map() -> dict[str, str]:
    """Return a valid answers map for direct service method calls."""
    return {
        "preferred_name": "Alex",
        "occupation": "Software engineer",
        "daily_rhythm": "Morning person",
        "health_goal": "Lose 10 kg",
        "stress_management": "Walks and podcasts",
        "sleep_schedule": "11 PM to 6:30 AM",
        "communication_style": "Check in regularly",
    }


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


# ---------------------------------------------------------------------------
# _parse_haiku_response -- extended edge cases
# ---------------------------------------------------------------------------


class TestParseHaikuResponseEdgeCases:
    """Additional edge cases for Haiku response parsing."""

    def test_json_dict_triggers_fallback(self) -> None:
        """JSON object (dict) instead of array triggers fallback."""
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = _build_answers_map()

        raw = '{"memory": "Prefers to be called Alex"}'
        result = service._parse_haiku_response(raw, answers_map)
        assert len(result) == 7
        assert result[0] == "Prefers to be called Alex"

    def test_json_list_of_numbers_triggers_fallback(self) -> None:
        """JSON array of numbers (not strings) triggers fallback."""
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = _build_answers_map()

        raw = "[1, 2, 3, 4, 5, 6, 7]"
        result = service._parse_haiku_response(raw, answers_map)
        assert len(result) == 7
        assert all(isinstance(m, str) for m in result)

    def test_json_list_mixed_types_triggers_fallback(self) -> None:
        """JSON array with mixed types (string + number) triggers fallback."""
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = _build_answers_map()

        raw = '["Prefers to be called Alex", 42, "Morning person"]'
        result = service._parse_haiku_response(raw, answers_map)
        assert len(result) == 7

    def test_code_block_without_json_qualifier(self) -> None:
        """Code block without 'json' qualifier is still stripped and parsed."""
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = {"preferred_name": "Alex"}

        raw = '```\n["Prefers to be called Alex"]\n```'
        result = service._parse_haiku_response(raw, answers_map)
        assert result == ["Prefers to be called Alex"]

    def test_json_string_not_array_triggers_fallback(self) -> None:
        """JSON string (not array) triggers fallback."""
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = _build_answers_map()

        raw = '"Just a string"'
        result = service._parse_haiku_response(raw, answers_map)
        assert len(result) == 7

    def test_json_null_triggers_fallback(self) -> None:
        """JSON null triggers fallback."""
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = _build_answers_map()

        raw = "null"
        result = service._parse_haiku_response(raw, answers_map)
        assert len(result) == 7

    def test_json_nested_array_triggers_fallback(self) -> None:
        """Nested array (list of lists) triggers fallback."""
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = _build_answers_map()

        raw = '[["nested"], ["arrays"]]'
        result = service._parse_haiku_response(raw, answers_map)
        assert len(result) == 7

    def test_valid_json_with_leading_whitespace(self) -> None:
        """JSON with leading whitespace is parsed correctly."""
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = {"preferred_name": "Alex"}

        raw = '   \n  ["Prefers to be called Alex"]  \n  '
        result = service._parse_haiku_response(raw, answers_map)
        assert result == ["Prefers to be called Alex"]

    def test_haiku_returns_more_than_7_memories(self) -> None:
        """Haiku returns more than 7 strings -- all are accepted (no truncation)."""
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = {"preferred_name": "Alex"}

        memories_10 = [f"Memory {i}" for i in range(10)]
        raw = json.dumps(memories_10)
        result = service._parse_haiku_response(raw, answers_map)
        assert len(result) == 10

    def test_haiku_returns_exactly_1_memory(self) -> None:
        """Haiku returns a list with exactly 1 string -- accepted (len > 0)."""
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = {"preferred_name": "Alex"}

        raw = '["Only one memory"]'
        result = service._parse_haiku_response(raw, answers_map)
        assert result == ["Only one memory"]

    def test_haiku_response_with_unicode(self) -> None:
        """Haiku response with unicode characters is parsed correctly."""
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = {"preferred_name": "Mehmet"}

        raw = json.dumps(["Mehmet olarak cagrilmayi tercih eder"])
        result = service._parse_haiku_response(raw, answers_map)
        assert len(result) == 1
        assert "Mehmet" in result[0]


# ---------------------------------------------------------------------------
# _fallback_memories -- extended edge cases
# ---------------------------------------------------------------------------


class TestFallbackMemoriesEdgeCases:
    """Extended tests for deterministic fallback memory generation."""

    def test_fallback_with_special_characters(self) -> None:
        """Fallback correctly formats answers with special characters."""
        answers_map = _build_answers_map()
        answers_map["preferred_name"] = 'Al"ex & <friends>'
        memories = OnboardingService._fallback_memories(answers_map)
        assert 'Prefers to be called Al"ex & <friends>' in memories

    def test_fallback_with_very_long_answers(self) -> None:
        """Fallback handles answers at the 500-char maximum."""
        answers_map = {k: "a" * 500 for k in _build_answers_map()}
        memories = OnboardingService._fallback_memories(answers_map)
        assert len(memories) == 7
        for m in memories:
            assert len(m) > 500  # template prefix + 500 char answer

    def test_fallback_preserves_answer_order(self) -> None:
        """Fallback memories follow _FALLBACK_TEMPLATES key order."""
        answers_map = _build_answers_map()
        memories = OnboardingService._fallback_memories(answers_map)
        expected_order = list(_FALLBACK_TEMPLATES.keys())
        for i, key in enumerate(expected_order):
            assert _FALLBACK_TEMPLATES[key].format(answer=answers_map[key]) == memories[i]

    def test_fallback_with_all_empty_answers(self) -> None:
        """Fallback returns empty list when all answers are empty strings."""
        answers_map = {k: "" for k in _build_answers_map()}
        memories = OnboardingService._fallback_memories(answers_map)
        assert len(memories) == 0

    def test_fallback_with_missing_key(self) -> None:
        """Fallback skips keys not present in answers_map."""
        answers_map = {
            "preferred_name": "Alex",
            # Missing all other keys
        }
        memories = OnboardingService._fallback_memories(answers_map)
        assert len(memories) == 1
        assert memories[0] == "Prefers to be called Alex"

    def test_fallback_templates_cover_all_valid_keys(self) -> None:
        """Every valid question key has a corresponding fallback template."""
        from app.schemas.onboarding import VALID_QUESTION_KEYS

        for key in VALID_QUESTION_KEYS:
            assert key in _FALLBACK_TEMPLATES


# ---------------------------------------------------------------------------
# _convert_answers_to_memories -- extended
# ---------------------------------------------------------------------------


class TestConvertAnswersToMemoriesExtended:
    """Extended tests for Haiku memory conversion."""

    @pytest.mark.asyncio
    async def test_haiku_called_with_max_tokens_512(self) -> None:
        """Haiku is called with max_tokens=512."""
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = _build_answers_map()

        mock_response = _mock_haiku_response(STANDARD_MEMORIES)

        with patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            await service._convert_answers_to_memories(answers_map)

            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert call_kwargs["max_tokens"] == 512

    @pytest.mark.asyncio
    async def test_haiku_called_with_single_user_message(self) -> None:
        """Haiku messages list contains exactly one user message."""
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = _build_answers_map()

        mock_response = _mock_haiku_response(STANDARD_MEMORIES)

        with patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            await service._convert_answers_to_memories(answers_map)

            call_kwargs = mock_client.messages.create.call_args.kwargs
            messages = call_kwargs["messages"]
            assert len(messages) == 1
            assert messages[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_httpexception_re_raised_not_wrapped(self) -> None:
        """HTTPException raised inside Haiku call is re-raised, not wrapped as 503.

        This covers line 148 of onboarding_service.py -- the `except HTTPException: raise`
        clause that prevents HTTPExceptions from being caught by the generic Exception handler.
        """
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = _build_answers_map()

        with patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            # Simulate an HTTPException being raised during the Haiku call
            mock_client.messages.create = AsyncMock(
                side_effect=HTTPException(status_code=429, detail="Rate limited"),
            )
            mock_cls.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                await service._convert_answers_to_memories(answers_map)

            # The original 429 should be preserved, not wrapped in 503
            assert exc_info.value.status_code == 429
            assert exc_info.value.detail == "Rate limited"

    @pytest.mark.asyncio
    async def test_fallback_used_when_haiku_returns_wrong_format(self) -> None:
        """Fallback is used when Haiku returns valid JSON but wrong structure."""
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = _build_answers_map()

        # Returns a dict instead of a list
        mock_response = _mock_haiku_response_text('{"key": "value"}')

        with patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            result = await service._convert_answers_to_memories(answers_map)

            assert len(result) == 7
            assert result[0] == "Prefers to be called Alex"

    @pytest.mark.asyncio
    async def test_prompt_template_format_is_valid(self) -> None:
        """The prompt template can be formatted with all required keys."""
        answers_map = _build_answers_map()
        # This should not raise any KeyError
        formatted = _MEMORY_CONVERSION_PROMPT.format(**answers_map)
        for value in answers_map.values():
            assert value in formatted


# ---------------------------------------------------------------------------
# complete_onboarding -- extended edge cases
# ---------------------------------------------------------------------------


class TestCompleteOnboardingExtended:
    """Extended tests for the complete_onboarding orchestration method."""

    @pytest.mark.asyncio
    async def test_profile_name_none_gets_updated(self) -> None:
        """When profile.name is None, preferred_name answer is used."""
        db = AsyncMock()
        profile = _make_fake_profile(name=None)
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

            assert profile.name == "Alex"

    @pytest.mark.asyncio
    async def test_profile_name_case_insensitive_UPPER(self) -> None:
        """Profile name 'ALEX' matches preferred_name 'Alex' (case-insensitive)."""
        db = AsyncMock()
        profile = _make_fake_profile(name="ALEX")
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

            # Name should not be updated -- "ALEX".lower() == "alex" == "Alex".lower()
            assert profile.name == "ALEX"

    @pytest.mark.asyncio
    async def test_profile_name_with_whitespace_trimmed(self) -> None:
        """Profile name ' Alex ' should match preferred_name 'Alex' after strip."""
        db = AsyncMock()
        profile = _make_fake_profile(name="  Alex  ")
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

            # Should not update because strip+lower matches
            assert profile.name == "  Alex  "

    @pytest.mark.asyncio
    async def test_db_commit_not_called_on_haiku_failure(self) -> None:
        """DB commit must NOT be called when Claude Haiku fails."""
        db = AsyncMock()
        profile = _make_fake_profile()
        service = OnboardingService(db)

        with patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=Exception("Haiku down"),
            )
            mock_cls.return_value = mock_client

            with pytest.raises(HTTPException):
                await service.complete_onboarding(
                    profile=profile, answers=_build_answers(),
                )

            db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_db_commit_not_called_on_mem0_failure(self) -> None:
        """DB commit must NOT be called when Mem0 fails."""
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
                side_effect=Exception("Mem0 down"),
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

            db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_onboarding_completed_not_set_on_haiku_failure(self) -> None:
        """profile.onboarding_completed remains False when Haiku fails."""
        db = AsyncMock()
        profile = _make_fake_profile()
        service = OnboardingService(db)

        with patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=Exception("Haiku error"),
            )
            mock_cls.return_value = mock_client

            with pytest.raises(HTTPException):
                await service.complete_onboarding(
                    profile=profile, answers=_build_answers(),
                )

            assert profile.onboarding_completed is False

    @pytest.mark.asyncio
    async def test_mem0_messages_format(self) -> None:
        """Mem0 add() receives memories as list of user-role message dicts."""
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

            async def fake_to_thread(func: object, *args: object, **kwargs: object) -> object:
                return func(*args, **kwargs)  # type: ignore[operator]

            mock_asyncio.to_thread = AsyncMock(side_effect=fake_to_thread)

            await service.complete_onboarding(profile=profile, answers=_build_answers())

            # Verify Mem0 add() received the correct format
            mock_mem0.add.assert_called_once()
            call_args = mock_mem0.add.call_args

            # First positional arg is the messages list
            messages = call_args.args[0]
            assert isinstance(messages, list)
            assert len(messages) == 7
            for msg in messages:
                assert msg["role"] == "user"
                assert isinstance(msg["content"], str)
                assert len(msg["content"]) > 0

    @pytest.mark.asyncio
    async def test_answer_order_does_not_affect_result(self) -> None:
        """Answers in any order produce the same result."""
        db = AsyncMock()
        profile = _make_fake_profile()
        service = OnboardingService(db)

        # Reverse the answer order
        answers = list(reversed(_build_answers()))

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

            result = await service.complete_onboarding(profile=profile, answers=answers)

            assert result.onboarding_completed is True
            assert result.memories_seeded == 7

    @pytest.mark.asyncio
    async def test_returns_onboarding_response_type(self) -> None:
        """complete_onboarding returns an OnboardingResponse instance."""
        from app.schemas.onboarding import OnboardingResponse

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

            assert isinstance(result, OnboardingResponse)

    @pytest.mark.asyncio
    async def test_fallback_memories_seeded_on_non_json_haiku(self) -> None:
        """When Haiku returns non-JSON, fallback memories are seeded to Mem0."""
        db = AsyncMock()
        profile = _make_fake_profile()
        service = OnboardingService(db)

        mock_response = _mock_haiku_response_text("Not valid JSON")

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

            async def fake_to_thread(func: object, *args: object, **kwargs: object) -> object:
                return func(*args, **kwargs)  # type: ignore[operator]

            mock_asyncio.to_thread = AsyncMock(side_effect=fake_to_thread)

            result = await service.complete_onboarding(
                profile=profile, answers=_build_answers(),
            )

            assert result.memories_seeded == 7

            # Verify fallback memories were passed to Mem0
            mock_mem0.add.assert_called_once()
            messages_arg = mock_mem0.add.call_args.args[0]
            # Check that the content matches fallback templates
            contents = [m["content"] for m in messages_arg]
            assert "Prefers to be called Alex" in contents
            assert "Works as Software engineer" in contents

    @pytest.mark.asyncio
    async def test_anthropic_client_created_with_api_key(self) -> None:
        """AsyncAnthropic is instantiated with the correct API key from settings."""
        db = AsyncMock()
        service = OnboardingService(db)
        answers_map = _build_answers_map()

        mock_response = _mock_haiku_response(STANDARD_MEMORIES)

        with patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            await service._convert_answers_to_memories(answers_map)

            # Verify AsyncAnthropic was instantiated with api_key
            mock_cls.assert_called_once()
            call_kwargs = mock_cls.call_args.kwargs
            assert "api_key" in call_kwargs

    @pytest.mark.asyncio
    async def test_mem0_client_created_with_api_key(self) -> None:
        """MemoryClient is instantiated with the correct API key from settings."""
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

            # Verify MemoryClient was instantiated with api_key
            mock_mem0_cls.assert_called_once()
            call_kwargs = mock_mem0_cls.call_args.kwargs
            assert "api_key" in call_kwargs
