"""Tests for the dependency injection module.

Verifies get_current_user stub returns 501 and get_db yields a session.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from app.dependencies import get_current_user


@pytest.mark.asyncio
async def test_get_current_user_raises_501() -> None:
    """get_current_user stub must raise 501 Not Implemented."""
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user()
    assert exc_info.value.status_code == 501
    assert "not yet implemented" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_get_current_user_detail_message() -> None:
    """get_current_user detail must indicate auth is not implemented."""
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user()
    assert "Authentication" in exc_info.value.detail or "authentication" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_db_is_async_generator() -> None:
    """get_db must be an async generator function."""
    import inspect

    from app.dependencies import get_db

    assert inspect.isasyncgenfunction(get_db)
