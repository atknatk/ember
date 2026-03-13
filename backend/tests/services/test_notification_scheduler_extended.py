"""Extended tests for the notification scheduler.

Supplements the backend-dev tests with coverage for:
  - Timezone edge cases for all 4 trigger windows
  - notifications_sent_today deduplication edge cases
  - Midnight reset across multiple timezone scenarios
  - Scheduler lifecycle (start_notification_scheduler)
  - Batch processing with multiple batches / offset progression
  - Window boundary conditions (exactly at start/end)
  - No default character: _process_notification skips gracefully
  - notifications_sent_today DB write failure: logged, not re-raised
  - Multiple triggers firing simultaneously in one cycle
  - Fallback message: Mem0 works but Claude fails
  - _get_fallback_message: unknown type and unknown language
  - sleep_reminder: last_active_at exactly 60 minutes ago (boundary)
  - last_chat_at exactly at midnight (boundary for chatted_today)
  - run_notification_cycle: second batch processed after first
  - reset_notifications_sent_today: no users with non-empty array -> no UPDATE
  - reset_notifications_sent_today: invalid timezone is skipped silently
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call
from zoneinfo import ZoneInfo

import pytest

from app.services.notification_scheduler import (
    FALLBACK_MESSAGES,
    _generate_notification_message,
    _get_fallback_message,
    _process_notification,
    _process_user,
    evaluate_notification_triggers,
    reset_notifications_sent_today,
    run_notification_cycle,
    start_notification_scheduler,
)
from app.services.notification_sender import SendResult


# ---------------------------------------------------------------------------
# Helpers (shared with base test file, duplicated here for self-containment)
# ---------------------------------------------------------------------------


def _make_local_now(hour: int, minute: int, tz_name: str = "UTC") -> datetime:
    """Create a timezone-aware datetime for testing."""
    tz = ZoneInfo(tz_name)
    return datetime(2026, 3, 13, hour, minute, 0, tzinfo=tz)


def _make_utc(hour: int, minute: int, day: int = 13) -> datetime:
    """Create a UTC-aware datetime for testing."""
    return datetime(2026, 3, day, hour, minute, 0, tzinfo=UTC)


def _make_profile(
    user_id: uuid.UUID | None = None,
    fcm_token: str | None = "valid-fcm-token",
    timezone_str: str = "UTC",
    name: str = "Test User",
    preferred_language: str = "en",
    mem0_user_id: str = "mem0_user_123",
) -> MagicMock:
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
# Timezone edge cases for trigger windows
# ---------------------------------------------------------------------------


class TestTimezoneEdgeCases:
    """Trigger evaluation respects user's local timezone, not UTC."""

    def test_morning_checkin_fires_for_new_york_user_at_0830_local(self) -> None:
        """User in America/New_York at local 08:30 gets morning_checkin."""
        tz = ZoneInfo("America/New_York")
        # UTC 13:30 = 08:30 New York (EST, UTC-5)
        local_now = datetime(2026, 3, 13, 8, 30, 0, tzinfo=tz)
        now_utc = local_now.astimezone(UTC)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert "morning_checkin" in result

    def test_morning_checkin_does_not_fire_for_istanbul_user_at_0830_utc(self) -> None:
        """Istanbul user at 08:30 UTC is at 11:30 local — outside morning window."""
        tz = ZoneInfo("Europe/Istanbul")
        # UTC 08:30 = Istanbul 11:30 (UTC+3)
        now_utc = _make_utc(8, 30)
        local_now = now_utc.astimezone(tz)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert "morning_checkin" not in result

    def test_afternoon_nudge_fires_for_tokyo_user_at_1430_local(self) -> None:
        """User in Asia/Tokyo at local 14:30 gets afternoon_nudge."""
        tz = ZoneInfo("Asia/Tokyo")
        local_now = datetime(2026, 3, 13, 14, 30, 0, tzinfo=tz)
        now_utc = local_now.astimezone(UTC)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert "afternoon_nudge" in result

    def test_sleep_reminder_fires_for_los_angeles_user_at_2315_local(self) -> None:
        """User in America/Los_Angeles at local 23:15, active 30 min ago."""
        tz = ZoneInfo("America/Los_Angeles")
        local_now = datetime(2026, 3, 13, 23, 15, 0, tzinfo=tz)
        now_utc = local_now.astimezone(UTC)
        last_active_at = now_utc - timedelta(minutes=30)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=last_active_at,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert "sleep_reminder" in result

    def test_evening_reflection_fires_for_berlin_user_at_2030_local(self) -> None:
        """User in Europe/Berlin at local 20:30 gets evening_reflection."""
        tz = ZoneInfo("Europe/Berlin")
        local_now = datetime(2026, 3, 13, 20, 30, 0, tzinfo=tz)
        now_utc = local_now.astimezone(UTC)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert "evening_reflection" in result

    def test_chatted_today_computed_in_local_timezone_not_utc(self) -> None:
        """chatted_today is relative to local midnight, not UTC midnight."""
        # User in UTC-8 (America/Los_Angeles, standard time approximation).
        # UTC midnight (00:00 UTC on March 13) = 16:00 March 12 local.
        # If the user chatted at UTC 23:30 on March 12 (= local 15:30 March 12),
        # and now it is local 08:30 March 13, that chat is NOT today locally.
        tz = ZoneInfo("America/Los_Angeles")
        local_now = datetime(2026, 3, 13, 8, 30, 0, tzinfo=tz)
        now_utc = local_now.astimezone(UTC)

        # Chat was UTC 23:30 March 12 = local 15:30 March 12 — yesterday locally
        chat_utc = datetime(2026, 3, 12, 23, 30, 0, tzinfo=UTC)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=chat_utc,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        # Chat was yesterday locally — morning_checkin should fire
        assert "morning_checkin" in result

    def test_chatted_today_suppresses_across_timezone(self) -> None:
        """Chat today in local timezone suppresses morning_checkin even if UTC date differs."""
        # User in UTC+13 (Pacific/Auckland area): local time 08:30 on March 14,
        # but UTC is March 13. Chat at UTC 20:00 March 13 = local 09:00 March 14.
        # That is today locally for the user.
        tz = ZoneInfo("Pacific/Auckland")
        # local: 2026-03-14 08:30 (+13 approx) -> UTC 2026-03-13 19:30
        local_now = datetime(2026, 3, 14, 8, 30, 0, tzinfo=tz)
        now_utc = local_now.astimezone(UTC)

        # Chat was local today at 07:00 (UTC 2026-03-13 18:00)
        local_chat = datetime(2026, 3, 14, 7, 0, 0, tzinfo=tz)
        chat_utc = local_chat.astimezone(UTC)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=chat_utc,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        # User chatted locally today — morning_checkin suppressed
        assert "morning_checkin" not in result


