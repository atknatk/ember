"""FastAPI application factory for the Ember backend.

Creates the app instance with lifespan management, CORS middleware,
request ID middleware, route registration, and global exception handling.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.logging import setup_logging
from app.core.rate_limit import RateLimiter
from app.core.sentry import init_sentry
from app.db.session import engine
from app.middleware.activity_tracking import ActivityTrackingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_id import RequestIDMiddleware
from app.routes import auth, characters, chat, health, media, memories, onboarding, profile

logger = logging.getLogger("ember")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle."""
    init_sentry()
    setup_logging(log_level=settings.log_level, debug=settings.debug)
    logger.info("Ember API starting up")
    yield
    logger.info("Ember API shutting down")
    await engine.dispose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="Ember API",
        version=settings.app_version,
        lifespan=lifespan,
        openapi_tags=[
            {"name": "health", "description": "Health check and dependency status"},
            {"name": "auth", "description": "Authentication (register, login, refresh)"},
            {"name": "characters", "description": "Character CRUD"},
            {"name": "chat", "description": "Message sending (SSE) and history"},
            {"name": "memories", "description": "Mem0 memory retrieval and deletion"},
            {"name": "media", "description": "S3 presigned URL generation"},
            {"name": "onboarding", "description": "Onboarding flow completion"},
            {"name": "profile", "description": "User profile management"},
        ],
    )

    # Middleware registration order: Starlette applies in reverse order.
    # Last registered = outermost in request flow.
    # Target flow: RequestID -> CORS -> RateLimit -> ActivityTracking -> route

    # Activity tracking middleware (innermost — only runs for non-rate-limited requests)
    app.add_middleware(ActivityTrackingMiddleware)

    # Rate limiting middleware
    rate_limiter = RateLimiter(
        group_limits={
            "chat": settings.rate_limit_chat,
            "write": settings.rate_limit_write,
            "read": settings.rate_limit_read,
        },
        exempt_paths={"/api/v1/health"},
    )
    app.state.rate_limiter = rate_limiter
    app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)

    # CORS middleware (middle layer)
    origins = [o.strip() for o in settings.cors_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request ID middleware (outermost — registered last)
    app.add_middleware(RequestIDMiddleware)

    # Route registration
    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(characters.router, prefix="/api/v1/characters", tags=["characters"])
    app.include_router(chat.router, prefix="/api/v1/characters", tags=["chat"])
    app.include_router(memories.global_router, prefix="/api/v1", tags=["memories"])
    app.include_router(memories.character_router, prefix="/api/v1/characters", tags=["memories"])
    app.include_router(media.router, prefix="/api/v1/media", tags=["media"])
    app.include_router(onboarding.router, prefix="/api/v1/onboarding", tags=["onboarding"])
    app.include_router(profile.router, prefix="/api/v1", tags=["profile"])

    # Global exception handler
    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    return app


app = create_app()
