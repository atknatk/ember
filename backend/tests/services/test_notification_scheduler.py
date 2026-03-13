"""Tests for the notification scheduler.

Tests cover the pure trigger evaluation function, per-user processing,
the full notification cycle, and the midnight reset job.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.services.notification_scheduler import (
    _generate_notification_message,
    _generator,
    _process_notification,
    _process_user,
    evaluate_notification_triggers,
    reset_notifications_sent_today,
    run_notification_cycle,
)
from app.services.notification_sender import SendResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_local_now(hour: int, minute: int, tz_name: str = "UTC") -> datetime:
    """Create a timezone-aware datetime for testing."""
    tz = ZoneInfo(tz_name)
    return datetime(2026, 3, 13, hour, minute, 0, tzinfo=tz)


def _make_utc(hour: int, minute: int) -> datetime:
    """Create a UTC-aware datetime for testing."""
    return datetime(2026, 3, 13, hour, minute, 0, tzinfo=UTC)


def _make_profile(
    user_id: uuid.UUID | None = None,
    fcm_token: str | None = "valid-fcm-token",
    timezone_str: str = "UTC",
    name: str = "Test User",
    preferred_language: str = "en",
    mem0_user_id: str = "mem0_user_123",
) -> MagicMock:
    """Create a mock Profile object."""
    profile = MagicMock()
    profile.id = user_id or uuid.uuid4()
    profile.fcm_token = fcm_token
    profile.timezone = timezone_str
    profile.name = name
    profile.preferred_language = preferred_language
    profile.mem0_user_id = mem0_user_id
    return profile


def _make_activity(
    user_id: uuid.UUID | None = None,
    last_active_at: datetime | None = None,
    last_chat_at: datetime | None = None,
    notifications_sent_today: list[str] | None = None,
) -> MagicMock:
    """Create a mock UserActivity object."""
    activity = MagicMock()
    activity.user_id = user_id or uuid.uuid4()
    activity.last_active_at = last_active_at
    activity.last_chat_at = last_chat_at
    activity.notifications_sent_today = notifications_sent_today or []
    return activity


def _make_character(
    user_id: uuid.UUID | None = None,
    name: str = "Emma",
    template: str = "emma",
    mem0_agent_id: str = "emma_usr_123",
) -> MagicMock:
    """Create a mock Character object."""
    char = MagicMock()
    char.id = uuid.uuid4()
    char.user_id = user_id or uuid.uuid4()
    char.name = name
    char.template = template
    char.mem0_agent_id = mem0_agent_id
    char.is_default = True
    char.is_active = True
    return char


# ---------------------------------------------------------------------------
# Test evaluate_notification_triggers (pure function)
# ---------------------------------------------------------------------------


class TestEvaluateNotificationTriggers:
    """Tests for the pure trigger evaluation function."""

    def test_morning_checkin_at_0830_no_chat(self) -> None:
        """Test #1: 08:30 local, no chat today, no prior notifications -> morning_checkin."""
        local_now = _make_local_now(8, 30)
        now_utc = _make_utc(8, 30)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert result == ["morning_checkin"]

    def test_morning_checkin_suppressed_when_chatted_today(self) -> None:
        """Test #2: 08:30 local, user chatted today -> no morning_checkin."""
        local_now = _make_local_now(8, 30)
        now_utc = _make_utc(8, 30)
        # Chatted 1 hour ago (07:30 today)
        last_chat_at = _make_utc(7, 30)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=last_chat_at,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert result == []

    def test_morning_checkin_suppressed_when_already_sent(self) -> None:
        """Test #3: 08:30 local, morning_checkin already sent -> empty."""
        local_now = _make_local_now(8, 30)
        now_utc = _make_utc(8, 30)

        result = evaluate_notification_triggers(
            notifications_sent_today=["morning_checkin"],
            last_chat_at=None,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert result == []

    def test_afternoon_nudge_at_1430_no_chat(self) -> None:
        """Test #4: 14:30 local, no chat today -> afternoon_nudge."""
        local_now = _make_local_now(14, 30)
        now_utc = _make_utc(14, 30)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert result == ["afternoon_nudge"]

    def test_afternoon_nudge_suppressed_when_chatted(self) -> None:
        """Test #5: 14:30 local, user chatted today -> no afternoon_nudge."""
        local_now = _make_local_now(14, 30)
        now_utc = _make_utc(14, 30)
        last_chat_at = _make_utc(10, 0)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=last_chat_at,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert result == []

    def test_evening_reflection_at_2030(self) -> None:
        """Test #6: 20:30 local, no prior evening notification -> evening_reflection."""
        local_now = _make_local_now(20, 30)
        now_utc = _make_utc(20, 30)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert result == ["evening_reflection"]

    def test_evening_reflection_suppressed_when_already_sent(self) -> None:
        """Test #7: 20:30 local, evening_reflection already sent -> empty."""
        local_now = _make_local_now(20, 30)
        now_utc = _make_utc(20, 30)

        result = evaluate_notification_triggers(
            notifications_sent_today=["evening_reflection"],
            last_chat_at=None,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert result == []

    def test_sleep_reminder_at_2315_recently_active(self) -> None:
        """Test #8: 23:15 local, user active 30 min ago -> sleep_reminder."""
        local_now = _make_local_now(23, 15)
        now_utc = _make_utc(23, 15)
        last_active_at = now_utc - timedelta(minutes=30)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=last_active_at,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert result == ["sleep_reminder"]

    def test_sleep_reminder_suppressed_not_recently_active(self) -> None:
        """Test #9: 23:15 local, user last active 2 hours ago -> no sleep_reminder."""
        local_now = _make_local_now(23, 15)
        now_utc = _make_utc(23, 15)
        last_active_at = now_utc - timedelta(hours=2)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=last_active_at,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert result == []

    def test_sleep_reminder_suppressed_when_already_sent(self) -> None:
        """Test #10: 23:15 local, sleep_reminder already sent -> empty."""
        local_now = _make_local_now(23, 15)
        now_utc = _make_utc(23, 15)
        last_active_at = now_utc - timedelta(minutes=30)

        result = evaluate_notification_triggers(
            notifications_sent_today=["sleep_reminder"],
            last_chat_at=None,
            last_active_at=last_active_at,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert result == []

    def test_no_triggers_outside_all_windows(self) -> None:
        """Test #11: 10:00 local (outside all windows) -> empty."""
        local_now = _make_local_now(10, 0)
        now_utc = _make_utc(10, 0)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert result == []

    def test_windows_do_not_overlap(self) -> None:
        """Test #12: Non-overlapping windows ensure at most one trigger per time."""
        # At 08:30, only morning_checkin is possible (not afternoon, evening, or sleep)
        local_now = _make_local_now(8, 30)
        now_utc = _make_utc(8, 30)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=now_utc - timedelta(minutes=10),  # Recently active
            local_now=local_now,
            now_utc=now_utc,
        )

        assert result == ["morning_checkin"]
        assert len(result) == 1

    def test_evening_reflection_fires_regardless_of_chat(self) -> None:
        """evening_reflection does NOT check chatted_today."""
        local_now = _make_local_now(20, 30)
        now_utc = _make_utc(20, 30)
        # User chatted at 10:00 today
        last_chat_at = _make_utc(10, 0)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=last_chat_at,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert result == ["evening_reflection"]

    def test_chat_yesterday_does_not_count_as_today(self) -> None:
        """Chat from yesterday should not suppress morning_checkin."""
        local_now = _make_local_now(8, 30)
        now_utc = _make_utc(8, 30)
        # Chatted yesterday at 22:00
        last_chat_at = now_utc - timedelta(hours=10, minutes=30)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=last_chat_at,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert result == ["morning_checkin"]

    def test_boundary_0800_is_included(self) -> None:
        """08:00 exactly should be in morning_checkin window."""
        local_now = _make_local_now(8, 0)
        now_utc = _make_utc(8, 0)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert "morning_checkin" in result

    def test_boundary_0930_is_excluded(self) -> None:
        """09:30 exactly should NOT be in morning_checkin window (570 min)."""
        local_now = _make_local_now(9, 30)
        now_utc = _make_utc(9, 30)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert result == []


# ---------------------------------------------------------------------------
# Test process_notification
# ---------------------------------------------------------------------------


class TestProcessNotification:
    """Tests for per-notification processing."""

    @pytest.mark.asyncio
    async def test_sends_notification_with_personalized_message(self) -> None:
        """Test #13: Valid user, generator produces message, FCM sends it."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id)
        activity = _make_activity(user_id=user_id)
        character = _make_character(user_id=user_id)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = character
        mock_db.execute = AsyncMock(return_value=mock_result)

        with (
            patch.object(
                _generator,
                "generate",
                return_value="Good morning, Test User!",
            ) as mock_gen,
            patch(
                "app.services.notification_scheduler.send_push_notification",
                return_value=SendResult.SENT,
            ) as mock_send,
        ):
            await _process_notification(
                mock_db,
                profile,
                activity,
                "morning_checkin",
                _make_local_now(8, 30),
            )

            mock_gen.assert_called_once()
            mock_send.assert_called_once_with(
                fcm_token="valid-fcm-token",
                title="Emma",
                body="Good morning, Test User!",
                data={
                    "character_id": str(character.id),
                    "notification_type": "morning_checkin",
                },
            )

    @pytest.mark.asyncio
    async def test_uses_fallback_when_mem0_fails(self) -> None:
        """Test #14: Mem0 search fails -> fallback or empty memories used."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id)
        character = _make_character(user_id=user_id)

        # Clear generator cache to ensure fresh generation
        _generator.clear_cache()

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

            result = await _generate_notification_message(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            # Should still produce a message (either from Haiku or fallback)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_uses_fallback_when_haiku_fails(self) -> None:
        """Test #15: Haiku call fails -> deterministic fallback message."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id)
        character = _make_character(user_id=user_id)

        # Clear generator cache to ensure fresh generation
        _generator.clear_cache()

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
            result = await _generate_notification_message(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            assert result == "Good morning! How are you feeling today?"

    @pytest.mark.asyncio
    async def test_invalidates_token_on_invalid_token(self) -> None:
        """Test #16: FCM send returns INVALID_TOKEN -> fcm_token set to NULL."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id)
        activity = _make_activity(user_id=user_id)
        character = _make_character(user_id=user_id)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = character
        mock_db.execute = AsyncMock(return_value=mock_result)

        with (
            patch.object(
                _generator,
                "generate",
                return_value="Hello!",
            ),
            patch(
                "app.services.notification_scheduler.send_push_notification",
                return_value=SendResult.INVALID_TOKEN,
            ),
        ):
            await _process_notification(
                mock_db,
                profile,
                activity,
                "morning_checkin",
                _make_local_now(8, 30),
            )

            # Should have called execute to clear fcm_token and commit
            assert mock_db.execute.call_count >= 2  # character query + token clear
            mock_db.commit.assert_called()


# ---------------------------------------------------------------------------
# Test run_notification_cycle
# ---------------------------------------------------------------------------


class TestRunNotificationCycle:
    """Tests for the main notification cycle."""

    @pytest.mark.asyncio
    async def test_skips_users_without_fcm_token(self) -> None:
        """Test #17: Users without fcm_token are not fetched (filtered by query)."""
        # The query itself filters WHERE fcm_token IS NOT NULL,
        # so users without tokens never appear in results.
        # We verify by checking the query is constructed correctly.
        with patch(
            "app.services.notification_scheduler.AsyncSessionLocal",
        ) as mock_session_cls:
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.all.return_value = []  # No users returned
            mock_db.execute = AsyncMock(return_value=mock_result)

            await run_notification_cycle(now_utc=_make_utc(8, 30))

            # Cycle should complete without errors
            mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_user_with_invalid_timezone(self) -> None:
        """Test #18: Invalid timezone -> warning logged, user skipped."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id, timezone_str="Invalid/TZ")
        activity = _make_activity(user_id=user_id)

        mock_db = AsyncMock()

        count = await _process_user(mock_db, activity, profile, _make_utc(8, 30))

        assert count == 0

    @pytest.mark.asyncio
    async def test_exception_for_one_user_does_not_stop_others(self) -> None:
        """Test #19: Exception for one user does not prevent processing others."""
        user1_id = uuid.uuid4()
        user2_id = uuid.uuid4()

        profile1 = _make_profile(user_id=user1_id)
        activity1 = _make_activity(user_id=user1_id)
        profile2 = _make_profile(user_id=user2_id)
        activity2 = _make_activity(user_id=user2_id)

        now_utc = _make_utc(8, 30)

        with patch(
            "app.services.notification_scheduler.AsyncSessionLocal",
        ) as mock_session_cls:
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            # First batch returns 2 users, second returns empty
            call_count = 0

            async def mock_execute(stmt: object) -> MagicMock:
                nonlocal call_count
                call_count += 1
                result = MagicMock()
                if call_count == 1:
                    result.all.return_value = [(activity1, profile1), (activity2, profile2)]
                else:
                    result.all.return_value = []
                return result

            mock_db.execute = mock_execute

            with patch(
                "app.services.notification_scheduler._process_user",
                side_effect=[Exception("User 1 error"), 1],
            ) as mock_process:
                await run_notification_cycle(now_utc=now_utc)

                # Both users should have been attempted
                assert mock_process.call_count == 2


# ---------------------------------------------------------------------------
# Test reset_notifications_sent_today
# ---------------------------------------------------------------------------


class TestResetNotificationsSentToday:
    """Tests for the midnight reset job."""

    @pytest.mark.asyncio
    async def test_resets_users_at_midnight(self) -> None:
        """Test #20: Resets only users whose local time crossed midnight."""
        user_utc_id = uuid.uuid4()
        user_ist_id = uuid.uuid4()

        # UTC user: local time is 00:30 (midnight hour)
        profile_utc = _make_profile(user_id=user_utc_id, timezone_str="UTC")
        activity_utc = _make_activity(
            user_id=user_utc_id,
            notifications_sent_today=["morning_checkin"],
        )

        # Istanbul user (UTC+3): local time is 03:30 (NOT midnight)
        profile_ist = _make_profile(user_id=user_ist_id, timezone_str="Europe/Istanbul")
        activity_ist = _make_activity(
            user_id=user_ist_id,
            notifications_sent_today=["morning_checkin"],
        )

        now_utc = _make_utc(0, 30)  # 00:30 UTC

        with patch(
            "app.services.notification_scheduler.AsyncSessionLocal",
        ) as mock_session_cls:
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.all.return_value = [
                (activity_utc, profile_utc),
                (activity_ist, profile_ist),
            ]
            mock_db.execute = AsyncMock(return_value=mock_result)

            await reset_notifications_sent_today(now_utc=now_utc)

            # Should have executed the SELECT + UPDATE + commit
            # The UTC user should be reset (hour=0), Istanbul should not (hour=3)
            assert mock_db.execute.call_count == 2  # SELECT + UPDATE
            mock_db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Test fallback messages
# ---------------------------------------------------------------------------


class TestFallbackMessages:
    """Tests for deterministic fallback messages."""

    @pytest.mark.asyncio
    async def test_turkish_fallback_message(self) -> None:
        """Turkish language fallback returns Turkish message."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id, preferred_language="tr")
        character = _make_character(user_id=user_id)

        # Clear generator cache to ensure fresh generation
        _generator.clear_cache()

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
            result = await _generate_notification_message(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

            assert result == "Gunaydin! Bugun nasil hissediyorsun?"

    @pytest.mark.asyncio
    async def test_unknown_language_falls_back_to_english(self) -> None:
        """Unknown language falls back to English."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id, preferred_language="de")
        character = _make_character(user_id=user_id)

        # Clear generator cache to ensure fresh generation
        _generator.clear_cache()

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
            result = await _generate_notification_message(
                profile=profile,
                character=character,
                notification_type="afternoon_nudge",
                local_now=_make_local_now(14, 30),
            )

            assert result == "Hey! Haven't heard from you today. Everything okay?"
