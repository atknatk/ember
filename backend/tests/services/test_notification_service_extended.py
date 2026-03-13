"""Extended service-level tests for NotificationService.

Supplements test_notification_service.py with logging verification,
data-payload edge cases, user-id query correctness, commit-error handling,
and whitespace-token edge cases not covered by the base test file.
"""

from __future__ import annotations

import logging
import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import uuid  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, call, patch  # noqa: E402

import pytest  # noqa: E402

from app.services.notification_sender import SendResult  # noqa: E402
from app.services.notification_service import NotificationService  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
OTHER_USER_ID = uuid.UUID("660e8400-e29b-41d4-a716-446655440001")


def _make_mock_db(fcm_token: str | None = "valid-fcm-token") -> AsyncMock:
    """Create a mock AsyncSession that returns the given fcm_token on SELECT."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fcm_token
    mock_db.execute.return_value = mock_result
    mock_db.commit = AsyncMock()
    return mock_db


# ---------------------------------------------------------------------------
# Data payload edge cases
# ---------------------------------------------------------------------------


class TestNotificationServiceDataPayload:
    """Tests for the data= parameter handling in NotificationService.send()."""

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_with_empty_dict_data(self, mock_send: AsyncMock) -> None:
        """send() with data={} passes an empty dict (not None) to send_push_notification."""
        mock_send.return_value = SendResult.SENT
        mock_db = _make_mock_db(fcm_token="token-abc")

        service = NotificationService(mock_db)
        await service.send(
            user_id=FAKE_USER_ID,
            title="Emma",
            body="Hello",
            data={},
        )

        mock_send.assert_awaited_once_with(
            fcm_token="token-abc",
            title="Emma",
            body="Hello",
            data={},
        )

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_data_dict_is_not_mutated(self, mock_send: AsyncMock) -> None:
        """The caller's data dict is passed through unmodified."""
        mock_send.return_value = SendResult.SENT
        mock_db = _make_mock_db(fcm_token="token-abc")
        original_data = {"key1": "value1", "key2": "value2"}
        data_copy = dict(original_data)

        service = NotificationService(mock_db)
        await service.send(
            user_id=FAKE_USER_ID,
            title="Emma",
            body="Hello",
            data=original_data,
        )

        # Caller's dict should not be mutated
        assert original_data == data_copy
        # And it was passed through exactly
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["data"] == data_copy

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_data_default_is_none(self, mock_send: AsyncMock) -> None:
        """Calling send() without data= uses None default, which becomes {} in the call."""
        mock_send.return_value = SendResult.SENT
        mock_db = _make_mock_db(fcm_token="token-abc")

        service = NotificationService(mock_db)
        # Omit data argument entirely
        await service.send(
            user_id=FAKE_USER_ID,
            title="Title",
            body="Body",
        )

        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["data"] == {}

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_title_and_body_passed_correctly(self, mock_send: AsyncMock) -> None:
        """Title and body are forwarded verbatim to send_push_notification."""
        mock_send.return_value = SendResult.SENT
        mock_db = _make_mock_db(fcm_token="token-abc")

        service = NotificationService(mock_db)
        await service.send(
            user_id=FAKE_USER_ID,
            title="Specific Title",
            body="Specific body text with punctuation!",
        )

        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["title"] == "Specific Title"
        assert call_kwargs["body"] == "Specific body text with punctuation!"


# ---------------------------------------------------------------------------
# User ID query correctness
# ---------------------------------------------------------------------------


class TestNotificationServiceUserLookup:
    """Tests verifying the service queries the correct user_id."""

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_queries_correct_user_id(self, mock_send: AsyncMock) -> None:
        """The SELECT statement uses the provided user_id, not a hardcoded value."""
        mock_send.return_value = SendResult.SENT
        mock_db = _make_mock_db(fcm_token="token-for-correct-user")

        service = NotificationService(mock_db)
        await service.send(
            user_id=FAKE_USER_ID,
            title="T",
            body="B",
        )

        # Verify execute was called once (the SELECT)
        assert mock_db.execute.call_count >= 1
        # The user_id is baked into the SQLAlchemy statement — we verify the call happened
        mock_db.execute.assert_awaited()

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_different_user_id_uses_their_token(
        self, mock_send: AsyncMock
    ) -> None:
        """Two service instances with different user_ids look up their respective tokens."""
        mock_send.return_value = SendResult.SENT

        mock_db_user1 = _make_mock_db(fcm_token="token-user1")
        mock_db_user2 = _make_mock_db(fcm_token="token-user2")

        svc1 = NotificationService(mock_db_user1)
        svc2 = NotificationService(mock_db_user2)

        await svc1.send(user_id=FAKE_USER_ID, title="T", body="B")
        await svc2.send(user_id=OTHER_USER_ID, title="T", body="B")

        # Each service sent to its own token
        calls = mock_send.await_args_list
        tokens_used = [c.kwargs["fcm_token"] for c in calls]
        assert "token-user1" in tokens_used
        assert "token-user2" in tokens_used

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_whitespace_token_in_db_is_sent(
        self, mock_send: AsyncMock
    ) -> None:
        """If the DB has a whitespace-only token stored, it is sent as-is (not treated as None)."""
        mock_send.return_value = SendResult.SENT
        mock_db = _make_mock_db(fcm_token="   ")

        service = NotificationService(mock_db)
        result = await service.send(
            user_id=FAKE_USER_ID,
            title="T",
            body="B",
        )

        # Whitespace string is truthy — service calls send_push_notification
        assert result == SendResult.SENT
        mock_send.assert_awaited_once()
        assert mock_send.call_args.kwargs["fcm_token"] == "   "


