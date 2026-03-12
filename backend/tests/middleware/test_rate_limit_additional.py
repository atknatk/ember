"""Additional edge-case tests for rate limiting core logic and middleware.

Supplements the tests written by backend-dev with coverage for:
  - Unknown HTTP method fallback (OPTIONS, HEAD)
  - extract_user_key exception path (malformed base64 / invalid JSON)
  - Middleware fail-open path (exception inside dispatch)
  - Boundary conditions at exact limit
  - Token bucket refill at exact threshold
  - Cleanup triggered by time passing (via _maybe_cleanup)
  - Config-driven limits reflected in headers
  - Write limit enforcement via integration client
  - Unauthenticated (IP-keyed) rate limiting
  - Sub claim with non-string value falls back to IP
  - JWT with exactly-padded payload
  - Retry-After is always a positive integer (>= 1)
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://ember:ember@localhost:5432/ember_test")

from app.core.rate_limit import RateLimiter, TokenBucket, extract_user_key  # noqa: E402
from app.dependencies import get_db  # noqa: E402
from app.main import app  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_jwt_token(payload: dict[str, object]) -> str:
    """Create a minimal JWT (header.payload.signature) for testing."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = base64.urlsafe_b64encode(b"fakesig").decode().rstrip("=")
    return f"{header}.{body}.{sig}"


def _make_request(
    *,
    authorization: str | None = None,
    client_host: str = "10.0.0.1",
) -> MagicMock:
    """Create a mock Starlette Request."""
    request = MagicMock()
    headers: dict[str, str] = {}
    if authorization is not None:
        headers["authorization"] = authorization
    request.headers = headers
    request.client = MagicMock()
    request.client.host = client_host
    return request


async def _override_get_db() -> AsyncGenerator[MagicMock, None]:
    from unittest.mock import AsyncMock
    yield AsyncMock()


