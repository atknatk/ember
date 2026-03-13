"""ModerationEvent model — append-only audit log for content moderation actions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ModerationEvent(Base):
    """Records a content moderation action for auditing and abuse rate detection."""

    __tablename__ = "moderation_events"

    __table_args__ = (
        Index("idx_moderation_events_user_time", "user_id", "created_at"),
        Index("idx_moderation_events_created", "created_at"),
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
    )
    event_type: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    severity: Mapped[str] = mapped_column(Text)
    user_content: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    details: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=None,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


__all__ = ["ModerationEvent"]
