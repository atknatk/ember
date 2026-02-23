"""Tests for the SQLAlchemy declarative base and TimestampMixin.

Verifies Base is a proper DeclarativeBase and TimestampMixin provides
created_at and updated_at columns with correct types.
"""

from __future__ import annotations

import pytest
from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase

from app.models.base import Base, TimestampMixin


@pytest.mark.asyncio
async def test_base_is_declarative_base() -> None:
    """Base must be a subclass of DeclarativeBase."""
    assert issubclass(Base, DeclarativeBase)


@pytest.mark.asyncio
async def test_timestamp_mixin_has_created_at() -> None:
    """TimestampMixin must define a created_at mapped column."""
    assert hasattr(TimestampMixin, "created_at")


@pytest.mark.asyncio
async def test_timestamp_mixin_has_updated_at() -> None:
    """TimestampMixin must define an updated_at mapped column."""
    assert hasattr(TimestampMixin, "updated_at")


@pytest.mark.asyncio
async def test_timestamp_mixin_created_at_is_timezone_aware() -> None:
    """created_at column must use DateTime(timezone=True)."""
    col = TimestampMixin.__dict__["created_at"]
    # The mapped_column wraps a Column object; access its type
    column_obj = col.column
    assert isinstance(column_obj.type, DateTime)
    assert column_obj.type.timezone is True


@pytest.mark.asyncio
async def test_timestamp_mixin_updated_at_is_timezone_aware() -> None:
    """updated_at column must use DateTime(timezone=True)."""
    col = TimestampMixin.__dict__["updated_at"]
    column_obj = col.column
    assert isinstance(column_obj.type, DateTime)
    assert column_obj.type.timezone is True


@pytest.mark.asyncio
async def test_timestamp_mixin_created_at_not_nullable() -> None:
    """created_at must be non-nullable."""
    col = TimestampMixin.__dict__["created_at"]
    column_obj = col.column
    assert column_obj.nullable is False


@pytest.mark.asyncio
async def test_timestamp_mixin_updated_at_not_nullable() -> None:
    """updated_at must be non-nullable."""
    col = TimestampMixin.__dict__["updated_at"]
    column_obj = col.column
    assert column_obj.nullable is False


@pytest.mark.asyncio
async def test_timestamp_mixin_created_at_has_server_default() -> None:
    """created_at must have a server_default (func.now())."""
    col = TimestampMixin.__dict__["created_at"]
    column_obj = col.column
    assert column_obj.server_default is not None


@pytest.mark.asyncio
async def test_timestamp_mixin_updated_at_has_onupdate() -> None:
    """updated_at must have an onupdate trigger (func.now())."""
    col = TimestampMixin.__dict__["updated_at"]
    column_obj = col.column
    assert column_obj.onupdate is not None
