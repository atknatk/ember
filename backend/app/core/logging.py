"""Structured logging configuration for the Ember backend.

JSON format in production (debug=False), human-readable in development (debug=True).
Logger name: 'ember'. Level configurable via LOG_LEVEL env var.
"""

from __future__ import annotations

import logging
import sys


def setup_logging(*, log_level: str = "INFO", debug: bool = False) -> None:
    """Configure application-wide logging.

    Args:
        log_level: The logging level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        debug: When True, use human-readable format. When False, use JSON format.
    """
    root_logger = logging.getLogger("ember")
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates on re-init
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)

    if debug:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    else:
        # JSON-style structured logging for production
        formatter = logging.Formatter(
            '{"time":"%(asctime)s","level":"%(levelname)s",'
            '"logger":"%(name)s","message":"%(message)s"}',
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Suppress overly verbose third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.DEBUG if debug else logging.WARNING,
    )
