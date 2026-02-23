"""Character model — AI character instances owned by a user."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.profile import Profile


class Character(TimestampMixin, Base):
    """AI character instance, one per user per character template."""

    __tablename__ = "characters"

    __table_args__ = (
        Index("idx_characters_user_active", "user_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"),
    )
    name: Mapped[str] = mapped_column(Text)
    template: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    system_prompt: Mapped[str] = mapped_column(Text)
    mem0_agent_id: Mapped[str] = mapped_column(Text, unique=True)
    avatar_style: Mapped[str] = mapped_column(Text, default="default")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships — class names resolved by SQLAlchemy mapper registry
    user: Mapped[Profile] = relationship(back_populates="characters")
    conversation: Mapped[Conversation | None] = relationship(
        back_populates="character",
        uselist=False,
    )


__all__ = ["Character"]
