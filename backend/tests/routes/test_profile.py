"""Route-level tests for profile CRUD endpoints.

Tests GET /api/v1/profile, PUT /api/v1/profile, and
DELETE /api/v1/profile/account via the FastAPI test client
with mocked dependencies.
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
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

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
    name: str = "Alex",
    timezone: str = "UTC",
    avatar_url: str | None = None,
    preferred_language: str = "en",
) -> MagicMock:
    """Create a fake Profile-like object for dependency override."""
    profile = MagicMock()
    profile.id = FAKE_USER_ID
    profile.email = "test@ember.ai"
    profile.name = name
    profile.mem0_user_id = f"user_{FAKE_USER_ID}"
    profile.fcm_token = None
    profile.timezone = timezone
    profile.avatar_url = avatar_url
    profile.preferred_language = preferred_language
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
    mock_db.refresh = AsyncMock()
    mock_db.delete = AsyncMock()
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
async def client_with_avatar() -> AsyncGenerator[AsyncClient, None]:
    """Provide a client where the user has an existing avatar_url."""
    fake_profile = _make_fake_profile(avatar_url="https://s3.amazonaws.com/photos/old.jpg")

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
# GET /api/v1/profile
# ---------------------------------------------------------------------------


class TestGetProfile:
    """Tests for GET /api/v1/profile."""

    @pytest.mark.asyncio
    async def test_happy_path(self, client: AsyncClient) -> None:
        """Returns 200 with all expected profile fields."""
        resp = await client.get("/api/v1/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "test@ember.ai"
        assert data["name"] == "Alex"
        assert data["timezone"] == "UTC"
        assert data["preferred_language"] == "en"
        assert data["onboarding_completed"] is True
        assert data["subscription_tier"] == "free"
        assert "subscription_expires_at" in data
        assert "created_at" in data
        assert "id" in data

    @pytest.mark.asyncio
    async def test_without_auth(self, unauthed_client: AsyncClient) -> None:
        """Returns 401/403 when no auth header is provided."""
        resp = await unauthed_client.get("/api/v1/profile")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# PUT /api/v1/profile
# ---------------------------------------------------------------------------


class TestUpdateProfile:
    """Tests for PUT /api/v1/profile."""

    @pytest.mark.asyncio
    async def test_update_name_only(self, client: AsyncClient) -> None:
        """Updates name only, returns 200."""
        resp = await client.put("/api/v1/profile", json={"name": "NewName"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_timezone(self, client: AsyncClient) -> None:
        """Updates timezone to a valid IANA timezone."""
        resp = await client.put("/api/v1/profile", json={"timezone": "Europe/Istanbul"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_preferred_language(self, client: AsyncClient) -> None:
        """Updates preferred_language to 'tr'."""
        resp = await client.put("/api/v1/profile", json={"preferred_language": "tr"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_avatar_url(self, client: AsyncClient) -> None:
        """Updates avatar_url to a valid https URL."""
        resp = await client.put(
            "/api/v1/profile",
            json={"avatar_url": "https://s3.amazonaws.com/photos/new.jpg"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_clear_avatar_url(self, client_with_avatar: AsyncClient) -> None:
        """Clears avatar_url by sending null."""
        resp = await client_with_avatar.put("/api/v1/profile", json={"avatar_url": None})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_multiple_fields(self, client: AsyncClient) -> None:
        """Updates multiple fields at once."""
        resp = await client.put(
            "/api/v1/profile",
            json={
                "name": "Updated",
                "timezone": "America/New_York",
                "preferred_language": "tr",
            },
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_empty_body(self, client: AsyncClient) -> None:
        """Empty body returns 200 with profile unchanged."""
        resp = await client.put("/api/v1/profile", json={})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_timezone(self, client: AsyncClient) -> None:
        """Invalid timezone returns 422."""
        resp = await client.put("/api/v1/profile", json={"timezone": "Invalid/Zone"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_name_after_trim(self, client: AsyncClient) -> None:
        """Empty name after trimming returns 422."""
        resp = await client.put("/api/v1/profile", json={"name": "   "})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_name_too_long(self, client: AsyncClient) -> None:
        """Name exceeding 100 characters returns 422."""
        resp = await client.put("/api/v1/profile", json={"name": "x" * 101})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_preferred_language(self, client: AsyncClient) -> None:
        """Invalid preferred_language returns 422."""
        resp = await client.put("/api/v1/profile", json={"preferred_language": "zz"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_avatar_url_not_https(self, client: AsyncClient) -> None:
        """avatar_url not starting with https:// returns 422."""
        resp = await client.put(
            "/api/v1/profile",
            json={"avatar_url": "http://example.com/img.jpg"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_without_auth(self, unauthed_client: AsyncClient) -> None:
        """Returns 401/403 without auth header."""
        resp = await unauthed_client.put("/api/v1/profile", json={"name": "Test"})
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# DELETE /api/v1/profile/account
# ---------------------------------------------------------------------------


class TestDeleteAccount:
    """Tests for DELETE /api/v1/profile/account."""

    @pytest.mark.asyncio
    async def test_happy_path(self, client: AsyncClient) -> None:
        """Correct confirmation string returns 204."""
        with patch(
            "app.services.profile_service.ProfileService.delete_account",
            new_callable=AsyncMock,
        ):
            resp = await client.request(
                "DELETE",
                "/api/v1/profile/account",
                json={"confirmation": "DELETE MY ACCOUNT"},
            )

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_wrong_confirmation(self, client: AsyncClient) -> None:
        """Wrong confirmation string returns 400."""
        resp = await client.request(
            "DELETE",
            "/api/v1/profile/account",
            json={"confirmation": "delete my account"},
        )
        assert resp.status_code == 400
        assert "DELETE MY ACCOUNT" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_missing_confirmation(self, client: AsyncClient) -> None:
        """Missing confirmation field returns 422."""
        resp = await client.request(
            "DELETE",
            "/api/v1/profile/account",
            json={},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_without_auth(self, unauthed_client: AsyncClient) -> None:
        """Returns 401/403 without auth header."""
        resp = await unauthed_client.request(
            "DELETE",
            "/api/v1/profile/account",
            json={"confirmation": "DELETE MY ACCOUNT"},
        )
        assert resp.status_code in (401, 403)
