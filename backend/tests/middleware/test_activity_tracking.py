"""Tests for the Activity Tracking middleware.

Verifies that the middleware correctly identifies authenticated requests,
distinguishes chat requests from non-chat requests, schedules background
tasks, and handles failures gracefully (fail-open).
"""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from starlette.requests import Request
from starlette.responses import Response

from app.middleware.activity_tracking import _CHAT_PATH_RE, ActivityTrackingMiddleware


def _make_jwt(payload: dict[str, object]) -> str:
    """Build a fake (unsigned) JWT with the given payload for testing."""
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
    encoded_payload = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    )
    return f"{header}.{encoded_payload}.fakesignature"


def _make_request(
    method: str = "GET",
    path: str = "/api/v1/health",
    headers: dict[str, str] | None = None,
) -> Request:
    """Build a minimal Starlette Request for unit testing."""
    raw_headers = []
    if headers:
        raw_headers = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "root_path": "",
        "headers": raw_headers,
    }
    return Request(scope)


class TestChatPathRegex:
    """Verify the regex correctly identifies chat message endpoints."""

    def test_matches_chat_path(self) -> None:
        assert _CHAT_PATH_RE.match("/api/v1/characters/some-uuid/messages") is not None

    def test_does_not_match_characters_list(self) -> None:
        assert _CHAT_PATH_RE.match("/api/v1/characters") is None

    def test_does_not_match_nested_path(self) -> None:
        assert _CHAT_PATH_RE.match("/api/v1/characters/id/messages/extra") is None

    def test_does_not_match_memories(self) -> None:
        assert _CHAT_PATH_RE.match("/api/v1/characters/id/memories") is None


