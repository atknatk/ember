"""BodyMeasurement model — body tracking data for fitness coaching."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.profile import Profile


class BodyMeasurement(TimestampMixin, Base):
    """Body measurement entry, one per user per day."""

    __tablename__ = "body_measurements"

    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_body_measurements_user_date"),
        Index("idx_body_measurements_user_date", "user_id", "date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"),
    )
    date: Mapped[date] = mapped_column(Date)
    weight_kg: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        default=None,
    )
    body_fat_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 1),
        nullable=True,
        default=None,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    # Relationships — class names resolved by SQLAlchemy mapper registry
    user: Mapped[Profile] = relationship()


__all__ = ["BodyMeasurement"]
