"""Model definition and metadata tests.

These tests verify ORM model structure (columns, types, constraints, indexes)
by inspecting SQLAlchemy metadata objects. No database connection is required.
"""

from __future__ import annotations

import sqlalchemy as sa

from app.models import (
    Base,
    BodyMeasurement,
    Character,
    Conversation,
    Message,
    Partner,
    Profile,
    UserActivity,
)

# ---------------------------------------------------------------------------
# 1. Import tests
# ---------------------------------------------------------------------------

class TestModelImports:
    """All seven model classes are importable from app.models."""

    def test_profile_importable(self) -> None:
        assert Profile is not None

    def test_character_importable(self) -> None:
        assert Character is not None

    def test_conversation_importable(self) -> None:
        assert Conversation is not None

    def test_message_importable(self) -> None:
        assert Message is not None

    def test_user_activity_importable(self) -> None:
        assert UserActivity is not None

    def test_partner_importable(self) -> None:
        assert Partner is not None

    def test_body_measurement_importable(self) -> None:
        assert BodyMeasurement is not None


# ---------------------------------------------------------------------------
# 2. Table name tests
# ---------------------------------------------------------------------------

class TestTableNames:
    """Each model class has the correct __tablename__."""

    def test_profile_tablename(self) -> None:
        assert Profile.__tablename__ == "profiles"

    def test_character_tablename(self) -> None:
        assert Character.__tablename__ == "characters"

    def test_conversation_tablename(self) -> None:
        assert Conversation.__tablename__ == "conversations"

    def test_message_tablename(self) -> None:
        assert Message.__tablename__ == "messages"

    def test_user_activity_tablename(self) -> None:
        assert UserActivity.__tablename__ == "user_activity"

    def test_partner_tablename(self) -> None:
        assert Partner.__tablename__ == "partners"

    def test_body_measurement_tablename(self) -> None:
        assert BodyMeasurement.__tablename__ == "body_measurements"


# ---------------------------------------------------------------------------
# 3. Column presence tests
# ---------------------------------------------------------------------------

def _column_names(model: type) -> set[str]:
    """Return the set of column names for a model."""
    return {c.name for c in model.__table__.columns}


class TestProfileColumns:
    """Profile model has all expected columns."""

    EXPECTED = {
        "id", "email", "name", "mem0_user_id", "fcm_token", "timezone",
        "avatar_url", "preferred_language", "onboarding_completed",
        "subscription_tier", "subscription_expires_at", "created_at", "updated_at",
    }

    def test_all_columns_present(self) -> None:
        actual = _column_names(Profile)
        assert self.EXPECTED.issubset(actual), f"Missing: {self.EXPECTED - actual}"

    def test_no_extra_columns(self) -> None:
        actual = _column_names(Profile)
        assert actual == self.EXPECTED, f"Extra: {actual - self.EXPECTED}"


class TestCharacterColumns:
    """Character model has all expected columns."""

    EXPECTED = {
        "id", "user_id", "name", "template", "description", "system_prompt",
        "mem0_agent_id", "avatar_style", "is_default", "is_active",
        "created_at", "updated_at",
    }

    def test_all_columns_present(self) -> None:
        actual = _column_names(Character)
        assert self.EXPECTED.issubset(actual), f"Missing: {self.EXPECTED - actual}"

    def test_no_extra_columns(self) -> None:
        actual = _column_names(Character)
        assert actual == self.EXPECTED, f"Extra: {actual - self.EXPECTED}"


class TestConversationColumns:
    """Conversation model has all expected columns."""

    EXPECTED = {
        "id", "user_id", "character_id", "last_message_at",
        "created_at", "updated_at",
    }

    def test_all_columns_present(self) -> None:
        actual = _column_names(Conversation)
        assert self.EXPECTED.issubset(actual), f"Missing: {self.EXPECTED - actual}"

    def test_no_extra_columns(self) -> None:
        actual = _column_names(Conversation)
        assert actual == self.EXPECTED, f"Extra: {actual - self.EXPECTED}"


