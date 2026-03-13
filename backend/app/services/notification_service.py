"""High-level notification service -- wraps FCM sending with user lookup and token cleanup.

Provides a single ``send()`` method that any backend code can use to push a notification
to a user by ``user_id``, without manually looking up FCM tokens or handling invalid
token cleanup. Reuses the existing ``send_push_notification()`` and ``SendResult`` from
``notification_sender.py``.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import Profile
from app.services.notification_sender import SendResult, send_push_notification

logger = logging.getLogger("ember")


class NotificationService:
    """Centralized push notification delivery with token lifecycle management."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def send(
        self,
        user_id: uuid.UUID,
        title: str,
        body: str,
        data: dict[str, str] | None = None,
    ) -> str:
        """Send a push notification to a user by user_id.

        Looks up the user's FCM token, sends the notification, and handles
        invalid token cleanup automatically.

        Args:
            user_id: The target user's UUID.
            title: Notification title.
            body: Notification body text.
            data: Optional data payload dict.

        Returns:
            One of ``SendResult.SENT``, ``SendResult.INVALID_TOKEN``,
            or ``SendResult.TRANSIENT_ERROR``.
        """
        # Look up the user's FCM token
        result = await self.db.execute(
            select(Profile.fcm_token).where(Profile.id == user_id),
        )
        fcm_token = result.scalar_one_or_none()

        if fcm_token is None:
            logger.debug("No FCM token for user_id=%s, skipping notification", user_id)
            return SendResult.INVALID_TOKEN

        # Send the notification
        send_result = await send_push_notification(
            fcm_token=fcm_token,
            title=title,
            body=body,
            data=data or {},
        )

        if send_result == SendResult.INVALID_TOKEN:
            await self._clear_token(user_id)
            logger.info("Cleared invalid FCM token for user_id=%s", user_id)
        elif send_result == SendResult.SENT:
            logger.debug("Notification sent to user_id=%s", user_id)

        return send_result

    async def _clear_token(self, user_id: uuid.UUID) -> None:
        """Set the user's FCM token to NULL in the database.

        Errors are caught and logged to avoid propagating DB failures
        from cleanup operations.
        """
        try:
            await self.db.execute(
                update(Profile)
                .where(Profile.id == user_id)
                .values(fcm_token=None),
            )
            await self.db.commit()
        except Exception:
            logger.exception(
                "Failed to clear FCM token for user_id=%s",
                user_id,
            )
