"""Unit tests for the rate limiting core logic.

Tests cover TokenBucket, RateLimiter, and extract_user_key without
requiring the full FastAPI application or HTTP client.
"""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

from app.core.rate_limit import RateLimiter, TokenBucket, extract_user_key

# ---------------------------------------------------------------------------
# TokenBucket unit tests
# ---------------------------------------------------------------------------


class TestTokenBucket:
    """Tests for the TokenBucket class."""

    def test_first_request_within_limit(self) -> None:
        """Test 1: First request within limit allows and returns 0 retry."""
        bucket = TokenBucket(max_tokens=10)
        allowed, retry_after = bucket.consume()
        assert allowed is True
        assert retry_after == 0.0
        assert bucket.tokens == 9.0

    def test_requests_up_to_limit(self) -> None:
        """Test 2: All requests up to the limit are allowed."""
        bucket = TokenBucket(max_tokens=10)
        # Freeze time so no refill occurs
        with patch("app.core.rate_limit.time.monotonic", return_value=0.0):
            bucket.last_refill = 0.0
            bucket.tokens = 10.0
            for _ in range(10):
                allowed, retry_after = bucket.consume()
                assert allowed is True
                assert retry_after == 0.0

    def test_request_exceeding_limit(self) -> None:
        """Test 3: Request after exhausting limit is rejected."""
        bucket = TokenBucket(max_tokens=10)
        with patch("app.core.rate_limit.time.monotonic", return_value=0.0):
            bucket.last_refill = 0.0
            bucket.tokens = 0.5  # Less than 1 token
            allowed, retry_after = bucket.consume()
            assert allowed is False
            assert retry_after > 0.0

    def test_refill_after_waiting(self) -> None:
        """Test 4: After waiting, tokens refill and request is allowed."""
        bucket = TokenBucket(max_tokens=10)
        # Exhaust all tokens at t=0
        with patch("app.core.rate_limit.time.monotonic", return_value=0.0):
            bucket.last_refill = 0.0
            bucket.tokens = 0.0

        # Advance time by 6 seconds: refill_rate = 10/60 = 1/6 tokens/sec
        # 6 seconds * 1/6 = 1.0 token
        with patch("app.core.rate_limit.time.monotonic", return_value=6.0):
            allowed, retry_after = bucket.consume()
            assert allowed is True
            assert retry_after == 0.0

    def test_tokens_capped_at_max(self) -> None:
        """Test 5: Tokens do not exceed max_tokens after long idle."""
        bucket = TokenBucket(max_tokens=10)
        with patch("app.core.rate_limit.time.monotonic", return_value=0.0):
            bucket.last_refill = 0.0
            bucket.tokens = 10.0

        # Advance time by 1000 seconds (well beyond full refill)
        with patch("app.core.rate_limit.time.monotonic", return_value=1000.0):
            bucket.consume()
            # After consuming 1, should be max_tokens - 1
            assert bucket.tokens == 9.0


# ---------------------------------------------------------------------------
# RateLimiter unit tests
# ---------------------------------------------------------------------------


