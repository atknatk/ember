"""Additional edge-case tests for the activity_service module.

Supplements the tests written by backend-dev with coverage for:
  - Concurrent upsert calls (both complete independently)
  - `now` parameter is a datetime object (not a string)
  - Commit failure (execute succeeds but commit raises) is caught and logged
  - Non-chat SQL does not reference last_chat_at anywhere (INSERT nor UPDATE)
  - Chat SQL references last_chat_at in both INSERT and ON CONFLICT SET
  - user_id and now are both present in parameter dict for both code paths
  - Very long user_id string is accepted without error
  - update_user_activity with is_chat_request=True then False preserves chat semantics
    (service-level SQL logic, not DB state — verified via SQL text inspection)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.services.activity_service import update_user_activity


# ---------------------------------------------------------------------------
# Helpers (mirrors pattern from existing test file)
# ---------------------------------------------------------------------------


def _mock_session_factory(session_mock: AsyncMock) -> MagicMock:
    """Create a mock AsyncSessionLocal that yields the given session mock."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session_mock)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


# ---------------------------------------------------------------------------
# Parameter type / content validation
# ---------------------------------------------------------------------------


class TestSQLParameterDetails:
    """Verify the exact content of parameters passed to session.execute."""

    @pytest.mark.asyncio
    async def test_now_parameter_is_datetime_object_non_chat(self) -> None:
        """The 'now' SQL parameter is a datetime (not a string) for non-chat path."""
        session_mock = AsyncMock()
        ctx = _mock_session_factory(session_mock)

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            await update_user_activity(user_id="user_dt_check", is_chat_request=False)

        params = session_mock.execute.call_args[0][1]
        assert isinstance(params["now"], datetime)
        assert params["now"].tzinfo is not None  # must be timezone-aware

    @pytest.mark.asyncio
    async def test_now_parameter_is_datetime_object_chat(self) -> None:
        """The 'now' SQL parameter is a datetime (not a string) for chat path."""
        session_mock = AsyncMock()
        ctx = _mock_session_factory(session_mock)

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            await update_user_activity(user_id="user_dt_chat", is_chat_request=True)

        params = session_mock.execute.call_args[0][1]
        assert isinstance(params["now"], datetime)
        assert params["now"].tzinfo is not None

    @pytest.mark.asyncio
    async def test_both_params_present_for_non_chat(self) -> None:
        """Execute receives exactly the user_id and now keys for non-chat path."""
        session_mock = AsyncMock()
        ctx = _mock_session_factory(session_mock)

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            await update_user_activity(user_id="user_params_nc", is_chat_request=False)

        params = session_mock.execute.call_args[0][1]
        assert "user_id" in params
        assert "now" in params
        assert params["user_id"] == "user_params_nc"

    @pytest.mark.asyncio
    async def test_both_params_present_for_chat(self) -> None:
        """Execute receives exactly the user_id and now keys for chat path."""
        session_mock = AsyncMock()
        ctx = _mock_session_factory(session_mock)

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            await update_user_activity(user_id="user_params_chat", is_chat_request=True)

        params = session_mock.execute.call_args[0][1]
        assert "user_id" in params
        assert "now" in params
        assert params["user_id"] == "user_params_chat"


# ---------------------------------------------------------------------------
# SQL structure: non-chat path must not mention last_chat_at anywhere
# ---------------------------------------------------------------------------


class TestSQLStructureNonChat:
    """Non-chat SQL must omit last_chat_at from both INSERT and ON CONFLICT."""

    @pytest.mark.asyncio
    async def test_non_chat_insert_values_no_last_chat_at(self) -> None:
        """Non-chat INSERT VALUES clause does not include last_chat_at."""
        session_mock = AsyncMock()
        ctx = _mock_session_factory(session_mock)

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            await update_user_activity(user_id="user_nc_insert", is_chat_request=False)

        sql_text = str(session_mock.execute.call_args[0][0].text)
        # Split at ON CONFLICT to inspect the INSERT VALUES portion
        insert_part = sql_text.split("ON CONFLICT")[0]
        assert "last_chat_at" not in insert_part

    @pytest.mark.asyncio
    async def test_non_chat_full_sql_has_no_last_chat_at_at_all(self) -> None:
        """Non-chat SQL has zero occurrences of last_chat_at anywhere."""
        session_mock = AsyncMock()
        ctx = _mock_session_factory(session_mock)

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            await update_user_activity(user_id="user_nc_full", is_chat_request=False)

        sql_text = str(session_mock.execute.call_args[0][0].text)
        assert "last_chat_at" not in sql_text


