"""Message model — conversation messages (append-only, no updated_at)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, desc, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.profile import Profile


class Message(Base):
    """A single message in a conversation. Append-only — never updated.

    Does NOT use TimestampMixin because messages are immutable.
    created_at is defined directly; updated_at is intentionally omitted.
    """

    __tablename__ = "messages"

    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant')",
            name="ck_messages_role",
        ),
        Index("idx_messages_conv_time", "conversation_id", desc("created_at")),
        Index("idx_messages_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"),
    )
    role: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    media_url: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    tts_url: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships — class names resolved by SQLAlchemy mapper registry
    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    user: Mapped[Profile] = relationship()


__all__ = ["Message"]
