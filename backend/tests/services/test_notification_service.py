"""Service-level tests for NotificationService.

Tests the high-level notification sending logic including user lookup,
FCM delivery delegation, and invalid token cleanup.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import uuid  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from app.services.notification_sender import SendResult  # noqa: E402
from app.services.notification_service import NotificationService  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")


def _make_mock_db(fcm_token: str | None = "valid-fcm-token") -> AsyncMock:
    """Create a mock AsyncSession that returns a profile with the given fcm_token."""
    mock_db = AsyncMock()

    # Mock the result of select(Profile.fcm_token).where(...)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fcm_token
    mock_db.execute.return_value = mock_result

    mock_db.commit = AsyncMock()
    return mock_db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNotificationServiceSend:
    """Tests for NotificationService.send()."""

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_with_valid_token(
        self,
        mock_send: AsyncMock,
    ) -> None:
        """Test #11: send() with user who has valid FCM token returns SENT."""
        mock_send.return_value = SendResult.SENT
        mock_db = _make_mock_db(fcm_token="valid-token-abc")

        service = NotificationService(mock_db)
        result = await service.send(
            user_id=FAKE_USER_ID,
            title="Emma",
            body="Good morning!",
            data={"character_id": "char-1"},
        )

        assert result == SendResult.SENT
        mock_send.assert_awaited_once_with(
            fcm_token="valid-token-abc",
            title="Emma",
            body="Good morning!",
            data={"character_id": "char-1"},
        )

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_with_no_token(
        self,
        mock_send: AsyncMock,
    ) -> None:
        """Test #12: send() with user who has no FCM token returns INVALID_TOKEN."""
        mock_db = _make_mock_db(fcm_token=None)

        service = NotificationService(mock_db)
        result = await service.send(
            user_id=FAKE_USER_ID,
            title="Emma",
            body="Good morning!",
        )

        assert result == SendResult.INVALID_TOKEN
        mock_send.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_clears_invalid_token(
        self,
        mock_send: AsyncMock,
    ) -> None:
        """Test #13: send() clears token when send_push_notification returns INVALID_TOKEN."""
        mock_send.return_value = SendResult.INVALID_TOKEN
        mock_db = _make_mock_db(fcm_token="expired-token")

        service = NotificationService(mock_db)
        result = await service.send(
            user_id=FAKE_USER_ID,
            title="Emma",
            body="Good morning!",
        )

        assert result == SendResult.INVALID_TOKEN
        # Should have executed UPDATE to clear the token + commit
        assert mock_db.execute.call_count == 2  # 1 for SELECT, 1 for UPDATE
        mock_db.commit.assert_awaited()

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_does_not_clear_on_transient_error(
        self,
        mock_send: AsyncMock,
    ) -> None:
        """Test #14: send() does NOT clear token on TRANSIENT_ERROR."""
        mock_send.return_value = SendResult.TRANSIENT_ERROR
        mock_db = _make_mock_db(fcm_token="some-token")

        service = NotificationService(mock_db)
        result = await service.send(
            user_id=FAKE_USER_ID,
            title="Emma",
            body="Good morning!",
        )

        assert result == SendResult.TRANSIENT_ERROR
        # Only 1 execute call (the SELECT), no UPDATE for clearing
        assert mock_db.execute.call_count == 1

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_returns_sent(
        self,
        mock_send: AsyncMock,
    ) -> None:
        """Test #15: send() returns SENT and does not modify token."""
        mock_send.return_value = SendResult.SENT
        mock_db = _make_mock_db(fcm_token="good-token")

        service = NotificationService(mock_db)
        result = await service.send(
            user_id=FAKE_USER_ID,
            title="Emma",
            body="Good morning!",
        )

        assert result == SendResult.SENT
        # Only 1 execute call (the SELECT), no UPDATE
        assert mock_db.execute.call_count == 1

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_with_data_none(
        self,
        mock_send: AsyncMock,
    ) -> None:
        """Test #16: send() with data=None passes empty dict to send_push_notification."""
        mock_send.return_value = SendResult.SENT
        mock_db = _make_mock_db(fcm_token="some-token")

        service = NotificationService(mock_db)
        await service.send(
            user_id=FAKE_USER_ID,
            title="Emma",
            body="Good morning!",
            data=None,
        )

        mock_send.assert_awaited_once_with(
            fcm_token="some-token",
            title="Emma",
            body="Good morning!",
            data={},
        )

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_with_custom_data(
        self,
        mock_send: AsyncMock,
    ) -> None:
        """Test #17: send() with custom data dict passes it through."""
        mock_send.return_value = SendResult.SENT
        mock_db = _make_mock_db(fcm_token="some-token")
        custom_data = {"character_id": "char-1", "notification_type": "morning_checkin"}

        service = NotificationService(mock_db)
        await service.send(
            user_id=FAKE_USER_ID,
            title="Emma",
            body="Good morning!",
            data=custom_data,
        )

        mock_send.assert_awaited_once_with(
            fcm_token="some-token",
            title="Emma",
            body="Good morning!",
            data=custom_data,
        )

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_db_error_on_clear_does_not_propagate(
        self,
        mock_send: AsyncMock,
    ) -> None:
        """Database errors during token cleanup are caught and do not propagate."""
        mock_send.return_value = SendResult.INVALID_TOKEN
        mock_db = _make_mock_db(fcm_token="expired-token")

        # Make the second execute (UPDATE) raise an exception
        call_count = 0
        original_execute = mock_db.execute

        async def side_effect(*args: object, **kwargs: object) -> object:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("DB connection lost")
            return await original_execute(*args, **kwargs)

        mock_db.execute = AsyncMock(side_effect=side_effect)

        service = NotificationService(mock_db)
        # Should not raise despite DB error during cleanup
        result = await service.send(
            user_id=FAKE_USER_ID,
            title="Emma",
            body="Good morning!",
        )

        assert result == SendResult.INVALID_TOKEN
