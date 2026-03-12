"""ASGI middleware for per-user rate limiting.

Integrates the ``RateLimiter`` into the FastAPI request lifecycle using
Starlette's ``BaseHTTPMiddleware``. Adds rate limit response headers to
all responses and returns HTTP 429 when the limit is exceeded.
"""

from __future__ import annotations

import logging

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.rate_limit import RateLimiter, extract_user_key

logger = logging.getLogger("ember")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware that enforces per-user request quotas.

    Extracts the user identity from the request (JWT sub or client IP),
    classifies the request into a rate limit group, and either allows
    the request through (adding rate limit headers) or returns a 429
    response.

    The middleware is fail-open: if any internal error occurs during
    rate limit processing, the request is allowed through to prevent
    the rate limiter from blocking all API traffic.
    """

    def __init__(self, app: ASGIApp, rate_limiter: RateLimiter) -> None:
        super().__init__(app)
        self._rate_limiter = rate_limiter

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Process the request through rate limiting.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or route handler.

        Returns:
            The response, with rate limit headers added. Returns a 429
            JSONResponse if the rate limit is exceeded.
        """
        try:
            group = self._rate_limiter.classify_request(
                request.method,
                request.url.path,
            )

            # Exempt paths bypass rate limiting entirely
            if group is None:
                return await call_next(request)

            key = extract_user_key(request)
            allowed, headers = self._rate_limiter.check(key, group)

            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded"},
                    headers=headers,
                )

            response = await call_next(request)

            # Add rate limit headers to successful responses
            for header_name, header_value in headers.items():
                response.headers[header_name] = header_value

            return response

        except Exception:
            logger.exception("Rate limiting middleware error — failing open")
            return await call_next(request)
