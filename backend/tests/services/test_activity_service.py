"""Tests for the activity_service module.

Verifies upsert behavior for user_activity updates, including insert,
update, chat vs non-chat logic, and error handling.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.activity_service import update_user_activity


def _mock_session_factory(session_mock: AsyncMock) -> MagicMock:
    """Create a mock AsyncSessionLocal that yields the given session mock."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session_mock)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


class TestUpdateUserActivity:
    """Unit tests for the update_user_activity function."""

    @pytest.mark.asyncio
    async def test_non_chat_request_executes_upsert(self) -> None:
        """Non-chat request executes SQL upsert with last_active_at only."""
        session_mock = AsyncMock()
        ctx = _mock_session_factory(session_mock)

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            await update_user_activity(user_id="user_001", is_chat_request=False)

        session_mock.execute.assert_called_once()
        session_mock.commit.assert_called_once()

        # Verify the SQL does NOT contain last_chat_at in the ON CONFLICT clause
        call_args = session_mock.execute.call_args
        sql_text = str(call_args[0][0].text)
        assert "last_active_at" in sql_text
        assert "ON CONFLICT" in sql_text
        # The ON CONFLICT UPDATE part should NOT set last_chat_at
        on_conflict_part = sql_text.split("ON CONFLICT")[1]
        assert "last_chat_at" not in on_conflict_part

    @pytest.mark.asyncio
    async def test_chat_request_executes_upsert_with_chat_at(self) -> None:
        """Chat request executes SQL upsert including last_chat_at."""
        session_mock = AsyncMock()
        ctx = _mock_session_factory(session_mock)

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            await update_user_activity(user_id="user_002", is_chat_request=True)

        session_mock.execute.assert_called_once()
        session_mock.commit.assert_called_once()

        # Verify the SQL contains last_chat_at
        call_args = session_mock.execute.call_args
        sql_text = str(call_args[0][0].text)
        assert "last_chat_at" in sql_text

    @pytest.mark.asyncio
    async def test_passes_correct_user_id_parameter(self) -> None:
        """The user_id is passed correctly as a SQL parameter."""
        session_mock = AsyncMock()
        ctx = _mock_session_factory(session_mock)

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            await update_user_activity(user_id="test-uuid-abc", is_chat_request=False)

        call_args = session_mock.execute.call_args
        params = call_args[0][1]
        assert params["user_id"] == "test-uuid-abc"

    @pytest.mark.asyncio
    async def test_database_error_is_caught_and_logged(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Database exceptions are caught and logged at warning level."""
        session_mock = AsyncMock()
        session_mock.execute.side_effect = RuntimeError("connection refused")
        ctx = _mock_session_factory(session_mock)

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            with caplog.at_level(logging.WARNING, logger="ember"):
                # Should not raise
                await update_user_activity(user_id="user_err", is_chat_request=False)

        assert "Failed to update user activity" in caplog.text

    @pytest.mark.asyncio
    async def test_session_creation_error_is_caught(self, caplog: pytest.LogCaptureFixture) -> None:
        """If AsyncSessionLocal() itself fails, the error is caught and logged."""
        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            side_effect=RuntimeError("pool exhausted"),
        ):
            with caplog.at_level(logging.WARNING, logger="ember"):
                await update_user_activity(user_id="user_pool", is_chat_request=False)

        assert "Failed to update user activity" in caplog.text

    @pytest.mark.asyncio
    async def test_non_chat_upsert_sql_has_correct_structure(self) -> None:
        """Non-chat upsert SQL includes INSERT with ON CONFLICT DO UPDATE."""
        session_mock = AsyncMock()
        ctx = _mock_session_factory(session_mock)

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            await update_user_activity(user_id="user_sql", is_chat_request=False)

        sql_text = str(session_mock.execute.call_args[0][0].text)
        assert "INSERT INTO user_activity" in sql_text
        assert "ON CONFLICT (user_id) DO UPDATE" in sql_text
        assert "updated_at" in sql_text

    @pytest.mark.asyncio
    async def test_chat_upsert_sql_has_correct_structure(self) -> None:
        """Chat upsert SQL includes last_chat_at in both INSERT and UPDATE."""
        session_mock = AsyncMock()
        ctx = _mock_session_factory(session_mock)

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            await update_user_activity(user_id="user_sql_chat", is_chat_request=True)

        sql_text = str(session_mock.execute.call_args[0][0].text)
        assert "INSERT INTO user_activity" in sql_text
        assert "ON CONFLICT (user_id) DO UPDATE" in sql_text
        # Both INSERT VALUES and ON CONFLICT SET should reference last_chat_at
        assert sql_text.count("last_chat_at") >= 2

    @pytest.mark.asyncio
    async def test_function_returns_none(self) -> None:
        """update_user_activity always returns None."""
        session_mock = AsyncMock()
        ctx = _mock_session_factory(session_mock)

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            result = await update_user_activity(user_id="user_ret", is_chat_request=False)

        assert result is None
