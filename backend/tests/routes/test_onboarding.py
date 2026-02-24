"""Route-level integration tests for the onboarding endpoint.

Uses the FastAPI test client with mocked dependencies to test HTTP status
codes, response structure, and request validation for
POST /api/v1/onboarding/complete.
"""

from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
)

import json  # noqa: E402
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

STANDARD_MEMORIES = [
    "Prefers to be called Alex",
    "Works as a software engineer",
    "Morning person",
    "Goal: lose 10 kg",
    "Manages stress with walks and podcasts",
    "Sleeps from 11 PM to 6:30 AM",
    "Wants regular check-ins without being overwhelmed",
]


def _build_valid_request_body() -> dict[str, list[dict[str, str]]]:
    """Return a valid request body with all 7 answers."""
    return {
        "answers": [
            {"question_key": "preferred_name", "answer": "Alex"},
            {"question_key": "occupation", "answer": "Software engineer"},
            {"question_key": "daily_rhythm", "answer": "Morning person"},
            {"question_key": "health_goal", "answer": "Lose 10 kg"},
            {"question_key": "stress_management", "answer": "Walks and podcasts"},
            {"question_key": "sleep_schedule", "answer": "11 PM to 6:30 AM"},
            {"question_key": "communication_style", "answer": "Check in regularly"},
        ],
    }


def _make_fake_profile(
    onboarding_completed: bool = False,
    name: str = "Alexander",
) -> MagicMock:
    """Create a fake Profile-like object for auth dependency override."""
    profile = MagicMock()
    profile.id = FAKE_USER_ID
    profile.email = "test@ember.ai"
    profile.name = name
    profile.mem0_user_id = f"user_{FAKE_USER_ID}"
    profile.fcm_token = None
    profile.timezone = "UTC"
    profile.avatar_url = None
    profile.preferred_language = "en"
    profile.onboarding_completed = onboarding_completed
    profile.subscription_tier = "free"
    profile.subscription_expires_at = None
    profile.created_at = datetime.now(tz=UTC)
    profile.updated_at = datetime.now(tz=UTC)
    return profile


