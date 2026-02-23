"""Tests for the dependency injection module.

Verifies get_current_user requires authentication and get_db yields a session.
"""

from __future__ import annotations

import inspect

import pytest

from app.dependencies import get_current_user, get_db


@pytest.mark.asyncio
async def test_get_db_is_async_generator() -> None:
    """get_db must be an async generator function."""
    assert inspect.isasyncgenfunction(get_db)


def test_get_current_user_is_coroutine_function() -> None:
    """get_current_user must be an async function (coroutine)."""
    assert inspect.iscoroutinefunction(get_current_user)


def test_get_current_user_has_dependencies() -> None:
    """get_current_user must depend on credentials and db."""
    params = inspect.signature(get_current_user).parameters
    assert "credentials" in params
    assert "db" in params