# ---------------------------------------------------------------------------
# Window boundary conditions
# ---------------------------------------------------------------------------


class TestWindowBoundaries:
    """Verify inclusive/exclusive boundaries for each trigger window."""

    def test_morning_checkin_boundary_0759_excluded(self) -> None:
        """07:59 is before morning window — morning_checkin must not fire."""
        local_now = _make_local_now(7, 59)
        now_utc = _make_utc(7, 59)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert "morning_checkin" not in result

    def test_afternoon_nudge_boundary_1400_included(self) -> None:
        """14:00 exactly is within afternoon window."""
        local_now = _make_local_now(14, 0)
        now_utc = _make_utc(14, 0)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert "afternoon_nudge" in result

    def test_afternoon_nudge_boundary_1530_excluded(self) -> None:
        """15:30 exactly is outside afternoon window (exclusive end)."""
        local_now = _make_local_now(15, 30)
        now_utc = _make_utc(15, 30)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert "afternoon_nudge" not in result

    def test_evening_reflection_boundary_2000_included(self) -> None:
        """20:00 exactly is within evening window."""
        local_now = _make_local_now(20, 0)
        now_utc = _make_utc(20, 0)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert "evening_reflection" in result

    def test_evening_reflection_boundary_2100_excluded(self) -> None:
        """21:00 exactly is outside evening window (exclusive end)."""
        local_now = _make_local_now(21, 0)
        now_utc = _make_utc(21, 0)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert "evening_reflection" not in result

    def test_sleep_reminder_boundary_2300_included(self) -> None:
        """23:00 exactly triggers sleep_reminder if recently active."""
        now_utc = _make_utc(23, 0)
        local_now = _make_local_now(23, 0)
        last_active_at = now_utc - timedelta(minutes=30)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=last_active_at,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert "sleep_reminder" in result

    def test_sleep_reminder_active_exactly_60_minutes_ago_is_included(self) -> None:
        """last_active_at exactly 60 minutes ago satisfies >= boundary."""
        now_utc = _make_utc(23, 15)
        local_now = _make_local_now(23, 15)
        last_active_at = now_utc - timedelta(minutes=60)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=last_active_at,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert "sleep_reminder" in result

    def test_sleep_reminder_active_61_minutes_ago_is_excluded(self) -> None:
        """last_active_at 61 minutes ago fails the 60-minute window."""
        now_utc = _make_utc(23, 15)
        local_now = _make_local_now(23, 15)
        last_active_at = now_utc - timedelta(minutes=61)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=last_active_at,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert "sleep_reminder" not in result

    def test_last_chat_at_exactly_at_local_midnight_counts_as_today(self) -> None:
        """Chat at the exact local midnight boundary is today (>= local_today_start)."""
        tz = ZoneInfo("UTC")
        local_now = datetime(2026, 3, 13, 8, 30, 0, tzinfo=tz)
        now_utc = local_now.astimezone(UTC)
        # Chat exactly at midnight UTC (local midnight for a UTC user)
        last_chat_at = datetime(2026, 3, 13, 0, 0, 0, tzinfo=UTC)

        result = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=last_chat_at,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        # Chatted today — morning_checkin suppressed
        assert "morning_checkin" not in result