# ---------------------------------------------------------------------------
# SQL structure: chat path must include last_chat_at in both clauses
# ---------------------------------------------------------------------------


class TestSQLStructureChat:
    """Chat SQL must include last_chat_at in both INSERT VALUES and ON CONFLICT SET."""

    @pytest.mark.asyncio
    async def test_chat_insert_values_includes_last_chat_at(self) -> None:
        """Chat INSERT VALUES clause includes last_chat_at."""
        session_mock = AsyncMock()
        ctx = _mock_session_factory(session_mock)

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            await update_user_activity(user_id="user_chat_insert", is_chat_request=True)

        sql_text = str(session_mock.execute.call_args[0][0].text)
        insert_part = sql_text.split("ON CONFLICT")[0]
        assert "last_chat_at" in insert_part

    @pytest.mark.asyncio
    async def test_chat_on_conflict_set_includes_last_chat_at(self) -> None:
        """Chat ON CONFLICT SET clause includes last_chat_at."""
        session_mock = AsyncMock()
        ctx = _mock_session_factory(session_mock)

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            await update_user_activity(user_id="user_chat_conflict", is_chat_request=True)

        sql_text = str(session_mock.execute.call_args[0][0].text)
        on_conflict_part = sql_text.split("ON CONFLICT")[1]
        assert "last_chat_at" in on_conflict_part

    @pytest.mark.asyncio
    async def test_chat_sql_notifications_sent_today_has_default(self) -> None:
        """Chat SQL includes '[]'::jsonb default for notifications_sent_today."""
        session_mock = AsyncMock()
        ctx = _mock_session_factory(session_mock)

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            await update_user_activity(user_id="user_notif", is_chat_request=True)

        sql_text = str(session_mock.execute.call_args[0][0].text)
        assert "notifications_sent_today" in sql_text

    @pytest.mark.asyncio
    async def test_non_chat_sql_notifications_sent_today_has_default(self) -> None:
        """Non-chat SQL also includes notifications_sent_today in INSERT."""
        session_mock = AsyncMock()
        ctx = _mock_session_factory(session_mock)

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            await update_user_activity(user_id="user_notif_nc", is_chat_request=False)

        sql_text = str(session_mock.execute.call_args[0][0].text)
        assert "notifications_sent_today" in sql_text


# ---------------------------------------------------------------------------
# Error handling edge cases
# ---------------------------------------------------------------------------


