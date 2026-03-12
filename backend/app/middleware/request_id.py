"""Request ID middleware for correlating log entries across a single request.

Generates or propagates an X-Request-ID header on every request/response.
Binds request_id (and optionally user_id) to structlog contextvars so all
log entries within the request lifecycle include them automatically.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger("ember")

# Valid request ID: 1-128 characters, alphanumeric plus hyphens
_VALID_REQUEST_ID_RE = re.compile(r"^[a-zA-Z0-9\-]{1,128}$")


def _extract_sub_from_jwt(request: Request) -> str | None:
    """Lightweight JWT sub extraction without signature verification.

    Parses the Authorization header to extract the sub claim from the
    JWT payload via base64 decoding only. Returns None on any failure.
    """
    try:
        auth_header = request.headers.get("authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]
        parts = token.split(".")
        if len(parts) != 3:  # noqa: PLR2004
            return None

        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:  # noqa: PLR2004
            payload_b64 += "=" * padding

        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes)
        sub = payload.get("sub")
        if sub and isinstance(sub, str):
            return sub
        return None
    except Exception:
        return None


class RequestIDMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that assigns and propagates X-Request-ID headers.

    - Reads incoming X-Request-ID header (uses it if valid format).
    - Generates a UUID v4 if no valid header is provided.
    - Binds request_id and optionally user_id to structlog contextvars.
    - Sets Sentry tag for request_id correlation.
    - Logs request start and completion with method, path, status, and duration.
    - Clears contextvars after response to prevent leakage.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process request with request ID tracking and logging."""
        # Step 1: Extract or generate request_id
        client_request_id = request.headers.get("x-request-id", "")
        if client_request_id and _VALID_REQUEST_ID_RE.match(client_request_id):
            request_id = client_request_id
        else:
            request_id = str(uuid.uuid4())

        # Step 2: Bind request_id to structlog contextvars
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        # Step 3: Optionally bind user_id from JWT
        user_id = _extract_sub_from_jwt(request)
        if user_id:
            structlog.contextvars.bind_contextvars(user_id=user_id)

        # Step 4: Set Sentry tag for correlation
        try:
            import sentry_sdk

            sentry_sdk.set_tag("request_id", request_id)
        except Exception:
            pass

        # Step 5: Log request start
        logger.info(
            "request_started",
            extra={"method": request.method, "path": request.url.path},
        )

        # Step 6: Call next middleware/handler, measure elapsed time
        start_time = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.error(
                "request_failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                },
            )
            structlog.contextvars.clear_contextvars()
            raise

        duration_ms = int((time.monotonic() - start_time) * 1000)
        status_code = response.status_code

        # Step 7: Log request completion at appropriate level
        log_extra = {
            "method": request.method,
            "path": request.url.path,
            "status_code": status_code,
            "duration_ms": duration_ms,
        }

        if status_code < 400:  # noqa: PLR2004
            logger.info("request_completed", extra=log_extra)
        elif status_code < 500:  # noqa: PLR2004
            logger.warning("request_completed", extra=log_extra)
        else:
            logger.error("request_completed", extra=log_extra)

        # Step 8: Add X-Request-ID to response headers
        response.headers["X-Request-ID"] = request_id

        # Step 9: Clear contextvars
        structlog.contextvars.clear_contextvars()

        return response
