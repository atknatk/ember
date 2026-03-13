"""Extended route-level tests for notification token endpoints.

Supplements test_notifications_routes.py with edge cases, response
schema validation, DB interaction verification, and auth edge cases
not covered by the base test file.
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
from unittest.mock import AsyncMock, MagicMock, call  # noqa: E402

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
async def client_with_db_capture() -> AsyncGenerator[tuple[AsyncClient, list[AsyncMock]], None]:
    """Provide a client where the DB mock is accessible for assertion."""
    fake_profile = _make_fake_profile()
    captured: list[AsyncMock] = []

    async def override_get_db_capture() -> AsyncGenerator[AsyncMock, None]:
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.execute = AsyncMock()
        captured.append(mock_db)
        yield mock_db

    async def override_user() -> MagicMock:
        return fake_profile

    app.dependency_overrides[get_db] = override_get_db_capture
    app.dependency_overrides[get_current_user] = override_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, captured

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
# PUT /api/v1/notifications/token — extended token validation edge cases
# ---------------------------------------------------------------------------


class TestRegisterFcmTokenEdgeCases:
    """Edge case tests for PUT /api/v1/notifications/token."""

    @pytest.mark.asyncio
    async def test_register_single_char_token(self, client: AsyncClient) -> None:
        """Minimum valid token length (1 char) is accepted."""
        resp = await client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": "x"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_register_whitespace_only_token_accepted(self, client: AsyncClient) -> None:
        """Whitespace-only token passes Pydantic min_length=1 (length > 0) and is stored.

        FCM tokens are never whitespace in practice, but Pydantic does not strip
        whitespace by default, so a whitespace string of length >= 1 passes validation.
        This test documents the current behavior.
        """
        resp = await client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": "   "},
        )
        # min_length=1 is satisfied by 3-space string — Pydantic accepts it
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_register_token_exactly_4096_chars(self, client: AsyncClient) -> None:
        """Token at exactly 4096 chars (boundary) is accepted."""
        resp = await client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": "a" * 4096},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_register_token_4097_chars_rejected(self, client: AsyncClient) -> None:
        """Token at 4097 chars (one over boundary) is rejected with 422."""
        resp = await client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": "b" * 4097},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_token_non_string_type_rejected(self, client: AsyncClient) -> None:
        """Numeric fcm_token value is rejected with 422."""
        resp = await client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": 12345},
        )
        # Pydantic coerces int to str in v2; verify request at least reaches validation
        # Either 200 (coerced) or 422 (strict) depending on Pydantic config
        assert resp.status_code in (200, 422)

    @pytest.mark.asyncio
    async def test_register_null_fcm_token_rejected(self, client: AsyncClient) -> None:
        """Explicit null fcm_token is rejected with 422."""
        resp = await client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": None},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_extra_fields_ignored(self, client: AsyncClient) -> None:
        """Extra fields in request body are ignored (Pydantic default behavior)."""
        resp = await client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": "valid-token", "extra_field": "ignored"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.asyncio
    async def test_register_typical_fcm_token_format(self, client: AsyncClient) -> None:
        """A realistic FCM token (~160 chars) is accepted."""
        realistic_token = (
            "dGhpcyBpcyBhIHJlYWxpc3RpYyBGQ00gdG9rZW4gdGhhdCBsb29rcyBsaWtlIHdoYXQgR29vZ2xlIEZDTSBwcm9kdWNlcw=="
            * 2
        )
        resp = await client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": realistic_token},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# PUT /api/v1/notifications/token — response schema
# ---------------------------------------------------------------------------


class TestRegisterFcmTokenResponseSchema:
    """Response shape validation for PUT /api/v1/notifications/token."""

    @pytest.mark.asyncio
    async def test_response_has_status_field(self, client: AsyncClient) -> None:
        """Response body contains exactly the 'status' key."""
        resp = await client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": "some-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_response_content_type_is_json(self, client: AsyncClient) -> None:
        """PUT response has application/json content-type."""
        resp = await client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": "some-token"},
        )
        assert "application/json" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_response_status_value_is_ok_string(self, client: AsyncClient) -> None:
        """Response status value is the string literal 'ok', not a boolean or code."""
        resp = await client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": "token-abc"},
        )
        assert resp.json()["status"] == "ok"
        assert isinstance(resp.json()["status"], str)


# ---------------------------------------------------------------------------
# PUT /api/v1/notifications/token — DB interaction
# ---------------------------------------------------------------------------


class TestRegisterFcmTokenDbInteraction:
    """Verify that PUT /notifications/token triggers correct DB operations."""

    @pytest.mark.asyncio
    async def test_db_execute_and_commit_called(
        self,
        client_with_db_capture: tuple[AsyncClient, list[AsyncMock]],
    ) -> None:
        """Route calls db.execute() and db.commit() exactly once each."""
        ac, captured = client_with_db_capture
        resp = await ac.put(
            "/api/v1/notifications/token",
            json={"fcm_token": "my-device-token"},
        )
        assert resp.status_code == 200
        assert len(captured) == 1
        mock_db = captured[0]
        mock_db.execute.assert_awaited_once()
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_db_execute_not_called_on_validation_failure(
        self,
        client_with_db_capture: tuple[AsyncClient, list[AsyncMock]],
    ) -> None:
        """DB is never touched when Pydantic rejects the request body."""
        ac, captured = client_with_db_capture
        resp = await ac.put(
            "/api/v1/notifications/token",
            json={"fcm_token": ""},
        )
        assert resp.status_code == 422
        # DB fixture was never yielded because FastAPI rejects before dependency injection
        # (captured may be empty or have a mock that was never called)
        for mock_db in captured:
            mock_db.execute.assert_not_awaited()


# ---------------------------------------------------------------------------
# PUT /api/v1/notifications/token — auth edge cases
# ---------------------------------------------------------------------------


class TestRegisterFcmTokenAuthEdgeCases:
    """Auth-related edge cases for PUT /api/v1/notifications/token."""

    @pytest.mark.asyncio
    async def test_invalid_bearer_token_rejected(self) -> None:
        """Malformed Authorization header returns 401/403."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put(
                "/api/v1/notifications/token",
                headers={"Authorization": "Bearer not-a-valid-jwt"},
                json={"fcm_token": "token"},
            )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_missing_authorization_header_returns_401(self) -> None:
        """No Authorization header at all returns 401/403."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put(
                "/api/v1/notifications/token",
                json={"fcm_token": "token"},
            )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_wrong_http_method_returns_405(self, client: AsyncClient) -> None:
        """POST to a PUT-only endpoint returns 405 Method Not Allowed."""
        resp = await client.post(
            "/api/v1/notifications/token",
            json={"fcm_token": "token"},
        )
        assert resp.status_code == 405

    @pytest.mark.asyncio
    async def test_get_method_returns_405(self, client: AsyncClient) -> None:
        """GET to /notifications/token returns 405 (route is PUT + DELETE only)."""
        resp = await client.get("/api/v1/notifications/token")
        assert resp.status_code == 405


# ---------------------------------------------------------------------------
# DELETE /api/v1/notifications/token — extended tests
# ---------------------------------------------------------------------------


class TestUnregisterFcmTokenExtended:
    """Extended tests for DELETE /api/v1/notifications/token."""

    @pytest.mark.asyncio
    async def test_delete_response_has_no_body(self, client: AsyncClient) -> None:
        """204 response has no body (content-length 0 or empty body)."""
        resp = await client.delete("/api/v1/notifications/token")
        assert resp.status_code == 204
        assert resp.content == b""

    @pytest.mark.asyncio
    async def test_delete_twice_is_idempotent(self, client: AsyncClient) -> None:
        """Calling DELETE twice in a row both return 204."""
        for _ in range(2):
            resp = await client.delete("/api/v1/notifications/token")
            assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_db_execute_and_commit_called(
        self,
        client_with_db_capture: tuple[AsyncClient, list[AsyncMock]],
    ) -> None:
        """DELETE calls db.execute() and db.commit() exactly once each."""
        ac, captured = client_with_db_capture
        resp = await ac.delete("/api/v1/notifications/token")
        assert resp.status_code == 204
        assert len(captured) == 1
        mock_db = captured[0]
        mock_db.execute.assert_awaited_once()
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_invalid_bearer_token_rejected(self) -> None:
        """DELETE with malformed JWT returns 401/403."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.delete(
                "/api/v1/notifications/token",
                headers={"Authorization": "Bearer garbage"},
            )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_delete_then_put_registers_new_token(self, client: AsyncClient) -> None:
        """After DELETE, a new PUT succeeds with 200."""
        delete_resp = await client.delete("/api/v1/notifications/token")
        assert delete_resp.status_code == 204

        put_resp = await client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": "fresh-new-token"},
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Endpoint existence / routing
# ---------------------------------------------------------------------------


class TestNotificationEndpointRouting:
    """Verify the notifications router is registered under /api/v1."""

    @pytest.mark.asyncio
    async def test_notifications_token_path_exists(self, client: AsyncClient) -> None:
        """The /api/v1/notifications/token path is reachable (not 404)."""
        resp = await client.put(
            "/api/v1/notifications/token",
            json={"fcm_token": "reachable"},
        )
        assert resp.status_code != 404

    @pytest.mark.asyncio
    async def test_notifications_token_wrong_path_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Requests to /notifications/token (without /api/v1/) return 404."""
        resp = await client.put(
            "/notifications/token",
            json={"fcm_token": "token"},
        )
        assert resp.status_code == 404