@pytest_asyncio.fixture
async def test_client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client with DB dependency overridden."""
    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# TokenBucket — additional edge cases
# ---------------------------------------------------------------------------


class TestTokenBucketEdgeCases:
    """Edge cases not covered by the primary token bucket tests."""

    def test_exactly_at_limit_boundary_allowed(self) -> None:
        """Exactly 1.0 tokens remaining allows the request."""
        bucket = TokenBucket(max_tokens=10)
        with patch("app.core.rate_limit.time.monotonic", return_value=0.0):
            bucket.last_refill = 0.0
            bucket.tokens = 1.0  # Exactly at the boundary
            allowed, retry_after = bucket.consume()
        assert allowed is True
        assert retry_after == 0.0
        assert bucket.tokens == 0.0

    def test_just_below_limit_boundary_rejected(self) -> None:
        """Token count just below 1.0 rejects the request."""
        bucket = TokenBucket(max_tokens=10)
        with patch("app.core.rate_limit.time.monotonic", return_value=0.0):
            bucket.last_refill = 0.0
            bucket.tokens = 0.9999
            allowed, retry_after = bucket.consume()
        assert allowed is False
        assert retry_after > 0.0

    def test_refill_rate_is_max_tokens_over_60(self) -> None:
        """Refill rate is always max_tokens / 60.0 seconds."""
        for max_t in (10, 20, 60):
            bucket = TokenBucket(max_tokens=max_t)
            assert bucket.refill_rate == max_t / 60.0

    def test_partial_refill_does_not_exceed_max(self) -> None:
        """Partially depleted bucket refills correctly but never exceeds max."""
        bucket = TokenBucket(max_tokens=60)
        with patch("app.core.rate_limit.time.monotonic", return_value=0.0):
            bucket.last_refill = 0.0
            bucket.tokens = 30.0

        # Advance 10 seconds: refill_rate = 60/60 = 1 token/sec; 10 tokens added
        with patch("app.core.rate_limit.time.monotonic", return_value=10.0):
            bucket.consume()
            # 30 + 10 - 1 (consumed) = 39
            assert bucket.tokens == 39.0

    def test_retry_after_is_inverse_of_refill_rate(self) -> None:
        """retry_after matches the time required to accumulate one token."""
        bucket = TokenBucket(max_tokens=10)
        with patch("app.core.rate_limit.time.monotonic", return_value=0.0):
            bucket.last_refill = 0.0
            bucket.tokens = 0.0  # Empty
            allowed, retry_after = bucket.consume()
        assert allowed is False
        # Need 1 full token; refill_rate = 10/60
        expected = 1.0 / (10 / 60.0)
        assert abs(retry_after - expected) < 0.001


# ---------------------------------------------------------------------------
# RateLimiter — additional edge cases
# ---------------------------------------------------------------------------


class TestRateLimiterEdgeCases:
    """Edge cases for RateLimiter not covered by primary tests."""

    def _make_limiter(self) -> RateLimiter:
        return RateLimiter(
            group_limits={"chat": 10, "write": 20, "read": 60},
            exempt_paths={"/api/v1/health"},
        )

    def test_classify_options_method_defaults_to_write(self) -> None:
        """Unknown HTTP methods (OPTIONS) default to 'write' group."""
        limiter = self._make_limiter()
        # OPTIONS is not POST/PUT/DELETE/PATCH/GET — hits the final return "write"
        result = limiter.classify_request("OPTIONS", "/api/v1/characters")
        assert result == "write"

    def test_classify_head_method_defaults_to_write(self) -> None:
        """HEAD method defaults to 'write' group (not GET)."""
        limiter = self._make_limiter()
        result = limiter.classify_request("HEAD", "/api/v1/characters")
        assert result == "write"

    def test_classify_patch_is_write(self) -> None:
        """PATCH method is classified as write."""
        limiter = self._make_limiter()
        result = limiter.classify_request("PATCH", "/api/v1/characters/some-id")
        assert result == "write"

    def test_classify_get_memories_is_read(self) -> None:
        """GET /api/v1/memories classified as read."""
        limiter = self._make_limiter()
        assert limiter.classify_request("GET", "/api/v1/memories") == "read"

    def test_classify_delete_memories_is_write(self) -> None:
        """DELETE /api/v1/memories/some-id classified as write."""
        limiter = self._make_limiter()
        assert limiter.classify_request("DELETE", "/api/v1/memories/some-id") == "write"

    def test_check_with_unknown_group_uses_default_20(self) -> None:
        """An unknown group falls back to default limit of 20."""
        limiter = self._make_limiter()
        # "unknown_group" is not in group_limits, so max_tokens defaults to 20
        allowed, headers = limiter.check("user-x", "unknown_group")
        assert allowed is True
        assert headers["X-RateLimit-Limit"] == "20"

    def test_headers_x_ratelimit_remaining_decrements(self) -> None:
        """X-RateLimit-Remaining decrements correctly after each request."""
        limiter = self._make_limiter()
        with patch("app.core.rate_limit.time.monotonic", return_value=0.0):
            _, h1 = limiter.check("user-dec", "chat")
            remaining1 = int(h1["X-RateLimit-Remaining"])

            _, h2 = limiter.check("user-dec", "chat")
            remaining2 = int(h2["X-RateLimit-Remaining"])

        assert remaining2 == remaining1 - 1

    def test_headers_x_ratelimit_limit_matches_group_config(self) -> None:
        """X-RateLimit-Limit matches the configured limit for each group."""
        limiter = self._make_limiter()
        _, hc = limiter.check("u", "chat")
        _, hw = limiter.check("u", "write")
        _, hr = limiter.check("u", "read")
        assert hc["X-RateLimit-Limit"] == "10"
        assert hw["X-RateLimit-Limit"] == "20"
        assert hr["X-RateLimit-Limit"] == "60"

    def test_retry_after_header_always_at_least_1(self) -> None:
        """Retry-After is >= 1 even when bucket is almost refilled."""
        limiter = self._make_limiter()
        with patch("app.core.rate_limit.time.monotonic", return_value=0.0):
            for _ in range(10):
                limiter.check("user-min", "chat")
            _, headers = limiter.check("user-min", "chat")
        assert int(headers["Retry-After"]) >= 1

    def test_maybe_cleanup_not_triggered_before_interval(self) -> None:
        """Cleanup does not run before cleanup_interval elapses."""
        with patch("app.core.rate_limit.time.monotonic", return_value=0.0):
            limiter = RateLimiter(
                group_limits={"chat": 10},
                exempt_paths=set(),
                cleanup_interval=300.0,
            )
            limiter._buckets["stale-user:chat"] = TokenBucket(max_tokens=10)

        # Only 100 seconds elapsed — cleanup interval not yet reached
        with patch("app.core.rate_limit.time.monotonic", return_value=100.0):
            limiter.check("trigger-user", "chat")

        # Stale bucket should still be present (no cleanup ran)
        assert "stale-user:chat" in limiter._buckets

    def test_cleanup_removes_only_full_buckets(self) -> None:
        """Cleanup removes full (max) buckets but keeps partially-consumed ones."""
        with patch("app.core.rate_limit.time.monotonic", return_value=0.0):
            limiter = RateLimiter(
                group_limits={"chat": 10},
                exempt_paths=set(),
                cleanup_interval=0.0,
            )

        # Create a full (stale) bucket and a partially-consumed bucket
        full_bucket = TokenBucket(max_tokens=10)
        full_bucket.tokens = 10.0
        partial_bucket = TokenBucket(max_tokens=10)
        partial_bucket.tokens = 5.0

        limiter._buckets["full-user:chat"] = full_bucket
        limiter._buckets["active-user:chat"] = partial_bucket

        with patch("app.core.rate_limit.time.monotonic", return_value=600.0):
            limiter.check("trigger-user", "chat")

        assert "full-user:chat" not in limiter._buckets
        assert "active-user:chat" in limiter._buckets

    def test_exempt_path_not_classified_regardless_of_method(self) -> None:
        """Exempt path returns None for all HTTP methods."""
        limiter = self._make_limiter()
        for method in ("GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"):
            result = limiter.classify_request(method, "/api/v1/health")
            assert result is None, f"Expected None for {method} /api/v1/health"

    def test_multiple_exempt_paths_all_bypassed(self) -> None:
        """All paths in exempt_paths set are bypassed."""
        limiter = RateLimiter(
            group_limits={"read": 60},
            exempt_paths={"/api/v1/health", "/api/v1/ready"},
        )
        assert limiter.classify_request("GET", "/api/v1/health") is None
        assert limiter.classify_request("GET", "/api/v1/ready") is None
        assert limiter.classify_request("GET", "/api/v1/characters") == "read"


# ---------------------------------------------------------------------------
# extract_user_key — additional edge cases
# ---------------------------------------------------------------------------


class TestExtractUserKeyEdgeCases:
    """Edge cases for extract_user_key not covered by primary tests."""

    def test_bearer_token_with_invalid_base64_falls_back_to_ip(self) -> None:
        """JWT payload with invalid base64 triggers except branch → IP fallback."""
        # Construct a token where the payload part is not valid base64url
        request = _make_request(
            authorization="Bearer header.!!!invalid_base64!!!.sig",
            client_host="1.2.3.4",
        )
        result = extract_user_key(request)
        assert result == "ip:1.2.3.4"

    def test_bearer_token_with_non_json_payload_falls_back_to_ip(self) -> None:
        """JWT payload that decodes but is not valid JSON triggers except branch."""
        # Encode a non-JSON string as the payload
        not_json = base64.urlsafe_b64encode(b"this is not json").decode().rstrip("=")
        request = _make_request(
            authorization=f"Bearer header.{not_json}.sig",
            client_host="5.6.7.8",
        )
        result = extract_user_key(request)
        assert result == "ip:5.6.7.8"

    def test_bearer_token_with_integer_sub_falls_back_to_ip(self) -> None:
        """JWT with a non-string sub claim (e.g., integer) falls back to IP."""
        token = _make_jwt_token({"sub": 12345})  # sub is int, not str
        request = _make_request(
            authorization=f"Bearer {token}",
            client_host="9.10.11.12",
        )
        result = extract_user_key(request)
        assert result == "ip:9.10.11.12"

    def test_bearer_token_with_null_sub_falls_back_to_ip(self) -> None:
        """JWT with sub=null falls back to IP."""
        token = _make_jwt_token({"sub": None})
        request = _make_request(
            authorization=f"Bearer {token}",
            client_host="13.14.15.16",
        )
        result = extract_user_key(request)
        assert result == "ip:13.14.15.16"

    def test_bearer_token_with_empty_string_sub_falls_back_to_ip(self) -> None:
        """JWT with sub='' (empty string, falsy) falls back to IP."""
        token = _make_jwt_token({"sub": ""})
        request = _make_request(
            authorization=f"Bearer {token}",
            client_host="17.18.19.20",
        )
        result = extract_user_key(request)
        assert result == "ip:17.18.19.20"

    def test_bearer_prefix_only_no_token_falls_back_to_ip(self) -> None:
        """'Bearer ' with nothing after it has 1 part — falls back to IP."""
        request = _make_request(
            authorization="Bearer ",
            client_host="21.22.23.24",
        )
        result = extract_user_key(request)
        assert result == "ip:21.22.23.24"

    def test_two_part_jwt_falls_back_to_ip(self) -> None:
        """JWT with only 2 parts (missing signature) falls back to IP."""
        request = _make_request(
            authorization="Bearer header.payload",
            client_host="25.26.27.28",
        )
        result = extract_user_key(request)
        assert result == "ip:25.26.27.28"

    def test_four_part_jwt_falls_back_to_ip(self) -> None:
        """JWT with 4 parts (malformed) falls back to IP."""
        request = _make_request(
            authorization="Bearer a.b.c.d",
            client_host="29.30.31.32",
        )
        result = extract_user_key(request)
        assert result == "ip:29.30.31.32"

    def test_correctly_padded_base64_payload(self) -> None:
        """JWT payload requiring no padding is decoded correctly."""
        # Create a sub that produces a base64 string with length divisible by 4
        sub = "user-abc-def-ghi"
        payload_bytes = json.dumps({"sub": sub}).encode()
        # Manually pad to ensure even length
        b64 = base64.urlsafe_b64encode(payload_bytes).decode().rstrip("=")
        header = base64.urlsafe_b64encode(b'{"alg":"RS256"}').decode().rstrip("=")
        sig = base64.urlsafe_b64encode(b"sig").decode().rstrip("=")
        token = f"{header}.{b64}.{sig}"
        request = _make_request(authorization=f"Bearer {token}")
        assert extract_user_key(request) == sub

    def test_ip_key_format_uses_prefix(self) -> None:
        """IP-based key always starts with 'ip:' prefix."""
        request = _make_request(client_host="192.168.0.100")
        result = extract_user_key(request)
        assert result.startswith("ip:")
        assert "192.168.0.100" in result


# ---------------------------------------------------------------------------
# Middleware integration — additional edge cases
# ---------------------------------------------------------------------------


class TestMiddlewareAdditionalIntegration:
    """Integration tests for edge cases in the RateLimitMiddleware dispatch."""

    def test_write_limit_exceeded_direct(self) -> None:
        """21st write-group check on RateLimiter returns not-allowed."""
        limiter = RateLimiter(
            group_limits={"write": 20},
            exempt_paths=set(),
        )
        with patch("app.core.rate_limit.time.monotonic", return_value=9000.0):
            for i in range(20):
                allowed, _ = limiter.check("write-user", "write")
                assert allowed is True, f"Request {i + 1} was prematurely limited"

            allowed, headers = limiter.check("write-user", "write")
            assert allowed is False
            assert "Retry-After" in headers

    def test_unauthenticated_ip_keyed_rate_limiting_direct(self) -> None:
        """IP-keyed requests (no JWT) are rate-limited independently from user buckets."""
        limiter = RateLimiter(
            group_limits={"write": 20},
            exempt_paths=set(),
        )
        ip_key = "ip:10.0.0.1"
        user_key = "some-user-uuid"

        with patch("app.core.rate_limit.time.monotonic", return_value=10000.0):
            # Exhaust the IP-keyed bucket (20 requests)
            for _ in range(20):
                limiter.check(ip_key, "write")

            # 21st IP request is blocked
            ip_allowed, _ = limiter.check(ip_key, "write")
            assert ip_allowed is False

            # But a different user key is still allowed
            user_allowed, _ = limiter.check(user_key, "write")
            assert user_allowed is True

    @pytest.mark.asyncio
    async def test_chat_and_read_groups_independent_for_same_user(
        self, test_client: AsyncClient
    ) -> None:
        """Exhausting the chat limit does not affect the read limit for the same user."""
        token = _make_jwt_token({"sub": "group-independence-user"})

        with patch("app.core.rate_limit.time.monotonic", return_value=11000.0):
            # Exhaust chat limit (10 requests)
            for _ in range(10):
                await test_client.post(
                    "/api/v1/characters/some-char/messages",
                    json={"content": "hi"},
                    headers={"Authorization": f"Bearer {token}"},
                )

            # Chat is now limited
            chat_response = await test_client.post(
                "/api/v1/characters/some-char/messages",
                json={"content": "hi"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert chat_response.status_code == 429

            # Read is still allowed
            read_response = await test_client.get(
                "/api/v1/characters",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert read_response.status_code != 429

    @pytest.mark.asyncio
    async def test_health_exempt_no_rate_limit_headers(self, test_client: AsyncClient) -> None:
        """Health endpoint responses do not include rate limit headers."""
        response = await test_client.get("/api/v1/health")
        assert response.status_code == 200
        assert "x-ratelimit-limit" not in response.headers
        assert "x-ratelimit-remaining" not in response.headers
        assert "x-ratelimit-reset" not in response.headers

    @pytest.mark.asyncio
    async def test_middleware_fail_open_on_exception(self, test_client: AsyncClient) -> None:
        """Middleware passes request through if an exception occurs during rate limiting."""
        with patch(
            "app.middleware.rate_limit.extract_user_key",
            side_effect=RuntimeError("unexpected error"),
        ):
            # Request should pass through (fail-open), not return 500 or 429
            response = await test_client.get("/api/v1/health")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_middleware_fail_open_on_classify_exception(self, test_client: AsyncClient) -> None:
        """Middleware passes request through if classify_request raises."""
        with patch.object(
            app.state.rate_limiter,
            "classify_request",
            side_effect=RuntimeError("classify failed"),
        ):
            response = await test_client.get("/api/v1/health")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_x_ratelimit_reset_is_integer_unix_timestamp(self, test_client: AsyncClient) -> None:
        """X-RateLimit-Reset is a valid integer Unix timestamp (> 0)."""
        token = _make_jwt_token({"sub": "reset-ts-user"})
        response = await test_client.get(
            "/api/v1/characters",
            headers={"Authorization": f"Bearer {token}"},
        )
        reset_header = response.headers.get("x-ratelimit-reset")
        assert reset_header is not None
        reset_val = int(reset_header)
        # Should be a reasonable Unix timestamp (after year 2020)
        assert reset_val > 1_580_000_000

    @pytest.mark.asyncio
    async def test_429_body_has_detail_key_only(self, test_client: AsyncClient) -> None:
        """429 body is exactly {'detail': 'Rate limit exceeded'} — no extra keys."""
        token = _make_jwt_token({"sub": "body-format-user"})

        with patch("app.core.rate_limit.time.monotonic", return_value=12000.0):
            for _ in range(10):
                await test_client.post(
                    "/api/v1/characters/x/messages",
                    json={"content": "hi"},
                    headers={"Authorization": f"Bearer {token}"},
                )

            response = await test_client.post(
                "/api/v1/characters/x/messages",
                json={"content": "hi"},
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 429
        body = response.json()
        assert set(body.keys()) == {"detail"}
        assert body["detail"] == "Rate limit exceeded"

    @pytest.mark.asyncio
    async def test_rate_limit_headers_present_on_non_200_responses(
        self, test_client: AsyncClient
    ) -> None:
        """Rate limit headers are present even on 401/403/404 responses."""
        token = _make_jwt_token({"sub": "headers-on-error-user"})
        # GET /api/v1/characters without proper auth will 401/403 but still has rate limit headers
        response = await test_client.get(
            "/api/v1/characters",
            headers={"Authorization": f"Bearer {token}"},
        )
        # Status could be 401 or another non-200; rate limit headers should still be set
        assert "x-ratelimit-limit" in response.headers
        assert "x-ratelimit-remaining" in response.headers


# ---------------------------------------------------------------------------
# Config — rate limit settings reflected in middleware
# ---------------------------------------------------------------------------


class TestRateLimitConfig:
    """Verify config fields are used by the rate limiter registered on app.state."""

    def test_app_state_rate_limiter_group_limits_match_settings(self) -> None:
        """app.state.rate_limiter group limits match Settings values."""
        from app.config import settings

        limiter = app.state.rate_limiter
        assert limiter._group_limits["chat"] == settings.rate_limit_chat
        assert limiter._group_limits["write"] == settings.rate_limit_write
        assert limiter._group_limits["read"] == settings.rate_limit_read

    def test_app_state_rate_limiter_exempt_paths_includes_health(self) -> None:
        """app.state.rate_limiter has health endpoint in exempt_paths."""
        limiter = app.state.rate_limiter
        assert "/api/v1/health" in limiter._exempt_paths

    def test_settings_default_values(self) -> None:
        """Default rate limit settings match the spec."""
        from app.config import Settings

        s = Settings(_env_file=None)  # type: ignore[call-arg]
        assert s.rate_limit_chat == 10
        assert s.rate_limit_write == 20
        assert s.rate_limit_read == 60
