from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from geoalchemy2 import Geography
from sqlalchemy import DateTime, Double, Index, Numeric, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.menu import MenuItem
    from app.models.rating import Rating


class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    google_place_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Plan A: PostGIS spatial column (nullable; trigger populates from lat/lng)
    # spatial_index=False because the GIST index is created explicitly in migration
    location = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False), nullable=True
    )
    # Plan B: always-present raw coordinates for Haversine fallback
    lat: Mapped[float] = mapped_column(Double, nullable=False)
    lng: Mapped[float] = mapped_column(Double, nullable=False)

    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_rating: Mapped[float | None] = mapped_column(Numeric(2, 1), nullable=True)
    price_level: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    hours_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    app_rating: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    rating_count: Mapped[int] = mapped_column(server_default=text("0"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )

    menu_items: Mapped[list["MenuItem"]] = relationship(
        back_populates="restaurant", cascade="all, delete-orphan"
    )
    ratings: Mapped[list["Rating"]] = relationship(
        back_populates="restaurant", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_restaurants_lat", "lat"),
        Index("idx_restaurants_lng", "lng"),
        Index("idx_restaurants_category", "category"),
    )
