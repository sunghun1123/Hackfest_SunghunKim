"""POST /submissions — user submits a menu item for a restaurant.

Branching (see docs/CLAUDE_CODE_TASKS.md Task 1.6 + docs/API.md):
  - same restaurant + normalized-name match + price diff < $1:
        treat as confirmation → bump existing confirmation_weight/count
  - same restaurant + normalized-name match + price diff $1 to $3:
        create new menu_item, mark BOTH rows as 'disputed'
  - otherwise: create a fresh menu_item with verification_status='ai_parsed'

is_first_submission is true iff the restaurant had zero active menu items
BEFORE this call — grants +5 bonus on top of the +10 base.

All DB writes live inside a single transaction.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas.submission import SubmissionCreate, SubmissionResponse
from app.services.devices import award_points, require_device_id, upsert_device

router = APIRouter(prefix="/submissions", tags=["submissions"])


# Price diff thresholds (cents).
_CONFIRM_THRESHOLD_CENTS = 100   # < $1 → same price, treat as confirmation
_DISPUTE_THRESHOLD_CENTS = 300   # <= $3 → dispute; beyond that, distinct item

_BASE_POINTS = 10
_FIRST_SUBMISSION_BONUS = 5
_FIRST_SUBMISSION_MESSAGE = "🎉 First to register this restaurant! +5 bonus"


def _normalize_name(name: str) -> str:
    """Lowercase + collapse whitespace. Anchors our fuzzy match so
    'Falafel Wrap', 'falafel wrap', and ' falafel  wrap ' all collide."""
    return " ".join(name.lower().split())


@router.post("", response_model=SubmissionResponse, status_code=201)
async def create_submission(
    body: SubmissionCreate,
    device_id: str = Depends(require_device_id),
    db: AsyncSession = Depends(get_db),
) -> SubmissionResponse:
    async with db.begin():
        device = await upsert_device(db, device_id)
        pre_level = device.level
        level_weight = device.level_weight

        # Count active menu items for this restaurant BEFORE any writes. If
        # it's zero, this submission earns the first-submission bonus and
        # necessarily takes the "create new" branch below.
        pre_count = (
            await db.execute(
                text(
                    """
                    SELECT COUNT(*)::int AS n
                    FROM menu_items
                    WHERE restaurant_id = :rid AND is_active = TRUE
                    """
                ),
                {"rid": body.restaurant_id},
            )
        ).scalar_one()
        is_first_submission = pre_count == 0

        normalized = _normalize_name(body.menu_name)
        # Candidate existing row to merge/dispute against.
        similar_row = (
            await db.execute(
                text(
                    """
                    SELECT id, price_cents, verification_status,
                           confirmation_weight, confirmation_count
                    FROM menu_items
                    WHERE restaurant_id = :rid
                      AND is_active = TRUE
                      AND regexp_replace(LOWER(TRIM(name)), '\\s+', ' ', 'g') = :n
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"rid": body.restaurant_id, "n": normalized},
            )
        ).first()

        menu_item_id: UUID
        if similar_row is not None:
            price_diff = abs(similar_row.price_cents - body.price_cents)
        else:
            price_diff = None  # type: ignore[assignment]

        if similar_row is not None and price_diff < _CONFIRM_THRESHOLD_CENTS:
            # Confirmation path: same item, same price. Bump weight/count on
            # the existing row; the auto_verify_menu trigger will flip status
            # to human_verified once weight >= 5.
            await db.execute(
                text(
                    """
                    UPDATE menu_items
                    SET confirmation_weight = confirmation_weight + :w,
                        confirmation_count  = confirmation_count + 1,
                        updated_at          = NOW()
                    WHERE id = :id
                    """
                ),
                {"w": level_weight, "id": similar_row.id},
            )
            menu_item_id = similar_row.id

        elif similar_row is not None and price_diff <= _DISPUTE_THRESHOLD_CENTS:
            # Dispute path: real disagreement. Flip the old row to 'disputed',
            # insert the new row as 'disputed' too so both show a warning
            # badge in the UI.
            await db.execute(
                text(
                    """
                    UPDATE menu_items
                    SET verification_status = 'disputed', updated_at = NOW()
                    WHERE id = :id
                    """
                ),
                {"id": similar_row.id},
            )
            new_row = (
                await db.execute(
                    text(
                        """
                        INSERT INTO menu_items
                            (restaurant_id, name, price_cents, source,
                             verification_status, photo_url)
                        VALUES (:rid, :name, :price, :src, 'disputed', :photo)
                        RETURNING id
                        """
                    ),
                    {
                        "rid": body.restaurant_id,
                        "name": body.menu_name.strip(),
                        "price": body.price_cents,
                        "src": body.source,
                        "photo": body.photo_url,
                    },
                )
            ).one()
            menu_item_id = new_row.id

        else:
            # New-item path (no match, or price diff > $3).
            new_row = (
                await db.execute(
                    text(
                        """
                        INSERT INTO menu_items
                            (restaurant_id, name, price_cents, source,
                             verification_status, photo_url)
                        VALUES (:rid, :name, :price, :src, 'ai_parsed', :photo)
                        RETURNING id
                        """
                    ),
                    {
                        "rid": body.restaurant_id,
                        "name": body.menu_name.strip(),
                        "price": body.price_cents,
                        "src": body.source,
                        "photo": body.photo_url,
                    },
                )
            ).one()
            menu_item_id = new_row.id

        points_awarded = _BASE_POINTS + (_FIRST_SUBMISSION_BONUS if is_first_submission else 0)

        submission_row = (
            await db.execute(
                text(
                    """
                    INSERT INTO submissions
                        (menu_item_id, restaurant_id, device_id, menu_name,
                         price_cents, photo_url, gemini_parsed,
                         points_awarded, is_first_submission)
                    VALUES
                        (:mid, :rid, :did, :mname, :price, :photo,
                         CAST(:gj AS JSONB), :pts, :first)
                    RETURNING id
                    """
                ),
                {
                    "mid": menu_item_id,
                    "rid": body.restaurant_id,
                    "did": device_id,
                    "mname": body.menu_name.strip(),
                    "price": body.price_cents,
                    "photo": body.photo_url,
                    "gj": _jsonify(body.gemini_parsed),
                    "pts": points_awarded,
                    "first": is_first_submission,
                },
            )
        ).one()

        updated_device = await award_points(
            db,
            device_id=device_id,
            points=points_awarded,
            action="submit_photo" if body.source == "gemini_photo" else "submit",
            reference_id=submission_row.id,
            increment_submission_count=True,
        )

    return SubmissionResponse(
        id=submission_row.id,
        menu_item_id=menu_item_id,
        status="accepted",
        points_awarded=points_awarded,
        is_first_submission=is_first_submission,
        bonus_message=_FIRST_SUBMISSION_MESSAGE if is_first_submission else None,
        user_total_points=updated_device.points,
        user_level=updated_device.level,
        level_up=updated_device.level > pre_level,
    )


def _jsonify(obj) -> str | None:
    """Serialize the gemini_parsed dict to JSON text for the JSONB cast.
    Returns None when the dict is absent so we insert SQL NULL."""
    if obj is None:
        return None
    import json
    return json.dumps(obj)
