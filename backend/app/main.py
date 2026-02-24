"""FastAPI application factory for the Ember backend.

Creates the app instance with lifespan management, CORS middleware,
route registration, and global exception handling.
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
from app.db.session import engine
from app.routes import auth, characters, chat, health, media, memories, onboarding

logger = logging.getLogger("ember")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle."""
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
    )

    # CORS middleware
    origins = [o.strip() for o in settings.cors_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Route registration
    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(characters.router, prefix="/api/v1/characters", tags=["characters"])
    app.include_router(chat.router, prefix="/api/v1/characters", tags=["chat"])
    app.include_router(memories.global_router, prefix="/api/v1", tags=["memories"])
    app.include_router(memories.character_router, prefix="/api/v1/characters", tags=["memories"])
    app.include_router(media.router, prefix="/api/v1/media", tags=["media"])
    app.include_router(onboarding.router, prefix="/api/v1/onboarding", tags=["onboarding"])

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
