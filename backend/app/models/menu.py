from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
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
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.restaurant import Restaurant


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    restaurant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    # Auto-populated by compute_tier trigger (BEFORE INSERT/UPDATE OF price_cents)
    tier: Mapped[str] = mapped_column(String(20), nullable=False)

    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[str] = mapped_column(String(30), nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'ai_parsed'")
    )

    confirmation_weight: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    confirmation_count: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("TRUE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

    restaurant: Mapped["Restaurant"] = relationship(back_populates="menu_items")

    __table_args__ = (
        CheckConstraint("tier IN ('survive', 'cost_effective', 'luxury')", name="check_tier"),
        CheckConstraint("price_cents > 0", name="check_price_positive"),
        CheckConstraint("price_cents <= 1500", name="check_price_in_scope"),
        CheckConstraint(
            "source IN ('gemini_web', 'gemini_photo', 'user_manual', 'seed', 'places_api', "
            "'gemini_screenshot', 'gemini_places_photo', 'gemini_pdf', 'gemini_yelp')",
            name="check_source",
        ),
        CheckConstraint(
            "verification_status IN ('ai_parsed', 'human_verified', 'disputed', 'needs_verification')",
            name="check_verification",
        ),
        Index("idx_menu_items_restaurant", "restaurant_id"),
        Index("idx_menu_items_tier", "tier", postgresql_where=text("is_active = TRUE")),
        Index(
            "idx_menu_items_status",
            "verification_status",
            postgresql_where=text("is_active = TRUE"),
        ),
        Index(
            "idx_menu_items_category",
            "category",
            postgresql_where=text("is_active = TRUE"),
        ),
    )