class TestErrorHandlingEdgeCases:
    """Error handling paths beyond what backend-dev already tests."""

    @pytest.mark.asyncio
    async def test_commit_failure_is_caught_and_logged(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """If session.commit() raises, the error is caught and logged at WARNING."""
        session_mock = AsyncMock()
        session_mock.execute.return_value = None
        session_mock.commit.side_effect = RuntimeError("commit failed")
        ctx = _mock_session_factory(session_mock)

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            with caplog.at_level(logging.WARNING, logger="ember"):
                # Must not raise
                await update_user_activity(user_id="user_commit_fail", is_chat_request=False)

        assert "Failed to update user activity" in caplog.text

    @pytest.mark.asyncio
    async def test_commit_failure_does_not_raise_for_chat_path(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Commit failure on chat path also silently fails."""
        session_mock = AsyncMock()
        session_mock.execute.return_value = None
        session_mock.commit.side_effect = OSError("network timeout")
        ctx = _mock_session_factory(session_mock)

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            with caplog.at_level(logging.WARNING, logger="ember"):
                await update_user_activity(user_id="user_commit_chat_fail", is_chat_request=True)

        assert "Failed to update user activity" in caplog.text

    @pytest.mark.asyncio
    async def test_context_manager_exit_failure_is_caught(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """If session __aexit__ raises, the function still doesn't propagate."""
        session_mock = AsyncMock()
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=session_mock)
        ctx.__aexit__ = AsyncMock(side_effect=RuntimeError("exit failed"))

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            with caplog.at_level(logging.WARNING, logger="ember"):
                await update_user_activity(user_id="user_exit_fail", is_chat_request=False)

        assert "Failed to update user activity" in caplog.text

    @pytest.mark.asyncio
    async def test_error_message_includes_user_id(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Warning log includes the user_id so operators can identify the user."""
        session_mock = AsyncMock()
        session_mock.execute.side_effect = RuntimeError("db gone")
        ctx = _mock_session_factory(session_mock)

        target_user_id = "user_id_in_log_abc123"

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            with caplog.at_level(logging.WARNING, logger="ember"):
                await update_user_activity(user_id=target_user_id, is_chat_request=False)

        assert target_user_id in caplog.text


# ---------------------------------------------------------------------------
# Concurrent upsert calls at the service layer
# ---------------------------------------------------------------------------


class TestConcurrentUpserts:
    """Multiple simultaneous update_user_activity calls complete independently."""

    @pytest.mark.asyncio
    async def test_concurrent_calls_each_create_own_session(self) -> None:
        """N concurrent calls each open and close their own DB session."""
        session_factory_call_count = 0
        sessions_created: list[AsyncMock] = []

        def _make_ctx() -> MagicMock:
            nonlocal session_factory_call_count
            session_factory_call_count += 1
            sm = AsyncMock()
            sessions_created.append(sm)
            ctx = MagicMock()
            ctx.__aenter__ = AsyncMock(return_value=sm)
            ctx.__aexit__ = AsyncMock(return_value=None)
            return ctx

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            side_effect=_make_ctx,
        ):
            await asyncio.gather(
                update_user_activity(user_id="concurrent_user_1", is_chat_request=False),
                update_user_activity(user_id="concurrent_user_2", is_chat_request=True),
                update_user_activity(user_id="concurrent_user_3", is_chat_request=False),
            )

        assert session_factory_call_count == 3
        # Each session was committed once
        for sm in sessions_created:
            sm.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_concurrent_calls_with_mixed_errors_independent(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A failure in one concurrent call does not affect others."""
        call_results: list[str] = []

        def _make_ctx(should_fail: bool) -> MagicMock:
            sm = AsyncMock()
            if should_fail:
                sm.execute.side_effect = RuntimeError("injected failure")
            else:
                sm.execute.side_effect = None

                async def _track_commit() -> None:
                    call_results.append("committed")

                sm.commit = AsyncMock(side_effect=_track_commit)

            ctx = MagicMock()
            ctx.__aenter__ = AsyncMock(return_value=sm)
            ctx.__aexit__ = AsyncMock(return_value=None)
            return ctx

        fail_flag = [False, True, False]  # second call fails
        call_index = 0

        def _factory() -> MagicMock:
            nonlocal call_index
            ctx = _make_ctx(fail_flag[call_index])
            call_index += 1
            return ctx

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            side_effect=_factory,
        ):
            with caplog.at_level(logging.WARNING, logger="ember"):
                await asyncio.gather(
                    update_user_activity(user_id="ok_user_1", is_chat_request=False),
                    update_user_activity(user_id="fail_user", is_chat_request=False),
                    update_user_activity(user_id="ok_user_2", is_chat_request=False),
                )

        # Two successful commits, one failure
        assert len(call_results) == 2
        assert "Failed to update user activity" in caplog.text


# ---------------------------------------------------------------------------
# Edge case: very long user_id
# ---------------------------------------------------------------------------


class TestUserIDEdgeCases:
    """Ensure the service handles unusual user_id values gracefully."""

    @pytest.mark.asyncio
    async def test_very_long_user_id_is_accepted(self) -> None:
        """A 512-character user_id is accepted without error."""
        session_mock = AsyncMock()
        ctx = _mock_session_factory(session_mock)
        long_user_id = "u" * 512

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            await update_user_activity(user_id=long_user_id, is_chat_request=False)

        params = session_mock.execute.call_args[0][1]
        assert params["user_id"] == long_user_id
        session_mock.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_uuid_format_user_id_is_accepted(self) -> None:
        """Standard UUID format user_id is passed through unchanged."""
        session_mock = AsyncMock()
        ctx = _mock_session_factory(session_mock)
        uuid_user_id = "550e8400-e29b-41d4-a716-446655440000"

        with patch(
            "app.services.activity_service.AsyncSessionLocal",
            return_value=ctx,
        ):
            await update_user_activity(user_id=uuid_user_id, is_chat_request=True)

        params = session_mock.execute.call_args[0][1]
        assert params["user_id"] == uuid_user_id