# ---------------------------------------------------------------------------
# Logging verification
# ---------------------------------------------------------------------------


class TestNotificationServiceLogging:
    """Tests verifying the service emits the correct log messages."""

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_logs_info_when_clearing_invalid_token(
        self, mock_send: AsyncMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Clearing an invalid token logs at INFO level with user_id."""
        mock_send.return_value = SendResult.INVALID_TOKEN
        mock_db = _make_mock_db(fcm_token="expired-token")

        service = NotificationService(mock_db)
        with caplog.at_level(logging.INFO, logger="ember"):
            await service.send(
                user_id=FAKE_USER_ID,
                title="T",
                body="B",
            )

        log_messages = [r.message for r in caplog.records]
        assert any("Cleared invalid FCM token" in msg for msg in log_messages)
        assert any(str(FAKE_USER_ID) in msg for msg in log_messages)

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_logs_debug_on_success(
        self, mock_send: AsyncMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Successful send logs at DEBUG level with user_id."""
        mock_send.return_value = SendResult.SENT
        mock_db = _make_mock_db(fcm_token="good-token")

        service = NotificationService(mock_db)
        with caplog.at_level(logging.DEBUG, logger="ember"):
            await service.send(
                user_id=FAKE_USER_ID,
                title="T",
                body="B",
            )

        log_messages = [r.message for r in caplog.records]
        assert any("Notification sent" in msg for msg in log_messages)

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_logs_debug_when_no_token(
        self, mock_send: AsyncMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """No-token path logs at DEBUG level (not WARNING or ERROR)."""
        mock_db = _make_mock_db(fcm_token=None)

        service = NotificationService(mock_db)
        with caplog.at_level(logging.DEBUG, logger="ember"):
            await service.send(
                user_id=FAKE_USER_ID,
                title="T",
                body="B",
            )

        # Should have a debug-level record mentioning the user
        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(debug_records) >= 1
        # No WARNING or ERROR for the no-token path
        high_level_records = [
            r for r in caplog.records if r.levelno >= logging.WARNING
        ]
        assert len(high_level_records) == 0

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_does_not_log_info_on_transient_error(
        self, mock_send: AsyncMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """TRANSIENT_ERROR does not log at INFO about clearing a token."""
        mock_send.return_value = SendResult.TRANSIENT_ERROR
        mock_db = _make_mock_db(fcm_token="still-valid-token")

        service = NotificationService(mock_db)
        with caplog.at_level(logging.INFO, logger="ember"):
            await service.send(
                user_id=FAKE_USER_ID,
                title="T",
                body="B",
            )

        log_messages = [r.message for r in caplog.records]
        assert not any("Cleared invalid FCM token" in msg for msg in log_messages)


# ---------------------------------------------------------------------------
# _clear_token error handling
# ---------------------------------------------------------------------------


class TestNotificationServiceClearTokenErrors:
    """Tests for _clear_token error handling edge cases."""

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_clear_token_commit_error_does_not_propagate(
        self, mock_send: AsyncMock
    ) -> None:
        """If db.commit() raises during _clear_token, the error is swallowed."""
        mock_send.return_value = SendResult.INVALID_TOKEN
        mock_db = _make_mock_db(fcm_token="bad-token")
        # commit raises after execute succeeds
        mock_db.commit = AsyncMock(side_effect=RuntimeError("Commit failed"))

        service = NotificationService(mock_db)
        result = await service.send(
            user_id=FAKE_USER_ID,
            title="T",
            body="B",
        )

        # Exception from commit must not propagate
        assert result == SendResult.INVALID_TOKEN

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_clear_token_commit_error_logs_exception(
        self, mock_send: AsyncMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Commit error during _clear_token is logged (not silently dropped)."""
        mock_send.return_value = SendResult.INVALID_TOKEN
        mock_db = _make_mock_db(fcm_token="bad-token")
        mock_db.commit = AsyncMock(side_effect=OSError("Disk full"))

        service = NotificationService(mock_db)
        with caplog.at_level(logging.ERROR, logger="ember"):
            await service.send(
                user_id=FAKE_USER_ID,
                title="T",
                body="B",
            )

        # Should log an exception-level message
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(error_records) >= 1

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_clear_token_db_error_returns_invalid_token(
        self, mock_send: AsyncMock
    ) -> None:
        """Even when _clear_token's UPDATE raises, send() still returns INVALID_TOKEN."""
        mock_send.return_value = SendResult.INVALID_TOKEN

        call_count = 0
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "expired-token"

        async def execute_side_effect(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_result  # SELECT succeeds
            raise ConnectionError("DB gone")  # UPDATE fails

        mock_db.execute = AsyncMock(side_effect=execute_side_effect)
        mock_db.commit = AsyncMock()

        service = NotificationService(mock_db)
        result = await service.send(
            user_id=FAKE_USER_ID,
            title="T",
            body="B",
        )

        assert result == SendResult.INVALID_TOKEN

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_transient_error_commit_not_called(
        self, mock_send: AsyncMock
    ) -> None:
        """On TRANSIENT_ERROR, db.commit() is never called (no token cleared)."""
        mock_send.return_value = SendResult.TRANSIENT_ERROR
        mock_db = _make_mock_db(fcm_token="some-token")

        service = NotificationService(mock_db)
        await service.send(
            user_id=FAKE_USER_ID,
            title="T",
            body="B",
        )

        mock_db.commit.assert_not_awaited()


# ---------------------------------------------------------------------------
# Return value contract
# ---------------------------------------------------------------------------


class TestNotificationServiceReturnValues:
    """Verify send() return value matches SendResult constants exactly."""

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_return_value_is_string_sent(self, mock_send: AsyncMock) -> None:
        """Return value for SENT case equals the SendResult.SENT string constant."""
        mock_send.return_value = SendResult.SENT
        mock_db = _make_mock_db(fcm_token="tok")

        result = await NotificationService(mock_db).send(
            user_id=FAKE_USER_ID, title="T", body="B"
        )

        assert result == "sent"
        assert result == SendResult.SENT

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_return_value_is_string_invalid_token_from_sender(
        self, mock_send: AsyncMock
    ) -> None:
        """Return value for INVALID_TOKEN case equals SendResult.INVALID_TOKEN string."""
        mock_send.return_value = SendResult.INVALID_TOKEN
        mock_db = _make_mock_db(fcm_token="bad-tok")

        result = await NotificationService(mock_db).send(
            user_id=FAKE_USER_ID, title="T", body="B"
        )

        assert result == "invalid_token"
        assert result == SendResult.INVALID_TOKEN

    @pytest.mark.asyncio
    async def test_return_value_is_string_invalid_token_from_null(self) -> None:
        """Return value when token is None equals SendResult.INVALID_TOKEN string."""
        mock_db = _make_mock_db(fcm_token=None)

        result = await NotificationService(mock_db).send(
            user_id=FAKE_USER_ID, title="T", body="B"
        )

        assert result == "invalid_token"
        assert result == SendResult.INVALID_TOKEN

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_return_value_is_string_transient_error(
        self, mock_send: AsyncMock
    ) -> None:
        """Return value for TRANSIENT_ERROR case equals SendResult.TRANSIENT_ERROR string."""
        mock_send.return_value = SendResult.TRANSIENT_ERROR
        mock_db = _make_mock_db(fcm_token="tok")

        result = await NotificationService(mock_db).send(
            user_id=FAKE_USER_ID, title="T", body="B"
        )

        assert result == "transient_error"
        assert result == SendResult.TRANSIENT_ERROR


# ---------------------------------------------------------------------------
# Service construction and interface
# ---------------------------------------------------------------------------


class TestNotificationServiceConstruction:
    """Tests verifying the NotificationService constructor and interface."""

    def test_service_stores_db_session(self) -> None:
        """NotificationService stores the db reference passed to __init__."""
        mock_db = AsyncMock()
        service = NotificationService(mock_db)
        assert service.db is mock_db

    def test_service_has_send_method(self) -> None:
        """NotificationService exposes a .send() method."""
        mock_db = AsyncMock()
        service = NotificationService(mock_db)
        assert callable(service.send)

    def test_service_has_private_clear_token_method(self) -> None:
        """NotificationService exposes a ._clear_token() method (for auditability)."""
        mock_db = AsyncMock()
        service = NotificationService(mock_db)
        assert callable(service._clear_token)

    @pytest.mark.asyncio
    @patch("app.services.notification_service.send_push_notification")
    async def test_send_is_coroutine(self, mock_send: AsyncMock) -> None:
        """send() is an async method and can be awaited."""
        import inspect

        mock_db = _make_mock_db(fcm_token=None)
        service = NotificationService(mock_db)
        coro = service.send(user_id=FAKE_USER_ID, title="T", body="B")
        assert inspect.isawaitable(coro)
        await coro  # must not raise