class TestMessageColumns:
    """Message model has all expected columns and no updated_at."""

    EXPECTED = {
        "id", "conversation_id", "user_id", "role", "content",
        "media_url", "tts_url", "metadata", "created_at",
    }

    def test_all_columns_present(self) -> None:
        actual = _column_names(Message)
        assert self.EXPECTED.issubset(actual), f"Missing: {self.EXPECTED - actual}"

    def test_no_updated_at(self) -> None:
        """Message is append-only — must NOT have updated_at."""
        assert "updated_at" not in _column_names(Message)

    def test_no_extra_columns(self) -> None:
        actual = _column_names(Message)
        assert actual == self.EXPECTED, f"Extra: {actual - self.EXPECTED}"


class TestUserActivityColumns:
    """UserActivity model has all expected columns and no created_at."""

    EXPECTED = {
        "user_id", "last_active_at", "last_chat_at",
        "notifications_sent_today", "updated_at",
    }

    def test_all_columns_present(self) -> None:
        actual = _column_names(UserActivity)
        assert self.EXPECTED.issubset(actual), f"Missing: {self.EXPECTED - actual}"

    def test_no_created_at(self) -> None:
        """UserActivity tracks updates only — must NOT have created_at."""
        assert "created_at" not in _column_names(UserActivity)

    def test_no_extra_columns(self) -> None:
        actual = _column_names(UserActivity)
        assert actual == self.EXPECTED, f"Extra: {actual - self.EXPECTED}"

    def test_user_id_is_primary_key(self) -> None:
        """user_id is both PK and FK — no separate id column."""
        pk_cols = [c.name for c in UserActivity.__table__.primary_key.columns]
        assert pk_cols == ["user_id"]


class TestPartnerColumns:
    """Partner model has all expected columns."""

    EXPECTED = {
        "id", "user_id_1", "user_id_2", "invite_token", "status",
        "created_at", "updated_at",
    }

    def test_all_columns_present(self) -> None:
        actual = _column_names(Partner)
        assert self.EXPECTED.issubset(actual), f"Missing: {self.EXPECTED - actual}"

    def test_no_extra_columns(self) -> None:
        actual = _column_names(Partner)
        assert actual == self.EXPECTED, f"Extra: {actual - self.EXPECTED}"


class TestBodyMeasurementColumns:
    """BodyMeasurement model has all expected columns."""

    EXPECTED = {
        "id", "user_id", "date", "weight_kg", "body_fat_pct", "notes",
        "created_at", "updated_at",
    }

    def test_all_columns_present(self) -> None:
        actual = _column_names(BodyMeasurement)
        assert self.EXPECTED.issubset(actual), f"Missing: {self.EXPECTED - actual}"

    def test_no_extra_columns(self) -> None:
        actual = _column_names(BodyMeasurement)
        assert actual == self.EXPECTED, f"Extra: {actual - self.EXPECTED}"


# ---------------------------------------------------------------------------
# 4. Unique constraint tests
# ---------------------------------------------------------------------------

def _has_unique_constraint(model: type, column_name: str) -> bool:
    """Check if a column or set of columns has a unique constraint."""
    table = model.__table__
    # Check column-level unique
    col = table.columns.get(column_name)
    if col is not None and col.unique:
        return True
    # Check table-level unique constraints
    for constraint in table.constraints:
        if hasattr(constraint, "columns"):
            constraint_cols = {c.name for c in constraint.columns}
            if constraint_cols == {column_name}:
                if isinstance(constraint, sa.UniqueConstraint):
                    return True
    return False


class TestUniqueConstraints:
    """Tables have the expected unique constraints."""

    def test_profiles_email_unique(self) -> None:
        assert _has_unique_constraint(Profile, "email")

    def test_profiles_mem0_user_id_unique(self) -> None:
        assert _has_unique_constraint(Profile, "mem0_user_id")

    def test_characters_mem0_agent_id_unique(self) -> None:
        assert _has_unique_constraint(Character, "mem0_agent_id")

    def test_conversations_character_id_unique(self) -> None:
        assert _has_unique_constraint(Conversation, "character_id")

    def test_partners_invite_token_unique(self) -> None:
        assert _has_unique_constraint(Partner, "invite_token")

    def test_body_measurements_user_date_unique(self) -> None:
        """Composite unique constraint on (user_id, date)."""
        table = BodyMeasurement.__table__
        found = False
        for constraint in table.constraints:
            if isinstance(constraint, sa.UniqueConstraint):
                cols = {c.name for c in constraint.columns}
                if cols == {"user_id", "date"}:
                    found = True
                    break
        assert found, "Missing unique constraint on (user_id, date)"


