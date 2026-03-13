"""Extended tests for the notification sender (FCM push delivery).

Supplements the backend-dev tests with coverage for:
  - InvalidArgumentError (separate from UnregisteredError)
  - initialize_firebase with invalid JSON raises
  - initialize_firebase with valid JSON and no prior app initializes once
  - send_push_notification constructs Message with correct structure
  - Short FCM token does not cause index errors in logging
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.notification_sender import SendResult, initialize_firebase, send_push_notification


class TestSendPushNotificationExtended:
    """Additional tests for send_push_notification."""

    @pytest.mark.asyncio
    async def test_returns_invalid_token_on_invalid_argument_error(self) -> None:
        """InvalidArgumentError (bad token format) returns INVALID_TOKEN."""
        from firebase_admin import exceptions as fb_exceptions

        with patch(
            "app.services.notification_sender.messaging.send",
            side_effect=fb_exceptions.InvalidArgumentError("Invalid token format"),
        ):
            result = await send_push_notification(
                fcm_token="bad-format-token",
                title="Emma",
                body="Good morning!",
                data={"character_id": "char-1", "notification_type": "morning_checkin"},
            )

        assert result == SendResult.INVALID_TOKEN

    @pytest.mark.asyncio
    async def test_message_constructed_with_correct_fields(self) -> None:
        """Verify the FCM Message is built with the right title, body, data, and token."""
        from firebase_admin import messaging as fb_messaging

        captured_messages: list[object] = []

        def capture_send(message: object) -> str:
            captured_messages.append(message)
            return "projects/test/messages/abc"

        with patch(
            "app.services.notification_sender.messaging.send",
            side_effect=capture_send,
        ):
            result = await send_push_notification(
                fcm_token="token-xyz",
                title="Luna",
                body="How are you feeling today?",
                data={
                    "character_id": "char-luna",
                    "notification_type": "evening_reflection",
                },
            )

        assert result == SendResult.SENT
        assert len(captured_messages) == 1
        msg = captured_messages[0]
        assert isinstance(msg, fb_messaging.Message)
        assert msg.token == "token-xyz"
        assert msg.notification.title == "Luna"
        assert msg.notification.body == "How are you feeling today?"
        assert msg.data["character_id"] == "char-luna"
        assert msg.data["notification_type"] == "evening_reflection"

    @pytest.mark.asyncio
    async def test_short_token_does_not_raise_on_logging(self) -> None:
        """Token shorter than 20 chars does not cause IndexError in logging code."""
        with patch(
            "app.services.notification_sender.messaging.send",
            side_effect=Exception("FCM error"),
        ):
            # Short token — should not raise IndexError from [:20] slice
            result = await send_push_notification(
                fcm_token="short",
                title="Emma",
                body="Hey!",
                data={"character_id": "c", "notification_type": "morning_checkin"},
            )

        assert result == SendResult.TRANSIENT_ERROR

    @pytest.mark.asyncio
    async def test_unregistered_and_invalid_both_return_invalid_token(self) -> None:
        """Both token-invalidity errors return INVALID_TOKEN without re-raising."""
        from firebase_admin import messaging as fb_messaging
        from firebase_admin import exceptions as fb_exceptions

        for exc in (
            fb_messaging.UnregisteredError("unregistered"),
            fb_exceptions.InvalidArgumentError("invalid"),
        ):
            with patch(
                "app.services.notification_sender.messaging.send",
                side_effect=exc,
            ):
                result = await send_push_notification(
                    fcm_token="token-abc",
                    title="Emma",
                    body="Hello",
                    data={"character_id": "c1", "notification_type": "morning_checkin"},
                )
            assert result == SendResult.INVALID_TOKEN


class TestInitializeFirebaseExtended:
    """Additional tests for initialize_firebase."""

    def test_invalid_json_raises_exception(self) -> None:
        """Malformed JSON credentials string causes an exception to propagate."""
        with patch("app.services.notification_sender.firebase_admin") as mock_fb:
            mock_fb._apps = {}

            with pytest.raises(Exception):
                initialize_firebase("not-valid-json")

    def test_valid_credentials_calls_initialize_app(self) -> None:
        """Valid JSON credentials calls firebase_admin.initialize_app exactly once."""
        creds_json = json.dumps(
            {
                "type": "service_account",
                "project_id": "ember-test",
                "private_key_id": "key123",
            }
        )

        with patch("app.services.notification_sender.firebase_admin") as mock_fb:
            mock_fb._apps = {}
            mock_fb.initialize_app = MagicMock()

            with patch(
                "app.services.notification_sender.credentials.Certificate",
                return_value=MagicMock(),
            ):
                initialize_firebase(creds_json)

            mock_fb.initialize_app.assert_called_once()

    def test_already_initialized_does_not_call_initialize_app(self) -> None:
        """If firebase_admin._apps is non-empty, initialize_app is not called."""
        with patch("app.services.notification_sender.firebase_admin") as mock_fb:
            mock_fb._apps = {"[DEFAULT]": MagicMock()}
            mock_fb.initialize_app = MagicMock()

            initialize_firebase('{"type": "service_account"}')

            mock_fb.initialize_app.assert_not_called()

    def test_none_credentials_treated_as_empty(self) -> None:
        """None-like empty string is skipped gracefully (same as empty string)."""
        with patch("app.services.notification_sender.firebase_admin") as mock_fb:
            mock_fb._apps = {}
            mock_fb.initialize_app = MagicMock()

            initialize_firebase("")

            mock_fb.initialize_app.assert_not_called()
