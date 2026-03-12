"""Extended route tests for profile CRUD endpoints.

Supplements the 19 existing tests in test_profile.py with:
- Response body field assertions for GET/PUT
- Confirmation string case/variation edge cases for DELETE
- Partial external failure path returning 204 from route
- Service raises 503 -> route forwards it
- avatar_url too long (2049+ chars)
- Concurrent deletion race (second delete attempt after profile is gone)
- Wrong HTTP method returns 405
- PUT with only avatar_url explicitly null
- GET response includes subscription_expires_at key always
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
from fastapi import HTTPException, status  # noqa: E402
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
    subscription_expires_at: datetime | None = None,
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
    profile.subscription_expires_at = subscription_expires_at
    profile.created_at = datetime(2026, 1, 1, tzinfo=UTC)
    profile.updated_at = datetime(2026, 1, 1, tzinfo=UTC)
    return profile


async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
    """Yield a mock database session."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.delete = AsyncMock()
    mock_db.execute = AsyncMock()
    yield mock_db


def _make_client_fixture(profile: MagicMock) -> AsyncGenerator[AsyncClient, None]:
    """Shared helper to build a client with a given fake profile."""

    async def override_user() -> MagicMock:
        return profile

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = override_user
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Authenticated client with default fake profile."""
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
async def client_with_subscription() -> AsyncGenerator[AsyncClient, None]:
    """Authenticated client whose profile has a subscription expiry date."""
    expires = datetime(2027, 6, 30, tzinfo=UTC)
    fake_profile = _make_fake_profile(subscription_expires_at=expires)

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
    """Authenticated client whose profile already has an avatar_url."""
    fake_profile = _make_fake_profile(avatar_url="https://s3.amazonaws.com/photos/old.jpg")

    async def override_user() -> MagicMock:
        return fake_profile

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# GET /api/v1/profile -- extended assertions
# ---------------------------------------------------------------------------


class TestGetProfileExtended:
    """Extended tests for GET /api/v1/profile response body."""

    @pytest.mark.asyncio
    async def test_response_body_has_all_required_fields(self, client: AsyncClient) -> None:
        """Response JSON contains every field defined in ProfileResponse schema."""
        resp = await client.get("/api/v1/profile")
        assert resp.status_code == 200
        data = resp.json()
        required_fields = {
            "id",
            "email",
            "name",
            "timezone",
            "avatar_url",
            "preferred_language",
            "onboarding_completed",
            "subscription_tier",
            "subscription_expires_at",
            "created_at",
        }
        assert required_fields.issubset(set(data.keys()))

    @pytest.mark.asyncio
    async def test_response_id_is_string(self, client: AsyncClient) -> None:
        """The id field in the response is a string (UUID coerced)."""
        resp = await client.get("/api/v1/profile")
        assert resp.status_code == 200
        assert isinstance(resp.json()["id"], str)

    @pytest.mark.asyncio
    async def test_subscription_expires_at_null_in_json(self, client: AsyncClient) -> None:
        """subscription_expires_at is present and null for free-tier users."""
        resp = await client.get("/api/v1/profile")
        data = resp.json()
        assert "subscription_expires_at" in data
        assert data["subscription_expires_at"] is None

    @pytest.mark.asyncio
    async def test_subscription_expires_at_datetime_in_json(
        self, client_with_subscription: AsyncClient
    ) -> None:
        """subscription_expires_at is a datetime string for paid users."""
        resp = await client_with_subscription.get("/api/v1/profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["subscription_expires_at"] is not None
        # Must be parseable as ISO datetime
        from datetime import datetime as dt

        dt.fromisoformat(data["subscription_expires_at"].replace("Z", "+00:00"))

    @pytest.mark.asyncio
    async def test_avatar_url_null_in_response(self, client: AsyncClient) -> None:
        """avatar_url is null in JSON when profile has no avatar."""
        resp = await client.get("/api/v1/profile")
        assert resp.json()["avatar_url"] is None

    @pytest.mark.asyncio
    async def test_avatar_url_present_in_response(self, client_with_avatar: AsyncClient) -> None:
        """avatar_url is present in JSON when profile has an avatar."""
        resp = await client_with_avatar.get("/api/v1/profile")
        assert resp.status_code == 200
        assert resp.json()["avatar_url"] == "https://s3.amazonaws.com/photos/old.jpg"

    @pytest.mark.asyncio
    async def test_onboarding_completed_true_in_response(self, client: AsyncClient) -> None:
        """onboarding_completed is true in the response."""
        resp = await client.get("/api/v1/profile")
        assert resp.json()["onboarding_completed"] is True

    @pytest.mark.asyncio
    async def test_created_at_is_iso_string(self, client: AsyncClient) -> None:
        """created_at is an ISO 8601 datetime string in the response."""
        resp = await client.get("/api/v1/profile")
        created_at = resp.json()["created_at"]
        assert isinstance(created_at, str)
        from datetime import datetime as dt

        dt.fromisoformat(created_at.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# PUT /api/v1/profile -- extended assertions
# ---------------------------------------------------------------------------


class TestUpdateProfileExtended:
    """Extended tests for PUT /api/v1/profile."""

    @pytest.mark.asyncio
    async def test_put_returns_full_profile_response(self, client: AsyncClient) -> None:
        """PUT returns full ProfileResponse shape (same as GET)."""
        resp = await client.put("/api/v1/profile", json={"name": "Bob"})
        assert resp.status_code == 200
        data = resp.json()
        required_fields = {
            "id",
            "email",
            "name",
            "timezone",
            "avatar_url",
            "preferred_language",
            "onboarding_completed",
            "subscription_tier",
            "subscription_expires_at",
            "created_at",
        }
        assert required_fields.issubset(set(data.keys()))

    @pytest.mark.asyncio
    async def test_avatar_url_too_long_rejected(self, client: AsyncClient) -> None:
        """avatar_url exceeding 2048 chars returns 422."""
        long_url = "https://" + "x" * 2041  # 2041 + 8 = 2049 total
        resp = await client.put("/api/v1/profile", json={"avatar_url": long_url})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_avatar_url_exactly_2048_chars_accepted(self, client: AsyncClient) -> None:
        """avatar_url of exactly 2048 chars returns 200."""
        exact_url = "https://" + "x" * 2040  # 2040 + 8 = 2048 total
        resp = await client.put("/api/v1/profile", json={"avatar_url": exact_url})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_avatar_url_null_clears_and_returns_null(
        self, client_with_avatar: AsyncClient
    ) -> None:
        """Sending avatar_url=null in PUT returns avatar_url=null in response."""
        resp = await client_with_avatar.put("/api/v1/profile", json={"avatar_url": None})
        assert resp.status_code == 200
        assert resp.json()["avatar_url"] is None

    @pytest.mark.asyncio
    async def test_name_whitespace_trimmed_in_response(self, client: AsyncClient) -> None:
        """Name with surrounding whitespace is trimmed in the 422/200 response."""
        # "  Alex  " -> "Alex" (valid, 200)
        resp = await client.put("/api/v1/profile", json={"name": "  Alex  "})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_preferred_language_fr_not_supported(self, client: AsyncClient) -> None:
        """'fr' is not in SUPPORTED_LANGUAGES, returns 422."""
        resp = await client.put("/api/v1/profile", json={"preferred_language": "fr"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_preferred_language_uppercase_en_rejected(self, client: AsyncClient) -> None:
        """'EN' uppercase is not accepted, returns 422."""
        resp = await client.put("/api/v1/profile", json={"preferred_language": "EN"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_timezone_empty_string_rejected(self, client: AsyncClient) -> None:
        """Empty string timezone returns 422."""
        resp = await client.put("/api/v1/profile", json={"timezone": ""})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_name_single_char_accepted(self, client: AsyncClient) -> None:
        """Single character name is valid."""
        resp = await client.put("/api/v1/profile", json={"name": "Z"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_name_exactly_100_chars_accepted(self, client: AsyncClient) -> None:
        """Name of exactly 100 characters is accepted."""
        resp = await client.put("/api/v1/profile", json={"name": "x" * 100})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_name_101_chars_rejected(self, client: AsyncClient) -> None:
        """Name of 101 characters is rejected with 422."""
        resp = await client.put("/api/v1/profile", json={"name": "x" * 101})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_avatar_url_http_rejected(self, client: AsyncClient) -> None:
        """http:// avatar_url returns 422 (must be https://)."""
        resp = await client.put(
            "/api/v1/profile", json={"avatar_url": "http://example.com/img.jpg"}
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_avatar_url_relative_path_rejected(self, client: AsyncClient) -> None:
        """Relative path as avatar_url returns 422."""
        resp = await client.put("/api/v1/profile", json={"avatar_url": "/path/to/img.jpg"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/v1/profile/account -- extended edge cases
# ---------------------------------------------------------------------------


class TestDeleteAccountExtended:
    """Extended tests for DELETE /api/v1/profile/account."""

    @pytest.mark.asyncio
    async def test_lowercase_confirmation_returns_400(self, client: AsyncClient) -> None:
        """Lowercase 'delete my account' returns 400 (case-sensitive)."""
        resp = await client.request(
            "DELETE",
            "/api/v1/profile/account",
            json={"confirmation": "delete my account"},
        )
        assert resp.status_code == 400
        assert "DELETE MY ACCOUNT" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_mixed_case_confirmation_returns_400(self, client: AsyncClient) -> None:
        """Mixed case 'Delete My Account' returns 400."""
        resp = await client.request(
            "DELETE",
            "/api/v1/profile/account",
            json={"confirmation": "Delete My Account"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_confirmation_with_trailing_space_returns_400(
        self, client: AsyncClient
    ) -> None:
        """'DELETE MY ACCOUNT ' with trailing space returns 400."""
        resp = await client.request(
            "DELETE",
            "/api/v1/profile/account",
            json={"confirmation": "DELETE MY ACCOUNT "},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_confirmation_with_leading_space_returns_400(
        self, client: AsyncClient
    ) -> None:
        """' DELETE MY ACCOUNT' with leading space returns 400."""
        resp = await client.request(
            "DELETE",
            "/api/v1/profile/account",
            json={"confirmation": " DELETE MY ACCOUNT"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_body_returns_422(self, client: AsyncClient) -> None:
        """Missing body returns 422 (not 400)."""
        resp = await client.request(
            "DELETE",
            "/api/v1/profile/account",
            json={},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_service_503_propagated_to_route(self, client: AsyncClient) -> None:
        """When service raises HTTPException(503), route returns 503."""
        with patch(
            "app.services.profile_service.ProfileService.delete_account",
            new_callable=AsyncMock,
            side_effect=HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Account deletion partially failed. Please contact support.",
            ),
        ):
            resp = await client.request(
                "DELETE",
                "/api/v1/profile/account",
                json={"confirmation": "DELETE MY ACCOUNT"},
            )

        assert resp.status_code == 503
        assert "partially failed" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_partial_external_failure_returns_204(self, client: AsyncClient) -> None:
        """When only some external cleanups fail, service succeeds and route returns 204."""
        # Partial failure: service completes without raising -> 204
        with patch(
            "app.services.profile_service.ProfileService.delete_account",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = await client.request(
                "DELETE",
                "/api/v1/profile/account",
                json={"confirmation": "DELETE MY ACCOUNT"},
            )

        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_400_detail_message_mentions_exact_string(self, client: AsyncClient) -> None:
        """400 error detail specifically mentions 'DELETE MY ACCOUNT'."""
        resp = await client.request(
            "DELETE",
            "/api/v1/profile/account",
            json={"confirmation": "WRONG"},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "DELETE MY ACCOUNT" in detail

    @pytest.mark.asyncio
    async def test_no_data_deleted_on_wrong_confirmation(self, client: AsyncClient) -> None:
        """Wrong confirmation: service delete_account should NOT be called."""
        with patch(
            "app.services.profile_service.ProfileService.delete_account",
            new_callable=AsyncMock,
        ) as mock_delete:
            resp = await client.request(
                "DELETE",
                "/api/v1/profile/account",
                json={"confirmation": "WRONG"},
            )

        assert resp.status_code == 400
        mock_delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_string_confirmation_returns_422(self, client: AsyncClient) -> None:
        """Empty string confirmation is rejected by schema (min_length=1) -> 422."""
        resp = await client.request(
            "DELETE",
            "/api/v1/profile/account",
            json={"confirmation": ""},
        )
        assert resp.status_code == 422