# ---------------------------------------------------------------------------
# 5. Foreign key tests
# ---------------------------------------------------------------------------

def _fk_targets(model: type) -> set[str]:
    """Return the set of FK target table.column strings."""
    targets = set()
    for col in model.__table__.columns:
        for fk in col.foreign_keys:
            targets.add(str(fk.target_fullname))
    return targets


class TestForeignKeys:
    """Tables have the expected foreign key references."""

    def test_characters_fk_to_profiles(self) -> None:
        assert "profiles.id" in _fk_targets(Character)

    def test_conversations_fk_to_profiles(self) -> None:
        assert "profiles.id" in _fk_targets(Conversation)

    def test_conversations_fk_to_characters(self) -> None:
        assert "characters.id" in _fk_targets(Conversation)

    def test_messages_fk_to_conversations(self) -> None:
        assert "conversations.id" in _fk_targets(Message)

    def test_messages_fk_to_profiles(self) -> None:
        assert "profiles.id" in _fk_targets(Message)

    def test_user_activity_fk_to_profiles(self) -> None:
        assert "profiles.id" in _fk_targets(UserActivity)

    def test_partners_fk_to_profiles_user1(self) -> None:
        assert "profiles.id" in _fk_targets(Partner)

    def test_body_measurements_fk_to_profiles(self) -> None:
        assert "profiles.id" in _fk_targets(BodyMeasurement)


# ---------------------------------------------------------------------------
# 6. CHECK constraint tests
# ---------------------------------------------------------------------------

def _check_constraint_names(model: type) -> set[str]:
    """Return names of CHECK constraints on a model."""
    return {
        c.name
        for c in model.__table__.constraints
        if isinstance(c, sa.CheckConstraint) and c.name is not None
    }


class TestCheckConstraints:
    """Tables have the expected CHECK constraints."""

    def test_profiles_subscription_tier_check(self) -> None:
        assert "ck_profiles_subscription_tier" in _check_constraint_names(Profile)

    def test_messages_role_check(self) -> None:
        assert "ck_messages_role" in _check_constraint_names(Message)

    def test_partners_status_check(self) -> None:
        assert "ck_partners_status" in _check_constraint_names(Partner)


# ---------------------------------------------------------------------------
# 7. Index tests
# ---------------------------------------------------------------------------

def _index_names(model: type) -> set[str]:
    """Return the set of explicit index names on a model."""
    return {idx.name for idx in model.__table__.indexes if idx.name}


class TestIndexes:
    """Tables have the expected named indexes."""

    def test_messages_conv_time_index(self) -> None:
        assert "idx_messages_conv_time" in _index_names(Message)

    def test_messages_user_id_index(self) -> None:
        assert "idx_messages_user_id" in _index_names(Message)

    def test_conversations_user_time_index(self) -> None:
        assert "idx_conversations_user_time" in _index_names(Conversation)

    def test_characters_user_active_index(self) -> None:
        assert "idx_characters_user_active" in _index_names(Character)

    def test_body_measurements_user_date_index(self) -> None:
        assert "idx_body_measurements_user_date" in _index_names(BodyMeasurement)

    def test_partners_user1_index(self) -> None:
        assert "idx_partners_user1" in _index_names(Partner)

    def test_partners_user2_index(self) -> None:
        assert "idx_partners_user2" in _index_names(Partner)


# ---------------------------------------------------------------------------
# 8. ON DELETE behavior tests (inspecting FK metadata)
# ---------------------------------------------------------------------------

def _fk_ondelete(model: type, column_name: str) -> str | None:
    """Return the ondelete rule for a FK column."""
    col = model.__table__.columns[column_name]
    for fk in col.foreign_keys:
        if fk.parent.name == column_name:
            return fk.ondelete
    return None


