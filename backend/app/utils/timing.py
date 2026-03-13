"""Timing utility for instrumenting external API calls.

Provides an async context manager that logs the duration and success/failure
of external service calls (Mem0, Claude, S3, Cognito JWKS) as structured
log entries. Never swallows exceptions from the wrapped call.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

logger = logging.getLogger("ember")


@asynccontextmanager
async def log_external_call(
    service: str,
    operation: str,
) -> AsyncGenerator[None, None]:
    """Async context manager that times an external API call and logs the result.

    Usage:
        async with log_external_call("mem0", "search"):
            results = await mem0_client.search(...)

    Logs a structured event with service, operation, duration_ms, and success fields.
    On exception, logs success=false with the error type, then re-raises.

    Args:
        service: The external service name (e.g., "mem0", "claude", "s3", "cognito").
        operation: The operation being performed (e.g., "search", "stream", "add").
    """
    start = time.monotonic()
    try:
        yield
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "external_call",
            extra={
                "service": service,
                "operation": operation,
                "duration_ms": duration_ms,
                "success": True,
            },
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning(
            "external_call",
            extra={
                "service": service,
                "operation": operation,
                "duration_ms": duration_ms,
                "success": False,
                "error": type(exc).__name__,
            },
        )
        raise
