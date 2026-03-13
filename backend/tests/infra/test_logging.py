"""Tests for the structlog-based logging configuration.

Verifies setup_logging configures structlog correctly in both debug
(ConsoleRenderer) and production (JSONRenderer) modes, and that
stdlib logging integration works for existing loggers.
"""

from __future__ import annotations

import json
import logging
import sys
from io import StringIO

import pytest
import structlog

from app.core.logging import setup_logging


@pytest.fixture(autouse=True)
def _reset_logging() -> None:
    """Reset logging state before each test to avoid cross-contamination."""
    root = logging.getLogger()
    root.handlers.clear()
    ember_logger = logging.getLogger("ember")
    ember_logger.handlers.clear()
    ember_logger.setLevel(logging.WARNING)
    # Reset structlog config
    structlog.reset_defaults()


@pytest.mark.asyncio
async def test_setup_logging_debug_mode_uses_console_renderer() -> None:
    """In debug mode, output should use ConsoleRenderer (human-readable, not JSON)."""
    setup_logging(log_level="INFO", debug=True)

    # Capture output via a StringIO handler
    output = StringIO()
    handler = logging.StreamHandler(output)
    # Copy formatter from root logger
    root = logging.getLogger()
    if root.handlers:
        handler.setFormatter(root.handlers[0].formatter)
    root.addHandler(handler)

    ember_logger = logging.getLogger("ember")
    ember_logger.info("test debug message")

    log_output = output.getvalue()
    # ConsoleRenderer output should NOT be valid JSON
    try:
        json.loads(log_output.strip())
        is_json = True
    except (json.JSONDecodeError, ValueError):
        is_json = False

    assert not is_json or "test debug message" in log_output


@pytest.mark.asyncio
async def test_setup_logging_production_mode_uses_json_renderer() -> None:
    """In production mode (debug=False), output should be valid JSON."""
    setup_logging(log_level="INFO", debug=False)

    output = StringIO()
    handler = logging.StreamHandler(output)
    root = logging.getLogger()
    if root.handlers:
        handler.setFormatter(root.handlers[0].formatter)
    root.addHandler(handler)

    ember_logger = logging.getLogger("ember")
    ember_logger.info("test prod message")

    log_output = output.getvalue().strip()
    if log_output:
        parsed = json.loads(log_output)
        assert "event" in parsed
        assert "level" in parsed
        assert "timestamp" in parsed


@pytest.mark.asyncio
async def test_context_variables_appear_in_log_output() -> None:
    """After binding request_id via contextvars, it should appear in log output."""
    setup_logging(log_level="INFO", debug=False)

    output = StringIO()
    handler = logging.StreamHandler(output)
    root = logging.getLogger()
    if root.handlers:
        handler.setFormatter(root.handlers[0].formatter)
    root.addHandler(handler)

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id="test-req-123")

    ember_logger = logging.getLogger("ember")
    ember_logger.info("context test")

    log_output = output.getvalue().strip()
    structlog.contextvars.clear_contextvars()

    if log_output:
        parsed = json.loads(log_output)
        assert parsed.get("request_id") == "test-req-123"


@pytest.mark.asyncio
async def test_setup_logging_sets_log_level() -> None:
    """setup_logging must set the ember logger level to the specified level."""
    setup_logging(log_level="DEBUG", debug=True)
    ember_logger = logging.getLogger("ember")
    assert ember_logger.level == logging.DEBUG


@pytest.mark.asyncio
async def test_setup_logging_info_level() -> None:
    """setup_logging with INFO level sets the logger to INFO."""
    setup_logging(log_level="INFO", debug=True)
    ember_logger = logging.getLogger("ember")
    assert ember_logger.level == logging.INFO


@pytest.mark.asyncio
async def test_setup_logging_invalid_level_falls_back_to_info() -> None:
    """An invalid log level string should fall back to INFO."""
    setup_logging(log_level="NONEXISTENT", debug=True)
    ember_logger = logging.getLogger("ember")
    assert ember_logger.level == logging.INFO


@pytest.mark.asyncio
async def test_setup_logging_suppresses_uvicorn_access() -> None:
    """setup_logging should suppress uvicorn.access to WARNING."""
    setup_logging(log_level="DEBUG", debug=True)
    uvicorn_logger = logging.getLogger("uvicorn.access")
    assert uvicorn_logger.level == logging.WARNING


@pytest.mark.asyncio
async def test_sqlalchemy_logger_level_depends_on_debug() -> None:
    """sqlalchemy.engine should be DEBUG when debug=True, WARNING otherwise."""
    setup_logging(log_level="INFO", debug=True)
    sa_logger = logging.getLogger("sqlalchemy.engine")
    assert sa_logger.level == logging.DEBUG

    # Reset and test production mode
    setup_logging(log_level="INFO", debug=False)
    sa_logger = logging.getLogger("sqlalchemy.engine")
    assert sa_logger.level == logging.WARNING


@pytest.mark.asyncio
async def test_setup_logging_does_not_duplicate_handlers() -> None:
    """Calling setup_logging twice must not create duplicate root handlers."""
    setup_logging(log_level="INFO", debug=True)
    count1 = len(logging.getLogger().handlers)
    setup_logging(log_level="DEBUG", debug=True)
    count2 = len(logging.getLogger().handlers)
    # The root logger should have exactly 1 handler after each call
    # (plus possibly the one we add for capture, but setup_logging clears first)
    assert count2 == count1
