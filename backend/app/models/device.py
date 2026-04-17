from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Index, Integer, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Device(Base):
    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(50), nullable=True)

    points: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, server_default=text("1"), nullable=False)
    level_weight: Mapped[int] = mapped_column(Integer, server_default=text("1"), nullable=False)

    submission_count: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    confirmation_count: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)

    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()"), nullable=False
    )
    daily_streak: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"), nullable=False)
    last_daily_bonus: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (Index("idx_devices_level", "level"),)
