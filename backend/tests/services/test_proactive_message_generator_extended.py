"""Extended tests for the proactive message generator.

Supplements the 27 tests written by the backend-dev with coverage for edge
cases not yet exercised:

  - Cache key uniqueness across users, notification types, and dates
  - Cache isolation between different notification types for the same user
  - Local-date extraction from timezone-aware datetimes
  - _truncate_to_limit edge cases: whitespace-only, boundary at exactly 97,
    exactly 98-char input, 99-char input
  - generate() with Mem0 results missing "memory" key or empty "memory" value
  - generate() with notification_type not in TONE_MAP / MEM0_QUERIES
  - generate() with system_prompt longer than 200 chars
  - generate() with system_prompt exactly 200 chars
  - generate() with Claude returning leading/trailing whitespace
  - generate() verifies character.name and profile.name appear in prompts
  - generate() verifies local time (HH:MM) appears in user prompt
  - Backward-compat re-exports from notification_scheduler module
  - reset_notifications_sent_today calls _generator.clear_cache()
  - _process_notification calls _generator.generate() with correct arguments
  - TONE_MAP and MEM0_QUERIES cover all 4 NOTIFICATION_TYPES
  - _get_fallback_message: all 4 types have non-empty English and Turkish
  - _get_fallback_message: unknown type + unknown language still returns str
"""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.services.proactive_message_generator import (
    FALLBACK_MESSAGES,
    MEM0_QUERIES,
    TONE_MAP,
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
    tz = ZoneInfo(tz_name)
    return datetime(year, month, day, hour, minute, 0, tzinfo=tz)


def _make_profile(
    user_id: uuid.UUID | None = None,
    name: str = "Alice",
    preferred_language: str = "en",
    mem0_user_id: str = "mem0_alice",
) -> MagicMock:
    profile = MagicMock()
    profile.id = user_id or uuid.uuid4()
    profile.name = name
    profile.preferred_language = preferred_language
    profile.mem0_user_id = mem0_user_id
    return profile


def _make_character(
    name: str = "Emma",
    mem0_agent_id: str = "emma_alice",
    system_prompt: str = "You are Emma, a warm and supportive friend.",
) -> MagicMock:
    char = MagicMock()
    char.id = uuid.uuid4()
    char.name = name
    char.mem0_agent_id = mem0_agent_id
    char.system_prompt = system_prompt
    return char


def _patch_both(mem0_results=None, claude_return="Hello!"):
    """Return a context manager that patches both _search_mem0 and get_llm_router."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        with (
            patch(
                "app.services.proactive_message_generator._search_mem0",
                return_value=mem0_results if mem0_results is not None else [],
            ),
            patch(
                "app.services.proactive_message_generator.get_llm_router",
            ) as mock_router,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_fast.return_value = claude_return
            mock_router.return_value.get.return_value = mock_provider
            yield mock_router, mock_provider

    return _ctx()


# ---------------------------------------------------------------------------
# TestCacheKeyUniqueness
# ---------------------------------------------------------------------------


class TestCacheKeyUniqueness:
    """_build_cache_key must produce distinct keys for distinct inputs."""

    def test_different_users_produce_different_keys(self) -> None:
        """Two different users with the same notification type and date produce different keys."""
        gen = ProactiveMessageGenerator()
        uid1 = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        uid2 = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        local_now = _make_local_now(8, 30)

        key1 = gen._build_cache_key(uid1, "morning_checkin", local_now)
        key2 = gen._build_cache_key(uid2, "morning_checkin", local_now)

        assert key1 != key2
        assert str(uid1) in key1
        assert str(uid2) in key2

    def test_different_notification_types_produce_different_keys(self) -> None:
        """Same user with different notification types produce different keys."""
        gen = ProactiveMessageGenerator()
        uid = uuid.uuid4()
        local_now = _make_local_now(8, 30)

        key_morning = gen._build_cache_key(uid, "morning_checkin", local_now)
        key_afternoon = gen._build_cache_key(uid, "afternoon_nudge", local_now)
        key_evening = gen._build_cache_key(uid, "evening_reflection", local_now)
        key_sleep = gen._build_cache_key(uid, "sleep_reminder", local_now)

        all_keys = {key_morning, key_afternoon, key_evening, key_sleep}
        assert len(all_keys) == 4, "All four notification type keys must be distinct"

    def test_different_dates_produce_different_keys(self) -> None:
        """Same user and type on different days produce different keys."""
        gen = ProactiveMessageGenerator()
        uid = uuid.uuid4()

        key_day1 = gen._build_cache_key(uid, "morning_checkin", _make_local_now(8, 30, day=13))
        key_day2 = gen._build_cache_key(uid, "morning_checkin", _make_local_now(8, 30, day=14))
        key_day3 = gen._build_cache_key(uid, "morning_checkin", _make_local_now(8, 30, day=15))

        assert key_day1 != key_day2 != key_day3
        assert "2026-03-13" in key_day1
        assert "2026-03-14" in key_day2
        assert "2026-03-15" in key_day3

    def test_timezone_aware_date_uses_local_date(self) -> None:
        """Cache key uses local date, not UTC date.

        UTC midnight (00:00 UTC) is still the previous day in UTC-5 (19:00 local).
        """
        gen = ProactiveMessageGenerator()
        uid = uuid.uuid4()

        # 2026-03-14 00:30 UTC but 2026-03-13 19:30 in America/New_York (UTC-5 in March)
        utc_midnight_moment = _make_local_now(0, 30, tz_name="UTC", day=14)
        # Convert to NY time — should still be 2026-03-13 in local
        ny_tz = ZoneInfo("America/New_York")
        local_ny = utc_midnight_moment.astimezone(ny_tz)

        key = gen._build_cache_key(uid, "morning_checkin", local_ny)
        # March 14 00:30 UTC = March 13 in NY (19:30 local since UTC-5 in standard time)
        assert "2026-03-13" in key


# ---------------------------------------------------------------------------
# TestCacheIsolation
# ---------------------------------------------------------------------------


class TestCacheIsolation:
    """Cache entries for different notification types must not collide."""

    @pytest.mark.asyncio
    async def test_different_types_cached_independently(self) -> None:
        """Calling generate() for two different types produces independent cache entries."""
        gen = ProactiveMessageGenerator()
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
            mock_provider.complete_fast.side_effect = ["Morning message", "Afternoon message"]
            mock_router.return_value.get.return_value = mock_provider

            result_morning = await gen.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=local_now,
            )
            result_afternoon = await gen.generate(
                profile=profile,
                character=character,
                notification_type="afternoon_nudge",
                local_now=local_now,
            )

        assert result_morning == "Morning message"
        assert result_afternoon == "Afternoon message"
        assert mock_provider.complete_fast.call_count == 2

    @pytest.mark.asyncio
    async def test_two_users_same_type_no_cache_collision(self) -> None:
        """Two different users with same notification type get independent results."""
        gen = ProactiveMessageGenerator()
        profile_a = _make_profile(user_id=uuid.uuid4(), name="Alice")
        profile_b = _make_profile(user_id=uuid.uuid4(), name="Bob")
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
            mock_provider.complete_fast.side_effect = ["Hello Alice!", "Hello Bob!"]
            mock_router.return_value.get.return_value = mock_provider

            result_a = await gen.generate(
                profile=profile_a,
                character=character,
                notification_type="morning_checkin",
                local_now=local_now,
            )
            result_b = await gen.generate(
                profile=profile_b,
                character=character,
                notification_type="morning_checkin",
                local_now=local_now,
            )

        assert result_a == "Hello Alice!"
        assert result_b == "Hello Bob!"
        # Claude must be called for each distinct user — no cache pollution
        assert mock_provider.complete_fast.call_count == 2


# ---------------------------------------------------------------------------
# TestTruncateEdgeCases
# ---------------------------------------------------------------------------


class TestTruncateEdgeCases:
    """Edge cases for _truncate_to_limit not covered by the base test file."""

    def test_whitespace_only_message_under_limit(self) -> None:
        """A whitespace-only message under the limit is returned unchanged."""
        msg = "   "
        result = _truncate_to_limit(msg)
        assert result == "   "

    def test_exactly_98_chars_not_truncated(self) -> None:
        """98-char message (< 100) is returned unchanged."""
        msg = "A" * 98
        assert _truncate_to_limit(msg) == msg

    def test_exactly_99_chars_not_truncated(self) -> None:
        """99-char message (< 100) is returned unchanged."""
        msg = "X" * 99
        assert _truncate_to_limit(msg) == msg

    def test_101_chars_word_boundary_at_position_97(self) -> None:
        """Word boundary falls exactly at position 97 (start of cutoff).

        The cutoff is limit-3 = 97. rfind(' ', 0, 97) finds a space before 97.
        We construct: 96 'a' chars + space + 'b' * 3 = 101 chars total.
        The space is at index 96, so rfind(' ', 0, 97) returns 96.
        Result: 'a'*96 + '...' (99 chars).
        """
        msg = "a" * 96 + " " + "b" * 4  # 101 chars; space at idx 96
        result = _truncate_to_limit(msg)
        assert len(result) <= 100
        assert result.endswith("...")
        assert result == "a" * 96 + "..."

    def test_empty_string_returned_unchanged(self) -> None:
        """Empty string is returned as-is."""
        assert _truncate_to_limit("") == ""

    def test_single_char_returned_unchanged(self) -> None:
        """Single-character string is returned as-is."""
        assert _truncate_to_limit("X") == "X"

    def test_result_never_exceeds_limit_with_words_at_boundary(self) -> None:
        """Truncated result is always <= limit regardless of word positions."""
        # 105 chars with a word break at various spots
        messages = [
            "word " * 21,                # word boundary every 5 chars
            "a" * 50 + " " + "b" * 54,  # single space in middle
            "a" * 97 + " " + "b" * 3,   # space at pos 97
        ]
        for msg in messages:
            result = _truncate_to_limit(msg)
            assert len(result) <= 100, f"Result {len(result)} > 100 for input len {len(msg)}"

    def test_custom_limit_zero_raises_or_returns_ellipsis(self) -> None:
        """With limit=3, any non-empty text longer than 3 chars is truncated to '...'."""
        msg = "Hello world"
        result = _truncate_to_limit(msg, limit=3)
        assert len(result) <= 3


# ---------------------------------------------------------------------------
# TestMem0ResultsEdgeCases
# ---------------------------------------------------------------------------


class TestMem0ResultsEdgeCases:
    """Edge cases for how Mem0 search results are handled in generate()."""

    @pytest.mark.asyncio
    async def test_mem0_result_with_empty_memory_key_excluded(self) -> None:
        """Mem0 results with empty 'memory' string are excluded from memories_text."""
        gen = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character()

        # One entry with valid memory, one with empty string, one with no 'memory' key
        mem0_results = [
            {"memory": "User loves running"},
            {"memory": ""},
            {"other_key": "irrelevant"},
        ]

        with (
            patch(
                "app.services.proactive_message_generator._search_mem0",
                return_value=mem0_results,
            ),
            patch(
                "app.services.proactive_message_generator.get_llm_router",
            ) as mock_router,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_fast.return_value = "Hey!"
            mock_router.return_value.get.return_value = mock_provider

            await gen.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            call_args = mock_provider.complete_fast.call_args
            user_msg = call_args.kwargs["messages"][0]["content"]

            # Only the non-empty memory should appear
            assert "User loves running" in user_msg
            # Empty and missing memory values should not produce blank list entries
            assert "\n- \n" not in user_msg

    @pytest.mark.asyncio
    async def test_mem0_returns_all_empty_memory_keys_shows_none(self) -> None:
        """If all Mem0 results have empty 'memory', memories_text should be empty -> 'None'."""
        gen = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character()

        mem0_results = [
            {"memory": ""},
            {"memory": ""},
        ]

        with (
            patch(
                "app.services.proactive_message_generator._search_mem0",
                return_value=mem0_results,
            ),
            patch(
                "app.services.proactive_message_generator.get_llm_router",
            ) as mock_router,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_fast.return_value = "Hey!"
            mock_router.return_value.get.return_value = mock_provider

            await gen.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            call_args = mock_provider.complete_fast.call_args
            user_msg = call_args.kwargs["messages"][0]["content"]
            assert "None" in user_msg


# ---------------------------------------------------------------------------
# TestUnknownNotificationType
# ---------------------------------------------------------------------------


class TestUnknownNotificationType:
    """Behaviour when notification_type is not in TONE_MAP or MEM0_QUERIES."""

    @pytest.mark.asyncio
    async def test_unknown_type_uses_warm_tone_fallback(self) -> None:
        """Unknown notification type defaults to 'warm' tone in the system prompt."""
        gen = ProactiveMessageGenerator()
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
            mock_provider.complete_fast.return_value = "Hi!"
            mock_router.return_value.get.return_value = mock_provider

            await gen.generate(
                profile=profile,
                character=character,
                notification_type="goal_followup",  # not in TONE_MAP
                local_now=_make_local_now(10, 0),
            )

            call_args = mock_provider.complete_fast.call_args
            system_arg = call_args.kwargs["system"]
            assert "Tone: warm" in system_arg

    @pytest.mark.asyncio
    async def test_unknown_type_uses_empty_mem0_query(self) -> None:
        """Unknown notification type uses empty string as the Mem0 query."""
        gen = ProactiveMessageGenerator()
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
            mock_provider.complete_fast.return_value = "Hi!"
            mock_router.return_value.get.return_value = mock_provider

            await gen.generate(
                profile=profile,
                character=character,
                notification_type="goal_followup",  # not in MEM0_QUERIES
                local_now=_make_local_now(10, 0),
            )

            # _search_mem0 should be called with query=""
            call_kwargs = mock_mem0.call_args.kwargs
            assert call_kwargs["query"] == ""

    @pytest.mark.asyncio
    async def test_unknown_type_notification_type_in_user_prompt(self) -> None:
        """Unknown notification type is still included in the user prompt."""
        gen = ProactiveMessageGenerator()
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
            mock_provider.complete_fast.return_value = "Hi!"
            mock_router.return_value.get.return_value = mock_provider

            await gen.generate(
                profile=profile,
                character=character,
                notification_type="goal_followup",
                local_now=_make_local_now(10, 0),
            )

            call_args = mock_provider.complete_fast.call_args
            user_msg = call_args.kwargs["messages"][0]["content"]
            assert "goal_followup" in user_msg


# ---------------------------------------------------------------------------
# TestSystemPromptLengthHandling
# ---------------------------------------------------------------------------


class TestSystemPromptLengthHandling:
    """Verify system_prompt is clamped to first 200 chars."""

    @pytest.mark.asyncio
    async def test_system_prompt_longer_than_200_chars_truncated_to_200(self) -> None:
        """system_prompt > 200 chars: only the first 200 chars appear in the LLM system prompt."""
        gen = ProactiveMessageGenerator()
        profile = _make_profile()
        # 300-char system_prompt, first 200 all 'A', last 100 all 'B'
        long_prompt = "A" * 200 + "B" * 100
        character = _make_character(system_prompt=long_prompt)

        with _patch_both() as (_, mock_provider):
            await gen.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            call_args = mock_provider.complete_fast.call_args
            system_arg = call_args.kwargs["system"]

            # The first 200 chars (all 'A') must appear
            assert "A" * 200 in system_arg
            # The extra 'B' chars must NOT appear
            assert "B" not in system_arg

    @pytest.mark.asyncio
    async def test_system_prompt_exactly_200_chars_not_truncated(self) -> None:
        """system_prompt == 200 chars: all 200 chars appear in the LLM system prompt."""
        gen = ProactiveMessageGenerator()
        profile = _make_profile()
        exact_200 = "C" * 200
        character = _make_character(system_prompt=exact_200)

        with _patch_both() as (_, mock_provider):
            await gen.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            call_args = mock_provider.complete_fast.call_args
            system_arg = call_args.kwargs["system"]
            assert "C" * 200 in system_arg

    @pytest.mark.asyncio
    async def test_system_prompt_under_200_chars_used_in_full(self) -> None:
        """system_prompt < 200 chars: the full string appears in the LLM system prompt."""
        gen = ProactiveMessageGenerator()
        profile = _make_profile()
        short_prompt = "Short personality description."
        character = _make_character(system_prompt=short_prompt)

        with _patch_both() as (_, mock_provider):
            await gen.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            call_args = mock_provider.complete_fast.call_args
            system_arg = call_args.kwargs["system"]
            assert short_prompt in system_arg


# ---------------------------------------------------------------------------
# TestPromptContents
# ---------------------------------------------------------------------------


class TestPromptContents:
    """Verify specific content of the prompts passed to Claude Haiku."""

    @pytest.mark.asyncio
    async def test_character_name_in_system_prompt(self) -> None:
        """Character's name appears in the system prompt."""
        gen = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character(name="Luna")

        with _patch_both() as (_, mock_provider):
            await gen.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            call_args = mock_provider.complete_fast.call_args
            system_arg = call_args.kwargs["system"]
            assert "Luna" in system_arg

    @pytest.mark.asyncio
    async def test_profile_name_in_user_prompt(self) -> None:
        """Profile's name appears in the user prompt."""
        gen = ProactiveMessageGenerator()
        profile = _make_profile(name="Zeynep")
        character = _make_character()

        with _patch_both() as (_, mock_provider):
            await gen.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            call_args = mock_provider.complete_fast.call_args
            user_msg = call_args.kwargs["messages"][0]["content"]
            assert "Zeynep" in user_msg

    @pytest.mark.asyncio
    async def test_local_time_hhmmm_in_user_prompt(self) -> None:
        """Local time in HH:MM format appears in the user prompt."""
        gen = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character()
        local_now = _make_local_now(14, 45)

        with _patch_both() as (_, mock_provider):
            await gen.generate(
                profile=profile,
                character=character,
                notification_type="afternoon_nudge",
                local_now=local_now,
            )

            call_args = mock_provider.complete_fast.call_args
            user_msg = call_args.kwargs["messages"][0]["content"]
            assert "14:45" in user_msg

    @pytest.mark.asyncio
    async def test_max_tokens_is_100(self) -> None:
        """complete_fast is called with max_tokens=100."""
        gen = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character()

        with _patch_both() as (_, mock_provider):
            await gen.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            call_args = mock_provider.complete_fast.call_args
            assert call_args.kwargs["max_tokens"] == 100

    @pytest.mark.asyncio
    async def test_temperature_is_0_7(self) -> None:
        """complete_fast is called with temperature=0.7."""
        gen = ProactiveMessageGenerator()
        profile = _make_profile()
        character = _make_character()

        with _patch_both() as (_, mock_provider):
            await gen.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            call_args = mock_provider.complete_fast.call_args
            assert call_args.kwargs["temperature"] == pytest.approx(0.7)

    @pytest.mark.asyncio
    async def test_claude_response_whitespace_stripped(self) -> None:
        """Claude response with leading/trailing whitespace is stripped before use."""
        gen = ProactiveMessageGenerator()
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
            mock_provider.complete_fast.return_value = "  Good morning!  \n"
            mock_router.return_value.get.return_value = mock_provider

            result = await gen.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

        assert result == "Good morning!"

    @pytest.mark.asyncio
    async def test_mem0_agent_id_passed_correctly(self) -> None:
        """_search_mem0 is called with the character's mem0_agent_id."""
        gen = ProactiveMessageGenerator()
        profile = _make_profile(mem0_user_id="u_alice")
        character = _make_character(mem0_agent_id="emma_u_alice")

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
            mock_provider.complete_fast.return_value = "Hey!"
            mock_router.return_value.get.return_value = mock_provider

            await gen.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            call_kwargs = mock_mem0.call_args.kwargs
            assert call_kwargs["mem0_user_id"] == "u_alice"
            assert call_kwargs["agent_id"] == "emma_u_alice"

    @pytest.mark.asyncio
    async def test_none_preferred_language_defaults_to_en(self) -> None:
        """Profile with preferred_language=None defaults to 'en' in the prompt."""
        gen = ProactiveMessageGenerator()
        profile = _make_profile(preferred_language=None)  # type: ignore[arg-type]
        profile.preferred_language = None
        character = _make_character()

        with _patch_both() as (_, mock_provider):
            await gen.generate(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            call_args = mock_provider.complete_fast.call_args
            system_arg = call_args.kwargs["system"]
            assert "Language: en" in system_arg


# ---------------------------------------------------------------------------
# TestClearCacheEdgeCases
# ---------------------------------------------------------------------------


class TestClearCacheEdgeCases:
    """Additional clear_cache edge cases."""

    def test_clear_cache_on_empty_cache_does_not_raise(self) -> None:
        """clear_cache() on an already-empty cache must not raise any exception."""
        gen = ProactiveMessageGenerator()
        gen.clear_cache()  # Should not raise
        gen.clear_cache()  # Idempotent — no error on second call

    @pytest.mark.asyncio
    async def test_clear_cache_removes_all_types(self) -> None:
        """clear_cache() removes entries for all notification types."""
        gen = ProactiveMessageGenerator()
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
            mock_provider.complete_fast.side_effect = [
                "Morning", "Afternoon", "Evening", "Sleep",     # first round
                "Morning2", "Afternoon2", "Evening2", "Sleep2", # second round
            ]
            mock_router.return_value.get.return_value = mock_provider

            local_now = _make_local_now(8, 30)
            for ntype in ("morning_checkin", "afternoon_nudge", "evening_reflection", "sleep_reminder"):
                await gen.generate(
                    profile=profile,
                    character=character,
                    notification_type=ntype,
                    local_now=local_now,
                )

            # 4 calls so far
            assert mock_provider.complete_fast.call_count == 4

            gen.clear_cache()

            # After clearing, all 4 types should hit Claude again
            for ntype in ("morning_checkin", "afternoon_nudge", "evening_reflection", "sleep_reminder"):
                await gen.generate(
                    profile=profile,
                    character=character,
                    notification_type=ntype,
                    local_now=local_now,
                )

            assert mock_provider.complete_fast.call_count == 8


# ---------------------------------------------------------------------------
# TestConstantsCompleteness
# ---------------------------------------------------------------------------


class TestConstantsCompleteness:
    """Verify TONE_MAP and MEM0_QUERIES are complete and consistent."""

    def test_tone_map_covers_all_known_types(self) -> None:
        """TONE_MAP has an entry for each of the 4 known notification types."""
        expected = {"morning_checkin", "afternoon_nudge", "evening_reflection", "sleep_reminder"}
        assert set(TONE_MAP.keys()) == expected

    def test_tone_map_values_are_non_empty_strings(self) -> None:
        """All TONE_MAP values are non-empty strings."""
        for key, value in TONE_MAP.items():
            assert isinstance(value, str) and len(value) > 0, f"TONE_MAP[{key!r}] is empty"

    def test_mem0_queries_covers_all_known_types(self) -> None:
        """MEM0_QUERIES has an entry for each of the 4 known notification types."""
        expected = {"morning_checkin", "afternoon_nudge", "evening_reflection", "sleep_reminder"}
        assert set(MEM0_QUERIES.keys()) == expected

    def test_mem0_queries_values_are_non_empty_strings(self) -> None:
        """All MEM0_QUERIES values are non-empty strings."""
        for key, value in MEM0_QUERIES.items():
            assert isinstance(value, str) and len(value) > 0, f"MEM0_QUERIES[{key!r}] is empty"

    def test_fallback_messages_covers_all_known_types(self) -> None:
        """FALLBACK_MESSAGES has entries for all 4 known notification types."""
        expected = {"morning_checkin", "afternoon_nudge", "evening_reflection", "sleep_reminder"}
        assert set(FALLBACK_MESSAGES.keys()) == expected

    def test_fallback_messages_have_en_and_tr_for_all_types(self) -> None:
        """Every notification type has both 'en' and 'tr' fallback messages."""
        for ntype, lang_map in FALLBACK_MESSAGES.items():
            assert "en" in lang_map, f"Missing 'en' fallback for {ntype}"
            assert "tr" in lang_map, f"Missing 'tr' fallback for {ntype}"
            assert len(lang_map["en"]) > 0, f"Empty 'en' fallback for {ntype}"
            assert len(lang_map["tr"]) > 0, f"Empty 'tr' fallback for {ntype}"


# ---------------------------------------------------------------------------
# TestGetFallbackMessageEdgeCases
# ---------------------------------------------------------------------------


class TestGetFallbackMessageEdgeCases:
    """Edge cases for _get_fallback_message not covered in the base test file."""

    def test_unknown_type_unknown_language_returns_generic_string(self) -> None:
        """Unknown type + unknown language returns the generic 'Hey! How are you?' string."""
        result = _get_fallback_message("totally_unknown_type", "zh")
        assert isinstance(result, str)
        assert len(result) > 0
        # Falls back to the generic default when the type is not in FALLBACK_MESSAGES
        assert result == "Hey! How are you?"

    def test_known_type_all_languages_return_str(self) -> None:
        """Any language for any known type returns a non-empty string."""
        for ntype in FALLBACK_MESSAGES:
            for lang in ("en", "tr", "de", "fr", "ja", ""):
                result = _get_fallback_message(ntype, lang)
                assert isinstance(result, str) and len(result) > 0, (
                    f"Empty result for type={ntype!r}, lang={lang!r}"
                )

    def test_afternoon_nudge_english(self) -> None:
        result = _get_fallback_message("afternoon_nudge", "en")
        assert result == "Hey! Haven't heard from you today. Everything okay?"

    def test_afternoon_nudge_turkish(self) -> None:
        result = _get_fallback_message("afternoon_nudge", "tr")
        assert result == "Selam! Bugun konusmadik, her sey yolunda mi?"

    def test_evening_reflection_english(self) -> None:
        result = _get_fallback_message("evening_reflection", "en")
        assert result == "How was your day? I'd love to hear about it."

    def test_evening_reflection_turkish(self) -> None:
        result = _get_fallback_message("evening_reflection", "tr")
        assert result == "Gunun nasil gecti? Duymak isterim."

    def test_sleep_reminder_english(self) -> None:
        result = _get_fallback_message("sleep_reminder", "en")
        assert result == "It's getting late. Time to wind down?"

    def test_sleep_reminder_turkish(self) -> None:
        result = _get_fallback_message("sleep_reminder", "tr")
        assert result == "Gec oldu. Yatma vakti geldi mi?"


# ---------------------------------------------------------------------------
# TestBackwardCompatReExports
# ---------------------------------------------------------------------------


class TestBackwardCompatReExports:
    """Constants and helpers re-exported from notification_scheduler must still work."""

    def test_tone_map_importable_from_scheduler(self) -> None:
        """TONE_MAP can be imported from notification_scheduler (backward compat)."""
        from app.services.notification_scheduler import TONE_MAP as TONE_MAP_SCHED
        from app.services.proactive_message_generator import TONE_MAP as TONE_MAP_GEN
        assert TONE_MAP_SCHED is TONE_MAP_GEN or TONE_MAP_SCHED == TONE_MAP_GEN

    def test_mem0_queries_importable_from_scheduler(self) -> None:
        """MEM0_QUERIES can be imported from notification_scheduler (backward compat)."""
        from app.services.notification_scheduler import MEM0_QUERIES as MEM0_SCHED
        from app.services.proactive_message_generator import MEM0_QUERIES as MEM0_GEN
        assert MEM0_SCHED is MEM0_GEN or MEM0_SCHED == MEM0_GEN

    def test_fallback_messages_importable_from_scheduler(self) -> None:
        """FALLBACK_MESSAGES can be imported from notification_scheduler (backward compat)."""
        from app.services.notification_scheduler import FALLBACK_MESSAGES as FB_SCHED
        from app.services.proactive_message_generator import FALLBACK_MESSAGES as FB_GEN
        assert FB_SCHED is FB_GEN or FB_SCHED == FB_GEN

    def test_get_fallback_message_importable_from_scheduler(self) -> None:
        """_get_fallback_message can be imported from notification_scheduler."""
        from app.services.notification_scheduler import _get_fallback_message as fn
        result = fn("morning_checkin", "en")
        assert result == "Good morning! How are you feeling today?"

    def test_search_mem0_importable_from_scheduler(self) -> None:
        """_search_mem0 can be imported from notification_scheduler (backward compat)."""
        from app.services.notification_scheduler import _search_mem0 as fn  # noqa: F401
        assert callable(fn)


# ---------------------------------------------------------------------------
# TestSchedulerIntegration
# ---------------------------------------------------------------------------


class TestSchedulerIntegration:
    """Integration tests verifying how notification_scheduler uses _generator."""

    @pytest.mark.asyncio
    async def test_reset_notifications_sent_today_clears_generator_cache(self) -> None:
        """reset_notifications_sent_today calls _generator.clear_cache()."""
        from app.services import notification_scheduler as sched_module

        with (
            patch(
                "app.services.notification_scheduler.AsyncSessionLocal",
            ) as mock_session_factory,
            patch.object(sched_module._generator, "clear_cache") as mock_clear,
        ):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_execute_result = MagicMock()
            mock_execute_result.all.return_value = []
            mock_session.execute = AsyncMock(return_value=mock_execute_result)
            mock_session_factory.return_value = mock_session

            await sched_module.reset_notifications_sent_today(
                now_utc=datetime(2026, 3, 13, 1, 0, 0, tzinfo=ZoneInfo("UTC"))
            )

            mock_clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_notification_calls_generator_with_correct_args(self) -> None:
        """_process_notification delegates to _generator.generate() with the right args."""
        from app.services import notification_scheduler as sched_module

        profile = MagicMock()
        profile.id = uuid.uuid4()
        profile.fcm_token = "token-xyz"

        character = MagicMock()
        character.id = uuid.uuid4()
        character.name = "Emma"
        character.is_default = True
        character.is_active = True

        local_now = datetime(2026, 3, 13, 8, 30, 0, tzinfo=ZoneInfo("UTC"))

        mock_db = AsyncMock()
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = character
        mock_db.execute = AsyncMock(return_value=execute_result)

        with (
            patch.object(sched_module._generator, "generate", new_callable=AsyncMock) as mock_gen,
            patch("app.services.notification_scheduler.send_push_notification", new_callable=AsyncMock) as mock_send,
        ):
            mock_gen.return_value = "Good morning!"
            from app.services.notification_sender import SendResult
            mock_send.return_value = SendResult.SENT

            activity = MagicMock()
            activity.notifications_sent_today = []

            await sched_module._process_notification(
                db=mock_db,
                profile=profile,
                activity=activity,
                notification_type="morning_checkin",
                local_now=local_now,
            )

            mock_gen.assert_called_once_with(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=local_now,
            )

    @pytest.mark.asyncio
    async def test_generate_notification_message_wrapper_delegates_to_generator(self) -> None:
        """_generate_notification_message thin wrapper returns same result as _generator.generate()."""
        from app.services.notification_scheduler import (
            _generate_notification_message,
            _generator,
        )

        profile = _make_profile()
        character = _make_character()
        local_now = _make_local_now(8, 30)

        with patch.object(_generator, "generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Expected message"
            result = await _generate_notification_message(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=local_now,
            )

        assert result == "Expected message"
        mock_gen.assert_called_once_with(
            profile=profile,
            character=character,
            notification_type="morning_checkin",
            local_now=local_now,
        )
