"""Integration tests for the RateLimitMiddleware.

Tests use the FastAPI test client with the middleware registered,
verifying end-to-end rate limiting behavior including headers,
429 responses, and exempt paths.
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set test environment before any app imports
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://ember:ember@localhost:5432/ember_test")

from app.dependencies import get_db  # noqa: E402
from app.main import app  # noqa: E402


def _make_jwt_token(sub: str) -> str:
    """Create a minimal JWT for testing (not cryptographically signed)."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).decode().rstrip("=")
    sig = base64.urlsafe_b64encode(b"fakesig").decode().rstrip("=")
    return f"{header}.{body}.{sig}"


async def _override_get_db() -> AsyncGenerator[AsyncMock, None]:
    """Yield a mock database session."""
    yield AsyncMock()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client with auth dependency overridden."""
    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


class TestRateLimitHeaders:
    """Tests for rate limit response headers on normal requests."""

    @pytest.mark.asyncio
    async def test_response_includes_rate_limit_headers(self, client: AsyncClient) -> None:
        """Test 21: Response includes rate limit headers."""
        response = await client.get("/api/v1/health")
        # Health is exempt, so no rate limit headers
        assert response.status_code == 200

        # Try a non-exempt endpoint — GET /api/v1/characters
        # This will likely 401 or 403, but headers should still be present
        # Use a token so the rate limiter keys by sub
        token = _make_jwt_token("test-user-1")
        response = await client.get(
            "/api/v1/characters",
            headers={"Authorization": f"Bearer {token}"},
        )
        # We care about headers regardless of status code
        assert "x-ratelimit-limit" in response.headers
        assert "x-ratelimit-remaining" in response.headers
        assert "x-ratelimit-reset" in response.headers


class TestHealthExemption:
    """Tests for health endpoint exemption from rate limiting."""

    @pytest.mark.asyncio
    async def test_health_never_rate_limited(self, client: AsyncClient) -> None:
        """Test 22: Health endpoint is never rate limited."""
        # Send many requests to health endpoint
        for _ in range(100):
            response = await client.get("/api/v1/health")
            assert response.status_code == 200


class TestRateLimitEnforcement:
    """Tests for rate limit enforcement (429 responses)."""

    @pytest.mark.asyncio
    async def test_chat_limit_exceeded(self, client: AsyncClient) -> None:
        """Test 23: 11th chat request within 1 minute returns 429."""
        token = _make_jwt_token("chat-limit-user")

        with patch("app.core.rate_limit.time.monotonic", return_value=1000.0):
            # First 10 requests should succeed (they may 401 from auth,
            # but the rate limiter should not block them)
            for i in range(10):
                response = await client.post(
                    "/api/v1/characters/some-char-id/messages",
                    json={"content": f"msg {i}"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert response.status_code != 429, f"Request {i + 1} was rate limited"

            # 11th request should be rate limited
            response = await client.post(
                "/api/v1/characters/some-char-id/messages",
                json={"content": "msg 11"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_read_limit_exceeded(self, client: AsyncClient) -> None:
        """Test 24: 61st GET request within 1 minute returns 429."""
        token = _make_jwt_token("read-limit-user")

        with patch("app.core.rate_limit.time.monotonic", return_value=2000.0):
            for i in range(60):
                response = await client.get(
                    "/api/v1/characters",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert response.status_code != 429, f"GET request {i + 1} was rate limited"

            # 61st request should be rate limited
            response = await client.get(
                "/api/v1/characters",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_429_response_format(self, client: AsyncClient) -> None:
        """Test 25: 429 response has correct content type and body."""
        token = _make_jwt_token("format-test-user")

        with patch("app.core.rate_limit.time.monotonic", return_value=3000.0):
            # Exhaust the chat limit
            for _ in range(10):
                await client.post(
                    "/api/v1/characters/some-id/messages",
                    json={"content": "msg"},
                    headers={"Authorization": f"Bearer {token}"},
                )

            response = await client.post(
                "/api/v1/characters/some-id/messages",
                json={"content": "msg"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 429
            assert response.headers["content-type"] == "application/json"
            body = response.json()
            assert body == {"detail": "Rate limit exceeded"}

    @pytest.mark.asyncio
    async def test_429_includes_cors_headers(self, client: AsyncClient) -> None:
        """Test 26: 429 response includes CORS headers."""
        token = _make_jwt_token("cors-test-user")

        with patch("app.core.rate_limit.time.monotonic", return_value=4000.0):
            for _ in range(10):
                await client.post(
                    "/api/v1/characters/some-id/messages",
                    json={"content": "msg"},
                    headers={"Authorization": f"Bearer {token}"},
                )

            response = await client.post(
                "/api/v1/characters/some-id/messages",
                json={"content": "msg"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Origin": "http://localhost:3000",
                },
            )
            assert response.status_code == 429
            # CORS middleware should add this header
            assert "access-control-allow-origin" in response.headers


class TestUserIsolation:
    """Tests for independent rate limits between users."""

    @pytest.mark.asyncio
    async def test_different_users_independent(self, client: AsyncClient) -> None:
        """Test 27: User A exhausted does not affect User B."""
        token_a = _make_jwt_token("user-a-isolation")
        token_b = _make_jwt_token("user-b-isolation")

        with patch("app.core.rate_limit.time.monotonic", return_value=5000.0):
            # Exhaust user A's chat limit
            for _ in range(10):
                await client.post(
                    "/api/v1/characters/some-id/messages",
                    json={"content": "msg"},
                    headers={"Authorization": f"Bearer {token_a}"},
                )

            # User A is limited
            response_a = await client.post(
                "/api/v1/characters/some-id/messages",
                json={"content": "msg"},
                headers={"Authorization": f"Bearer {token_a}"},
            )
            assert response_a.status_code == 429

            # User B should not be limited
            response_b = await client.post(
                "/api/v1/characters/some-id/messages",
                json={"content": "msg"},
                headers={"Authorization": f"Bearer {token_b}"},
            )
            assert response_b.status_code != 429


class TestRetryAfter:
    """Tests for Retry-After header behavior."""

    @pytest.mark.asyncio
    async def test_retry_after_is_positive_integer(self, client: AsyncClient) -> None:
        """Test 28: Retry-After is a positive integer."""
        token = _make_jwt_token("retry-after-user")

        with patch("app.core.rate_limit.time.monotonic", return_value=6000.0):
            for _ in range(10):
                await client.post(
                    "/api/v1/characters/some-id/messages",
                    json={"content": "msg"},
                    headers={"Authorization": f"Bearer {token}"},
                )

            response = await client.post(
                "/api/v1/characters/some-id/messages",
                json={"content": "msg"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 429
            retry_after = response.headers.get("retry-after")
            assert retry_after is not None
            assert int(retry_after) > 0

    @pytest.mark.asyncio
    async def test_request_succeeds_after_retry_wait(self, client: AsyncClient) -> None:
        """Test 29: Request succeeds after waiting Retry-After seconds."""
        token = _make_jwt_token("retry-wait-user")

        # Exhaust at t=7000
        with patch("app.core.rate_limit.time.monotonic", return_value=7000.0):
            for _ in range(10):
                await client.post(
                    "/api/v1/characters/some-id/messages",
                    json={"content": "msg"},
                    headers={"Authorization": f"Bearer {token}"},
                )

            response = await client.post(
                "/api/v1/characters/some-id/messages",
                json={"content": "msg"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 429
            retry_after = int(response.headers["retry-after"])

        # Advance time by retry_after + 1 seconds
        with patch("app.core.rate_limit.time.monotonic", return_value=7000.0 + retry_after + 1):
            response = await client.post(
                "/api/v1/characters/some-id/messages",
                json={"content": "msg"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code != 429