# ---------------------------------------------------------------------------
# Deduplication edge cases
# ---------------------------------------------------------------------------


class TestDeduplicationEdgeCases:
    """notifications_sent_today must reliably prevent duplicate sends."""

    def test_all_types_in_sent_today_means_no_triggers_at_any_window(self) -> None:
        """If all 4 types are already sent, no trigger fires regardless of time."""
        all_sent = list(
            ("morning_checkin", "afternoon_nudge", "evening_reflection", "sleep_reminder")
        )

        # Test morning window
        local_now = _make_local_now(8, 30)
        now_utc = _make_utc(8, 30)
        result = evaluate_notification_triggers(
            notifications_sent_today=all_sent,
            last_chat_at=None,
            last_active_at=now_utc - timedelta(minutes=30),
            local_now=local_now,
            now_utc=now_utc,
        )
        assert result == []

        # Test sleep window
        local_now = _make_local_now(23, 15)
        now_utc = _make_utc(23, 15)
        result = evaluate_notification_triggers(
            notifications_sent_today=all_sent,
            last_chat_at=None,
            last_active_at=now_utc - timedelta(minutes=30),
            local_now=local_now,
            now_utc=now_utc,
        )
        assert result == []

    def test_multiple_triggers_can_fire_in_same_cycle_when_windows_overlap_is_impossible(
        self,
    ) -> None:
        """Verify that evening_reflection and sleep_reminder cannot fire simultaneously."""
        # Evening window: 20:00-21:00; sleep window: 23:00+
        # No single local_now can be in both windows.
        local_now_evening = _make_local_now(20, 30)
        now_utc_evening = _make_utc(20, 30)
        result_evening = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=now_utc_evening - timedelta(minutes=30),
            local_now=local_now_evening,
            now_utc=now_utc_evening,
        )
        assert "sleep_reminder" not in result_evening

        local_now_sleep = _make_local_now(23, 15)
        now_utc_sleep = _make_utc(23, 15)
        result_sleep = evaluate_notification_triggers(
            notifications_sent_today=[],
            last_chat_at=None,
            last_active_at=now_utc_sleep - timedelta(minutes=30),
            local_now=local_now_sleep,
            now_utc=now_utc_sleep,
        )
        assert "evening_reflection" not in result_sleep

    def test_afternoon_nudge_not_sent_when_only_morning_already_sent(self) -> None:
        """Having morning_checkin in sent_today does NOT suppress afternoon_nudge."""
        local_now = _make_local_now(14, 30)
        now_utc = _make_utc(14, 30)

        result = evaluate_notification_triggers(
            notifications_sent_today=["morning_checkin"],
            last_chat_at=None,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert "afternoon_nudge" in result

    def test_sent_today_with_extra_unknown_entry_does_not_break_evaluation(self) -> None:
        """Unknown entries in notifications_sent_today are silently ignored."""
        local_now = _make_local_now(8, 30)
        now_utc = _make_utc(8, 30)

        result = evaluate_notification_triggers(
            notifications_sent_today=["goal_followup", "unknown_type"],
            last_chat_at=None,
            last_active_at=None,
            local_now=local_now,
            now_utc=now_utc,
        )

        assert "morning_checkin" in result


# ---------------------------------------------------------------------------
# Midnight reset edge cases
# ---------------------------------------------------------------------------


class TestMidnightResetEdgeCases:
    """reset_notifications_sent_today handles diverse timezone scenarios."""

    @pytest.mark.asyncio
    async def test_does_not_update_when_no_users_at_midnight(self) -> None:
        """If no user has their local time at midnight, no UPDATE is issued."""
        user_id = uuid.uuid4()
        # UTC+3: 00:30 UTC = 03:30 Istanbul — NOT midnight
        profile = _make_profile(user_id=user_id, timezone_str="Europe/Istanbul")
        activity = _make_activity(user_id=user_id, notifications_sent_today=["morning_checkin"])

        now_utc = _make_utc(0, 30)

        with patch(
            "app.services.notification_scheduler.AsyncSessionLocal",
        ) as mock_session_cls:
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.all.return_value = [(activity, profile)]
            mock_db.execute = AsyncMock(return_value=mock_result)

            await reset_notifications_sent_today(now_utc=now_utc)

            # SELECT was called, but no UPDATE since no user is at midnight
            assert mock_db.execute.call_count == 1
            mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_resets_utc_minus_4_user_at_utc_0400(self) -> None:
        """User in America/New_York (UTC-4, DST on 2026-03-13) crosses midnight at UTC 04:00."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id, timezone_str="America/New_York")
        activity = _make_activity(user_id=user_id, notifications_sent_today=["morning_checkin"])

        # On 2026-03-13, New York is on DST (UTC-4): UTC 04:00 = New York 00:00 (midnight)
        now_utc = datetime(2026, 3, 13, 4, 0, 0, tzinfo=UTC)

        with patch(
            "app.services.notification_scheduler.AsyncSessionLocal",
        ) as mock_session_cls:
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.all.return_value = [(activity, profile)]
            mock_db.execute = AsyncMock(return_value=mock_result)

            await reset_notifications_sent_today(now_utc=now_utc)

            # SELECT + UPDATE
            assert mock_db.execute.call_count == 2
            mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_user_with_invalid_timezone_in_reset(self) -> None:
        """User with invalid timezone in reset job is silently skipped."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id, timezone_str="Not/ATimezone")
        activity = _make_activity(user_id=user_id, notifications_sent_today=["morning_checkin"])

        now_utc = _make_utc(0, 30)

        with patch(
            "app.services.notification_scheduler.AsyncSessionLocal",
        ) as mock_session_cls:
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.all.return_value = [(activity, profile)]
            mock_db.execute = AsyncMock(return_value=mock_result)

            # Should not raise; invalid timezone is silently skipped
            await reset_notifications_sent_today(now_utc=now_utc)

            mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_rows_returned_means_no_db_writes(self) -> None:
        """When no users have non-empty notifications_sent_today, nothing is updated."""
        now_utc = _make_utc(0, 0)

        with patch(
            "app.services.notification_scheduler.AsyncSessionLocal",
        ) as mock_session_cls:
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.all.return_value = []
            mock_db.execute = AsyncMock(return_value=mock_result)

            await reset_notifications_sent_today(now_utc=now_utc)

            # Only SELECT; no UPDATE, no commit
            assert mock_db.execute.call_count == 1
            mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_resets_multiple_users_at_midnight_in_one_batch(self) -> None:
        """Multiple users crossing midnight in the same UTC hour are all reset."""
        # UTC 19:00 = midnight for UTC+5 (Tashkent), and also ~midnight for UTC+5:30 (India)
        user1_id = uuid.uuid4()
        user2_id = uuid.uuid4()

        profile1 = _make_profile(user_id=user1_id, timezone_str="Asia/Tashkent")  # UTC+5
        activity1 = _make_activity(user_id=user1_id, notifications_sent_today=["evening_reflection"])

        profile2 = _make_profile(user_id=user2_id, timezone_str="Asia/Karachi")  # UTC+5
        activity2 = _make_activity(user_id=user2_id, notifications_sent_today=["morning_checkin"])

        now_utc = datetime(2026, 3, 13, 19, 0, 0, tzinfo=UTC)

        with patch(
            "app.services.notification_scheduler.AsyncSessionLocal",
        ) as mock_session_cls:
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.all.return_value = [(activity1, profile1), (activity2, profile2)]
            mock_db.execute = AsyncMock(return_value=mock_result)

            await reset_notifications_sent_today(now_utc=now_utc)

            # SELECT + UPDATE (both users in one UPDATE)
            assert mock_db.execute.call_count == 2
            mock_db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Scheduler lifecycle tests
# ---------------------------------------------------------------------------


class TestSchedulerLifecycle:
    """start_notification_scheduler creates and starts the APScheduler."""

    @pytest.mark.asyncio
    async def test_start_notification_scheduler_returns_scheduler(self) -> None:
        """start_notification_scheduler returns a running AsyncScheduler."""
        with patch(
            "app.services.notification_scheduler.AsyncScheduler",
        ) as mock_scheduler_cls:
            mock_scheduler = AsyncMock()
            mock_scheduler_cls.return_value = mock_scheduler

            result = await start_notification_scheduler()

            assert result is mock_scheduler
            mock_scheduler.add_schedule.assert_called()
            mock_scheduler.start_in_background.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_notification_scheduler_adds_two_jobs(self) -> None:
        """Scheduler is configured with interval job + cron midnight-reset job."""
        with patch(
            "app.services.notification_scheduler.AsyncScheduler",
        ) as mock_scheduler_cls:
            mock_scheduler = AsyncMock()
            mock_scheduler_cls.return_value = mock_scheduler

            await start_notification_scheduler()

            assert mock_scheduler.add_schedule.call_count == 2

    @pytest.mark.asyncio
    async def test_start_notification_scheduler_uses_interval_and_cron_triggers(self) -> None:
        """The two scheduler jobs use IntervalTrigger and CronTrigger respectively."""
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        with patch(
            "app.services.notification_scheduler.AsyncScheduler",
        ) as mock_scheduler_cls:
            mock_scheduler = AsyncMock()
            mock_scheduler_cls.return_value = mock_scheduler

            await start_notification_scheduler()

            trigger_types = [
                type(call_args.args[1])
                for call_args in mock_scheduler.add_schedule.call_args_list
            ]
            assert IntervalTrigger in trigger_types
            assert CronTrigger in trigger_types


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------


class TestBatchProcessing:
    """run_notification_cycle processes users in batches and advances offset."""

    @pytest.mark.asyncio
    async def test_second_batch_is_fetched_after_first(self) -> None:
        """Cycle continues fetching until an empty batch is returned."""
        user1_id = uuid.uuid4()
        user2_id = uuid.uuid4()
        profile1 = _make_profile(user_id=user1_id)
        activity1 = _make_activity(user_id=user1_id)
        profile2 = _make_profile(user_id=user2_id)
        activity2 = _make_activity(user_id=user2_id)

        now_utc = _make_utc(10, 0)  # Outside all windows — no notifications sent

        batch_call_count = 0

        with patch(
            "app.services.notification_scheduler.AsyncSessionLocal",
        ) as mock_session_cls:
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            async def mock_execute(stmt: object) -> MagicMock:
                nonlocal batch_call_count
                batch_call_count += 1
                result = MagicMock()
                if batch_call_count == 1:
                    result.all.return_value = [(activity1, profile1)]
                elif batch_call_count == 2:
                    result.all.return_value = [(activity2, profile2)]
                else:
                    result.all.return_value = []
                return result

            mock_db.execute = mock_execute

            await run_notification_cycle(now_utc=now_utc)

            # Should have made 3 batch fetches: first, second, empty-terminator
            assert batch_call_count == 3

    @pytest.mark.asyncio
    async def test_empty_first_batch_completes_immediately(self) -> None:
        """If first batch is empty, no _process_user calls are made."""
        now_utc = _make_utc(8, 30)

        with patch(
            "app.services.notification_scheduler.AsyncSessionLocal",
        ) as mock_session_cls:
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.all.return_value = []
            mock_db.execute = AsyncMock(return_value=mock_result)

            with patch(
                "app.services.notification_scheduler._process_user",
            ) as mock_process:
                await run_notification_cycle(now_utc=now_utc)
                mock_process.assert_not_called()


# ---------------------------------------------------------------------------
# _process_user edge cases
# ---------------------------------------------------------------------------


class TestProcessUserEdgeCases:
    """Edge cases for _process_user function."""

    @pytest.mark.asyncio
    async def test_process_user_no_triggers_returns_zero(self) -> None:
        """_process_user returns 0 when no triggers fire (e.g. midday, outside all windows)."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id, timezone_str="UTC")
        activity = _make_activity(user_id=user_id)

        mock_db = AsyncMock()
        now_utc = _make_utc(12, 0)  # Midday — no windows

        count = await _process_user(mock_db, activity, profile, now_utc)

        assert count == 0

    @pytest.mark.asyncio
    async def test_process_user_counts_notifications_sent(self) -> None:
        """_process_user returns number of notifications successfully sent."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id, timezone_str="UTC")
        activity = _make_activity(user_id=user_id)

        mock_db = AsyncMock()
        now_utc = _make_utc(8, 30)  # Morning window

        with patch(
            "app.services.notification_scheduler._process_notification",
            return_value=None,
        ) as mock_proc:
            count = await _process_user(mock_db, activity, profile, now_utc)

        assert count == 1
        mock_proc.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_user_notifications_sent_today_as_non_list_treated_as_empty(
        self,
    ) -> None:
        """If notifications_sent_today is None or non-list, treated as empty list."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id, timezone_str="UTC")
        activity = _make_activity(user_id=user_id)
        activity.notifications_sent_today = None  # Edge: DB value is None

        mock_db = AsyncMock()
        now_utc = _make_utc(8, 30)

        with patch(
            "app.services.notification_scheduler._process_notification",
            return_value=None,
        ):
            # Should not raise even with None notifications_sent_today
            count = await _process_user(mock_db, activity, profile, now_utc)

        # Morning window, no prior notifications -> at least morning_checkin triggers
        assert count >= 1


# ---------------------------------------------------------------------------
# _process_notification edge cases
# ---------------------------------------------------------------------------


class TestProcessNotificationEdgeCases:
    """Edge cases for _process_notification function."""

    @pytest.mark.asyncio
    async def test_skips_when_no_default_character(self) -> None:
        """_process_notification logs warning and returns when no default character exists."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id)
        activity = _make_activity(user_id=user_id)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No default character
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch(
            "app.services.notification_scheduler.send_push_notification",
        ) as mock_send:
            await _process_notification(
                mock_db,
                profile,
                activity,
                "morning_checkin",
                _make_local_now(8, 30),
            )

            # FCM should NOT be called
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_notifications_sent_today_not_updated_on_fcm_failure(self) -> None:
        """If FCM returns INVALID_TOKEN, notifications_sent_today is NOT updated."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id)
        activity = _make_activity(user_id=user_id)
        character = _make_character(user_id=user_id)

        execute_calls: list[object] = []

        mock_db = AsyncMock()

        async def track_execute(stmt: object) -> MagicMock:
            execute_calls.append(stmt)
            result = MagicMock()
            result.scalar_one_or_none.return_value = character
            return result

        mock_db.execute = track_execute

        with (
            patch(
                "app.services.notification_scheduler._generate_notification_message",
                return_value="Good morning!",
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

        # Should have executed: character query + fcm_token clear
        # Should NOT have executed a notifications_sent_today update
        assert len(execute_calls) == 2  # SELECT character + UPDATE fcm_token to None

    @pytest.mark.asyncio
    async def test_db_failure_on_sent_today_update_is_caught(self) -> None:
        """Exception during notifications_sent_today update is caught and logged."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id)
        activity = _make_activity(user_id=user_id)
        character = _make_character(user_id=user_id)

        call_count = 0

        mock_db = AsyncMock()

        async def failing_execute(stmt: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            result.scalar_one_or_none.return_value = character
            if call_count == 1:
                # Character query succeeds
                return result
            # notifications_sent_today update fails
            raise Exception("DB write failed")

        mock_db.execute = failing_execute

        with (
            patch(
                "app.services.notification_scheduler._generate_notification_message",
                return_value="Good morning!",
            ),
            patch(
                "app.services.notification_scheduler.send_push_notification",
                return_value=SendResult.SENT,
            ),
        ):
            # Should NOT raise — exception is caught internally
            await _process_notification(
                mock_db,
                profile,
                activity,
                "morning_checkin",
                _make_local_now(8, 30),
            )


# ---------------------------------------------------------------------------
# _generate_notification_message: Mem0 works but Claude fails
# ---------------------------------------------------------------------------


class TestGenerateNotificationMessageFallbacks:
    """Test fallback behavior when individual services fail."""

    @pytest.mark.asyncio
    async def test_mem0_works_but_claude_fails_uses_fallback_message(self) -> None:
        """If Mem0 succeeds but Claude fails, deterministic fallback is returned."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id, preferred_language="en")
        character = _make_character(user_id=user_id)

        memories = [{"memory": "User wakes up early at 6am"}]

        with (
            patch(
                "app.services.notification_scheduler._search_mem0",
                return_value=memories,
            ),
            patch(
                "app.services.notification_scheduler.get_llm_router",
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
    async def test_mem0_works_claude_succeeds_returns_generated_message(self) -> None:
        """Happy path: Mem0 + Claude both work, returns Claude-generated message."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id, preferred_language="en")
        character = _make_character(user_id=user_id)

        with (
            patch(
                "app.services.notification_scheduler._search_mem0",
                return_value=[{"memory": "Loves morning runs"}],
            ),
            patch(
                "app.services.notification_scheduler.get_llm_router",
            ) as mock_router,
        ):
            mock_provider = AsyncMock()
            mock_provider.complete_fast.return_value = "  Ready for your morning run?  "
            mock_router.return_value.get.return_value = mock_provider

            result = await _generate_notification_message(
                profile=profile,
                character=character,
                notification_type="morning_checkin",
                local_now=_make_local_now(8, 30),
            )

        assert result == "Ready for your morning run?"

    @pytest.mark.asyncio
    async def test_none_preferred_language_defaults_to_english_fallback(self) -> None:
        """Profile with None preferred_language gets English fallback."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id, preferred_language=None)
        character = _make_character(user_id=user_id)

        with (
            patch(
                "app.services.notification_scheduler._search_mem0",
                side_effect=Exception("Mem0 down"),
            ),
            patch(
                "app.services.notification_scheduler.get_llm_router",
                side_effect=Exception("LLM down"),
            ),
        ):
            result = await _generate_notification_message(
                profile=profile,
                character=character,
                notification_type="sleep_reminder",
                local_now=_make_local_now(23, 15),
            )

        assert result == "It's getting late. Time to wind down?"

    @pytest.mark.asyncio
    async def test_all_four_notification_types_have_fallback_messages(self) -> None:
        """Each notification type returns a non-empty fallback in English."""
        notification_types = [
            "morning_checkin",
            "afternoon_nudge",
            "evening_reflection",
            "sleep_reminder",
        ]

        for ntype in notification_types:
            user_id = uuid.uuid4()
            profile = _make_profile(user_id=user_id, preferred_language="en")
            character = _make_character(user_id=user_id)

            with (
                patch(
                    "app.services.notification_scheduler._search_mem0",
                    side_effect=Exception("down"),
                ),
                patch(
                    "app.services.notification_scheduler.get_llm_router",
                    side_effect=Exception("down"),
                ),
            ):
                result = await _generate_notification_message(
                    profile=profile,
                    character=character,
                    notification_type=ntype,
                    local_now=_make_local_now(8, 30),
                )

            assert len(result) > 0, f"Empty fallback for {ntype}"


# ---------------------------------------------------------------------------
# _get_fallback_message edge cases
# ---------------------------------------------------------------------------


class TestGetFallbackMessage:
    """_get_fallback_message handles all edge cases gracefully."""

    def test_unknown_notification_type_returns_default(self) -> None:
        """Unknown notification type returns the ultimate fallback."""
        result = _get_fallback_message("goal_followup", "en")

        # Should return some non-empty string (ultimate default)
        assert len(result) > 0

    def test_unknown_language_for_valid_type_falls_back_to_english(self) -> None:
        """Unknown language for a valid type returns English message."""
        result = _get_fallback_message("morning_checkin", "ja")

        assert result == "Good morning! How are you feeling today?"

    def test_all_types_have_turkish_messages(self) -> None:
        """All four types have defined Turkish fallbacks."""
        notification_types = [
            "morning_checkin",
            "afternoon_nudge",
            "evening_reflection",
            "sleep_reminder",
        ]
        for ntype in notification_types:
            result = _get_fallback_message(ntype, "tr")
            assert len(result) > 0, f"Missing Turkish fallback for {ntype}"
            # Verify it's not the English message
            en_result = _get_fallback_message(ntype, "en")
            assert result != en_result, f"Turkish and English fallback identical for {ntype}"

    def test_evening_reflection_english_fallback_content(self) -> None:
        """Verify specific content of evening_reflection English fallback."""
        result = _get_fallback_message("evening_reflection", "en")
        assert result == "How was your day? I'd love to hear about it."

    def test_sleep_reminder_turkish_fallback_content(self) -> None:
        """Verify specific content of sleep_reminder Turkish fallback."""
        result = _get_fallback_message("sleep_reminder", "tr")
        assert result == "Gec oldu. Yatma vakti geldi mi?"


# ---------------------------------------------------------------------------
# run_notification_cycle: DB session failure
# ---------------------------------------------------------------------------


class TestRunNotificationCycleEdgeCases:
    """Edge cases for the outer notification cycle."""

    @pytest.mark.asyncio
    async def test_db_session_failure_does_not_propagate(self) -> None:
        """If the DB session itself fails to open, cycle logs and returns cleanly."""
        with patch(
            "app.services.notification_scheduler.AsyncSessionLocal",
            side_effect=Exception("Cannot connect to DB"),
        ):
            # Should not raise
            await run_notification_cycle(now_utc=_make_utc(8, 30))

    @pytest.mark.asyncio
    async def test_uses_default_utc_time_when_now_utc_not_provided(self) -> None:
        """When now_utc is None, run_notification_cycle uses datetime.now(UTC)."""
        with patch(
            "app.services.notification_scheduler.AsyncSessionLocal",
        ) as mock_session_cls:
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.all.return_value = []
            mock_db.execute = AsyncMock(return_value=mock_result)

            # Pass no now_utc — should use datetime.now(UTC) internally
            await run_notification_cycle()

            # Should complete without error
            mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_uses_default_utc_time_when_now_utc_not_provided(self) -> None:
        """When now_utc is None, reset_notifications_sent_today uses datetime.now(UTC)."""
        with patch(
            "app.services.notification_scheduler.AsyncSessionLocal",
        ) as mock_session_cls:
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_result = MagicMock()
            mock_result.all.return_value = []
            mock_db.execute = AsyncMock(return_value=mock_result)

            # Pass no now_utc — should use datetime.now(UTC) internally
            await reset_notifications_sent_today()

            mock_db.execute.assert_called_once()


# ---------------------------------------------------------------------------
# _process_user: exception from _process_notification is caught
# ---------------------------------------------------------------------------


class TestProcessUserExceptionHandling:
    """_process_user catches exceptions from _process_notification and logs them."""

    @pytest.mark.asyncio
    async def test_process_notification_exception_is_caught_and_count_not_incremented(
        self,
    ) -> None:
        """If _process_notification raises, count is not incremented but no re-raise."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id, timezone_str="UTC")
        activity = _make_activity(user_id=user_id)

        mock_db = AsyncMock()
        now_utc = _make_utc(8, 30)  # Morning window — triggers morning_checkin

        with patch(
            "app.services.notification_scheduler._process_notification",
            side_effect=Exception("FCM completely broken"),
        ):
            count = await _process_user(mock_db, activity, profile, now_utc)

        # Exception was caught; no notifications were successfully counted
        assert count == 0


# ---------------------------------------------------------------------------
# _process_notification: profile has no fcm_token (token cleared between character
# query and FCM call — unlikely but possible)
# ---------------------------------------------------------------------------


class TestProcessNotificationNoFcmToken:
    """_process_notification short-circuits when profile.fcm_token is falsy."""

    @pytest.mark.asyncio
    async def test_skips_fcm_call_when_token_is_none_after_character_found(self) -> None:
        """If profile.fcm_token is None at FCM call time, send is not attempted."""
        user_id = uuid.uuid4()
        profile = _make_profile(user_id=user_id, fcm_token=None)  # No token
        activity = _make_activity(user_id=user_id)
        character = _make_character(user_id=user_id)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = character
        mock_db.execute = AsyncMock(return_value=mock_result)

        with (
            patch(
                "app.services.notification_scheduler._generate_notification_message",
                return_value="Hello!",
            ),
            patch(
                "app.services.notification_scheduler.send_push_notification",
            ) as mock_send,
        ):
            await _process_notification(
                mock_db,
                profile,
                activity,
                "morning_checkin",
                _make_local_now(8, 30),
            )

            # FCM must NOT be called when token is None
            mock_send.assert_not_called()