class TestOnDeleteBehavior:
    """Foreign keys have the correct ON DELETE behavior."""

    def test_characters_user_id_cascade(self) -> None:
        assert _fk_ondelete(Character, "user_id") == "CASCADE"

    def test_conversations_user_id_cascade(self) -> None:
        assert _fk_ondelete(Conversation, "user_id") == "CASCADE"

    def test_conversations_character_id_cascade(self) -> None:
        assert _fk_ondelete(Conversation, "character_id") == "CASCADE"

    def test_messages_conversation_id_cascade(self) -> None:
        assert _fk_ondelete(Message, "conversation_id") == "CASCADE"

    def test_messages_user_id_cascade(self) -> None:
        assert _fk_ondelete(Message, "user_id") == "CASCADE"

    def test_user_activity_user_id_cascade(self) -> None:
        assert _fk_ondelete(UserActivity, "user_id") == "CASCADE"

    def test_partners_user_id_1_cascade(self) -> None:
        assert _fk_ondelete(Partner, "user_id_1") == "CASCADE"

    def test_partners_user_id_2_set_null(self) -> None:
        assert _fk_ondelete(Partner, "user_id_2") == "SET NULL"

    def test_body_measurements_user_id_cascade(self) -> None:
        assert _fk_ondelete(BodyMeasurement, "user_id") == "CASCADE"


# ---------------------------------------------------------------------------
# 9. Column type / nullability / default tests
# ---------------------------------------------------------------------------

class TestColumnTypes:
    """Columns have the correct types and nullability."""

    def test_profile_id_is_uuid(self) -> None:
        col = Profile.__table__.columns["id"]
        assert isinstance(col.type, (sa.Uuid,)) or "UUID" in str(col.type).upper()

    def test_message_metadata_is_jsonb(self) -> None:
        from sqlalchemy.dialects.postgresql import JSONB

        col = Message.__table__.columns["metadata"]
        assert isinstance(col.type, JSONB)

    def test_user_activity_notifications_is_jsonb(self) -> None:
        from sqlalchemy.dialects.postgresql import JSONB

        col = UserActivity.__table__.columns["notifications_sent_today"]
        assert isinstance(col.type, JSONB)

    def test_body_measurement_weight_is_numeric(self) -> None:
        col = BodyMeasurement.__table__.columns["weight_kg"]
        assert isinstance(col.type, sa.Numeric)
        assert col.type.precision == 5
        assert col.type.scale == 2

    def test_body_measurement_body_fat_is_numeric(self) -> None:
        col = BodyMeasurement.__table__.columns["body_fat_pct"]
        assert isinstance(col.type, sa.Numeric)
        assert col.type.precision == 4
        assert col.type.scale == 1

    def test_profile_fcm_token_nullable(self) -> None:
        assert Profile.__table__.columns["fcm_token"].nullable is True

    def test_profile_email_not_nullable(self) -> None:
        assert Profile.__table__.columns["email"].nullable is False

    def test_conversation_last_message_at_nullable(self) -> None:
        assert Conversation.__table__.columns["last_message_at"].nullable is True

    def test_partner_user_id_2_nullable(self) -> None:
        assert Partner.__table__.columns["user_id_2"].nullable is True

    def test_partner_user_id_1_not_nullable(self) -> None:
        assert Partner.__table__.columns["user_id_1"].nullable is False


# ---------------------------------------------------------------------------
# 10. Base.metadata.sorted_tables resolves without circular deps
# ---------------------------------------------------------------------------

class TestMetadata:
    """Base metadata is well-formed."""

    def test_sorted_tables_no_circular_deps(self) -> None:
        tables = Base.metadata.sorted_tables
        table_names = {t.name for t in tables}
        expected = {
            "profiles", "characters", "conversations", "messages",
            "user_activity", "partners", "body_measurements",
        }
        assert expected.issubset(table_names)

    def test_seven_application_tables(self) -> None:
        """At least 7 tables exist in Base.metadata."""
        table_names = set(Base.metadata.tables.keys())
        expected = {
            "profiles", "characters", "conversations", "messages",
            "user_activity", "partners", "body_measurements",
        }
        assert expected.issubset(table_names)
