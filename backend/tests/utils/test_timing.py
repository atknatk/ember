"""Tests for the external call timing utility.

Verifies that log_external_call correctly logs duration, success/failure,
service and operation names, and that exceptions are never swallowed.
"""

from __future__ import annotations

import logging

import pytest

from app.utils.timing import log_external_call


class _RecordHandler(logging.Handler):
    """Simple handler that collects LogRecords for test assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def _log_capture() -> _RecordHandler:  # type: ignore[return]
    """Capture ember logger records for assertions."""
    handler = _RecordHandler()
    ember_logger = logging.getLogger("ember")
    original_level = ember_logger.level
    ember_logger.setLevel(logging.DEBUG)
    ember_logger.addHandler(handler)
    yield handler  # type: ignore[misc]
    ember_logger.removeHandler(handler)
    ember_logger.setLevel(original_level)


@pytest.mark.asyncio
async def test_successful_call_logs_duration_and_success(
    _log_capture: _RecordHandler,
) -> None:
    """A successful external call should log duration_ms and success=True."""
    async with log_external_call("mem0", "search"):
        pass  # Simulate a successful call

    timing_records = [r for r in _log_capture.records if r.msg == "external_call"]
    assert len(timing_records) == 1
    record = timing_records[0]
    assert record.levelno == logging.INFO
    assert record.__dict__["service"] == "mem0"
    assert record.__dict__["operation"] == "search"
    assert record.__dict__["success"] is True
    assert isinstance(record.__dict__["duration_ms"], int)
    assert record.__dict__["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_failed_call_logs_duration_and_error(
    _log_capture: _RecordHandler,
) -> None:
    """A failed external call should log success=False with error type name."""
    with pytest.raises(ValueError, match="test error"):
        async with log_external_call("claude", "stream"):
            raise ValueError("test error")

    timing_records = [r for r in _log_capture.records if r.msg == "external_call"]
    assert len(timing_records) == 1
    record = timing_records[0]
    assert record.levelno == logging.WARNING
    assert record.__dict__["service"] == "claude"
    assert record.__dict__["operation"] == "stream"
    assert record.__dict__["success"] is False
    assert record.__dict__["error"] == "ValueError"
    assert isinstance(record.__dict__["duration_ms"], int)


@pytest.mark.asyncio
async def test_timing_does_not_swallow_exceptions() -> None:
    """Exceptions raised inside the context manager must propagate to the caller."""
    with pytest.raises(RuntimeError, match="propagate me"):
        async with log_external_call("s3", "upload"):
            raise RuntimeError("propagate me")


@pytest.mark.asyncio
async def test_service_and_operation_in_log(
    _log_capture: _RecordHandler,
) -> None:
    """Service and operation names must appear in the log output."""
    async with log_external_call("cognito", "jwks_fetch"):
        pass

    timing_records = [r for r in _log_capture.records if r.msg == "external_call"]
    assert len(timing_records) == 1
    assert timing_records[0].__dict__["service"] == "cognito"
    assert timing_records[0].__dict__["operation"] == "jwks_fetch"


@pytest.mark.asyncio
async def test_duration_measured_correctly(
    _log_capture: _RecordHandler,
) -> None:
    """Duration should reflect actual elapsed time."""
    import asyncio

    async with log_external_call("test", "sleep"):
        await asyncio.sleep(0.05)

    timing_records = [r for r in _log_capture.records if r.msg == "external_call"]
    assert len(timing_records) == 1
    duration = timing_records[0].__dict__["duration_ms"]
    # Should be at least ~50ms but allow some tolerance
    assert duration >= 40
