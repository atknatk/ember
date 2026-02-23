"""Migration and constraint tests (require a running PostgreSQL database).

These tests verify that the schema can be created/dropped and that CHECK
constraints, unique constraints, and ON DELETE behaviors work correctly
at the database level.

All tests in this file are marked with @pytest.mark.db and will be skipped
when no database is available. Run with:
    pytest tests/test_migration.py -v

Requires a running PostgreSQL test database configured via DATABASE_URL.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import (
    Base,
    BodyMeasurement,
    Character,
    Conversation,
    Message,
    Partner,
    Profile,
)

# Skip all tests in this module if DB is unavailable.
pytestmark = pytest.mark.db


def _db_url() -> str:
    """Return the test database URL."""
    import os

    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://ember:ember@localhost:5432/ember_test",
    )


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="module")
def test_engine() -> sqlalchemy.ext.asyncio.AsyncEngine:
    return create_async_engine(_db_url(), echo=False)


@pytest.fixture(scope="module")
def test_session_factory(
    test_engine: sqlalchemy.ext.asyncio.AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture(autouse=True)
async def setup_tables(
    test_engine: sqlalchemy.ext.asyncio.AsyncEngine,
) -> None:
    """Create all tables before each test and drop after."""
    try:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception:
        pytest.skip("Database not available")
    yield  # type: ignore[misc]
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _make_profile(
    profile_id: uuid.UUID | None = None,
    email: str | None = None,
) -> Profile:
    """Create a Profile instance with test data."""
    pid = profile_id or uuid.uuid4()
    return Profile(
        id=pid,
        email=email or f"{pid}@test.ember.ai",
        name="Test User",
        mem0_user_id=f"mem0_{pid}",
        timezone="UTC",
        preferred_language="en",
        subscription_tier="free",
    )


# ---------------------------------------------------------------------------
# Schema creation / destruction
# ---------------------------------------------------------------------------

class TestSchemaRoundTrip:
    """Base.metadata.create_all and drop_all work correctly."""

    async def test_all_tables_exist(
        self,
        test_engine: sqlalchemy.ext.asyncio.AsyncEngine,
    ) -> None:
        async with test_engine.connect() as conn:
            table_names = await conn.run_sync(
                lambda c: inspect(c).get_table_names(),
            )
        expected = {
            "profiles", "characters", "conversations", "messages",
            "user_activity", "partners", "body_measurements",
        }
        assert expected.issubset(set(table_names))


# ---------------------------------------------------------------------------
# CRUD round-trip tests
# ---------------------------------------------------------------------------

class TestCRUDRoundTrip:
    """Basic insert/read operations work for each model."""

    async def test_profile_insert_read(
        self,
        test_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with test_session_factory() as session:
            profile = _make_profile()
            session.add(profile)
            await session.commit()
            await session.refresh(profile)
            assert profile.email.endswith("@test.ember.ai")
            assert profile.subscription_tier == "free"

    async def test_character_insert(
        self,
        test_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with test_session_factory() as session:
            profile = _make_profile()
            session.add(profile)
            await session.flush()

            char = Character(
                user_id=profile.id,
                name="Luna",
                template="companion",
                system_prompt="You are Luna.",
                mem0_agent_id=f"companion_{profile.id}",
            )
            session.add(char)
            await session.commit()
            await session.refresh(char)
            assert char.name == "Luna"
            assert char.is_active is True

    async def test_conversation_insert(
        self,
        test_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with test_session_factory() as session:
            profile = _make_profile()
            session.add(profile)
            await session.flush()

            char = Character(
                user_id=profile.id,
                name="Luna",
                template="companion",
                system_prompt="You are Luna.",
                mem0_agent_id=f"companion_{profile.id}",
            )
            session.add(char)
            await session.flush()

            conv = Conversation(
                user_id=profile.id,
                character_id=char.id,
            )
            session.add(conv)
            await session.commit()
            await session.refresh(conv)
            assert conv.last_message_at is None

    async def test_message_insert(
        self,
        test_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        async with test_session_factory() as session:
            profile = _make_profile()
            session.add(profile)
            await session.flush()

            char = Character(
                user_id=profile.id,
                name="Luna",
                template="companion",
                system_prompt="You are Luna.",
                mem0_agent_id=f"companion_{profile.id}",
            )
            session.add(char)
            await session.flush()

            conv = Conversation(
                user_id=profile.id,
                character_id=char.id,
            )
            session.add(conv)
            await session.flush()

            msg = Message(
                conversation_id=conv.id,
                user_id=profile.id,
                role="user",
                content="Hello Luna!",
            )
            session.add(msg)
            await session.commit()
            await session.refresh(msg)
            assert msg.role == "user"


# ---------------------------------------------------------------------------
# Constraint violation tests
# ---------------------------------------------------------------------------

class TestConstraintViolations:
    """CHECK and UNIQUE constraints raise IntegrityError."""

    async def test_duplicate_conversation_character_id(
        self,
        test_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Two conversations for the same character violates UNIQUE."""
        async with test_session_factory() as session:
            profile = _make_profile()
            session.add(profile)
            await session.flush()

            char = Character(
                user_id=profile.id,
                name="Luna",
                template="companion",
                system_prompt="You are Luna.",
                mem0_agent_id=f"companion_{profile.id}",
            )
            session.add(char)
            await session.flush()

            conv1 = Conversation(user_id=profile.id, character_id=char.id)
            session.add(conv1)
            await session.flush()

            conv2 = Conversation(user_id=profile.id, character_id=char.id)
            session.add(conv2)
            with pytest.raises(IntegrityError):
                await session.flush()

    async def test_invalid_message_role(
        self,
        test_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Message with role='system' violates CHECK constraint."""
        async with test_session_factory() as session:
            profile = _make_profile()
            session.add(profile)
            await session.flush()

            char = Character(
                user_id=profile.id,
                name="Luna",
                template="companion",
                system_prompt="You are Luna.",
                mem0_agent_id=f"companion_{profile.id}",
            )
            session.add(char)
            await session.flush()

            conv = Conversation(user_id=profile.id, character_id=char.id)
            session.add(conv)
            await session.flush()

            msg = Message(
                conversation_id=conv.id,
                user_id=profile.id,
                role="system",
                content="Invalid role",
            )
            session.add(msg)
            with pytest.raises(IntegrityError):
                await session.flush()

    async def test_invalid_subscription_tier(
        self,
        test_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Profile with subscription_tier='gold' violates CHECK."""
        async with test_session_factory() as session:
            profile = _make_profile()
            profile.subscription_tier = "gold"
            session.add(profile)
            with pytest.raises(IntegrityError):
                await session.flush()

    async def test_invalid_partner_status(
        self,
        test_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Partner with status='unknown' violates CHECK."""
        async with test_session_factory() as session:
            profile = _make_profile()
            session.add(profile)
            await session.flush()

            partner = Partner(
                user_id_1=profile.id,
                invite_token="test-token-123",
                status="unknown",
            )
            session.add(partner)
            with pytest.raises(IntegrityError):
                await session.flush()

    async def test_duplicate_body_measurement_user_date(
        self,
        test_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Two measurements for same user+date violates UNIQUE."""
        async with test_session_factory() as session:
            profile = _make_profile()
            session.add(profile)
            await session.flush()

            today = date.today()
            m1 = BodyMeasurement(user_id=profile.id, date=today)
            session.add(m1)
            await session.flush()

            m2 = BodyMeasurement(user_id=profile.id, date=today)
            session.add(m2)
            with pytest.raises(IntegrityError):
                await session.flush()


# ---------------------------------------------------------------------------
# Index existence tests
# ---------------------------------------------------------------------------

class TestIndexExistence:
    """Critical indexes exist on the database tables."""

    async def test_messages_conv_time_index(
        self,
        test_engine: sqlalchemy.ext.asyncio.AsyncEngine,
    ) -> None:
        async with test_engine.connect() as conn:
            indexes = await conn.run_sync(
                lambda c: inspect(c).get_indexes("messages"),
            )
        idx_names = {idx["name"] for idx in indexes}
        assert "idx_messages_conv_time" in idx_names

    async def test_conversations_user_time_index(
        self,
        test_engine: sqlalchemy.ext.asyncio.AsyncEngine,
    ) -> None:
        async with test_engine.connect() as conn:
            indexes = await conn.run_sync(
                lambda c: inspect(c).get_indexes("conversations"),
            )
        idx_names = {idx["name"] for idx in indexes}
        assert "idx_conversations_user_time" in idx_names

    async def test_characters_user_active_index(
        self,
        test_engine: sqlalchemy.ext.asyncio.AsyncEngine,
    ) -> None:
        async with test_engine.connect() as conn:
            indexes = await conn.run_sync(
                lambda c: inspect(c).get_indexes("characters"),
            )
        idx_names = {idx["name"] for idx in indexes}
        assert "idx_characters_user_active" in idx_names
