"""Structured logging configuration for the Ember backend using structlog.

JSON format in production (debug=False), human-readable in development (debug=True).
All existing logging.getLogger() calls continue to work via stdlib integration.
Context variables (request_id, user_id) are automatically merged into every log entry.
"""

from __future__ import annotations

import logging
import sys

import structlog


def setup_logging(*, log_level: str = "INFO", debug: bool = False) -> None:
    """Configure application-wide structured logging with structlog.

    Args:
        log_level: The logging level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        debug: When True, use human-readable ConsoleRenderer.
               When False, use JSON renderer for production.
    """
    # Determine the numeric log level, falling back to INFO for invalid values
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Shared structlog processors applied to every log entry
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if debug:
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    # Configure structlog for structlog.get_logger() calls
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib logging to pass through structlog's ProcessorFormatter.
    # The ProcessorFormatter applies shared processors to stdlib log records
    # so that logging.getLogger("ember").info("msg") produces structured output.
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    # Set up root logger handler
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(numeric_level)

    # Set the ember logger level explicitly
    ember_logger = logging.getLogger("ember")
    ember_logger.setLevel(numeric_level)

    # Suppress overly verbose third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.DEBUG if debug else logging.WARNING,
    )
