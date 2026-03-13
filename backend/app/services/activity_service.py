"""Activity tracking service for updating user_activity table.

Provides a standalone async function that performs an upsert on the
user_activity table. Designed to be called from a background task
after the response is sent, using its own database session.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import text

from app.db.session import AsyncSessionLocal

logger = logging.getLogger("ember")


async def update_user_activity(
    user_id: str,
    is_chat_request: bool,
) -> None:
    """Upsert user activity timestamps in the user_activity table.

    Creates a new row if the user has no activity record, or updates
    the existing row. Uses INSERT ... ON CONFLICT DO UPDATE for
    atomic upsert behavior.

    This function manages its own database session because it runs
    as a background task after the request session is closed.

    Args:
        user_id: The user's UUID string (from JWT sub claim).
        is_chat_request: Whether the triggering request was a chat message.
    """
    try:
        now = datetime.now(UTC)

        if is_chat_request:
            sql = text(
                "INSERT INTO user_activity "
                "(user_id, last_active_at, last_chat_at, notifications_sent_today, updated_at) "
                "VALUES (:user_id, :now, :now, '[]'::jsonb, :now) "
                "ON CONFLICT (user_id) DO UPDATE SET "
                "last_active_at = :now, "
                "last_chat_at = :now, "
                "updated_at = :now"
            )
        else:
            sql = text(
                "INSERT INTO user_activity "
                "(user_id, last_active_at, notifications_sent_today, updated_at) "
                "VALUES (:user_id, :now, '[]'::jsonb, :now) "
                "ON CONFLICT (user_id) DO UPDATE SET "
                "last_active_at = :now, "
                "updated_at = :now"
            )

        async with AsyncSessionLocal() as session:
            await session.execute(sql, {"user_id": user_id, "now": now})
            await session.commit()

    except Exception:
        logger.warning(
            "Failed to update user activity for user_id=%s",
            user_id,
            exc_info=True,
        )
