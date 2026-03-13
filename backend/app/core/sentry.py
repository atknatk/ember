"""Sentry error tracking integration for the Ember backend.

Initializes Sentry SDK when a DSN is configured. Includes a before_send
hook that scrubs sensitive data (Authorization headers) from events.
Sentry is entirely optional — the app functions normally without it.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger("ember")


def _scrub_event(
    event: dict[str, Any],
    hint: dict[str, Any],
) -> dict[str, Any] | None:
    """Remove sensitive data from Sentry events before transmission.

    Strips Authorization header values from request data to prevent
    JWT tokens from being sent to Sentry.
    """
    request_data = event.get("request", {})
    headers = request_data.get("headers", {})
    if isinstance(headers, dict) and "Authorization" in headers:
        headers["Authorization"] = "[Filtered]"
    elif isinstance(headers, dict) and "authorization" in headers:
        headers["authorization"] = "[Filtered]"
    return event


def init_sentry() -> None:
    """Initialize Sentry SDK if a DSN is configured.

    Called during application startup. If SENTRY_DSN is empty or not set,
    Sentry is not initialized and the function returns silently.
    If initialization fails, a warning is logged but no exception is raised.
    """
    dsn = settings.sentry_dsn
    if not dsn:
        logger.info("Sentry DSN not configured — Sentry disabled")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=settings.sentry_environment,
            release=settings.app_version,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            send_default_pii=False,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
            ],
            before_send=_scrub_event,
        )
        logger.info(
            "Sentry initialized (environment=%s)",
            settings.sentry_environment,
        )
    except Exception:
        logger.warning("Sentry initialization failed — continuing without Sentry", exc_info=True)
