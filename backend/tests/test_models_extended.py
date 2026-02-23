"""Extended model definition tests for the database-schema feature (P01-02).

Complements the 76 tests in test_models.py by covering areas not tested:
- Relationship definitions (back_populates, uselist, cascade, foreign_keys)
- Default value correctness (uuid4, Python-level defaults)
- __init__.py import completeness and __all__ exports
- CHECK constraint text content
- Index column compositions
- Column nullability for all columns
- Column type verification (UUID, Text, Boolean, DateTime, Date, JSONB)
- Server defaults (func.now(), '[]'::jsonb)
- Primary key structure
- Message.metadata_ attribute mapping
- TimestampMixin inheritance
- Profile.id has no auto-default (Cognito sub)

All tests work WITHOUT a running database using SQLAlchemy metadata introspection.
"""

from __future__ import annotations

import uuid
from datetime import date

import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import RelationshipProperty

from app.models import (
    Base,
    BodyMeasurement,
    Character,
    Conversation,
    Message,
    Partner,
    Profile,
    TimestampMixin,
    UserActivity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _column(model: type, name: str) -> sa.Column:  # type: ignore[type-arg]
    """Return a column object from the model's table."""
    return model.__table__.columns[name]


def _column_names(model: type) -> set[str]:
    """Return the set of column names for a model."""
    return {c.name for c in model.__table__.columns}


def _index_names(model: type) -> set[str]:
    """Return the set of explicit index names on a model."""
    return {idx.name for idx in model.__table__.indexes if idx.name}


def _index_expression_strings(model: type, index_name: str) -> list[str]:
    """Return string representations of index expressions.

    Uses idx.expressions to capture DESC-wrapped columns correctly.
    """
    for idx in model.__table__.indexes:
        if idx.name == index_name:
            return [str(expr) for expr in idx.expressions]
    return []


def _get_relationship(model: type, attr_name: str) -> RelationshipProperty | None:  # type: ignore[type-arg]
    """Return the relationship property for a given attribute name."""
    mapper = sa_inspect(model)
    for prop in mapper.relationships:
        if prop.key == attr_name:
            return prop
    return None


def _check_constraint_names(model: type) -> set[str]:
    """Return names of CHECK constraints on a model."""
    return {
        c.name
        for c in model.__table__.constraints
        if isinstance(c, sa.CheckConstraint) and c.name is not None
    }


def _get_check_constraint_text(model: type, name: str) -> str | None:
    """Return the SQL text of a named CHECK constraint."""
    for c in model.__table__.constraints:
        if isinstance(c, sa.CheckConstraint) and c.name == name:
            return str(c.sqltext)
    return None


def _pk_column_names(model: type) -> list[str]:
    """Return the primary key column names for a model."""
    return [c.name for c in model.__table__.primary_key.columns]


# ---------------------------------------------------------------------------
# 1. __init__.py import completeness
# ---------------------------------------------------------------------------

class TestInitImports:
    """Verify __init__.py exports all expected symbols."""

    def test_base_importable_from_models(self) -> None:
        assert Base is not None

    def test_timestamp_mixin_importable_from_models(self) -> None:
        assert TimestampMixin is not None

    def test_all_exports_list_has_nine_entries(self) -> None:
        """__all__ should contain all 7 models + Base + TimestampMixin."""
        import app.models as models_module

        assert hasattr(models_module, "__all__")
        expected = {
            "Base", "TimestampMixin",
            "Profile", "Character", "Conversation", "Message",
            "UserActivity", "Partner", "BodyMeasurement",
        }
        assert set(models_module.__all__) == expected

    def test_all_models_registered_in_base_metadata(self) -> None:
        """All 7 application tables must be registered in Base.metadata."""
        table_names = set(Base.metadata.tables.keys())
        expected = {
            "profiles", "characters", "conversations", "messages",
            "user_activity", "partners", "body_measurements",
        }
        assert expected.issubset(table_names)


# ---------------------------------------------------------------------------
# 2. TimestampMixin inheritance tests
# ---------------------------------------------------------------------------

class TestTimestampMixinUsage:
    """Verify which models use TimestampMixin and which do not."""

    def test_profile_uses_timestamp_mixin(self) -> None:
        assert issubclass(Profile, TimestampMixin)

    def test_character_uses_timestamp_mixin(self) -> None:
        assert issubclass(Character, TimestampMixin)

    def test_conversation_uses_timestamp_mixin(self) -> None:
        assert issubclass(Conversation, TimestampMixin)

    def test_partner_uses_timestamp_mixin(self) -> None:
        assert issubclass(Partner, TimestampMixin)

    def test_body_measurement_uses_timestamp_mixin(self) -> None:
        assert issubclass(BodyMeasurement, TimestampMixin)

    def test_message_does_not_use_timestamp_mixin(self) -> None:
        """Message is append-only: no TimestampMixin."""
        assert not issubclass(Message, TimestampMixin)

    def test_user_activity_does_not_use_timestamp_mixin(self) -> None:
        """UserActivity has custom timestamps: no TimestampMixin."""
        assert not issubclass(UserActivity, TimestampMixin)


# ---------------------------------------------------------------------------
# 3. Primary key tests
# ---------------------------------------------------------------------------

class TestPrimaryKeys:
    """Each model has the correct primary key columns."""

    def test_profile_pk_is_id(self) -> None:
        assert _pk_column_names(Profile) == ["id"]

    def test_character_pk_is_id(self) -> None:
        assert _pk_column_names(Character) == ["id"]

    def test_conversation_pk_is_id(self) -> None:
        assert _pk_column_names(Conversation) == ["id"]

    def test_message_pk_is_id(self) -> None:
        assert _pk_column_names(Message) == ["id"]

    def test_user_activity_pk_is_user_id(self) -> None:
        """UserActivity PK is user_id, not a separate id column."""
        assert _pk_column_names(UserActivity) == ["user_id"]

    def test_partner_pk_is_id(self) -> None:
        assert _pk_column_names(Partner) == ["id"]

    def test_body_measurement_pk_is_id(self) -> None:
        assert _pk_column_names(BodyMeasurement) == ["id"]

    def test_user_activity_has_no_id_column(self) -> None:
        """UserActivity should NOT have a separate id column."""
        assert "id" not in _column_names(UserActivity)


# ---------------------------------------------------------------------------
# 4. Column type tests (comprehensive)
# ---------------------------------------------------------------------------

class TestProfileColumnTypes:
    """Profile column types and properties."""

    def test_id_type_is_uuid(self) -> None:
        col = _column(Profile, "id")
        assert isinstance(col.type, sa.Uuid) or "UUID" in str(col.type).upper()

    def test_email_type_is_text(self) -> None:
        col = _column(Profile, "email")
        assert isinstance(col.type, sa.Text)

    def test_name_type_is_text(self) -> None:
        col = _column(Profile, "name")
        assert isinstance(col.type, sa.Text)

    def test_mem0_user_id_type_is_text(self) -> None:
        col = _column(Profile, "mem0_user_id")
        assert isinstance(col.type, sa.Text)

    def test_fcm_token_type_is_text(self) -> None:
        col = _column(Profile, "fcm_token")
        assert isinstance(col.type, sa.Text)

    def test_timezone_type_is_text(self) -> None:
        col = _column(Profile, "timezone")
        assert isinstance(col.type, sa.Text)

    def test_avatar_url_type_is_text(self) -> None:
        col = _column(Profile, "avatar_url")
        assert isinstance(col.type, sa.Text)

    def test_preferred_language_type_is_text(self) -> None:
        col = _column(Profile, "preferred_language")
        assert isinstance(col.type, sa.Text)

    def test_onboarding_completed_type_is_boolean(self) -> None:
        col = _column(Profile, "onboarding_completed")
        assert isinstance(col.type, sa.Boolean)

    def test_subscription_tier_type_is_text(self) -> None:
        col = _column(Profile, "subscription_tier")
        assert isinstance(col.type, sa.Text)

    def test_subscription_expires_at_type_is_datetime_tz(self) -> None:
        col = _column(Profile, "subscription_expires_at")
        assert isinstance(col.type, sa.DateTime)
        assert col.type.timezone is True

    def test_created_at_type_is_datetime_tz(self) -> None:
        col = _column(Profile, "created_at")
        assert isinstance(col.type, sa.DateTime)
        assert col.type.timezone is True

    def test_updated_at_type_is_datetime_tz(self) -> None:
        col = _column(Profile, "updated_at")
        assert isinstance(col.type, sa.DateTime)
        assert col.type.timezone is True


class TestCharacterColumnTypes:
    """Character column types and properties."""

    def test_id_type_is_uuid(self) -> None:
        col = _column(Character, "id")
        assert isinstance(col.type, sa.Uuid) or "UUID" in str(col.type).upper()

    def test_user_id_type_is_uuid(self) -> None:
        col = _column(Character, "user_id")
        assert isinstance(col.type, sa.Uuid) or "UUID" in str(col.type).upper()

    def test_name_type_is_text(self) -> None:
        col = _column(Character, "name")
        assert isinstance(col.type, sa.Text)

    def test_template_type_is_text(self) -> None:
        col = _column(Character, "template")
        assert isinstance(col.type, sa.Text)

    def test_description_type_is_text(self) -> None:
        col = _column(Character, "description")
        assert isinstance(col.type, sa.Text)

    def test_system_prompt_type_is_text(self) -> None:
        col = _column(Character, "system_prompt")
        assert isinstance(col.type, sa.Text)

    def test_mem0_agent_id_type_is_text(self) -> None:
        col = _column(Character, "mem0_agent_id")
        assert isinstance(col.type, sa.Text)

    def test_avatar_style_type_is_text(self) -> None:
        col = _column(Character, "avatar_style")
        assert isinstance(col.type, sa.Text)

    def test_is_default_type_is_boolean(self) -> None:
        col = _column(Character, "is_default")
        assert isinstance(col.type, sa.Boolean)

    def test_is_active_type_is_boolean(self) -> None:
        col = _column(Character, "is_active")
        assert isinstance(col.type, sa.Boolean)


class TestConversationColumnTypes:
    """Conversation column types and properties."""

    def test_id_type_is_uuid(self) -> None:
        col = _column(Conversation, "id")
        assert isinstance(col.type, sa.Uuid) or "UUID" in str(col.type).upper()

    def test_user_id_type_is_uuid(self) -> None:
        col = _column(Conversation, "user_id")
        assert isinstance(col.type, sa.Uuid) or "UUID" in str(col.type).upper()

    def test_character_id_type_is_uuid(self) -> None:
        col = _column(Conversation, "character_id")
        assert isinstance(col.type, sa.Uuid) or "UUID" in str(col.type).upper()

    def test_last_message_at_type_is_datetime_tz(self) -> None:
        col = _column(Conversation, "last_message_at")
        assert isinstance(col.type, sa.DateTime)
        assert col.type.timezone is True


class TestMessageColumnTypes:
    """Message column types and properties."""

    def test_id_type_is_uuid(self) -> None:
        col = _column(Message, "id")
        assert isinstance(col.type, sa.Uuid) or "UUID" in str(col.type).upper()

    def test_conversation_id_type_is_uuid(self) -> None:
        col = _column(Message, "conversation_id")
        assert isinstance(col.type, sa.Uuid) or "UUID" in str(col.type).upper()

    def test_user_id_type_is_uuid(self) -> None:
        col = _column(Message, "user_id")
        assert isinstance(col.type, sa.Uuid) or "UUID" in str(col.type).upper()

    def test_role_type_is_text(self) -> None:
        col = _column(Message, "role")
        assert isinstance(col.type, sa.Text)

    def test_content_type_is_text(self) -> None:
        col = _column(Message, "content")
        assert isinstance(col.type, sa.Text)

    def test_media_url_type_is_text(self) -> None:
        col = _column(Message, "media_url")
        assert isinstance(col.type, sa.Text)

    def test_tts_url_type_is_text(self) -> None:
        col = _column(Message, "tts_url")
        assert isinstance(col.type, sa.Text)

    def test_metadata_type_is_jsonb(self) -> None:
        col = _column(Message, "metadata")
        assert isinstance(col.type, JSONB)

    def test_created_at_type_is_datetime_tz(self) -> None:
        col = _column(Message, "created_at")
        assert isinstance(col.type, sa.DateTime)
        assert col.type.timezone is True


class TestUserActivityColumnTypes:
    """UserActivity column types and properties."""

    def test_user_id_type_is_uuid(self) -> None:
        col = _column(UserActivity, "user_id")
        assert isinstance(col.type, sa.Uuid) or "UUID" in str(col.type).upper()

    def test_last_active_at_type_is_datetime_tz(self) -> None:
        col = _column(UserActivity, "last_active_at")
        assert isinstance(col.type, sa.DateTime)
        assert col.type.timezone is True

    def test_last_chat_at_type_is_datetime_tz(self) -> None:
        col = _column(UserActivity, "last_chat_at")
        assert isinstance(col.type, sa.DateTime)
        assert col.type.timezone is True

    def test_notifications_sent_today_type_is_jsonb(self) -> None:
        col = _column(UserActivity, "notifications_sent_today")
        assert isinstance(col.type, JSONB)

    def test_updated_at_type_is_datetime_tz(self) -> None:
        col = _column(UserActivity, "updated_at")
        assert isinstance(col.type, sa.DateTime)
        assert col.type.timezone is True


class TestPartnerColumnTypes:
    """Partner column types and properties."""

    def test_id_type_is_uuid(self) -> None:
        col = _column(Partner, "id")
        assert isinstance(col.type, sa.Uuid) or "UUID" in str(col.type).upper()

    def test_user_id_1_type_is_uuid(self) -> None:
        col = _column(Partner, "user_id_1")
        assert isinstance(col.type, sa.Uuid) or "UUID" in str(col.type).upper()

    def test_user_id_2_type_is_uuid(self) -> None:
        col = _column(Partner, "user_id_2")
        assert isinstance(col.type, sa.Uuid) or "UUID" in str(col.type).upper()

    def test_invite_token_type_is_text(self) -> None:
        col = _column(Partner, "invite_token")
        assert isinstance(col.type, sa.Text)

    def test_status_type_is_text(self) -> None:
        col = _column(Partner, "status")
        assert isinstance(col.type, sa.Text)


class TestBodyMeasurementColumnTypes:
    """BodyMeasurement column types and properties."""

    def test_id_type_is_uuid(self) -> None:
        col = _column(BodyMeasurement, "id")
        assert isinstance(col.type, sa.Uuid) or "UUID" in str(col.type).upper()

    def test_user_id_type_is_uuid(self) -> None:
        col = _column(BodyMeasurement, "user_id")
        assert isinstance(col.type, sa.Uuid) or "UUID" in str(col.type).upper()

    def test_date_type_is_date(self) -> None:
        col = _column(BodyMeasurement, "date")
        assert isinstance(col.type, sa.Date)

    def test_weight_kg_numeric_precision(self) -> None:
        col = _column(BodyMeasurement, "weight_kg")
        assert isinstance(col.type, sa.Numeric)
        assert col.type.precision == 5
        assert col.type.scale == 2

    def test_body_fat_pct_numeric_precision(self) -> None:
        col = _column(BodyMeasurement, "body_fat_pct")
        assert isinstance(col.type, sa.Numeric)
        assert col.type.precision == 4
        assert col.type.scale == 1

    def test_notes_type_is_text(self) -> None:
        col = _column(BodyMeasurement, "notes")
        assert isinstance(col.type, sa.Text)


# ---------------------------------------------------------------------------
# 5. Column nullability tests (comprehensive)
# ---------------------------------------------------------------------------

class TestProfileNullability:
    """Profile column nullability."""

    def test_id_not_nullable(self) -> None:
        assert _column(Profile, "id").nullable is False

    def test_email_not_nullable(self) -> None:
        assert _column(Profile, "email").nullable is False

    def test_name_not_nullable(self) -> None:
        assert _column(Profile, "name").nullable is False

    def test_mem0_user_id_not_nullable(self) -> None:
        assert _column(Profile, "mem0_user_id").nullable is False

    def test_fcm_token_nullable(self) -> None:
        assert _column(Profile, "fcm_token").nullable is True

    def test_timezone_not_nullable(self) -> None:
        assert _column(Profile, "timezone").nullable is False

    def test_avatar_url_nullable(self) -> None:
        assert _column(Profile, "avatar_url").nullable is True

    def test_preferred_language_not_nullable(self) -> None:
        assert _column(Profile, "preferred_language").nullable is False

    def test_onboarding_completed_not_nullable(self) -> None:
        assert _column(Profile, "onboarding_completed").nullable is False

    def test_subscription_tier_not_nullable(self) -> None:
        assert _column(Profile, "subscription_tier").nullable is False

    def test_subscription_expires_at_nullable(self) -> None:
        assert _column(Profile, "subscription_expires_at").nullable is True

    def test_created_at_not_nullable(self) -> None:
        assert _column(Profile, "created_at").nullable is False

    def test_updated_at_not_nullable(self) -> None:
        assert _column(Profile, "updated_at").nullable is False


class TestCharacterNullability:
    """Character column nullability."""

    def test_id_not_nullable(self) -> None:
        assert _column(Character, "id").nullable is False

    def test_user_id_not_nullable(self) -> None:
        assert _column(Character, "user_id").nullable is False

    def test_name_not_nullable(self) -> None:
        assert _column(Character, "name").nullable is False

    def test_template_not_nullable(self) -> None:
        assert _column(Character, "template").nullable is False

    def test_description_nullable(self) -> None:
        assert _column(Character, "description").nullable is True

    def test_system_prompt_not_nullable(self) -> None:
        assert _column(Character, "system_prompt").nullable is False

    def test_mem0_agent_id_not_nullable(self) -> None:
        assert _column(Character, "mem0_agent_id").nullable is False

    def test_avatar_style_not_nullable(self) -> None:
        assert _column(Character, "avatar_style").nullable is False

    def test_is_default_not_nullable(self) -> None:
        assert _column(Character, "is_default").nullable is False

    def test_is_active_not_nullable(self) -> None:
        assert _column(Character, "is_active").nullable is False


class TestConversationNullability:
    """Conversation column nullability."""

    def test_id_not_nullable(self) -> None:
        assert _column(Conversation, "id").nullable is False

    def test_user_id_not_nullable(self) -> None:
        assert _column(Conversation, "user_id").nullable is False

    def test_character_id_not_nullable(self) -> None:
        assert _column(Conversation, "character_id").nullable is False

    def test_last_message_at_nullable(self) -> None:
        assert _column(Conversation, "last_message_at").nullable is True


class TestMessageNullability:
    """Message column nullability."""

    def test_id_not_nullable(self) -> None:
        assert _column(Message, "id").nullable is False

    def test_conversation_id_not_nullable(self) -> None:
        assert _column(Message, "conversation_id").nullable is False

    def test_user_id_not_nullable(self) -> None:
        assert _column(Message, "user_id").nullable is False

    def test_role_not_nullable(self) -> None:
        assert _column(Message, "role").nullable is False

    def test_content_not_nullable(self) -> None:
        assert _column(Message, "content").nullable is False

    def test_media_url_nullable(self) -> None:
        assert _column(Message, "media_url").nullable is True

    def test_tts_url_nullable(self) -> None:
        assert _column(Message, "tts_url").nullable is True

    def test_metadata_nullable(self) -> None:
        assert _column(Message, "metadata").nullable is True

    def test_created_at_not_nullable(self) -> None:
        assert _column(Message, "created_at").nullable is False


class TestUserActivityNullability:
    """UserActivity column nullability."""

    def test_user_id_not_nullable(self) -> None:
        assert _column(UserActivity, "user_id").nullable is False

    def test_last_active_at_nullable(self) -> None:
        assert _column(UserActivity, "last_active_at").nullable is True

    def test_last_chat_at_nullable(self) -> None:
        assert _column(UserActivity, "last_chat_at").nullable is True

    def test_notifications_sent_today_not_nullable(self) -> None:
        assert _column(UserActivity, "notifications_sent_today").nullable is False

    def test_updated_at_not_nullable(self) -> None:
        assert _column(UserActivity, "updated_at").nullable is False


class TestPartnerNullability:
    """Partner column nullability."""

    def test_id_not_nullable(self) -> None:
        assert _column(Partner, "id").nullable is False

    def test_user_id_1_not_nullable(self) -> None:
        assert _column(Partner, "user_id_1").nullable is False

    def test_user_id_2_nullable(self) -> None:
        assert _column(Partner, "user_id_2").nullable is True

    def test_invite_token_not_nullable(self) -> None:
        assert _column(Partner, "invite_token").nullable is False

    def test_status_not_nullable(self) -> None:
        assert _column(Partner, "status").nullable is False


class TestBodyMeasurementNullability:
    """BodyMeasurement column nullability."""

    def test_id_not_nullable(self) -> None:
        assert _column(BodyMeasurement, "id").nullable is False

    def test_user_id_not_nullable(self) -> None:
        assert _column(BodyMeasurement, "user_id").nullable is False

    def test_date_not_nullable(self) -> None:
        assert _column(BodyMeasurement, "date").nullable is False

    def test_weight_kg_nullable(self) -> None:
        assert _column(BodyMeasurement, "weight_kg").nullable is True

    def test_body_fat_pct_nullable(self) -> None:
        assert _column(BodyMeasurement, "body_fat_pct").nullable is True

    def test_notes_nullable(self) -> None:
        assert _column(BodyMeasurement, "notes").nullable is True


# ---------------------------------------------------------------------------
# 6. Default value tests
# ---------------------------------------------------------------------------

def _has_callable_default_named(model: type, col_name: str, func_name: str) -> bool:
    """Check if a column has a callable default with a given function name."""
    col = _column(model, col_name)
    if col.default is None:
        return False
    if callable(col.default.arg):
        return col.default.arg.__name__ == func_name
    return False


def _get_scalar_default(model: type, attr_name: str) -> object:
    """Return the scalar default value for a mapped column attribute.

    For nullable columns with no explicit default, SQLAlchemy may not create
    a ColumnDefault object -- returns a sentinel _NO_DEFAULT in that case.
    """
    attr = model.__mapper__.column_attrs[attr_name]
    col = attr.columns[0]
    if col.default is not None:
        return col.default.arg
    return _NO_DEFAULT


_NO_DEFAULT = object()


class TestProfileDefaults:
    """Profile model Python-level defaults."""

    def test_id_has_no_default(self) -> None:
        """Profile.id is the Cognito sub -- no auto-generated default."""
        col = _column(Profile, "id")
        assert col.default is None

    def test_timezone_default_utc(self) -> None:
        assert _get_scalar_default(Profile, "timezone") == "UTC"

    def test_preferred_language_default_en(self) -> None:
        assert _get_scalar_default(Profile, "preferred_language") == "en"

    def test_onboarding_completed_default_false(self) -> None:
        assert _get_scalar_default(Profile, "onboarding_completed") is False

    def test_subscription_tier_default_free(self) -> None:
        assert _get_scalar_default(Profile, "subscription_tier") == "free"

    def test_fcm_token_is_nullable(self) -> None:
        """fcm_token is nullable -- None is implicitly the default."""
        assert _column(Profile, "fcm_token").nullable is True

    def test_avatar_url_is_nullable(self) -> None:
        """avatar_url is nullable -- None is implicitly the default."""
        assert _column(Profile, "avatar_url").nullable is True

    def test_subscription_expires_at_is_nullable(self) -> None:
        """subscription_expires_at is nullable -- None is implicitly the default."""
        assert _column(Profile, "subscription_expires_at").nullable is True


class TestCharacterDefaults:
    """Character model Python-level defaults."""

    def test_id_default_is_uuid4_callable(self) -> None:
        """Character.id uses uuid4 as default generator."""
        assert _has_callable_default_named(Character, "id", "uuid4")

    def test_avatar_style_default_is_default(self) -> None:
        assert _get_scalar_default(Character, "avatar_style") == "default"

    def test_is_default_default_false(self) -> None:
        assert _get_scalar_default(Character, "is_default") is False

    def test_is_active_default_true(self) -> None:
        assert _get_scalar_default(Character, "is_active") is True

    def test_description_is_nullable(self) -> None:
        """description is nullable -- None is implicitly the default."""
        assert _column(Character, "description").nullable is True


class TestConversationDefaults:
    """Conversation model Python-level defaults."""

    def test_id_default_is_uuid4_callable(self) -> None:
        assert _has_callable_default_named(Conversation, "id", "uuid4")

    def test_last_message_at_is_nullable(self) -> None:
        """last_message_at is nullable -- None is implicitly the default."""
        assert _column(Conversation, "last_message_at").nullable is True


class TestMessageDefaults:
    """Message model defaults."""

    def test_id_default_is_uuid4_callable(self) -> None:
        assert _has_callable_default_named(Message, "id", "uuid4")

    def test_created_at_has_server_default(self) -> None:
        """Message.created_at uses server_default=func.now()."""
        col = _column(Message, "created_at")
        assert col.server_default is not None

    def test_media_url_is_nullable(self) -> None:
        """media_url is nullable -- None is implicitly the default."""
        assert _column(Message, "media_url").nullable is True

    def test_tts_url_is_nullable(self) -> None:
        """tts_url is nullable -- None is implicitly the default."""
        assert _column(Message, "tts_url").nullable is True

    def test_metadata_is_nullable(self) -> None:
        """metadata is nullable -- None is implicitly the default."""
        assert _column(Message, "metadata").nullable is True


class TestPartnerDefaults:
    """Partner model defaults."""

    def test_id_default_is_uuid4_callable(self) -> None:
        assert _has_callable_default_named(Partner, "id", "uuid4")

    def test_status_default_pending(self) -> None:
        assert _get_scalar_default(Partner, "status") == "pending"

    def test_user_id_2_is_nullable(self) -> None:
        """user_id_2 is nullable -- None is implicitly the default."""
        assert _column(Partner, "user_id_2").nullable is True


class TestBodyMeasurementDefaults:
    """BodyMeasurement model defaults."""

    def test_id_default_is_uuid4_callable(self) -> None:
        assert _has_callable_default_named(BodyMeasurement, "id", "uuid4")

    def test_weight_kg_is_nullable(self) -> None:
        assert _column(BodyMeasurement, "weight_kg").nullable is True

    def test_body_fat_pct_is_nullable(self) -> None:
        assert _column(BodyMeasurement, "body_fat_pct").nullable is True

    def test_notes_is_nullable(self) -> None:
        assert _column(BodyMeasurement, "notes").nullable is True


class TestUserActivityDefaults:
    """UserActivity model defaults."""

    def test_notifications_sent_today_server_default(self) -> None:
        """notifications_sent_today should have server_default='[]'::jsonb."""
        col = _column(UserActivity, "notifications_sent_today")
        assert col.server_default is not None
        server_default_text = str(col.server_default.arg)
        assert "[]" in server_default_text

    def test_updated_at_has_server_default(self) -> None:
        col = _column(UserActivity, "updated_at")
        assert col.server_default is not None

    def test_updated_at_has_onupdate(self) -> None:
        col = _column(UserActivity, "updated_at")
        assert col.onupdate is not None

    def test_last_active_at_is_nullable(self) -> None:
        """last_active_at is nullable -- None is implicitly the default."""
        assert _column(UserActivity, "last_active_at").nullable is True

    def test_last_chat_at_is_nullable(self) -> None:
        """last_chat_at is nullable -- None is implicitly the default."""
        assert _column(UserActivity, "last_chat_at").nullable is True


# ---------------------------------------------------------------------------
# 7. Server default tests
# ---------------------------------------------------------------------------

class TestServerDefaults:
    """Server-side defaults (func.now() etc.)."""

    def test_profile_created_at_has_server_default(self) -> None:
        col = _column(Profile, "created_at")
        assert col.server_default is not None

    def test_profile_updated_at_has_server_default(self) -> None:
        col = _column(Profile, "updated_at")
        assert col.server_default is not None

    def test_profile_updated_at_has_onupdate(self) -> None:
        col = _column(Profile, "updated_at")
        assert col.onupdate is not None

    def test_character_created_at_has_server_default(self) -> None:
        col = _column(Character, "created_at")
        assert col.server_default is not None

    def test_conversation_created_at_has_server_default(self) -> None:
        col = _column(Conversation, "created_at")
        assert col.server_default is not None

    def test_partner_created_at_has_server_default(self) -> None:
        col = _column(Partner, "created_at")
        assert col.server_default is not None

    def test_body_measurement_created_at_has_server_default(self) -> None:
        col = _column(BodyMeasurement, "created_at")
        assert col.server_default is not None

    def test_message_created_at_has_server_default(self) -> None:
        col = _column(Message, "created_at")
        assert col.server_default is not None


# ---------------------------------------------------------------------------
# 8. CHECK constraint content tests
# ---------------------------------------------------------------------------

class TestCheckConstraintContent:
    """Verify CHECK constraint SQL text contains expected values."""

    def test_subscription_tier_check_has_free(self) -> None:
        text = _get_check_constraint_text(Profile, "ck_profiles_subscription_tier")
        assert text is not None
        assert "'free'" in text

    def test_subscription_tier_check_has_premium(self) -> None:
        text = _get_check_constraint_text(Profile, "ck_profiles_subscription_tier")
        assert text is not None
        assert "'premium'" in text

    def test_message_role_check_has_user(self) -> None:
        text = _get_check_constraint_text(Message, "ck_messages_role")
        assert text is not None
        assert "'user'" in text

    def test_message_role_check_has_assistant(self) -> None:
        text = _get_check_constraint_text(Message, "ck_messages_role")
        assert text is not None
        assert "'assistant'" in text

    def test_partner_status_check_has_pending(self) -> None:
        text = _get_check_constraint_text(Partner, "ck_partners_status")
        assert text is not None
        assert "'pending'" in text

    def test_partner_status_check_has_active(self) -> None:
        text = _get_check_constraint_text(Partner, "ck_partners_status")
        assert text is not None
        assert "'active'" in text

    def test_partner_status_check_has_disconnected(self) -> None:
        text = _get_check_constraint_text(Partner, "ck_partners_status")
        assert text is not None
        assert "'disconnected'" in text


# ---------------------------------------------------------------------------
# 9. Index column composition tests
# ---------------------------------------------------------------------------

class TestIndexCompositions:
    """Verify which columns each index covers."""

    def test_messages_conv_time_index_columns(self) -> None:
        exprs = _index_expression_strings(Message, "idx_messages_conv_time")
        joined = " ".join(exprs)
        assert "conversation_id" in joined
        assert "created_at" in joined

    def test_messages_conv_time_index_has_desc(self) -> None:
        """The created_at column in idx_messages_conv_time uses DESC."""
        exprs = _index_expression_strings(Message, "idx_messages_conv_time")
        joined = " ".join(exprs).upper()
        assert "DESC" in joined

    def test_messages_user_id_index_columns(self) -> None:
        exprs = _index_expression_strings(Message, "idx_messages_user_id")
        joined = " ".join(exprs)
        assert "user_id" in joined

    def test_conversations_user_time_index_columns(self) -> None:
        exprs = _index_expression_strings(Conversation, "idx_conversations_user_time")
        joined = " ".join(exprs)
        assert "user_id" in joined
        assert "last_message_at" in joined

    def test_conversations_user_time_index_has_desc(self) -> None:
        """The last_message_at column in idx_conversations_user_time uses DESC."""
        exprs = _index_expression_strings(Conversation, "idx_conversations_user_time")
        joined = " ".join(exprs).upper()
        assert "DESC" in joined

    def test_characters_user_active_index_columns(self) -> None:
        exprs = _index_expression_strings(Character, "idx_characters_user_active")
        joined = " ".join(exprs)
        assert "user_id" in joined
        assert "is_active" in joined

    def test_body_measurements_user_date_index_columns(self) -> None:
        exprs = _index_expression_strings(BodyMeasurement, "idx_body_measurements_user_date")
        joined = " ".join(exprs)
        assert "user_id" in joined
        assert "date" in joined

    def test_partners_user1_index_columns(self) -> None:
        exprs = _index_expression_strings(Partner, "idx_partners_user1")
        joined = " ".join(exprs)
        assert "user_id_1" in joined

    def test_partners_user2_index_columns(self) -> None:
        exprs = _index_expression_strings(Partner, "idx_partners_user2")
        joined = " ".join(exprs)
        assert "user_id_2" in joined


# ---------------------------------------------------------------------------
# 10. Relationship tests
# ---------------------------------------------------------------------------

class TestProfileRelationships:
    """Profile model relationship definitions."""

    def test_has_characters_relationship(self) -> None:
        rel = _get_relationship(Profile, "characters")
        assert rel is not None

    def test_characters_back_populates_user(self) -> None:
        rel = _get_relationship(Profile, "characters")
        assert rel is not None
        assert rel.back_populates == "user"

    def test_characters_cascade_includes_delete_and_delete_orphan(self) -> None:
        rel = _get_relationship(Profile, "characters")
        assert rel is not None
        assert "delete" in rel.cascade
        assert "delete-orphan" in rel.cascade

    def test_has_conversations_relationship(self) -> None:
        rel = _get_relationship(Profile, "conversations")
        assert rel is not None

    def test_conversations_back_populates_user(self) -> None:
        rel = _get_relationship(Profile, "conversations")
        assert rel is not None
        assert rel.back_populates == "user"

    def test_conversations_cascade_includes_delete_and_delete_orphan(self) -> None:
        rel = _get_relationship(Profile, "conversations")
        assert rel is not None
        assert "delete" in rel.cascade
        assert "delete-orphan" in rel.cascade


class TestCharacterRelationships:
    """Character model relationship definitions."""

    def test_has_user_relationship(self) -> None:
        rel = _get_relationship(Character, "user")
        assert rel is not None

    def test_user_back_populates_characters(self) -> None:
        rel = _get_relationship(Character, "user")
        assert rel is not None
        assert rel.back_populates == "characters"

    def test_has_conversation_relationship(self) -> None:
        rel = _get_relationship(Character, "conversation")
        assert rel is not None

    def test_conversation_is_one_to_one(self) -> None:
        """Character.conversation uses uselist=False for one-to-one."""
        rel = _get_relationship(Character, "conversation")
        assert rel is not None
        assert rel.uselist is False

    def test_conversation_back_populates_character(self) -> None:
        rel = _get_relationship(Character, "conversation")
        assert rel is not None
        assert rel.back_populates == "character"


class TestConversationRelationships:
    """Conversation model relationship definitions."""

    def test_has_user_relationship(self) -> None:
        rel = _get_relationship(Conversation, "user")
        assert rel is not None

    def test_user_back_populates_conversations(self) -> None:
        rel = _get_relationship(Conversation, "user")
        assert rel is not None
        assert rel.back_populates == "conversations"

    def test_has_character_relationship(self) -> None:
        rel = _get_relationship(Conversation, "character")
        assert rel is not None

    def test_character_back_populates_conversation(self) -> None:
        rel = _get_relationship(Conversation, "character")
        assert rel is not None
        assert rel.back_populates == "conversation"

    def test_has_messages_relationship(self) -> None:
        rel = _get_relationship(Conversation, "messages")
        assert rel is not None

    def test_messages_back_populates_conversation(self) -> None:
        rel = _get_relationship(Conversation, "messages")
        assert rel is not None
        assert rel.back_populates == "conversation"

    def test_messages_cascade_includes_delete_and_delete_orphan(self) -> None:
        rel = _get_relationship(Conversation, "messages")
        assert rel is not None
        assert "delete" in rel.cascade
        assert "delete-orphan" in rel.cascade


class TestMessageRelationships:
    """Message model relationship definitions."""

    def test_has_conversation_relationship(self) -> None:
        rel = _get_relationship(Message, "conversation")
        assert rel is not None

    def test_conversation_back_populates_messages(self) -> None:
        rel = _get_relationship(Message, "conversation")
        assert rel is not None
        assert rel.back_populates == "messages"

    def test_has_user_relationship(self) -> None:
        rel = _get_relationship(Message, "user")
        assert rel is not None


class TestUserActivityRelationships:
    """UserActivity model relationship definitions."""

    def test_has_user_relationship(self) -> None:
        rel = _get_relationship(UserActivity, "user")
        assert rel is not None


class TestPartnerRelationships:
    """Partner model relationship definitions."""

    def test_has_inviter_relationship(self) -> None:
        rel = _get_relationship(Partner, "inviter")
        assert rel is not None

    def test_has_invitee_relationship(self) -> None:
        rel = _get_relationship(Partner, "invitee")
        assert rel is not None


class TestBodyMeasurementRelationships:
    """BodyMeasurement model relationship definitions."""

    def test_has_user_relationship(self) -> None:
        rel = _get_relationship(BodyMeasurement, "user")
        assert rel is not None


# ---------------------------------------------------------------------------
# 11. Message.metadata_ attribute mapping
# ---------------------------------------------------------------------------

class TestMessageMetadataMapping:
    """Message.metadata_ Python attribute maps to 'metadata' DB column."""

    def test_metadata_column_exists_in_table(self) -> None:
        """The DB column name is 'metadata' (not 'metadata_')."""
        assert "metadata" in _column_names(Message)

    def test_metadata_underscore_not_in_column_names(self) -> None:
        """There should not be a column literally named 'metadata_'."""
        assert "metadata_" not in _column_names(Message)

    def test_metadata_mapped_attribute_key(self) -> None:
        """The Python attribute key is 'metadata_'."""
        mapper = sa_inspect(Message)
        attr_keys = [prop.key for prop in mapper.column_attrs]
        assert "metadata_" in attr_keys

    def test_metadata_mapped_column_name(self) -> None:
        """The mapper attribute metadata_ maps to the 'metadata' column."""
        attr = Message.__mapper__.column_attrs["metadata_"]
        col = attr.columns[0]
        assert col.name == "metadata"


# ---------------------------------------------------------------------------
# 12. Unique constraint name tests
# ---------------------------------------------------------------------------

class TestUniqueConstraintNames:
    """Verify unique constraints have expected names."""

    def test_body_measurements_user_date_constraint_name(self) -> None:
        """The composite unique on (user_id, date) must be named uq_body_measurements_user_date."""
        table = BodyMeasurement.__table__
        for constraint in table.constraints:
            if isinstance(constraint, sa.UniqueConstraint):
                cols = {c.name for c in constraint.columns}
                if cols == {"user_id", "date"}:
                    assert constraint.name == "uq_body_measurements_user_date"
                    return
        raise AssertionError("Unique constraint on (user_id, date) not found")


# ---------------------------------------------------------------------------
# 13. Base.metadata structural tests
# ---------------------------------------------------------------------------

class TestBaseMetadataStructure:
    """Base.metadata resolves without issues."""

    def test_sorted_tables_no_circular_deps(self) -> None:
        """sorted_tables must resolve without circular dependency errors."""
        tables = Base.metadata.sorted_tables
        assert len(tables) >= 7

    def test_sorted_tables_profiles_before_characters(self) -> None:
        """profiles must appear before characters in topological sort (FK dependency)."""
        tables = Base.metadata.sorted_tables
        table_order = [t.name for t in tables]
        profiles_idx = table_order.index("profiles")
        characters_idx = table_order.index("characters")
        assert profiles_idx < characters_idx

    def test_sorted_tables_characters_before_conversations(self) -> None:
        """characters must appear before conversations (FK dependency)."""
        tables = Base.metadata.sorted_tables
        table_order = [t.name for t in tables]
        characters_idx = table_order.index("characters")
        conversations_idx = table_order.index("conversations")
        assert characters_idx < conversations_idx

    def test_sorted_tables_conversations_before_messages(self) -> None:
        """conversations must appear before messages (FK dependency)."""
        tables = Base.metadata.sorted_tables
        table_order = [t.name for t in tables]
        conversations_idx = table_order.index("conversations")
        messages_idx = table_order.index("messages")
        assert conversations_idx < messages_idx

    def test_all_seven_tables_in_metadata(self) -> None:
        """All 7 application tables are in Base.metadata.tables."""
        expected = {
            "profiles", "characters", "conversations", "messages",
            "user_activity", "partners", "body_measurements",
        }
        actual = set(Base.metadata.tables.keys())
        assert expected.issubset(actual)


# ---------------------------------------------------------------------------
# 14. Model instantiation tests (Python-level, no DB)
# ---------------------------------------------------------------------------

class TestModelInstantiation:
    """Models can be instantiated without errors.

    Note: SQLAlchemy 2.0 mapped_column(default=...) values are applied at
    flush time, not __init__ time. These tests verify constructability and
    that nullable fields default to None on the Python object.
    """

    def test_character_can_be_constructed(self) -> None:
        """Character can be instantiated with required fields only."""
        c = Character(
            user_id=uuid.uuid4(),
            name="Test",
            template="companion",
            system_prompt="Hello",
            mem0_agent_id="test_agent_inst",
        )
        assert c.name == "Test"

    def test_partner_user_id_2_defaults_none(self) -> None:
        p = Partner(
            user_id_1=uuid.uuid4(),
            invite_token="tok456",
        )
        assert p.user_id_2 is None

    def test_conversation_last_message_at_defaults_none(self) -> None:
        c = Conversation(
            user_id=uuid.uuid4(),
            character_id=uuid.uuid4(),
        )
        assert c.last_message_at is None

    def test_message_can_be_constructed(self) -> None:
        """Message can be instantiated with required fields only."""
        m = Message(
            conversation_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            role="user",
            content="Hello",
        )
        assert m.role == "user"
        assert m.content == "Hello"

    def test_profile_can_be_constructed(self) -> None:
        """Profile can be instantiated with required fields."""
        p = Profile(
            id=uuid.uuid4(),
            email="test_inst@test.com",
            name="Tester",
            mem0_user_id="m0_inst",
        )
        assert p.email == "test_inst@test.com"

    def test_body_measurement_can_be_constructed(self) -> None:
        """BodyMeasurement can be instantiated with required fields."""
        b = BodyMeasurement(
            user_id=uuid.uuid4(),
            date=date.today(),
        )
        assert b.date == date.today()

    def test_user_activity_can_be_constructed(self) -> None:
        """UserActivity can be instantiated with user_id."""
        ua = UserActivity(
            user_id=uuid.uuid4(),
        )
        assert ua.last_active_at is None