class TestRateLimiter:
    """Tests for the RateLimiter class."""

    def _make_limiter(self) -> RateLimiter:
        """Create a RateLimiter with standard test limits."""
        return RateLimiter(
            group_limits={"chat": 10, "write": 20, "read": 60},
            exempt_paths={"/api/v1/health"},
        )

    def test_classify_health_exempt(self) -> None:
        """Test 6: Health endpoint is exempt."""
        limiter = self._make_limiter()
        assert limiter.classify_request("GET", "/api/v1/health") is None

    def test_classify_chat_post_messages(self) -> None:
        """Test 7: POST to messages endpoint classified as chat."""
        limiter = self._make_limiter()
        result = limiter.classify_request(
            "POST", "/api/v1/characters/550e8400-e29b-41d4-a716-446655440000/messages"
        )
        assert result == "chat"

    def test_classify_chat_post_messages_stream(self) -> None:
        """Test 7b: POST to messages/stream endpoint also classified as chat."""
        limiter = self._make_limiter()
        result = limiter.classify_request(
            "POST",
            "/api/v1/characters/550e8400-e29b-41d4-a716-446655440000/messages/stream",
        )
        assert result == "chat"

    def test_classify_post_characters_is_write(self) -> None:
        """Test 8: POST to characters endpoint classified as write."""
        limiter = self._make_limiter()
        assert limiter.classify_request("POST", "/api/v1/characters") == "write"

    def test_classify_get_characters_is_read(self) -> None:
        """Test 9: GET to characters endpoint classified as read."""
        limiter = self._make_limiter()
        assert limiter.classify_request("GET", "/api/v1/characters") == "read"

    def test_classify_put_is_write(self) -> None:
        """Test 10: PUT classified as write."""
        limiter = self._make_limiter()
        result = limiter.classify_request(
            "PUT", "/api/v1/characters/550e8400-e29b-41d4-a716-446655440000"
        )
        assert result == "write"

    def test_classify_delete_is_write(self) -> None:
        """Test 11: DELETE classified as write."""
        limiter = self._make_limiter()
        result = limiter.classify_request(
            "DELETE", "/api/v1/characters/550e8400-e29b-41d4-a716-446655440000"
        )
        assert result == "write"

    def test_classify_post_auth_is_write(self) -> None:
        """Test 12: POST to auth endpoint classified as write."""
        limiter = self._make_limiter()
        assert limiter.classify_request("POST", "/api/v1/auth/register") == "write"

    def test_classify_post_onboarding_is_write(self) -> None:
        """Test 13: POST to onboarding endpoint classified as write."""
        limiter = self._make_limiter()
        assert limiter.classify_request("POST", "/api/v1/onboarding/complete") == "write"

    def test_independent_user_buckets(self) -> None:
        """Test 14: Different users have independent buckets."""
        limiter = self._make_limiter()

        with patch("app.core.rate_limit.time.monotonic", return_value=0.0):
            # Exhaust user A's chat bucket
            for _ in range(10):
                allowed, _ = limiter.check("user-a", "chat")
                assert allowed is True

            # User A is now rate limited
            allowed_a, _ = limiter.check("user-a", "chat")
            assert allowed_a is False

            # User B should still be allowed
            allowed_b, _ = limiter.check("user-b", "chat")
            assert allowed_b is True

    def test_independent_group_buckets(self) -> None:
        """Test 15: Same user has independent buckets per group."""
        limiter = self._make_limiter()

        with patch("app.core.rate_limit.time.monotonic", return_value=0.0):
            # Exhaust user's chat bucket
            for _ in range(10):
                limiter.check("user-a", "chat")

            # Chat is exhausted
            allowed_chat, _ = limiter.check("user-a", "chat")
            assert allowed_chat is False

            # Read should still be allowed
            allowed_read, _ = limiter.check("user-a", "read")
            assert allowed_read is True

    def test_stale_bucket_cleanup(self) -> None:
        """Test 16: Stale buckets are removed during cleanup."""
        with patch("app.core.rate_limit.time.monotonic", return_value=0.0):
            limiter = RateLimiter(
                group_limits={"chat": 10},
                exempt_paths=set(),
                cleanup_interval=0.0,  # Cleanup on every check
            )

        # Create a bucket for user-a and set it to fully refilled (stale)
        bucket_key = "user-a:chat"
        bucket = TokenBucket(max_tokens=10)
        bucket.tokens = 10.0
        limiter._buckets[bucket_key] = bucket

        # Verify it exists before cleanup
        assert bucket_key in limiter._buckets

        with patch("app.core.rate_limit.time.monotonic", return_value=600.0):
            # Trigger cleanup via a check for a different user
            limiter.check("user-b", "chat")

        # user-a's full bucket should have been cleaned up
        assert bucket_key not in limiter._buckets
        # user-b's bucket should still exist (it was just consumed from)
        assert "user-b:chat" in limiter._buckets

    def test_check_returns_headers(self) -> None:
        """Check returns proper rate limit headers."""
        limiter = self._make_limiter()
        allowed, headers = limiter.check("user-a", "chat")
        assert allowed is True
        assert "X-RateLimit-Limit" in headers
        assert "X-RateLimit-Remaining" in headers
        assert "X-RateLimit-Reset" in headers
        assert headers["X-RateLimit-Limit"] == "10"

    def test_check_429_returns_retry_after(self) -> None:
        """Check returns Retry-After header when rate limited."""
        limiter = self._make_limiter()

        with patch("app.core.rate_limit.time.monotonic", return_value=0.0):
            # Exhaust the bucket
            for _ in range(10):
                limiter.check("user-a", "chat")

            allowed, headers = limiter.check("user-a", "chat")
            assert allowed is False
            assert "Retry-After" in headers
            assert int(headers["Retry-After"]) >= 1


# ---------------------------------------------------------------------------
# extract_user_key unit tests
# ---------------------------------------------------------------------------


def _make_jwt_token(payload: dict[str, object]) -> str:
    """Create a minimal JWT (header.payload.signature) for testing.

    No actual signing; extract_user_key only base64-decodes the payload.
    """
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = base64.urlsafe_b64encode(b"fakesig").decode().rstrip("=")
    return f"{header}.{body}.{sig}"


def _make_request(
    *,
    authorization: str | None = None,
    client_host: str = "192.168.1.1",
) -> MagicMock:
    """Create a mock Starlette Request with headers and client info."""
    request = MagicMock()
    headers: dict[str, str] = {}
    if authorization is not None:
        headers["authorization"] = authorization
    request.headers = headers
    request.client = MagicMock()
    request.client.host = client_host
    return request


class TestExtractUserKey:
    """Tests for the extract_user_key function."""

    def test_valid_bearer_jwt(self) -> None:
        """Test 17: Valid JWT extracts sub claim."""
        sub = "550e8400-e29b-41d4-a716-446655440000"
        token = _make_jwt_token({"sub": sub, "aud": "test"})
        request = _make_request(authorization=f"Bearer {token}")
        assert extract_user_key(request) == sub

    def test_no_authorization_header(self) -> None:
        """Test 18: Missing Authorization header falls back to IP."""
        request = _make_request()
        assert extract_user_key(request) == "ip:192.168.1.1"

    def test_malformed_bearer_token(self) -> None:
        """Test 19: Malformed token falls back to IP."""
        request = _make_request(authorization="Bearer not-a-jwt")
        assert extract_user_key(request) == "ip:192.168.1.1"

    def test_basic_auth_header(self) -> None:
        """Test 20: Basic auth falls back to IP."""
        request = _make_request(authorization="Basic dXNlcjpwYXNz")
        assert extract_user_key(request) == "ip:192.168.1.1"

    def test_jwt_without_sub_claim(self) -> None:
        """JWT without sub claim falls back to IP."""
        token = _make_jwt_token({"aud": "test"})
        request = _make_request(authorization=f"Bearer {token}")
        assert extract_user_key(request) == "ip:192.168.1.1"

    def test_no_client_info(self) -> None:
        """Request with no client info uses 'unknown'."""
        request = MagicMock()
        request.headers = {}
        request.client = None
        assert extract_user_key(request) == "ip:unknown"
