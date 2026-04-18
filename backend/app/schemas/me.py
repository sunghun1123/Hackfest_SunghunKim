"""Response model for GET /me."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MeResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    device_id: str
    display_name: str | None
    points: int
    level: int
    level_name: str
    level_weight: int
    next_level_points: int   # -1 when at Legend (no further level)
    submission_count: int
    confirmation_count: int
    daily_streak: int
    can_rate_restaurants: bool
    first_seen: datetime
