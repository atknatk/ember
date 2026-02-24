"""Tests for the structured logging configuration.

Verifies setup_logging configures the 'ember' logger correctly
in both debug (human-readable) and production (JSON) modes.
"""

from __future__ import annotations

import logging

import pytest

from app.core.logging import setup_logging


@pytest.fixture(autouse=True)
def _reset_ember_logger() -> None:
    """Reset the ember logger handlers before each test to avoid cross-contamination."""
    ember_logger = logging.getLogger("ember")
    ember_logger.handlers.clear()
    ember_logger.setLevel(logging.WARNING)


@pytest.mark.asyncio
async def test_setup_logging_creates_ember_logger_handler() -> None:
    """setup_logging must add at least one handler to the 'ember' logger."""
    setup_logging(log_level="INFO", debug=True)
    ember_logger = logging.getLogger("ember")
    assert len(ember_logger.handlers) >= 1


@pytest.mark.asyncio
async def test_setup_logging_sets_log_level() -> None:
    """setup_logging must set the logger level to the specified level."""
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
async def test_setup_logging_warning_level() -> None:
    """setup_logging with WARNING level sets the logger to WARNING."""
    setup_logging(log_level="WARNING", debug=True)
    ember_logger = logging.getLogger("ember")
    assert ember_logger.level == logging.WARNING


@pytest.mark.asyncio
async def test_setup_logging_debug_mode_human_readable() -> None:
    """In debug mode, formatter should use human-readable format (not JSON)."""
    setup_logging(log_level="INFO", debug=True)
    ember_logger = logging.getLogger("ember")
    handler = ember_logger.handlers[0]
    format_str = handler.formatter._fmt
    # Human-readable format includes pipe separators
    assert "|" in format_str
    # Should NOT be JSON format
    assert '{"time"' not in format_str


@pytest.mark.asyncio
async def test_setup_logging_production_mode_json() -> None:
    """In production mode (debug=False), formatter should use JSON format."""
    setup_logging(log_level="INFO", debug=False)
    ember_logger = logging.getLogger("ember")
    handler = ember_logger.handlers[0]
    format_str = handler.formatter._fmt
    # JSON format includes curly braces and JSON keys
    assert '{"time"' in format_str


@pytest.mark.asyncio
async def test_setup_logging_does_not_duplicate_handlers() -> None:
    """Calling setup_logging twice must not create duplicate handlers."""
    setup_logging(log_level="INFO", debug=True)
    setup_logging(log_level="DEBUG", debug=True)
    ember_logger = logging.getLogger("ember")
    assert len(ember_logger.handlers) == 1


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
