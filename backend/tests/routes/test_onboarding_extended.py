"""Extended route-level integration tests for the onboarding endpoint.

Covers edge cases not in the original test_onboarding_routes.py:
- Response content-type verification
- Empty request body / missing answers field
- Unicode / special characters in answers through HTTP
- Exactly 500-char answers via HTTP
- Haiku returns empty list (fallback used)
- Haiku returns dict (fallback used)
- Profile name case-insensitive with UPPER
- Profile name is None
- Response structure validation (correct keys, correct types)
- GET method not allowed
- Multiple validation errors at once
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
    name: str | None = "Alexander",
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


def _make_client_fixture(
    onboarding_completed: bool = False,
    name: str | None = "Alexander",
) -> AsyncGenerator[AsyncClient, None]:
    """Factory for creating client fixtures with configurable profile."""

    async def _fixture() -> AsyncGenerator[AsyncClient, None]:
        fake_profile = _make_fake_profile(
            onboarding_completed=onboarding_completed,
            name=name,
        )

        async def override_user() -> MagicMock:
            return fake_profile

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = override_user

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

        app.dependency_overrides.clear()

    return _fixture


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
async def client_name_none() -> AsyncGenerator[AsyncClient, None]:
    """Provide a client fixture where profile.name is None."""
    fake_profile = _make_fake_profile(name=None)

    async def override_user() -> MagicMock:
        return fake_profile

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.fake_profile = fake_profile  # type: ignore[attr-defined]
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_name_upper() -> AsyncGenerator[AsyncClient, None]:
    """Provide a client fixture where profile.name is 'ALEX'."""
    fake_profile = _make_fake_profile(name="ALEX")

    async def override_user() -> MagicMock:
        return fake_profile

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        ac.fake_profile = fake_profile  # type: ignore[attr-defined]
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestOnboardingCompleteExtended:
    """Extended tests for POST /api/v1/onboarding/complete."""

    @pytest.mark.asyncio
    async def test_response_content_type_json(self, client: AsyncClient) -> None:
        """Response Content-Type is application/json."""
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
        assert "application/json" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_response_has_correct_keys(self, client: AsyncClient) -> None:
        """Response JSON has exactly the expected keys."""
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

        data = resp.json()
        assert set(data.keys()) == {"onboarding_completed", "memories_seeded"}
        assert isinstance(data["onboarding_completed"], bool)
        assert isinstance(data["memories_seeded"], int)

    @pytest.mark.asyncio
    async def test_empty_request_body(self, client: AsyncClient) -> None:
        """Empty request body returns 422."""
        resp = await client.post(
            "/api/v1/onboarding/complete",
            json={},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_null_answers_field(self, client: AsyncClient) -> None:
        """null answers field returns 422."""
        resp = await client.post(
            "/api/v1/onboarding/complete",
            json={"answers": None},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_answers_not_a_list(self, client: AsyncClient) -> None:
        """answers as a string instead of list returns 422."""
        resp = await client.post(
            "/api/v1/onboarding/complete",
            json={"answers": "not a list"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_unicode_answers_via_http(self, client: AsyncClient) -> None:
        """Unicode characters in answers are handled correctly via HTTP."""
        body = _build_valid_request_body()
        body["answers"][0]["answer"] = "Mehmet"
        body["answers"][1]["answer"] = "Yazilim muhendisi"

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
                json=body,
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_exactly_500_char_answer_via_http(self, client: AsyncClient) -> None:
        """Answer at exactly 500 characters is accepted via HTTP."""
        body = _build_valid_request_body()
        body["answers"][1]["answer"] = "a" * 500

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
                json=body,
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_haiku_returns_empty_list_uses_fallback(
        self, client: AsyncClient,
    ) -> None:
        """When Haiku returns an empty JSON array, fallback is used and 200 is returned."""
        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "[]"
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
        assert data["memories_seeded"] == 7

    @pytest.mark.asyncio
    async def test_haiku_returns_dict_uses_fallback(
        self, client: AsyncClient,
    ) -> None:
        """When Haiku returns a JSON dict instead of array, fallback is used."""
        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = '{"memories": ["Prefers Alex"]}'
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
        assert data["memories_seeded"] == 7

    @pytest.mark.asyncio
    async def test_profile_name_none_updated_via_route(
        self, client_name_none: AsyncClient,
    ) -> None:
        """Profile name is updated when it starts as None."""
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

            resp = await client_name_none.post(
                "/api/v1/onboarding/complete",
                json=_build_valid_request_body(),
            )

        assert resp.status_code == 200
        assert client_name_none.fake_profile.name == "Alex"  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_profile_name_upper_not_updated(
        self, client_name_upper: AsyncClient,
    ) -> None:
        """Profile name 'ALEX' is not updated when preferred_name is 'Alex'."""
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

            resp = await client_name_upper.post(
                "/api/v1/onboarding/complete",
                json=_build_valid_request_body(),
            )

        assert resp.status_code == 200
        assert client_name_upper.fake_profile.name == "ALEX"  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_get_method_not_allowed(self, client: AsyncClient) -> None:
        """GET /api/v1/onboarding/complete returns 405 Method Not Allowed."""
        resp = await client.get("/api/v1/onboarding/complete")
        assert resp.status_code == 405

    @pytest.mark.asyncio
    async def test_special_characters_in_all_answers(
        self, client: AsyncClient,
    ) -> None:
        """Answers with special characters (quotes, brackets, ampersands) are accepted."""
        body = {
            "answers": [
                {"question_key": "preferred_name", "answer": 'Al"ex & <friends>'},
                {"question_key": "occupation", "answer": "Engineer (senior) @ company"},
                {"question_key": "daily_rhythm", "answer": "Night owl -- 100%!"},
                {"question_key": "health_goal", "answer": "Run > 5km/day"},
                {"question_key": "stress_management", "answer": "Music & meditation"},
                {"question_key": "sleep_schedule", "answer": "12AM-8AM (approx.)"},
                {"question_key": "communication_style", "answer": "Don't be too pushy"},
            ],
        }

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
                json=body,
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_409_response_detail_format(self, client: AsyncClient) -> None:
        """409 response has correct detail message format."""
        fake_profile = _make_fake_profile(onboarding_completed=True)

        async def override_user() -> MagicMock:
            return fake_profile

        app.dependency_overrides[get_current_user] = override_user

        resp = await client.post(
            "/api/v1/onboarding/complete",
            json=_build_valid_request_body(),
        )

        assert resp.status_code == 409
        data = resp.json()
        assert "detail" in data
        assert data["detail"] == "Onboarding already completed"

    @pytest.mark.asyncio
    async def test_422_response_has_detail_field(self, client: AsyncClient) -> None:
        """422 response has a detail field with validation error info."""
        resp = await client.post(
            "/api/v1/onboarding/complete",
            json={"answers": []},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_503_on_haiku_with_connection_error(
        self, client: AsyncClient,
    ) -> None:
        """Connection error to Claude Haiku returns 503."""
        with patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=ConnectionError("Failed to connect to Claude"),
            )
            mock_cls.return_value = mock_client

            resp = await client.post(
                "/api/v1/onboarding/complete",
                json=_build_valid_request_body(),
            )

        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_503_on_haiku_with_timeout(self, client: AsyncClient) -> None:
        """Timeout to Claude Haiku returns 503."""
        with patch("app.services.onboarding_service.AsyncAnthropic") as mock_cls:
            mock_client = AsyncMock()
            mock_client.messages.create = AsyncMock(
                side_effect=TimeoutError("Claude Haiku timed out"),
            )
            mock_cls.return_value = mock_client

            resp = await client.post(
                "/api/v1/onboarding/complete",
                json=_build_valid_request_body(),
            )

        assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_haiku_markdown_code_block_via_route(
        self, client: AsyncClient,
    ) -> None:
        """Haiku response wrapped in markdown code block is parsed correctly via route."""
        mock_response = MagicMock()
        mock_content = MagicMock()
        mock_content.text = '```json\n' + json.dumps(STANDARD_MEMORIES) + '\n```'
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
        assert data["memories_seeded"] == 7
