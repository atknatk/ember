"""Activity tracking middleware for updating user_activity on authenticated requests.

Updates last_active_at on every authenticated request, and additionally
last_chat_at when the request is POST /api/v1/characters/{id}/messages.
The update runs as a background task after the response is sent, adding
zero latency to the request. Fail-open: errors are logged but never
propagate to the caller.
"""

from __future__ import annotations

import logging
import re

from starlette.background import BackgroundTask, BackgroundTasks
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.middleware.request_id import _extract_sub_from_jwt
from app.services.activity_service import update_user_activity

logger = logging.getLogger("ember")

# Matches POST /api/v1/characters/{uuid-or-id}/messages
_CHAT_PATH_RE = re.compile(r"^/api/v1/characters/[^/]+/messages$")


class ActivityTrackingMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that tracks user activity via background upserts.

    On every authenticated request, schedules a background task to update
    the user_activity table. For chat requests (POST to the messages
    endpoint), both last_active_at and last_chat_at are updated.

    The middleware is fail-open: if any error occurs during setup,
    the request proceeds normally without activity tracking.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process request and schedule activity update as a background task."""
        # Always call next first — never delay the response
        response = await call_next(request)

        try:
            # Extract user identity from JWT (lightweight, no signature check)
            sub = _extract_sub_from_jwt(request)
            if sub is None:
                return response

            # Determine if this is a chat request
            is_chat = (
                request.method == "POST"
                and _CHAT_PATH_RE.match(request.url.path) is not None
            )

            # Schedule the activity update as a background task
            activity_task = BackgroundTask(
                update_user_activity,
                user_id=sub,
                is_chat_request=is_chat,
            )

            # Chain with any existing background task on the response
            if response.background is not None:
                tasks = BackgroundTasks()
                tasks.tasks.append(response.background)  # type: ignore[arg-type]
                tasks.tasks.append(activity_task)
                response.background = tasks
            else:
                response.background = activity_task

        except Exception:
            logger.warning(
                "Activity tracking middleware error — skipping update",
                exc_info=True,
            )

        return response
