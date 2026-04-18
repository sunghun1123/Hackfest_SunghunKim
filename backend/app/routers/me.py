"""GET /me — device profile + daily-bonus check.

On every call we:
  1. upsert_device (bumps last_seen; creates the row if missing)
  2. check last_daily_bonus against today in Pacific time; if not yet
     claimed, award +1 and update streak (consecutive-day counter, resets
     after a gap)
  3. Return the profile with derived fields (level_name, next_level_points,
     can_rate_restaurants)

Using America/Los_Angeles as the canonical "day boundary" regardless of
where the user is — predictable and matches our hackathon's PT timezone.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas.me import MeResponse
from app.services.devices import award_points, require_device_id, upsert_device

router = APIRouter(tags=["me"])

_DAILY_BONUS_POINTS = 1
_PT = ZoneInfo("America/Los_Angeles")

# level → display name (schema trigger only produces {1,2,3,4,5,7,10}; the
# rest are here for future-proofing in case the ladder expands).
_LEVEL_NAMES: dict[int, str] = {
    1: "Newbie",
    2: "Scout",
    3: "Regular",
    4: "Explorer",
    5: "Expert",
    6: "Expert",
    7: "Veteran",
    8: "Veteran",
    9: "Veteran",
    10: "Legend",
}

# 1-indexed thresholds: next_level_points[level] = first threshold the user
# hasn't crossed. Level 10 (Legend) has no next tier → -1 sentinel.
_NEXT_LEVEL_THRESHOLDS: dict[int, int] = {
    1: 50,
    2: 150,
    3: 400,
    4: 1000,
    5: 2500,
    6: 2500,
    7: 10_000,
    8: 10_000,
    9: 10_000,
    10: -1,
}


def _today_pt() -> date:
    return datetime.now(_PT).date()


@router.get("/me", response_model=MeResponse)
async def get_me(
    device_id: str = Depends(require_device_id),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    async with db.begin():
        await upsert_device(db, device_id)

        # Pull the full profile (upsert_device only returns the subset we
        # use for level math).
        profile = (
            await db.execute(
                text(
                    """
                    SELECT device_id, display_name, points, level, level_weight,
                           submission_count, confirmation_count,
                           daily_streak, last_daily_bonus, first_seen
                    FROM devices
                    WHERE device_id = :id
                    """
                ),
                {"id": device_id},
            )
        ).one()

        today = _today_pt()
        if profile.last_daily_bonus != today:
            # Streak logic: +1 if yesterday was the last bonus, else reset.
            yesterday = today - timedelta(days=1)
            new_streak = (
                (profile.daily_streak or 0) + 1
                if profile.last_daily_bonus == yesterday
                else 1
            )
            await db.execute(
                text(
                    """
                    UPDATE devices
                    SET last_daily_bonus = :today,
                        daily_streak = :streak
                    WHERE device_id = :id
                    """
                ),
                {"today": today, "streak": new_streak, "id": device_id},
            )
            updated = await award_points(
                db,
                device_id=device_id,
                points=_DAILY_BONUS_POINTS,
                action="daily",
            )
            points = updated.points
            level = updated.level
            level_weight = updated.level_weight
            daily_streak = new_streak
        else:
            points = profile.points
            level = profile.level
            level_weight = profile.level_weight
            daily_streak = profile.daily_streak or 0

    return MeResponse(
        device_id=profile.device_id,
        display_name=profile.display_name,
        points=points,
        level=level,
        level_name=_LEVEL_NAMES.get(level, "Unknown"),
        level_weight=level_weight,
        next_level_points=_NEXT_LEVEL_THRESHOLDS.get(level, -1),
        submission_count=profile.submission_count,
        confirmation_count=profile.confirmation_count,
        daily_streak=daily_streak,
        can_rate_restaurants=level >= 3,
        first_seen=profile.first_seen,
    )
