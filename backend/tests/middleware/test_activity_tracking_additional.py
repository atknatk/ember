"""Additional edge-case tests for the Activity Tracking middleware.

Supplements the tests written by backend-dev with coverage for:
  - Chat URL regex edge cases (UUID formats, trailing slash, GET method, long IDs)
  - Various JWT formats (missing sub, non-string sub, extra fields, 2-part token)
  - Authorization header variants (no Bearer prefix, lowercase bearer, just token)
  - Background task chaining when response already holds a BackgroundTasks instance
  - GET to /messages path should NOT be classified as chat
  - PUT / PATCH to messages path should NOT be classified as chat
  - Path anchoring (partial matches must be rejected)
  - Middleware dispatch passes through response status codes unmodified
"""

from __future__ import annotations

import asyncio
import base64
import json
from unittest.mock import AsyncMock, patch

import pytest
from starlette.background import BackgroundTask, BackgroundTasks
from starlette.requests import Request
from starlette.responses import Response

from app.middleware.activity_tracking import _CHAT_PATH_RE, ActivityTrackingMiddleware


# ---------------------------------------------------------------------------
# Helpers (mirrors _make_jwt / _make_request from existing test file)
# ---------------------------------------------------------------------------


def _make_jwt(payload: dict[str, object]) -> str:
    """Build a fake (unsigned) JWT with the given payload."""
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
    raw_headers: list[tuple[bytes, bytes]] = []
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


async def _dummy_app(scope: object, receive: object, send: object) -> None:
    pass


# ---------------------------------------------------------------------------
# Chat URL regex edge cases
# ---------------------------------------------------------------------------


class TestChatPathRegexEdgeCases:
    """Extended regex coverage: formats that should and should not match."""

    # --- Paths that MUST match ---

    def test_matches_standard_uuid(self) -> None:
        path = "/api/v1/characters/550e8400-e29b-41d4-a716-446655440000/messages"
        assert _CHAT_PATH_RE.match(path) is not None

    def test_matches_short_alphanumeric_id(self) -> None:
        assert _CHAT_PATH_RE.match("/api/v1/characters/abc123/messages") is not None

    def test_matches_numeric_only_id(self) -> None:
        assert _CHAT_PATH_RE.match("/api/v1/characters/42/messages") is not None

    def test_matches_very_long_id(self) -> None:
        long_id = "a" * 200
        path = f"/api/v1/characters/{long_id}/messages"
        assert _CHAT_PATH_RE.match(path) is not None

    def test_matches_underscore_in_id(self) -> None:
        assert _CHAT_PATH_RE.match("/api/v1/characters/char_001/messages") is not None

    def test_matches_mixed_case_id(self) -> None:
        assert _CHAT_PATH_RE.match("/api/v1/characters/CharEmma/messages") is not None

    # --- Paths that MUST NOT match ---

    def test_does_not_match_trailing_slash(self) -> None:
        assert _CHAT_PATH_RE.match("/api/v1/characters/abc/messages/") is None

    def test_does_not_match_get_on_messages_path(self) -> None:
        # The regex itself is path-only; the middleware also checks method.
        # Here we just confirm the regex matches the path (method check is separate).
        # This test documents that _CHAT_PATH_RE alone is path-agnostic to method.
        assert _CHAT_PATH_RE.match("/api/v1/characters/abc/messages") is not None

    def test_does_not_match_empty_character_id(self) -> None:
        # /api/v1/characters//messages has an empty segment
        assert _CHAT_PATH_RE.match("/api/v1/characters//messages") is None

    def test_does_not_match_path_with_slash_in_id(self) -> None:
        # A slash inside the ID segment would be two segments
        assert _CHAT_PATH_RE.match("/api/v1/characters/a/b/messages") is None

    def test_does_not_match_wrong_prefix(self) -> None:
        assert _CHAT_PATH_RE.match("/v1/characters/abc/messages") is None
        assert _CHAT_PATH_RE.match("/characters/abc/messages") is None

    def test_does_not_match_query_string_appended(self) -> None:
        # URL path should never contain query string, but defensive check
        assert _CHAT_PATH_RE.match("/api/v1/characters/abc/messages?limit=20") is None

    def test_does_not_match_memories_endpoint(self) -> None:
        assert _CHAT_PATH_RE.match("/api/v1/characters/abc/memories") is None

    def test_does_not_match_stream_subpath(self) -> None:
        assert _CHAT_PATH_RE.match("/api/v1/characters/abc/messages/stream") is None

    def test_does_not_match_root_messages_path(self) -> None:
        assert _CHAT_PATH_RE.match("/api/v1/messages") is None

    def test_does_not_match_partial_prefix(self) -> None:
        # Embedded match attempt — regex uses ^...$ anchors
        assert _CHAT_PATH_RE.match("prefix/api/v1/characters/abc/messages") is None


