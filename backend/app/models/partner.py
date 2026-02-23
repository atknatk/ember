"""Partner model — partner connections for couple/accountability features."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.profile import Profile


class Partner(TimestampMixin, Base):
    """Partner connection between two users."""

    __tablename__ = "partners"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'active', 'disconnected')",
            name="ck_partners_status",
        ),
        Index("idx_partners_user1", "user_id_1"),
        Index("idx_partners_user2", "user_id_2"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id_1: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"),
    )
    user_id_2: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    invite_token: Mapped[str] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(Text, default="pending")

    # Relationships — class names resolved by SQLAlchemy mapper registry
    inviter: Mapped[Profile] = relationship(foreign_keys=[user_id_1])
    invitee: Mapped[Profile | None] = relationship(foreign_keys=[user_id_2])


__all__ = ["Partner"]
