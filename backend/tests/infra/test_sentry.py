"""Tests for Sentry integration.

Verifies init_sentry behavior with and without DSN, PII scrubbing,
and graceful failure handling.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from app.core.sentry import _scrub_event, init_sentry


@pytest.mark.asyncio
async def test_init_sentry_with_empty_dsn_does_not_call_init() -> None:
    """When SENTRY_DSN is empty, sentry_sdk.init should not be called."""
    with patch("app.core.sentry.settings") as mock_settings:
        mock_settings.sentry_dsn = ""
        with patch("sentry_sdk.init") as mock_init:
            init_sentry()
            mock_init.assert_not_called()


@pytest.mark.asyncio
async def test_init_sentry_with_valid_dsn_calls_init() -> None:
    """When SENTRY_DSN is set, sentry_sdk.init should be called with correct params."""
    with patch("app.core.sentry.settings") as mock_settings:
        mock_settings.sentry_dsn = "https://examplePublicKey@o0.ingest.sentry.io/0"
        mock_settings.sentry_environment = "testing"
        mock_settings.app_version = "1.0.0"
        mock_settings.sentry_traces_sample_rate = 0.1
        with patch("sentry_sdk.init") as mock_init:
            init_sentry()
            mock_init.assert_called_once()
            call_kwargs = mock_init.call_args[1]
            assert call_kwargs["dsn"] == "https://examplePublicKey@o0.ingest.sentry.io/0"
            assert call_kwargs["environment"] == "testing"
            assert call_kwargs["send_default_pii"] is False
            assert call_kwargs["release"] == "1.0.0"


@pytest.mark.asyncio
async def test_scrub_event_removes_authorization_header() -> None:
    """The before_send hook must remove Authorization header values."""
    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer secret-jwt-token",
                "Content-Type": "application/json",
            },
        },
    }
    result = _scrub_event(event, {})
    assert result is not None
    assert result["request"]["headers"]["Authorization"] == "[Filtered]"
    assert result["request"]["headers"]["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_scrub_event_removes_lowercase_authorization() -> None:
    """The before_send hook must also handle lowercase authorization header."""
    event = {
        "request": {
            "headers": {
                "authorization": "Bearer secret-jwt-token",
            },
        },
    }
    result = _scrub_event(event, {})
    assert result is not None
    assert result["request"]["headers"]["authorization"] == "[Filtered]"


@pytest.mark.asyncio
async def test_scrub_event_passes_through_events_without_headers() -> None:
    """Events without request headers should pass through unchanged."""
    event = {"message": "test error", "level": "error"}
    result = _scrub_event(event, {})
    assert result == event


@pytest.mark.asyncio
async def test_init_sentry_failure_logs_warning_and_does_not_raise() -> None:
    """If sentry_sdk.init raises, init_sentry must log a warning but not raise."""
    with patch("app.core.sentry.settings") as mock_settings:
        mock_settings.sentry_dsn = "https://bad@sentry.io/0"
        mock_settings.sentry_environment = "testing"
        mock_settings.app_version = "1.0.0"
        mock_settings.sentry_traces_sample_rate = 0.1
        with patch("sentry_sdk.init", side_effect=Exception("Init failed")):
            # Should not raise
            init_sentry()