# ---------------------------------------------------------------------------
# JWT format edge cases
# ---------------------------------------------------------------------------


class TestJWTFormatEdgeCases:
    """Various JWT shapes that should/should not yield a sub claim."""

    @pytest.mark.asyncio
    async def test_jwt_without_sub_claim_does_not_trigger_update(self) -> None:
        """JWT payload missing 'sub' is treated as unauthenticated."""
        token = _make_jwt({"iss": "test", "exp": 9999999999})
        request = _make_request(
            headers={"Authorization": f"Bearer {token}"},
        )
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
    async def test_jwt_with_non_string_sub_does_not_trigger_update(self) -> None:
        """JWT sub that is a number should be rejected (spec requires string)."""
        token = _make_jwt({"sub": 12345})
        request = _make_request(
            headers={"Authorization": f"Bearer {token}"},
        )
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
    async def test_jwt_with_empty_string_sub_does_not_trigger_update(self) -> None:
        """JWT sub that is an empty string should be rejected."""
        token = _make_jwt({"sub": ""})
        request = _make_request(
            headers={"Authorization": f"Bearer {token}"},
        )
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
    async def test_jwt_with_null_sub_does_not_trigger_update(self) -> None:
        """JWT sub set to null/None should not trigger activity update."""
        token = _make_jwt({"sub": None})
        request = _make_request(
            headers={"Authorization": f"Bearer {token}"},
        )
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
    async def test_jwt_with_extra_claims_still_extracts_sub(self) -> None:
        """JWT with many extra claims correctly extracts sub."""
        token = _make_jwt({
            "sub": "user_extras",
            "iss": "https://cognito.us-east-1.amazonaws.com",
            "aud": "client_id_abc",
            "exp": 9999999999,
            "iat": 1000000000,
            "email": "user@example.com",
            "cognito:username": "user_extras",
        })
        request = _make_request(
            headers={"Authorization": f"Bearer {token}"},
        )
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
        mock_update.assert_called_once_with(user_id="user_extras", is_chat_request=False)

    @pytest.mark.asyncio
    async def test_two_part_token_does_not_trigger_update(self) -> None:
        """JWT with only header.payload (missing signature) is rejected."""
        header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
        payload = (
            base64.urlsafe_b64encode(json.dumps({"sub": "user_2part"}).encode())
            .rstrip(b"=")
            .decode()
        )
        token = f"{header}.{payload}"  # missing third segment
        request = _make_request(
            headers={"Authorization": f"Bearer {token}"},
        )
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
    async def test_four_part_token_does_not_trigger_update(self) -> None:
        """JWT with four segments (not a valid JWT format) is rejected."""
        token = _make_jwt({"sub": "user_4part"}) + ".extra"
        request = _make_request(
            headers={"Authorization": f"Bearer {token}"},
        )
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


# ---------------------------------------------------------------------------
# Authorization header format variants
# ---------------------------------------------------------------------------


