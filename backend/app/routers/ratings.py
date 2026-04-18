"""POST /ratings — Level 3+ users rate a restaurant 1-5.

  - weight_applied snapshots the user's level_weight at rating time (same
    pattern as confirmations — future level-ups don't retroactively sway
    old ratings)
  - app_rating is a weighted mean: SUM(score * weight) / SUM(weight) over
    all ratings for the restaurant; cheaper to recompute than to maintain
    incrementally and keeps the math transparent
  - +2 points per rating
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas.rating import (
    RatingCreate,
    RatingResponse,
    RestaurantRatingUpdated,
)
from app.services.devices import award_points, require_device_id, upsert_device

router = APIRouter(prefix="/ratings", tags=["ratings"])

_POINTS_PER_RATING = 2
_MIN_RATING_LEVEL = 3


@router.post("", response_model=RatingResponse, status_code=201)
async def create_rating(
    body: RatingCreate,
    device_id: str = Depends(require_device_id),
    db: AsyncSession = Depends(get_db),
) -> RatingResponse:
    async with db.begin():
        device = await upsert_device(db, device_id)

        if device.level < _MIN_RATING_LEVEL:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "INSUFFICIENT_LEVEL",
                        "message": f"Rating requires level {_MIN_RATING_LEVEL}+",
                        "details": {
                            "current_level": device.level,
                            "required_level": _MIN_RATING_LEVEL,
                        },
                    }
                },
            )

        restaurant = (
            await db.execute(
                text("SELECT id FROM restaurants WHERE id = :id"),
                {"id": body.restaurant_id},
            )
        ).first()
        if restaurant is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "RESTAURANT_NOT_FOUND",
                        "message": "Restaurant not found",
                        "details": {},
                    }
                },
            )

        existing = (
            await db.execute(
                text(
                    """
                    SELECT id FROM ratings
                    WHERE restaurant_id = :rid AND device_id = :did
                    """
                ),
                {"rid": body.restaurant_id, "did": device_id},
            )
        ).first()
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "ALREADY_RATED",
                        "message": "This device already rated this restaurant",
                        "details": {"rating_id": str(existing.id)},
                    }
                },
            )

        try:
            rating_row = (
                await db.execute(
                    text(
                        """
                        INSERT INTO ratings
                            (restaurant_id, device_id, score, weight_applied, comment)
                        VALUES (:rid, :did, :score, :w, :comment)
                        RETURNING id
                        """
                    ),
                    {
                        "rid": body.restaurant_id,
                        "did": device_id,
                        "score": body.score,
                        "w": device.level_weight,
                        "comment": body.comment,
                    },
                )
            ).one()
        except IntegrityError:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "ALREADY_RATED",
                        "message": "This device already rated this restaurant",
                        "details": {},
                    }
                },
            )

        # Weighted mean recalc. Cast to NUMERIC first so we don't get integer
        # truncation; round to 2 decimals to match the column (NUMERIC(3,2)).
        stats = (
            await db.execute(
                text(
                    """
                    SELECT
                        ROUND(
                            SUM(score * weight_applied)::NUMERIC
                            / NULLIF(SUM(weight_applied), 0)::NUMERIC,
                            2
                        ) AS avg_rating,
                        COUNT(*)::int AS n
                    FROM ratings
                    WHERE restaurant_id = :rid
                    """
                ),
                {"rid": body.restaurant_id},
            )
        ).one()

        await db.execute(
            text(
                """
                UPDATE restaurants
                SET app_rating = :avg, rating_count = :n, updated_at = NOW()
                WHERE id = :rid
                """
            ),
            {"avg": stats.avg_rating, "n": stats.n, "rid": body.restaurant_id},
        )

        await award_points(
            db,
            device_id=device_id,
            points=_POINTS_PER_RATING,
            action="rating",
            reference_id=rating_row.id,
        )

    return RatingResponse(
        id=rating_row.id,
        restaurant_updated=RestaurantRatingUpdated(
            id=body.restaurant_id,
            app_rating=float(stats.avg_rating) if stats.avg_rating is not None else None,
            rating_count=stats.n,
        ),
        points_awarded=_POINTS_PER_RATING,
    )
