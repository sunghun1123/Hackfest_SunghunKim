"""POST /reports — flag a menu_item as wrong/spam/etc.

The `auto_dispute_on_reports` trigger flips verification_status to 'disputed'
once pending reports for a menu_item reach 3. We detect the flip by
re-reading verification_status after the INSERT and surface it as
`menu_item_auto_disputed` so clients can show a toast.

Rate-limited to 10 reports per rolling 24h per device (abuse guard).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas.report import ReportCreate, ReportResponse
from app.services.devices import require_device_id, upsert_device
from app.services.rate_limit import reports_limiter

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("", response_model=ReportResponse, status_code=201)
async def create_report(
    body: ReportCreate,
    device_id: str = Depends(require_device_id),
    db: AsyncSession = Depends(get_db),
) -> ReportResponse:
    if not reports_limiter.check_and_record(device_id):
        raise HTTPException(
            status_code=429,
            detail={
                "error": {
                    "code": "RATE_LIMITED",
                    "message": "Report limit reached — 10 per day per device",
                    "details": {"window_seconds": 86_400, "max_calls": 10},
                }
            },
        )

    async with db.begin():
        await upsert_device(db, device_id)

        menu = (
            await db.execute(
                text(
                    """
                    SELECT id, verification_status
                    FROM menu_items
                    WHERE id = :id AND is_active = TRUE
                    """
                ),
                {"id": body.menu_item_id},
            )
        ).first()
        if menu is None:
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

        existing = (
            await db.execute(
                text(
                    """
                    SELECT id FROM reports
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
                        "code": "ALREADY_REPORTED",
                        "message": "This device already reported this menu item",
                        "details": {"report_id": str(existing.id)},
                    }
                },
            )

        try:
            report_row = (
                await db.execute(
                    text(
                        """
                        INSERT INTO reports
                            (menu_item_id, device_id, reason, comment)
                        VALUES (:mid, :did, :reason, :comment)
                        RETURNING id, status
                        """
                    ),
                    {
                        "mid": body.menu_item_id,
                        "did": device_id,
                        "reason": body.reason,
                        "comment": body.comment,
                    },
                )
            ).one()
        except IntegrityError:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "ALREADY_REPORTED",
                        "message": "This device already reported this menu item",
                        "details": {},
                    }
                },
            )

        # Trigger auto_dispute_on_reports fires AFTER INSERT — re-read the
        # menu_item to see whether it just flipped.
        refreshed = (
            await db.execute(
                text(
                    """
                    SELECT verification_status
                    FROM menu_items
                    WHERE id = :id
                    """
                ),
                {"id": body.menu_item_id},
            )
        ).one()
        auto_disputed = (
            menu.verification_status != "disputed"
            and refreshed.verification_status == "disputed"
        )

    return ReportResponse(
        id=report_row.id,
        status=report_row.status,
        menu_item_auto_disputed=auto_disputed,
    )
