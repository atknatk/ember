"""Tests for the Request ID middleware.

Verifies X-Request-ID generation, propagation, validation, and
log context variable binding for request correlation.
"""

from __future__ import annotations

import re
import uuid

import pytest
from httpx import AsyncClient

# UUID v4 pattern for validation
_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@pytest.mark.asyncio
async def test_response_has_request_id_header(client: AsyncClient) -> None:
    """Every response must include an X-Request-ID header."""
    response = await client.get("/api/v1/health")
    assert "X-Request-ID" in response.headers


@pytest.mark.asyncio
async def test_generated_request_id_is_valid_uuid4(client: AsyncClient) -> None:
    """When no X-Request-ID is sent, the server generates a valid UUID v4."""
    response = await client.get("/api/v1/health")
    request_id = response.headers["X-Request-ID"]
    assert _UUID4_RE.match(request_id), f"Expected UUID v4, got: {request_id}"


@pytest.mark.asyncio
async def test_client_request_id_is_echoed(client: AsyncClient) -> None:
    """When client sends X-Request-ID, the server echoes it back."""
    custom_id = "custom-id-123"
    response = await client.get(
        "/api/v1/health",
        headers={"X-Request-ID": custom_id},
    )
    assert response.headers["X-Request-ID"] == custom_id


@pytest.mark.asyncio
async def test_invalid_long_request_id_is_replaced(client: AsyncClient) -> None:
    """An excessively long X-Request-ID (>128 chars) is replaced with a new UUID."""
    long_id = "a" * 200
    response = await client.get(
        "/api/v1/health",
        headers={"X-Request-ID": long_id},
    )
    request_id = response.headers["X-Request-ID"]
    assert request_id != long_id
    assert _UUID4_RE.match(request_id)


@pytest.mark.asyncio
async def test_invalid_chars_request_id_is_replaced(client: AsyncClient) -> None:
    """An X-Request-ID with invalid characters is replaced with a new UUID."""
    bad_id = "request id with spaces!"
    response = await client.get(
        "/api/v1/health",
        headers={"X-Request-ID": bad_id},
    )
    request_id = response.headers["X-Request-ID"]
    assert request_id != bad_id
    assert _UUID4_RE.match(request_id)


@pytest.mark.asyncio
async def test_different_requests_get_different_ids(client: AsyncClient) -> None:
    """Two sequential requests must get different request IDs (context cleared)."""
    response1 = await client.get("/api/v1/health")
    response2 = await client.get("/api/v1/health")
    id1 = response1.headers["X-Request-ID"]
    id2 = response2.headers["X-Request-ID"]
    assert id1 != id2


@pytest.mark.asyncio
async def test_health_still_returns_200_with_request_id(client: AsyncClient) -> None:
    """Health endpoint should still work correctly with the middleware active."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "X-Request-ID" in response.headers