def _mock_haiku_response(memories: list[str]) -> MagicMock:
    """Create a mock Claude Haiku response."""
    mock_response = MagicMock()
    mock_content = MagicMock()
    mock_content.text = json.dumps(memories)
    mock_response.content = [mock_content]
    return mock_response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
    """Yield a mock database session."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    yield mock_db


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client with mocked DB and auth (onboarding NOT completed)."""
    fake_profile = _make_fake_profile(onboarding_completed=False)

    async def override_user() -> MagicMock:
        return fake_profile

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def completed_client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client where onboarding is already completed."""
    fake_profile = _make_fake_profile(onboarding_completed=True)

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
# Tests
# ---------------------------------------------------------------------------


class TestOnboardingComplete:
    """Tests for POST /api/v1/onboarding/complete."""

    @pytest.mark.asyncio
    async def test_r1_happy_path(self, client: AsyncClient) -> None:
        """R1: Valid request with all 7 answers returns 200."""
        mock_response = _mock_haiku_response(STANDARD_MEMORIES)

        with (
            patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls,
            patch("app.services.onboarding_service.MemoryClient") as mock_mem0_cls,
        ):
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            mock_mem0 = MagicMock()
            mock_mem0.add.return_value = None
            mock_mem0_cls.return_value = mock_mem0

            resp = await client.post(
                "/api/v1/onboarding/complete",
                json=_build_valid_request_body(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["onboarding_completed"] is True
        assert data["memories_seeded"] == 7

    @pytest.mark.asyncio
    async def test_r2_already_completed(self, completed_client: AsyncClient) -> None:
        """R2: Returns 409 when onboarding already completed."""
        resp = await completed_client.post(
            "/api/v1/onboarding/complete",
            json=_build_valid_request_body(),
        )
        assert resp.status_code == 409
        assert resp.json()["detail"] == "Onboarding already completed"

    @pytest.mark.asyncio
    async def test_r3_missing_question_keys(self, client: AsyncClient) -> None:
        """R3: Returns 422 when fewer than 7 answers provided."""
        body = _build_valid_request_body()
        body["answers"] = body["answers"][:5]
        resp = await client.post("/api/v1/onboarding/complete", json=body)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_r4_duplicate_question_keys(self, client: AsyncClient) -> None:
        """R4: Returns 422 when duplicate question keys provided."""
        body = _build_valid_request_body()
        # Replace last answer with a duplicate of the first key
        body["answers"][6] = {"question_key": "preferred_name", "answer": "Duplicate"}
        resp = await client.post("/api/v1/onboarding/complete", json=body)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_r5_invalid_question_key(self, client: AsyncClient) -> None:
        """R5: Returns 422 when an invalid question_key is provided."""
        body = _build_valid_request_body()
        body["answers"][0] = {"question_key": "favorite_color", "answer": "Blue"}
        resp = await client.post("/api/v1/onboarding/complete", json=body)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_r6_empty_answer(self, client: AsyncClient) -> None:
        """R6: Returns 422 when an answer is empty string."""
        body = _build_valid_request_body()
        body["answers"][0]["answer"] = ""
        resp = await client.post("/api/v1/onboarding/complete", json=body)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_r7_answer_exceeding_500_chars(self, client: AsyncClient) -> None:
        """R7: Returns 422 when an answer exceeds 500 characters."""
        body = _build_valid_request_body()
        body["answers"][0]["answer"] = "x" * 501
        resp = await client.post("/api/v1/onboarding/complete", json=body)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_r8_without_auth(self, unauthed_client: AsyncClient) -> None:
        """R8: Returns 401/403 without auth header."""
        resp = await unauthed_client.post(
            "/api/v1/onboarding/complete",
            json=_build_valid_request_body(),
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_r9_haiku_failure(self, client: AsyncClient) -> None:
        """R9: Returns 503 when Claude Haiku fails."""
        with patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=Exception("Claude API error"),
            )
            mock_cls.return_value = mock_client

            resp = await client.post(
                "/api/v1/onboarding/complete",
                json=_build_valid_request_body(),
            )

        assert resp.status_code == 503
        assert resp.json()["detail"] == "AI service temporarily unavailable"

    @pytest.mark.asyncio
    async def test_r10_mem0_failure(self, client: AsyncClient) -> None:
        """R10: Returns 503 when Mem0 fails."""
        mock_response = _mock_haiku_response(STANDARD_MEMORIES)

        with (
            patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls,
            patch(
                "app.services.onboarding_service.asyncio.to_thread",
                new_callable=AsyncMock,
                side_effect=Exception("Mem0 connection refused"),
            ),
        ):
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            resp = await client.post(
                "/api/v1/onboarding/complete",
                json=_build_valid_request_body(),
            )

        assert resp.status_code == 503
        assert resp.json()["detail"] == "AI service temporarily unavailable"

    @pytest.mark.asyncio
    async def test_r11_updates_profile_name(self, client: AsyncClient) -> None:
        """R11: Updates profile name when preferred_name differs from current name."""
        # The fake profile has name="Alexander", preferred_name answer is "Alex"
        fake_profile = _make_fake_profile(name="Alexander")

        async def override_user() -> MagicMock:
            return fake_profile

        app.dependency_overrides[get_current_user] = override_user

        mock_response = _mock_haiku_response(STANDARD_MEMORIES)

        with (
            patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls,
            patch("app.services.onboarding_service.MemoryClient") as mock_mem0_cls,
        ):
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            mock_mem0 = MagicMock()
            mock_mem0.add.return_value = None
            mock_mem0_cls.return_value = mock_mem0

            resp = await client.post(
                "/api/v1/onboarding/complete",
                json=_build_valid_request_body(),
            )

        assert resp.status_code == 200
        assert fake_profile.name == "Alex"

    @pytest.mark.asyncio
    async def test_r12_does_not_update_name_when_same(self, client: AsyncClient) -> None:
        """R12: Does not update profile name when preferred_name matches."""
        fake_profile = _make_fake_profile(name="Alex")

        async def override_user() -> MagicMock:
            return fake_profile

        app.dependency_overrides[get_current_user] = override_user

        mock_response = _mock_haiku_response(STANDARD_MEMORIES)

        with (
            patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls,
            patch("app.services.onboarding_service.MemoryClient") as mock_mem0_cls,
        ):
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            mock_mem0 = MagicMock()
            mock_mem0.add.return_value = None
            mock_mem0_cls.return_value = mock_mem0

            resp = await client.post(
                "/api/v1/onboarding/complete",
                json=_build_valid_request_body(),
            )

        assert resp.status_code == 200
        assert fake_profile.name == "Alex"

    @pytest.mark.asyncio
    async def test_r13_haiku_unparseable_uses_fallback(self, client: AsyncClient) -> None:
        """R13: Returns 200 with fallback memories when Haiku returns non-JSON."""
        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "Here are the memories:\n- Prefers to be called Alex"
        mock_response.content = [mock_content]

        with (
            patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls,
            patch("app.services.onboarding_service.MemoryClient") as mock_mem0_cls,
        ):
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            mock_mem0 = MagicMock()
            mock_mem0.add.return_value = None
            mock_mem0_cls.return_value = mock_mem0

            resp = await client.post(
                "/api/v1/onboarding/complete",
                json=_build_valid_request_body(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["onboarding_completed"] is True
        assert data["memories_seeded"] == 7

    @pytest.mark.asyncio
    async def test_r14_whitespace_only_answer(self, client: AsyncClient) -> None:
        """R14: Returns 422 for whitespace-only answer."""
        body = _build_valid_request_body()
        body["answers"][0]["answer"] = "   "
        resp = await client.post("/api/v1/onboarding/complete", json=body)
        assert resp.status_code == 422
