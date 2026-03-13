"""Route-level tests for notification token endpoints.

Tests PUT /api/v1/notifications/token and DELETE /api/v1/notifications/token
via the FastAPI test client with mocked dependencies.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import uuid  # noqa: E402
from collections.abc import AsyncGenerator  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.dependencies import get_current_user, get_db  # noqa: E402
from app.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")


def _make_fake_profile(
    fcm_token: str | None = None,
) -> MagicMock:
    """Create a fake Profile-like object for dependency override."""
    profile = MagicMock()
    profile.id = FAKE_USER_ID
    profile.email = "test@ember.ai"
    profile.name = "Alex"
    profile.mem0_user_id = f"user_{FAKE_USER_ID}"
    profile.fcm_token = fcm_token
    profile.timezone = "UTC"
    profile.avatar_url = None
    profile.preferred_language = "en"
    profile.onboarding_completed = True
    profile.subscription_tier = "free"
    profile.subscription_expires_at = None
    profile.created_at = datetime.now(tz=UTC)
    profile.updated_at = datetime.now(tz=UTC)
    return profile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
    """Yield a mock database session."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.execute = AsyncMock()
    yield mock_db


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client with mocked DB and auth."""
    fake_profile = _make_fake_profile()

    async def override_user() -> MagicMock:
        return fake_profile

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unauthed_client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client without auth override."""
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# PUT /api/v1/notifications/token
# ---------------------------------------------------------------------------


class TestRegisterFcmToken:
    """Tests for PUT /api/v1/notifications/token."""

    @pytest.mark.asyncio
    async def test_register_valid_token(self, client: AsyncClient) -> None:
        """Test #1: Register FCM token with valid JWT returns 200."""
        resp = await client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": "valid-fcm-token-abc123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_register_without_auth(self, unauthed_client: AsyncClient) -> None:
        """Test #2: Register FCM token without JWT returns 401/403."""
        resp = await unauthed_client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": "some-token"},
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_register_empty_token(self, client: AsyncClient) -> None:
        """Test #3: Register FCM token with empty string returns 422."""
        resp = await client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": ""},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_token_too_long(self, client: AsyncClient) -> None:
        """Test #4: Register FCM token with string > 4096 chars returns 422."""
        resp = await client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": "x" * 4097},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_missing_body_field(self, client: AsyncClient) -> None:
        """Test #5: Register FCM token with missing body field returns 422."""
        resp = await client.put(
            "/api/v1/notifications/token",
            json={},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_idempotent(self, client: AsyncClient) -> None:
        """Test #6: Register same FCM token twice returns 200 both times."""
        for _ in range(2):
            resp = await client.put(
                "/api/v1/notifications/token",
                json={"fcm_token": "same-token-value"},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_register_updates_existing(self, client: AsyncClient) -> None:
        """Test #7: Register new FCM token replaces old one, returns 200."""
        resp1 = await client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": "old-token"},
        )
        assert resp1.status_code == 200

        resp2 = await client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": "new-token"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_register_max_length_token(self, client: AsyncClient) -> None:
        """Register FCM token at exactly 4096 chars succeeds."""
        resp = await client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": "x" * 4096},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_register_missing_content_type(self, client: AsyncClient) -> None:
        """Request without JSON body returns 422."""
        resp = await client.put("/api/v1/notifications/token")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/v1/notifications/token
# ---------------------------------------------------------------------------


class TestUnregisterFcmToken:
    """Tests for DELETE /api/v1/notifications/token."""

    @pytest.mark.asyncio
    async def test_delete_token(self, client: AsyncClient) -> None:
        """Test #8: Delete FCM token with valid JWT returns 204."""
        resp = await client.delete("/api/v1/notifications/token")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_without_auth(self, unauthed_client: AsyncClient) -> None:
        """Test #9: Delete FCM token without JWT returns 401/403."""
        resp = await unauthed_client.delete("/api/v1/notifications/token")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_delete_when_none_exists(self, client: AsyncClient) -> None:
        """Test #10: Delete FCM token when none exists returns 204 (idempotent)."""
        resp = await client.delete("/api/v1/notifications/token")
        assert resp.status_code == 204
