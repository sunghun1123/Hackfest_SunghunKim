"""POST /confirmations — user affirms or disputes a menu_item's price.

Agreement path:
  - confirmations row (weight_applied = device's current level_weight)
  - menu_items.confirmation_weight += weight_applied, confirmation_count += 1
  - the auto_verify_menu trigger flips ai_parsed → human_verified once
    weight reaches 5

Disagreement path:
  - menu_items.verification_status → 'disputed'
  - if the user supplied a reported_price, insert a brand-new menu_item at
    that price with source='user_manual', status='ai_parsed'

Unique (device_id, menu_item_id) is enforced by the schema; we surface a 409
on duplicate confirmation attempts.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas.confirmation import (
    ConfirmationCreate,
    ConfirmationResponse,
    MenuItemUpdated,
)
from app.services.devices import award_points, require_device_id, upsert_device

router = APIRouter(prefix="/confirmations", tags=["confirmations"])

_POINTS_PER_CONFIRMATION = 3


@router.post("", response_model=ConfirmationResponse, status_code=201)
async def create_confirmation(
    body: ConfirmationCreate,
    device_id: str = Depends(require_device_id),
    db: AsyncSession = Depends(get_db),
) -> ConfirmationResponse:
    async with db.begin():
        device = await upsert_device(db, device_id)
        weight_applied = device.level_weight

        # Verify target exists and is active.
        menu = (
            await db.execute(
                text(
                    """
                    SELECT id, is_active
                    FROM menu_items
                    WHERE id = :id
                    """
                ),
                {"id": body.menu_item_id},
            )
        ).first()
        if menu is None or menu.is_active is False:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "MENU_ITEM_NOT_FOUND",
                        "message": "Menu item not found",
                        "details": {},
                    }
                },
            )

        # Reject duplicate up front so we return a clean 409. The DB UNIQUE
        # constraint is still the source of truth if a race slips through.
        existing = (
            await db.execute(
                text(
                    """
                    SELECT id FROM confirmations
                    WHERE menu_item_id = :mid AND device_id = :did
                    """
                ),
                {"mid": body.menu_item_id, "did": device_id},
            )
        ).first()
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "ALREADY_CONFIRMED",
                        "message": "This device already confirmed this menu item",
                        "details": {"confirmation_id": str(existing.id)},
                    }
                },
            )

        try:
            confirmation_row = (
                await db.execute(
                    text(
                        """
                        INSERT INTO confirmations
                            (menu_item_id, device_id, weight_applied,
                             is_agreement, reported_price)
                        VALUES (:mid, :did, :w, :agree, :price)
                        RETURNING id
                        """
                    ),
                    {
                        "mid": body.menu_item_id,
                        "did": device_id,
                        "w": weight_applied,
                        "agree": body.is_agreement,
                        "price": body.reported_price,
                    },
                )
            ).one()
        except IntegrityError:
            # Race lost to another request between our SELECT and INSERT.
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "ALREADY_CONFIRMED",
                        "message": "This device already confirmed this menu item",
                        "details": {},
                    }
                },
            )

        if body.is_agreement:
            # Trigger auto_verify_menu runs BEFORE UPDATE OF confirmation_weight
            # and promotes ai_parsed → human_verified when weight >= 5.
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
                {"w": weight_applied, "id": body.menu_item_id},
            )
        else:
            await db.execute(
                text(
                    """
                    UPDATE menu_items
                    SET verification_status = 'disputed',
                        updated_at          = NOW()
                    WHERE id = :id
                    """
                ),
                {"id": body.menu_item_id},
            )
            if body.reported_price is not None:
                # Grab restaurant_id + original name so the new row lands on
                # the same menu list. Restaurant is always present since the
                # menu_item existed and FKs to it.
                orig = (
                    await db.execute(
                        text(
                            """
                            SELECT restaurant_id, name
                            FROM menu_items
                            WHERE id = :id
                            """
                        ),
                        {"id": body.menu_item_id},
                    )
                ).one()
                await db.execute(
                    text(
                        """
                        INSERT INTO menu_items
                            (restaurant_id, name, price_cents, source,
                             verification_status)
                        VALUES (:rid, :name, :price, 'user_manual', 'ai_parsed')
                        """
                    ),
                    {
                        "rid": orig.restaurant_id,
                        "name": orig.name,
                        "price": body.reported_price,
                    },
                )

        # Re-select after the UPDATE so we include any trigger-driven status
        # flip in the response.
        updated = (
            await db.execute(
                text(
                    """
                    SELECT id, verification_status, confirmation_weight,
                           confirmation_count
                    FROM menu_items
                    WHERE id = :id
                    """
                ),
                {"id": body.menu_item_id},
            )
        ).one()

        updated_device = await award_points(
            db,
            device_id=device_id,
            points=_POINTS_PER_CONFIRMATION,
            action="confirm",
            reference_id=confirmation_row.id,
            increment_confirmation_count=True,
        )

    return ConfirmationResponse(
        id=confirmation_row.id,
        menu_item_updated=MenuItemUpdated(
            id=updated.id,
            verification_status=updated.verification_status,
            confirmation_weight=updated.confirmation_weight,
            confirmation_count=updated.confirmation_count,
        ),
        points_awarded=_POINTS_PER_CONFIRMATION,
        user_total_points=updated_device.points,
    )
