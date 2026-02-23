"""Conversation model — one conversation per character, auto-created."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, desc
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.character import Character
    from app.models.message import Message
    from app.models.profile import Profile


class Conversation(TimestampMixin, Base):
    """One conversation per character. Users never see this table directly."""

    __tablename__ = "conversations"

    __table_args__ = (
        Index(
            "idx_conversations_user_time",
            "user_id",
            desc("last_message_at"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"),
    )
    character_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"),
        unique=True,
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # Relationships — class names resolved by SQLAlchemy mapper registry
    user: Mapped[Profile] = relationship(back_populates="conversations")
    character: Mapped[Character] = relationship(back_populates="conversation")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


__all__ = ["Conversation"]
