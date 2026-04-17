from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    menu_item_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("menu_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    restaurant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("restaurants.id"),
        nullable=False,
    )
    device_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("devices.device_id"), nullable=False
    )

    menu_name: Mapped[str] = mapped_column(String(255), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    gemini_parsed: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    points_awarded: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    is_first_submission: Mapped[bool] = mapped_column(
        Boolean, server_default=text("FALSE"), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20), server_default=text("'accepted'"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('accepted', 'flagged', 'rejected')", name="check_submission_status"
        ),
        Index("idx_submissions_restaurant", "restaurant_id"),
        Index("idx_submissions_device", "device_id"),
        Index("idx_submissions_created", "created_at", postgresql_ops={"created_at": "DESC"}),
    )


class Confirmation(Base):
    __tablename__ = "confirmations"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    menu_item_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("menu_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    device_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("devices.device_id"), nullable=False
    )

    weight_applied: Mapped[int] = mapped_column(Integer, nullable=False)
    is_agreement: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reported_price: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("menu_item_id", "device_id", name="unique_confirmation"),
        Index("idx_confirmations_menu", "menu_item_id"),
    )
