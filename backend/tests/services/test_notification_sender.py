"""Tests for the notification sender (FCM push delivery)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.notification_sender import initialize_firebase, send_push_notification


class TestSendPushNotification:
    """Tests for send_push_notification function."""

    @pytest.mark.asyncio
    async def test_returns_true_on_successful_send(self) -> None:
        """Test #21: send_push_notification with valid token returns True."""
        with patch(
            "app.services.notification_sender.messaging.send",
            return_value="projects/test/messages/123",
        ):
            result = await send_push_notification(
                fcm_token="valid-token-abc123",
                title="Emma",
                body="Good morning!",
                data={"character_id": "char-1", "notification_type": "morning_checkin"},
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_unregistered_token(self) -> None:
        """Test #22: send_push_notification with unregistered token returns False."""
        from firebase_admin import messaging

        with patch(
            "app.services.notification_sender.messaging.send",
            side_effect=messaging.UnregisteredError("Token not registered"),
        ):
            result = await send_push_notification(
                fcm_token="expired-token-xyz",
                title="Emma",
                body="Good morning!",
                data={"character_id": "char-1", "notification_type": "morning_checkin"},
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_other_fcm_error(self) -> None:
        """Test #23: send_push_notification with other FCM error returns False."""
        with patch(
            "app.services.notification_sender.messaging.send",
            side_effect=Exception("FCM internal error"),
        ):
            result = await send_push_notification(
                fcm_token="some-token",
                title="Emma",
                body="Good morning!",
                data={"character_id": "char-1", "notification_type": "morning_checkin"},
            )

        assert result is False


class TestInitializeFirebase:
    """Tests for initialize_firebase function."""

    def test_initialize_firebase_idempotent(self) -> None:
        """Test #24: initialize_firebase called twice is a no-op on second call."""
        with patch("app.services.notification_sender.firebase_admin") as mock_fb:
            # First call: no apps exist
            mock_fb._apps = {}
            mock_fb.initialize_app = MagicMock()

            with patch(
                "app.services.notification_sender.credentials.Certificate",
                return_value=MagicMock(),
            ):
                initialize_firebase('{"type": "service_account", "project_id": "test"}')

            mock_fb.initialize_app.assert_called_once()

            # Second call: app already exists
            mock_fb._apps = {"[DEFAULT]": MagicMock()}
            mock_fb.initialize_app.reset_mock()

            initialize_firebase('{"type": "service_account", "project_id": "test"}')

            mock_fb.initialize_app.assert_not_called()

    def test_initialize_firebase_empty_credentials_skipped(self) -> None:
        """Empty credentials string should skip initialization."""
        with patch("app.services.notification_sender.firebase_admin") as mock_fb:
            mock_fb._apps = {}
            mock_fb.initialize_app = MagicMock()

            initialize_firebase("")

            mock_fb.initialize_app.assert_not_called()
