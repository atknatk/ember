"""Notification scheduler — APScheduler-based async cron job.

Runs every N minutes (configurable), evaluates notification triggers per user,
generates personalized messages via Claude Haiku + Mem0, and sends push
notifications via Firebase Cloud Messaging.

A separate hourly job resets the daily notification tracking array at each
user's local midnight.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler import AsyncScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from mem0 import MemoryClient
from sqlalchemy import select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.models.character import Character
from app.models.profile import Profile
from app.models.user_activity import UserActivity
from app.services.llm.exceptions import LLMProviderError
from app.services.llm.router import get_llm_router
from app.services.notification_sender import SendResult, send_push_notification

logger = logging.getLogger("ember")

# ---------------------------------------------------------------------------
# Notification type constants
# ---------------------------------------------------------------------------

NOTIFICATION_TYPES = ("morning_checkin", "afternoon_nudge", "evening_reflection", "sleep_reminder")

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
# Scheduler lifecycle
# ---------------------------------------------------------------------------


async def start_notification_scheduler() -> AsyncScheduler:
    """Create and start the APScheduler instance with notification jobs.

    Returns:
        The running AsyncScheduler instance (caller stores it for shutdown).
    """
    scheduler = AsyncScheduler()

    await scheduler.add_schedule(
        run_notification_cycle,
        IntervalTrigger(minutes=settings.notification_scheduler_interval_minutes),
        id="notification_cycle",
    )
    await scheduler.add_schedule(
        reset_notifications_sent_today,
        CronTrigger(minute=0),
        id="midnight_reset",
    )

    await scheduler.start_in_background()
    logger.info(
        "Notification scheduler started (interval=%d min)",
        settings.notification_scheduler_interval_minutes,
    )
    return scheduler


# ---------------------------------------------------------------------------
# Core cycle
# ---------------------------------------------------------------------------


async def run_notification_cycle(now_utc: datetime | None = None) -> None:
    """Main cron job — evaluate triggers and send notifications for all users.

    Args:
        now_utc: Override for the current UTC time (for testing).
                 Defaults to datetime.now(UTC).
    """
    if now_utc is None:
        now_utc = datetime.now(UTC)

    logger.info("Notification cycle starting at %s", now_utc.isoformat())
    processed = 0
    sent = 0

    try:
        async with AsyncSessionLocal() as db:
            offset = 0
            batch_size = settings.notification_batch_size

            while True:
                users = await _fetch_user_batch(db, offset, batch_size)
                if not users:
                    break

                for activity, profile in users:
                    try:
                        user_sent = await _process_user(
                            db, activity, profile, now_utc,
                        )
                        sent += user_sent
                        processed += 1
                    except Exception:
                        logger.exception(
                            "Error processing notifications for user_id=%s",
                            activity.user_id,
                        )
                        processed += 1

                offset += batch_size

    except Exception:
        logger.exception("Notification cycle failed")

    logger.info(
        "Notification cycle complete: %d users processed, %d notifications sent",
        processed,
        sent,
    )


# ---------------------------------------------------------------------------
# Midnight reset
# ---------------------------------------------------------------------------


async def reset_notifications_sent_today(now_utc: datetime | None = None) -> None:
    """Reset notifications_sent_today for users whose local time crossed midnight.

    Runs every hour. Checks each user's timezone and resets the array
    if their local hour is 0 (midnight hour).

    Args:
        now_utc: Override for the current UTC time (for testing).
    """
    if now_utc is None:
        now_utc = datetime.now(UTC)

    logger.info("Midnight reset check starting at %s", now_utc.isoformat())
    reset_count = 0

    try:
        async with AsyncSessionLocal() as db:
            # Only fetch users who have non-empty notifications_sent_today
            stmt = (
                select(UserActivity, Profile)
                .join(Profile, UserActivity.user_id == Profile.id)
                .where(UserActivity.notifications_sent_today != [])
            )
            result = await db.execute(stmt)
            rows = result.all()

            user_ids_to_reset: list[object] = []

            for activity, profile in rows:
                try:
                    tz = ZoneInfo(profile.timezone)
                except (ZoneInfoNotFoundError, KeyError):
                    continue

                local_now = now_utc.astimezone(tz)
                if local_now.hour == 0:
                    user_ids_to_reset.append(activity.user_id)

            if user_ids_to_reset:
                await db.execute(
                    update(UserActivity)
                    .where(UserActivity.user_id.in_(user_ids_to_reset))
                    .values(notifications_sent_today=[]),
                )
                await db.commit()
                reset_count = len(user_ids_to_reset)

    except Exception:
        logger.exception("Midnight reset failed")

    logger.info("Midnight reset complete: %d users reset", reset_count)


# ---------------------------------------------------------------------------
# Pure trigger evaluation
# ---------------------------------------------------------------------------


def evaluate_notification_triggers(
    notifications_sent_today: list[str],
    last_chat_at: datetime | None,
    last_active_at: datetime | None,
    local_now: datetime,
    now_utc: datetime,
) -> list[str]:
    """Determine which notification types should fire for a user.

    This is a pure function (no I/O) for easy testing.

    Args:
        notifications_sent_today: List of notification type strings already sent today.
        last_chat_at: When the user last sent a chat message (UTC, timezone-aware).
        last_active_at: When the user was last active (UTC, timezone-aware).
        local_now: Current time in the user's local timezone.
        now_utc: Current UTC time.

    Returns:
        List of notification type strings that should be triggered.
    """
    triggered: list[str] = []
    local_minutes = local_now.hour * 60 + local_now.minute

    # Compute local today start (midnight in user's timezone)
    local_today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    # Convert to UTC-aware for comparison with last_chat_at
    local_today_start_utc = local_today_start.astimezone(UTC)

    chatted_today = (
        last_chat_at is not None and last_chat_at >= local_today_start_utc
    )

    # morning_checkin: 08:00 - 09:30 (480 - 570 minutes)
    if (
        480 <= local_minutes < 570
        and not chatted_today
        and "morning_checkin" not in notifications_sent_today
    ):
        triggered.append("morning_checkin")

    # afternoon_nudge: 14:00 - 15:30 (840 - 930 minutes)
    if (
        840 <= local_minutes < 930
        and not chatted_today
        and "afternoon_nudge" not in notifications_sent_today
    ):
        triggered.append("afternoon_nudge")

    # evening_reflection: 20:00 - 21:00 (1200 - 1260 minutes)
    if (
        1200 <= local_minutes < 1260
        and "evening_reflection" not in notifications_sent_today
    ):
        triggered.append("evening_reflection")

    # sleep_reminder: 23:00+ (1380+ minutes)
    if (
        local_minutes >= 1380
        and last_active_at is not None
        and last_active_at >= (now_utc - timedelta(minutes=60))
        and "sleep_reminder" not in notifications_sent_today
    ):
        triggered.append("sleep_reminder")

    return triggered


# ---------------------------------------------------------------------------
# Per-user processing
# ---------------------------------------------------------------------------


async def _process_user(
    db: AsyncSession,
    activity: UserActivity,
    profile: Profile,
    now_utc: datetime,
) -> int:
    """Process notification triggers for a single user.

    Returns:
        Number of notifications sent.
    """
    # Validate timezone
    try:
        tz = ZoneInfo(profile.timezone)
    except (ZoneInfoNotFoundError, KeyError):
        logger.warning(
            "Invalid timezone '%s' for user_id=%s, skipping",
            profile.timezone,
            profile.id,
        )
        return 0

    local_now = now_utc.astimezone(tz)

    # Parse notifications_sent_today
    raw_sent = activity.notifications_sent_today
    sent_today: list[str] = list(raw_sent) if isinstance(raw_sent, list) else []

    triggers = evaluate_notification_triggers(
        notifications_sent_today=sent_today,
        last_chat_at=activity.last_chat_at,
        last_active_at=activity.last_active_at,
        local_now=local_now,
        now_utc=now_utc,
    )

    count = 0
    for notification_type in triggers:
        try:
            await _process_notification(db, profile, activity, notification_type, local_now)
            count += 1
        except Exception:
            logger.exception(
                "Failed to process %s for user_id=%s",
                notification_type,
                profile.id,
            )

    return count


async def _process_notification(
    db: AsyncSession,
    profile: Profile,
    activity: UserActivity,
    notification_type: str,
    local_now: datetime,
) -> None:
    """Generate and send a single notification for a user.

    Steps:
    1. Find user's default character
    2. Search Mem0 for relevant memories
    3. Generate personalized message via Claude Haiku
    4. Send FCM push notification
    5. Update notifications_sent_today
    """
    # 1. Find default character
    result = await db.execute(
        select(Character).where(
            Character.user_id == profile.id,
            Character.is_default == true(),
            Character.is_active == true(),
        ),
    )
    default_character = result.scalar_one_or_none()

    if default_character is None:
        logger.warning(
            "No default active character for user_id=%s, skipping %s",
            profile.id,
            notification_type,
        )
        return

    # 2. Generate message (Mem0 search + Claude Haiku)
    message = await _generate_notification_message(
        profile=profile,
        character=default_character,
        notification_type=notification_type,
        local_now=local_now,
    )

    # 3. Send FCM
    if not profile.fcm_token:
        return

    result = await send_push_notification(
        fcm_token=profile.fcm_token,
        title=default_character.name,
        body=message,
        data={
            "character_id": str(default_character.id),
            "notification_type": notification_type,
        },
    )

    if result == SendResult.INVALID_TOKEN:
        # Permanently invalid token — clear it
        await db.execute(
            update(Profile)
            .where(Profile.id == profile.id)
            .values(fcm_token=None),
        )
        await db.commit()
        logger.info("Cleared invalid FCM token for user_id=%s", profile.id)
        return

    if result == SendResult.TRANSIENT_ERROR:
        # Transient failure — keep the token, skip recording this notification
        return

    # 4. Update notifications_sent_today
    try:
        raw = activity.notifications_sent_today
        current_sent: list[str] = list(raw) if isinstance(raw, list) else []
        updated_sent = [*current_sent, notification_type]

        await db.execute(
            update(UserActivity)
            .where(UserActivity.user_id == profile.id)
            .values(notifications_sent_today=updated_sent),
        )
        await db.commit()
        # Update in-memory object for subsequent triggers in same cycle
        activity.notifications_sent_today = updated_sent  # type: ignore[assignment]
    except Exception:
        logger.exception(
            "Failed to update notifications_sent_today for user_id=%s",
            profile.id,
        )


# ---------------------------------------------------------------------------
# Message generation
# ---------------------------------------------------------------------------


async def _generate_notification_message(
    profile: Profile,
    character: Character,
    notification_type: str,
    local_now: datetime,
) -> str:
    """Generate a personalized notification message using Mem0 + Claude Haiku.

    Falls back to deterministic messages if either service fails.
    """
    language = profile.preferred_language or "en"

    # Search Mem0 for relevant memories
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

    # Generate message via Claude Haiku
    try:
        tone = TONE_MAP.get(notification_type, "warm")
        system_prompt = (
            f"You are {character.name}, the user's personal AI companion. "
            f"Generate a short push notification message (1-2 sentences max, "
            f"under 100 characters if possible). The tone should be {tone}. "
            f"Write in {language}."
        )

        user_prompt = (
            f"Notification type: {notification_type}\n"
            f"User's name: {profile.name}\n"
            f"Current local time: {local_now.strftime('%H:%M')}\n"
            f"Relevant memories:\n{memories_text or 'None'}\n\n"
            f"Generate a warm, personalized notification message. "
            f"Do not use quotes. Do not include emoji."
        )

        llm = get_llm_router().get()
        message = await llm.complete_fast(
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=150,
            temperature=0.7,
        )
        return message.strip()

    except (LLMProviderError, Exception):
        logger.warning(
            "Claude Haiku failed for notification %s, user_id=%s, using fallback",
            notification_type,
            profile.id,
        )
        return _get_fallback_message(notification_type, language)


def _get_fallback_message(notification_type: str, language: str) -> str:
    """Return a deterministic fallback message for the given type and language."""
    type_messages = FALLBACK_MESSAGES.get(notification_type, {})
    return type_messages.get(language, type_messages.get("en", "Hey! How are you?"))


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
# Database helpers
# ---------------------------------------------------------------------------


async def _fetch_user_batch(
    db: AsyncSession,
    offset: int,
    batch_size: int,
) -> list[tuple[UserActivity, Profile]]:
    """Fetch a batch of users with activity data and FCM tokens.

    Note: We use OFFSET here because this is a background batch job iterating
    over all eligible users, not a user-facing paginated API. The user_activity
    table is bounded by total user count and is not a high-volume append table.
    """
    stmt = (
        select(UserActivity, Profile)
        .join(Profile, UserActivity.user_id == Profile.id)
        .where(Profile.fcm_token.isnot(None))
        .order_by(UserActivity.user_id)
        .offset(offset)
        .limit(batch_size)
    )
    result = await db.execute(stmt)
    rows = result.all()
    return [(row[0], row[1]) for row in rows]
