"""SQLAlchemy ORM models for the Ember backend.

All model classes are imported here so that Alembic autogenerate can detect them
via Base.metadata. This is the canonical import point for all models.
"""

from app.models.base import Base, TimestampMixin
from app.models.body_measurement import BodyMeasurement
from app.models.character import Character
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.moderation_event import ModerationEvent
from app.models.partner import Partner
from app.models.profile import Profile
from app.models.user_activity import UserActivity
from app.models.user_moderation_state import UserModerationState

__all__ = [
    "Base",
    "BodyMeasurement",
    "Character",
    "Conversation",
    "Message",
    "ModerationEvent",
    "Partner",
    "Profile",
    "TimestampMixin",
    "UserActivity",
    "UserModerationState",
]