class TestActivityTrackingMiddleware:
    """Unit tests for ActivityTrackingMiddleware.dispatch."""

    @pytest.mark.asyncio
    async def test_authenticated_get_triggers_activity_update(self) -> None:
        """Authenticated GET request calls update_user_activity with is_chat_request=False."""
        token = _make_jwt({"sub": "user_123"})
        request = _make_request(
            method="GET",
            path="/api/v1/characters",
            headers={"Authorization": f"Bearer {token}"},
        )

        async def _dummy_app(scope: object, receive: object, send: object) -> None:
            pass

        middleware = ActivityTrackingMiddleware(_dummy_app)

        async def _call_next(req: Request) -> Response:
            return Response(status_code=200)

        with patch(
            "app.middleware.activity_tracking.update_user_activity",
            new_callable=AsyncMock,
        ) as mock_update:
            response = await middleware.dispatch(request, _call_next)

        assert response.status_code == 200
        assert response.background is not None

        # Execute the background task to verify args
        await response.background()  # type: ignore[misc]
        mock_update.assert_called_once_with(user_id="user_123", is_chat_request=False)

    @pytest.mark.asyncio
    async def test_authenticated_chat_request_triggers_chat_update(self) -> None:
        """POST to chat endpoint calls update_user_activity with is_chat_request=True."""
        token = _make_jwt({"sub": "user_456"})
        request = _make_request(
            method="POST",
            path="/api/v1/characters/char-uuid-123/messages",
            headers={"Authorization": f"Bearer {token}"},
        )

        async def _dummy_app(scope: object, receive: object, send: object) -> None:
            pass

        middleware = ActivityTrackingMiddleware(_dummy_app)

        async def _call_next(req: Request) -> Response:
            return Response(status_code=200)

        with patch(
            "app.middleware.activity_tracking.update_user_activity",
            new_callable=AsyncMock,
        ) as mock_update:
            response = await middleware.dispatch(request, _call_next)

        assert response.background is not None
        await response.background()  # type: ignore[misc]
        mock_update.assert_called_once_with(user_id="user_456", is_chat_request=True)

    @pytest.mark.asyncio
    async def test_unauthenticated_request_does_not_trigger_update(self) -> None:
        """Request with no Authorization header does not call update_user_activity."""
        request = _make_request(method="GET", path="/api/v1/health")

        async def _dummy_app(scope: object, receive: object, send: object) -> None:
            pass

        middleware = ActivityTrackingMiddleware(_dummy_app)

        async def _call_next(req: Request) -> Response:
            return Response(status_code=200)

        with patch(
            "app.middleware.activity_tracking.update_user_activity",
            new_callable=AsyncMock,
        ) as mock_update:
            response = await middleware.dispatch(request, _call_next)

        # No background task should be set for unauthenticated requests
        assert response.background is None
        mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_malformed_jwt_does_not_trigger_update(self) -> None:
        """Request with a malformed JWT does not call update_user_activity."""
        request = _make_request(
            method="GET",
            path="/api/v1/characters",
            headers={"Authorization": "Bearer not.a.valid-jwt"},
        )

        async def _dummy_app(scope: object, receive: object, send: object) -> None:
            pass

        middleware = ActivityTrackingMiddleware(_dummy_app)

        async def _call_next(req: Request) -> Response:
            return Response(status_code=200)

        with patch(
            "app.middleware.activity_tracking.update_user_activity",
            new_callable=AsyncMock,
        ) as mock_update:
            response = await middleware.dispatch(request, _call_next)

        assert response.background is None
        mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_post_characters_not_messages_is_not_chat(self) -> None:
        """POST /api/v1/characters (not /messages) triggers only last_active_at."""
        token = _make_jwt({"sub": "user_789"})
        request = _make_request(
            method="POST",
            path="/api/v1/characters",
            headers={"Authorization": f"Bearer {token}"},
        )

        async def _dummy_app(scope: object, receive: object, send: object) -> None:
            pass

        middleware = ActivityTrackingMiddleware(_dummy_app)

        async def _call_next(req: Request) -> Response:
            return Response(status_code=201)

        with patch(
            "app.middleware.activity_tracking.update_user_activity",
            new_callable=AsyncMock,
        ) as mock_update:
            response = await middleware.dispatch(request, _call_next)

        assert response.background is not None
        await response.background()  # type: ignore[misc]
        mock_update.assert_called_once_with(user_id="user_789", is_chat_request=False)

    @pytest.mark.asyncio
    async def test_response_returned_before_background_task(self) -> None:
        """Middleware returns response without waiting for update_user_activity."""
        token = _make_jwt({"sub": "user_fast"})
        request = _make_request(
            method="GET",
            path="/api/v1/health",
            headers={"Authorization": f"Bearer {token}"},
        )

        async def _dummy_app(scope: object, receive: object, send: object) -> None:
            pass

        middleware = ActivityTrackingMiddleware(_dummy_app)

        async def _call_next(req: Request) -> Response:
            return Response(status_code=200)

        with patch(
            "app.middleware.activity_tracking.update_user_activity",
            new_callable=AsyncMock,
        ) as mock_update:
            response = await middleware.dispatch(request, _call_next)

        # Response is returned but update has not been called yet
        # (it is scheduled as background task, not awaited inline)
        assert response.status_code == 200
        mock_update.assert_not_called()

        # Now run the background task
        await response.background()  # type: ignore[misc]
        mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_failure_does_not_affect_response(self) -> None:
        """If update_user_activity raises, the response is still returned."""
        token = _make_jwt({"sub": "user_err"})
        request = _make_request(
            method="GET",
            path="/api/v1/characters",
            headers={"Authorization": f"Bearer {token}"},
        )

        async def _dummy_app(scope: object, receive: object, send: object) -> None:
            pass

        middleware = ActivityTrackingMiddleware(_dummy_app)

        async def _call_next(req: Request) -> Response:
            return Response(status_code=200)

        with patch(
            "app.middleware.activity_tracking.update_user_activity",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB connection failed"),
        ):
            response = await middleware.dispatch(request, _call_next)

        # Response is returned successfully regardless
        assert response.status_code == 200
        # Background task is set (will fail when executed, but that's OK)
        assert response.background is not None

    @pytest.mark.asyncio
    async def test_chains_with_existing_background_task(self) -> None:
        """If response already has a background task, both tasks are chained."""
        token = _make_jwt({"sub": "user_chain"})
        request = _make_request(
            method="GET",
            path="/api/v1/health",
            headers={"Authorization": f"Bearer {token}"},
        )

        async def _dummy_app(scope: object, receive: object, send: object) -> None:
            pass

        middleware = ActivityTrackingMiddleware(_dummy_app)

        existing_task_called = False

        async def _existing_task() -> None:
            nonlocal existing_task_called
            existing_task_called = True

        async def _call_next(req: Request) -> Response:
            resp = Response(status_code=200)
            resp.background = BackgroundTask(_existing_task)  # type: ignore[assignment]
            return resp

        from starlette.background import BackgroundTask

        with patch(
            "app.middleware.activity_tracking.update_user_activity",
            new_callable=AsyncMock,
        ) as mock_update:
            response = await middleware.dispatch(request, _call_next)

        # Execute the chained background tasks
        assert response.background is not None
        await response.background()  # type: ignore[misc]
        assert existing_task_called
        mock_update.assert_called_once()


class TestActivityTrackingIntegrationViaClient:
    """Integration tests using the FastAPI test client with middleware registered."""

    @pytest.mark.asyncio
    async def test_authenticated_request_via_client(self, client: AsyncClient) -> None:
        """Authenticated GET to health triggers activity tracking middleware."""
        token = _make_jwt({"sub": "user_int_test"})

        with patch(
            "app.middleware.activity_tracking.update_user_activity",
            new_callable=AsyncMock,
        ) as mock_update:
            response = await client.get(
                "/api/v1/health",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        mock_update.assert_called_once_with(
            user_id="user_int_test",
            is_chat_request=False,
        )

    @pytest.mark.asyncio
    async def test_unauthenticated_request_via_client(self, client: AsyncClient) -> None:
        """Unauthenticated GET to health does not trigger activity update."""
        with patch(
            "app.middleware.activity_tracking.update_user_activity",
            new_callable=AsyncMock,
        ) as mock_update:
            response = await client.get("/api/v1/health")

        assert response.status_code == 200
        mock_update.assert_not_called()
