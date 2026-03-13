"""Tests for the proactive message generator.

Tests cover caching, character personality integration, 100-char truncation,
Mem0/Claude failure fallbacks, and cache clearing.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.services.proactive_message_generator import (
    FALLBACK_MESSAGES,
    ProactiveMessageGenerator,
    _get_fallback_message,
    _truncate_to_limit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_local_now(
    hour: int,
    minute: int,
    tz_name: str = "UTC",
    year: int = 2026,
    month: int = 3,
    day: int = 13,
) -> datetime:
    """Create a timezone-aware datetime for testing."""
    tz = ZoneInfo(tz_name)
    return datetime(year, month, day, hour, minute, 0, tzinfo=tz)


def _make_profile(
    user_id: uuid.UUID | None = None,
    name: str = "Test User",
    preferred_language: str = "en",
    mem0_user_id: str = "mem0_user_123",
) -> MagicMock:
    """Create a mock Profile object."""
    profile = MagicMock()
    profile.id = user_id or uuid.uuid4()
    profile.name = name
    profile.preferred_language = preferred_language
    profile.mem0_user_id = mem0_user_id
    return profile


def _make_character(
    name: str = "Emma",
    mem0_agent_id: str = "emma_usr_123",
    system_prompt: str = "You are Emma, a warm and supportive AI companion who speaks casually.",
) -> MagicMock:
    """Create a mock Character object."""
    char = MagicMock()
    char.id = uuid.uuid4()
    char.name = name
    char.mem0_agent_id = mem0_agent_id
    char.system_prompt = system_prompt
    return char


# ---------------------------------------------------------------------------
# Test generate() — core functionality
# ---------------------------------------------------------------------------


class TestGenerate:
    """Tests for ProactiveMessageGenerator.generate()."""

    @pytest.mark.asyncio
    async def test_returns_claude_message_under_100_chars(self) -> None:
        """Test #1: Valid Mem0 memories and Claude response under 100 chars."""
        generator = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character()

        with (
            patch(
                "app.services.proactive_message_generator._search_mem0",
                return_value=[{"memory": "User likes morning coffee"}],
            ),
            patch(
                "app.services.proactive_message_generator.get_llm_router",
            ) as mock_router,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_fast.return_value = "Good morning, Test User!"
            mock_router.return_value.get.return_value = mock_provider

            result = await generator.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            assert result == "Good morning, Test User!"
            mock_provider.complete_fast.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_hit_on_second_call_same_day(self) -> None:
        """Test #2: Second call returns cached result without calling Mem0 or Claude."""
        generator = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character()

        with (
            patch(
                "app.services.proactive_message_generator._search_mem0",
                return_value=[],
            ) as mock_mem0,
            patch(
                "app.services.proactive_message_generator.get_llm_router",
            ) as mock_router,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_fast.return_value = "Hello there!"
            mock_router.return_value.get.return_value = mock_provider

            local_now = _make_local_now(8, 30)

            # First call
            result1 = await generator.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=local_now,
            )
            # Second call — same user/type/date
            result2 = await generator.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=local_now,
            )

            assert result1 == result2 == "Hello there!"
            # Mem0 and Claude should only be called once
            assert mock_mem0.call_count == 1
            assert mock_provider.complete_fast.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_miss_on_different_dates(self) -> None:
        """Test #3: Different dates result in separate cache entries."""
        generator = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character()

        with (
            patch(
                "app.services.proactive_message_generator._search_mem0",
                return_value=[],
            ),
            patch(
                "app.services.proactive_message_generator.get_llm_router",
            ) as mock_router,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_fast.side_effect = ["Day 1 message", "Day 2 message"]
            mock_router.return_value.get.return_value = mock_provider

            day1 = _make_local_now(8, 30, day=13)
            day2 = _make_local_now(8, 30, day=14)

            result1 = await generator.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=day1,
            )
            result2 = await generator.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=day2,
            )

            assert result1 == "Day 1 message"
            assert result2 == "Day 2 message"
            assert mock_provider.complete_fast.call_count == 2

    @pytest.mark.asyncio
    async def test_mem0_failure_still_generates_message(self) -> None:
        """Test #4: Mem0 search fails, Claude is called with empty memories."""
        generator = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character()

        with (
            patch(
                "app.services.proactive_message_generator._search_mem0",
                side_effect=Exception("Mem0 down"),
            ),
            patch(
                "app.services.proactive_message_generator.get_llm_router",
            ) as mock_router,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_fast.return_value = "Hello there!"
            mock_router.return_value.get.return_value = mock_provider

            result = await generator.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            assert result == "Hello there!"
            # Verify Claude was still called
            mock_provider.complete_fast.assert_called_once()
            # Verify the user prompt contains "None" for memories
            call_args = mock_provider.complete_fast.call_args
            user_msg = call_args.kwargs["messages"][0]["content"]
            assert "None" in user_msg

    @pytest.mark.asyncio
    async def test_claude_failure_returns_fallback(self) -> None:
        """Test #5: Claude Haiku fails, returns fallback message."""
        generator = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character()

        with (
            patch(
                "app.services.proactive_message_generator._search_mem0",
                return_value=[],
            ),
            patch(
                "app.services.proactive_message_generator.get_llm_router",
                side_effect=Exception("LLM unavailable"),
            ),
        ):
            result = await generator.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            assert result == "Good morning! How are you feeling today?"

    @pytest.mark.asyncio
    async def test_both_mem0_and_claude_fail_returns_fallback(self) -> None:
        """Test #6: Both Mem0 and Claude fail, returns fallback."""
        generator = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character()

        with (
            patch(
                "app.services.proactive_message_generator._search_mem0",
                side_effect=Exception("Mem0 down"),
            ),
            patch(
                "app.services.proactive_message_generator.get_llm_router",
                side_effect=Exception("LLM down"),
            ),
        ):
            result = await generator.generate(
                profile=profile,
                character=character,
                notification_type="afternoon_nudge",
                local_now=_make_local_now(14, 30),
            )

            assert result == "Hey! Haven't heard from you today. Everything okay?"

    @pytest.mark.asyncio
    async def test_truncates_message_over_100_chars_at_word_boundary(self) -> None:
        """Test #7: Claude returns message > 100 chars, truncated at word boundary."""
        generator = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character()

        long_message = "Good morning Test User! I hope you have a wonderful day ahead of you. Remember to take breaks and stay hydrated!"
        assert len(long_message) > 100

        with (
            patch(
                "app.services.proactive_message_generator._search_mem0",
                return_value=[],
            ),
            patch(
                "app.services.proactive_message_generator.get_llm_router",
            ) as mock_router,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_fast.return_value = long_message
            mock_router.return_value.get.return_value = mock_provider

            result = await generator.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            assert len(result) <= 100
            assert result.endswith("...")

    @pytest.mark.asyncio
    async def test_exactly_100_chars_not_truncated(self) -> None:
        """Test #8: Claude returns exactly 100 chars, returned as-is."""
        generator = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character()

        # Create a message of exactly 100 chars
        exact_100 = "A" * 100
        assert len(exact_100) == 100

        with (
            patch(
                "app.services.proactive_message_generator._search_mem0",
                return_value=[],
            ),
            patch(
                "app.services.proactive_message_generator.get_llm_router",
            ) as mock_router,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_fast.return_value = exact_100
            mock_router.return_value.get.return_value = mock_provider

            result = await generator.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            assert result == exact_100
            assert len(result) == 100

    @pytest.mark.asyncio
    async def test_101_chars_no_space_hard_truncate(self) -> None:
        """Test #9: 101 chars with no space, hard-truncated at 97 + '...'."""
        generator = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character()

        no_space_message = "A" * 101

        with (
            patch(
                "app.services.proactive_message_generator._search_mem0",
                return_value=[],
            ),
            patch(
                "app.services.proactive_message_generator.get_llm_router",
            ) as mock_router,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_fast.return_value = no_space_message
            mock_router.return_value.get.return_value = mock_provider

            result = await generator.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            assert len(result) == 100
            assert result == "A" * 97 + "..."

    @pytest.mark.asyncio
    async def test_includes_character_system_prompt_in_llm_prompt(self) -> None:
        """Test #10: Character system_prompt excerpt is included in LLM prompt."""
        generator = ProactiveMessageGenerator()
        profile = _make_profile()
        system_prompt_text = "You are Emma, a warm and supportive AI companion."
        character = _make_character(system_prompt=system_prompt_text)

        with (
            patch(
                "app.services.proactive_message_generator._search_mem0",
                return_value=[],
            ),
            patch(
                "app.services.proactive_message_generator.get_llm_router",
            ) as mock_router,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_fast.return_value = "Hello!"
            mock_router.return_value.get.return_value = mock_provider

            await generator.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            call_args = mock_provider.complete_fast.call_args
            system_arg = call_args.kwargs["system"]
            assert system_prompt_text[:200] in system_arg
            assert "Your personality:" in system_arg

    @pytest.mark.asyncio
    async def test_includes_day_of_week_in_user_prompt(self) -> None:
        """Test #11: Day of week is included in user prompt."""
        generator = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character()

        local_now = _make_local_now(8, 30)  # 2026-03-13 is a Friday

        with (
            patch(
                "app.services.proactive_message_generator._search_mem0",
                return_value=[],
            ),
            patch(
                "app.services.proactive_message_generator.get_llm_router",
            ) as mock_router,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_fast.return_value = "Hello!"
            mock_router.return_value.get.return_value = mock_provider

            await generator.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=local_now,
            )

            call_args = mock_provider.complete_fast.call_args
            user_msg = call_args.kwargs["messages"][0]["content"]
            assert "Day of week:" in user_msg
            assert local_now.strftime("%A") in user_msg

    @pytest.mark.asyncio
    async def test_turkish_language_in_prompt(self) -> None:
        """Test #12: Turkish language profile sets 'Language: tr' in prompt."""
        generator = ProactiveMessageGenerator()
        profile = _make_profile(preferred_language="tr")
        character = _make_character()

        with (
            patch(
                "app.services.proactive_message_generator._search_mem0",
                return_value=[],
            ),
            patch(
                "app.services.proactive_message_generator.get_llm_router",
            ) as mock_router,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_fast.return_value = "Gunaydin!"
            mock_router.return_value.get.return_value = mock_provider

            await generator.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            call_args = mock_provider.complete_fast.call_args
            system_arg = call_args.kwargs["system"]
            assert "Language: tr" in system_arg

    @pytest.mark.asyncio
    async def test_fallback_is_also_cached(self) -> None:
        """Test #13: After Claude failure, fallback is cached."""
        generator = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character()
        local_now = _make_local_now(8, 30)

        with (
            patch(
                "app.services.proactive_message_generator._search_mem0",
                return_value=[],
            ),
            patch(
                "app.services.proactive_message_generator.get_llm_router",
                side_effect=Exception("LLM down"),
            ) as mock_router,
        ):
            result1 = await generator.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=local_now,
            )

            # Second call should return cached fallback without retrying
            result2 = await generator.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=local_now,
            )

            assert result1 == result2 == "Good morning! How are you feeling today?"
            # get_llm_router should only be called once (first call)
            assert mock_router.call_count == 1

    @pytest.mark.asyncio
    async def test_empty_system_prompt_handled(self) -> None:
        """Character with empty system_prompt does not crash."""
        generator = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character(system_prompt="")

        with (
            patch(
                "app.services.proactive_message_generator._search_mem0",
                return_value=[],
            ),
            patch(
                "app.services.proactive_message_generator.get_llm_router",
            ) as mock_router,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_fast.return_value = "Hello!"
            mock_router.return_value.get.return_value = mock_provider

            result = await generator.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            assert result == "Hello!"

    @pytest.mark.asyncio
    async def test_none_system_prompt_handled(self) -> None:
        """Character with None system_prompt does not crash."""
        generator = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character(system_prompt=None)
        character.system_prompt = None

        with (
            patch(
                "app.services.proactive_message_generator._search_mem0",
                return_value=[],
            ),
            patch(
                "app.services.proactive_message_generator.get_llm_router",
            ) as mock_router,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_fast.return_value = "Hello!"
            mock_router.return_value.get.return_value = mock_provider

            result = await generator.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            assert result == "Hello!"


# ---------------------------------------------------------------------------
# Test clear_cache
# ---------------------------------------------------------------------------


class TestClearCache:
    """Tests for ProactiveMessageGenerator.clear_cache()."""

    @pytest.mark.asyncio
    async def test_clear_cache_empties_cache(self) -> None:
        """Test #14: After clear_cache(), next generate() call hits Claude again."""
        generator = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character()
        local_now = _make_local_now(8, 30)

        with (
            patch(
                "app.services.proactive_message_generator._search_mem0",
                return_value=[],
            ),
            patch(
                "app.services.proactive_message_generator.get_llm_router",
            ) as mock_router,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_fast.side_effect = ["First message", "Second message"]
            mock_router.return_value.get.return_value = mock_provider

            # First call
            result1 = await generator.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=local_now,
            )
            assert result1 == "First message"

            # Clear cache
            generator.clear_cache()

            # Second call — should hit Claude again
            result2 = await generator.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=local_now,
            )
            assert result2 == "Second message"
            assert mock_provider.complete_fast.call_count == 2


# ---------------------------------------------------------------------------
# Test _build_cache_key
# ---------------------------------------------------------------------------


class TestBuildCacheKey:
    """Tests for ProactiveMessageGenerator._build_cache_key()."""

    def test_cache_key_format(self) -> None:
        """Test #15: Cache key format is '{user_id}:{notification_type}:{YYYY-MM-DD}'."""
        generator = ProactiveMessageGenerator()
        user_id = uuid.UUID("12345678-1234-5678-1234-567812345678")
        local_now = _make_local_now(8, 30)

        key = generator._build_cache_key(user_id, "morning_checkin", local_now)

        assert key == "12345678-1234-5678-1234-567812345678:morning_checkin:2026-03-13"


# ---------------------------------------------------------------------------
# Test _get_fallback_message
# ---------------------------------------------------------------------------


class TestGetFallbackMessage:
    """Tests for _get_fallback_message()."""

    def test_english_fallback(self) -> None:
        """Test #16a: English fallback for morning_checkin."""
        result = _get_fallback_message("morning_checkin", "en")
        assert result == "Good morning! How are you feeling today?"

    def test_turkish_fallback(self) -> None:
        """Test #16b: Turkish fallback for morning_checkin."""
        result = _get_fallback_message("morning_checkin", "tr")
        assert result == "Gunaydin! Bugun nasil hissediyorsun?"

    def test_unknown_language_falls_back_to_english(self) -> None:
        """Test #16c: Unknown language falls back to English."""
        result = _get_fallback_message("morning_checkin", "ja")
        assert result == "Good morning! How are you feeling today?"

    def test_unknown_type_returns_generic(self) -> None:
        """Unknown notification type returns generic fallback."""
        result = _get_fallback_message("goal_followup", "en")
        assert result == "Hey! How are you?"

    def test_all_types_have_turkish(self) -> None:
        """All notification types have Turkish fallback."""
        for ntype in FALLBACK_MESSAGES:
            result = _get_fallback_message(ntype, "tr")
            assert len(result) > 0


# ---------------------------------------------------------------------------
# Test _truncate_to_limit
# ---------------------------------------------------------------------------


class TestTruncateToLimit:
    """Tests for the truncation helper."""

    def test_under_limit_unchanged(self) -> None:
        """Message under limit is returned unchanged."""
        assert _truncate_to_limit("Hello world") == "Hello world"

    def test_exactly_at_limit(self) -> None:
        """Message exactly at limit is returned unchanged."""
        msg = "A" * 100
        assert _truncate_to_limit(msg) == msg

    def test_over_limit_truncated_at_word_boundary(self) -> None:
        """Message over limit is truncated at last word boundary + '...'."""
        msg = "word " * 25  # 125 chars
        result = _truncate_to_limit(msg)
        assert len(result) <= 100
        assert result.endswith("...")

    def test_over_limit_no_space_hard_truncate(self) -> None:
        """Message with no spaces is hard-truncated at 97 + '...'."""
        msg = "A" * 110
        result = _truncate_to_limit(msg)
        assert len(result) == 100
        assert result == "A" * 97 + "..."

    def test_custom_limit(self) -> None:
        """Custom limit is respected."""
        msg = "Hello world, this is a test"
        result = _truncate_to_limit(msg, limit=15)
        assert len(result) <= 15
        assert result.endswith("...")