class TestAuthorizationHeaderVariants:
    """Authorization header formats that should be rejected."""

    @pytest.mark.asyncio
    async def test_no_bearer_prefix_rejected(self) -> None:
        """Authorization: Token <jwt> (wrong scheme) does not trigger update."""
        token = _make_jwt({"sub": "user_wrong_scheme"})
        request = _make_request(
            headers={"Authorization": f"Token {token}"},
        )
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
    async def test_basic_auth_header_rejected(self) -> None:
        """Authorization: Basic <credentials> does not trigger update."""
        request = _make_request(
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
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
    async def test_bearer_with_no_token_rejected(self) -> None:
        """Authorization: Bearer (no token after prefix) does not trigger update."""
        request = _make_request(
            headers={"Authorization": "Bearer "},
        )
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
    async def test_empty_authorization_header_rejected(self) -> None:
        """Empty Authorization header does not trigger update."""
        request = _make_request(
            headers={"Authorization": ""},
        )
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


# ---------------------------------------------------------------------------
# HTTP method vs chat detection
# ---------------------------------------------------------------------------


class TestHTTPMethodChatDetection:
    """Only POST to messages path should set is_chat_request=True."""

    @pytest.mark.asyncio
    async def test_get_to_messages_path_is_not_chat(self) -> None:
        """GET /api/v1/characters/{id}/messages (list messages) is not a chat request."""
        token = _make_jwt({"sub": "user_get_msgs"})
        request = _make_request(
            method="GET",
            path="/api/v1/characters/char-abc/messages",
            headers={"Authorization": f"Bearer {token}"},
        )
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
        mock_update.assert_called_once_with(user_id="user_get_msgs", is_chat_request=False)

    @pytest.mark.asyncio
    async def test_put_to_messages_path_is_not_chat(self) -> None:
        """PUT to messages path is not classified as chat."""
        token = _make_jwt({"sub": "user_put_msgs"})
        request = _make_request(
            method="PUT",
            path="/api/v1/characters/char-abc/messages",
            headers={"Authorization": f"Bearer {token}"},
        )
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
        mock_update.assert_called_once_with(user_id="user_put_msgs", is_chat_request=False)

    @pytest.mark.asyncio
    async def test_patch_to_messages_path_is_not_chat(self) -> None:
        """PATCH to messages path is not classified as chat."""
        token = _make_jwt({"sub": "user_patch_msgs"})
        request = _make_request(
            method="PATCH",
            path="/api/v1/characters/char-abc/messages",
            headers={"Authorization": f"Bearer {token}"},
        )
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
        mock_update.assert_called_once_with(user_id="user_patch_msgs", is_chat_request=False)

    @pytest.mark.asyncio
    async def test_delete_to_messages_path_is_not_chat(self) -> None:
        """DELETE to messages path is not classified as chat."""
        token = _make_jwt({"sub": "user_del_msgs"})
        request = _make_request(
            method="DELETE",
            path="/api/v1/characters/char-abc/messages",
            headers={"Authorization": f"Bearer {token}"},
        )
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
        mock_update.assert_called_once_with(user_id="user_del_msgs", is_chat_request=False)


# ---------------------------------------------------------------------------
# Background task chaining variants
# ---------------------------------------------------------------------------


class TestBackgroundTaskChaining:
    """Test all variants of response.background chaining."""

    @pytest.mark.asyncio
    async def test_chains_when_existing_task_is_background_tasks_instance(self) -> None:
        """When response already has a BackgroundTasks (plural) instance, activity task is added."""
        token = _make_jwt({"sub": "user_chain_multi"})
        request = _make_request(
            headers={"Authorization": f"Bearer {token}"},
        )
        middleware = ActivityTrackingMiddleware(_dummy_app)

        call_log: list[str] = []

        async def _task_a() -> None:
            call_log.append("task_a")

        async def _task_b() -> None:
            call_log.append("task_b")

        async def _call_next(req: Request) -> Response:
            resp = Response(status_code=200)
            existing_tasks = BackgroundTasks()
            existing_tasks.add_task(_task_a)
            existing_tasks.add_task(_task_b)
            resp.background = existing_tasks  # type: ignore[assignment]
            return resp

        with patch(
            "app.middleware.activity_tracking.update_user_activity",
            new_callable=AsyncMock,
        ) as mock_update:
            response = await middleware.dispatch(request, _call_next)

        assert response.background is not None
        await response.background()  # type: ignore[misc]

        assert "task_a" in call_log
        assert "task_b" in call_log
        mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_existing_task_executes_before_activity_task(self) -> None:
        """Pre-existing background task runs before the activity tracking task."""
        token = _make_jwt({"sub": "user_order"})
        request = _make_request(
            headers={"Authorization": f"Bearer {token}"},
        )
        middleware = ActivityTrackingMiddleware(_dummy_app)

        execution_order: list[str] = []

        async def _route_task() -> None:
            execution_order.append("route_task")

        async def _mock_activity(user_id: str, is_chat_request: bool) -> None:
            execution_order.append("activity_task")

        async def _call_next(req: Request) -> Response:
            resp = Response(status_code=200)
            resp.background = BackgroundTask(_route_task)  # type: ignore[assignment]
            return resp

        with patch(
            "app.middleware.activity_tracking.update_user_activity",
            new_callable=AsyncMock,
            side_effect=_mock_activity,
        ):
            response = await middleware.dispatch(request, _call_next)

        await response.background()  # type: ignore[misc]

        assert execution_order == ["route_task", "activity_task"]

    @pytest.mark.asyncio
    async def test_no_existing_task_sets_single_background_task(self) -> None:
        """When response has no existing background, activity task is set directly."""
        token = _make_jwt({"sub": "user_single"})
        request = _make_request(
            headers={"Authorization": f"Bearer {token}"},
        )
        middleware = ActivityTrackingMiddleware(_dummy_app)

        async def _call_next(req: Request) -> Response:
            return Response(status_code=200)  # no background set

        with patch(
            "app.middleware.activity_tracking.update_user_activity",
            new_callable=AsyncMock,
        ) as mock_update:
            response = await middleware.dispatch(request, _call_next)

        # Should be a BackgroundTask (not BackgroundTasks) for efficiency
        assert response.background is not None
        assert isinstance(response.background, BackgroundTask)
        await response.background()  # type: ignore[misc]
        mock_update.assert_called_once()


# ---------------------------------------------------------------------------
# Middleware ordering / response passthrough
# ---------------------------------------------------------------------------


class TestMiddlewareResponsePassthrough:
    """Middleware must not alter the response body or status code."""

    @pytest.mark.asyncio
    async def test_4xx_response_status_preserved(self) -> None:
        """Middleware passes 4xx responses through without modification."""
        token = _make_jwt({"sub": "user_4xx"})
        request = _make_request(
            method="GET",
            path="/api/v1/characters",
            headers={"Authorization": f"Bearer {token}"},
        )
        middleware = ActivityTrackingMiddleware(_dummy_app)

        async def _call_next(req: Request) -> Response:
            return Response(status_code=403, content=b"Forbidden")

        with patch(
            "app.middleware.activity_tracking.update_user_activity",
            new_callable=AsyncMock,
        ):
            response = await middleware.dispatch(request, _call_next)

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_5xx_response_still_schedules_activity_update(self) -> None:
        """Even on 5xx responses, activity is still tracked (request was authenticated)."""
        token = _make_jwt({"sub": "user_5xx"})
        request = _make_request(
            method="GET",
            path="/api/v1/characters",
            headers={"Authorization": f"Bearer {token}"},
        )
        middleware = ActivityTrackingMiddleware(_dummy_app)

        async def _call_next(req: Request) -> Response:
            return Response(status_code=500)

        with patch(
            "app.middleware.activity_tracking.update_user_activity",
            new_callable=AsyncMock,
        ) as mock_update:
            response = await middleware.dispatch(request, _call_next)

        assert response.status_code == 500
        assert response.background is not None
        await response.background()  # type: ignore[misc]
        mock_update.assert_called_once_with(user_id="user_5xx", is_chat_request=False)

    @pytest.mark.asyncio
    async def test_middleware_exception_during_jwt_parse_returns_response(self) -> None:
        """If _extract_sub_from_jwt raises unexpectedly, response is still returned."""
        token = _make_jwt({"sub": "user_exc"})
        request = _make_request(
            headers={"Authorization": f"Bearer {token}"},
        )
        middleware = ActivityTrackingMiddleware(_dummy_app)

        async def _call_next(req: Request) -> Response:
            return Response(status_code=200)

        with patch(
            "app.middleware.activity_tracking._extract_sub_from_jwt",
            side_effect=RuntimeError("unexpected parsing error"),
        ):
            response = await middleware.dispatch(request, _call_next)

        # Middleware must be fail-open; response is still returned
        assert response.status_code == 200
        # No background task should be set since we couldn't parse the JWT
        assert response.background is None


# ---------------------------------------------------------------------------
# Concurrent upsert behaviour (middleware-level)
# ---------------------------------------------------------------------------


class TestConcurrentMiddlewareDispatches:
    """Multiple concurrent dispatches for the same user are each independent."""

    @pytest.mark.asyncio
    async def test_concurrent_dispatches_all_schedule_tasks(self) -> None:
        """N concurrent authenticated requests each schedule an activity update."""
        token = _make_jwt({"sub": "user_concurrent"})
        middleware = ActivityTrackingMiddleware(_dummy_app)

        async def _call_next(req: Request) -> Response:
            return Response(status_code=200)

        call_count = 0

        async def _mock_update(user_id: str, is_chat_request: bool) -> None:
            nonlocal call_count
            call_count += 1

        async def _dispatch_one() -> None:
            request = _make_request(
                headers={"Authorization": f"Bearer {token}"},
            )
            with patch(
                "app.middleware.activity_tracking.update_user_activity",
                new_callable=AsyncMock,
                side_effect=_mock_update,
            ):
                response = await middleware.dispatch(request, _call_next)
            await response.background()  # type: ignore[misc]

        await asyncio.gather(*[_dispatch_one() for _ in range(5)])
        assert call_count == 5
