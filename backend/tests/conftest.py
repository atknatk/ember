"""Shared test fixtures for the Ember backend test suite.

Provides an AsyncClient fixture using httpx.ASGITransport for testing
endpoints without a running server. Database dependency is overridden
with a no-op for tests that do not require DB access.

Environment is configured for testing before app imports.
"""

from __future__ import annotations

import os

# Set test environment before any app imports.
# This prevents config.py from attempting AWS Secrets Manager calls
# and db/session.py from requiring a real database URL.
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://ember:ember@localhost:5432/ember_test")

from collections.abc import AsyncGenerator  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.dependencies import get_db  # noqa: E402
from app.main import app  # noqa: E402


async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
    """Yield a mock database session for tests that do not need a real DB."""
    yield AsyncMock()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client for testing FastAPI endpoints."""
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
