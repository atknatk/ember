"""Firebase Cloud Messaging sender — extracted for testability.

Handles FCM push notification delivery and Firebase Admin SDK initialization.
All firebase-admin calls are synchronous and wrapped in asyncio.to_thread().
"""

from __future__ import annotations

import asyncio
import json
import logging

import firebase_admin
from firebase_admin import credentials, messaging
from firebase_admin import exceptions as fb_exceptions

logger = logging.getLogger("ember")


def initialize_firebase(credentials_json: str) -> None:
    """Initialize Firebase Admin SDK with service account credentials.

    Idempotent — checks firebase_admin._apps before initializing.

    Args:
        credentials_json: JSON string containing the Firebase service account credentials.
    """
    if firebase_admin._apps:
        logger.debug("Firebase already initialized, skipping")
        return

    if not credentials_json:
        logger.warning("Firebase credentials JSON is empty, skipping initialization")
        return

    try:
        cred_dict = json.loads(credentials_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized successfully")
    except Exception:
        logger.exception("Failed to initialize Firebase Admin SDK")
        raise


async def send_push_notification(
    fcm_token: str,
    title: str,
    body: str,
    data: dict[str, str],
) -> bool:
    """Send a push notification via Firebase Cloud Messaging.

    Args:
        fcm_token: The recipient's FCM registration token.
        title: Notification title (character name).
        body: Notification body (generated message).
        data: Additional data payload (character_id, notification_type).

    Returns:
        True on successful send, False on failure.
        The caller should invalidate the token when this returns False
        and the error is UnregisteredError or InvalidArgumentError.
    """
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        data=data,
        token=fcm_token,
    )

    try:
        await asyncio.to_thread(messaging.send, message)
        return True
    except (messaging.UnregisteredError, fb_exceptions.InvalidArgumentError) as exc:
        logger.warning(
            "FCM token invalid or unregistered: %s (token=%s...)",
            exc,
            fcm_token[:20],
        )
        return False
    except Exception:
        logger.exception("FCM send failed for token=%s...", fcm_token[:20])
        return False
