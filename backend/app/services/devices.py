"""Shared device-lifecycle helpers (upsert, point awards).

Multiple routers (submissions, confirmations, ratings, reports, me) all need
to ensure a device row exists before writing child rows that FK to it. The
compute_level trigger on `devices` auto-updates level + level_weight when
`points` changes, so callers just need to adjust `points` and SELECT the
fresh row.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class DeviceRow:
    device_id: str
    points: int
    level: int
    level_weight: int


async def require_device_id(x_device_id: str | None = Header(None)) -> str:
    """FastAPI dependency: enforces the X-Device-Id header on protected routes."""
    if not x_device_id:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "code": "DEVICE_ID_REQUIRED",
                    "message": "X-Device-Id header is required",
                    "details": {},
                }
            },
        )
    return x_device_id


async def upsert_device(db: AsyncSession, device_id: str) -> DeviceRow:
    """Create the device row on first contact, else bump last_seen. Returns
    the current points/level snapshot so callers can diff against the
    post-update values to detect level-ups."""
    result = await db.execute(
        text(
            """
            INSERT INTO devices (device_id) VALUES (:id)
            ON CONFLICT (device_id)
            DO UPDATE SET last_seen = NOW()
            RETURNING device_id, points, level, level_weight
            """
        ),
        {"id": device_id},
    )
    row = result.one()
    return DeviceRow(
        device_id=row.device_id,
        points=row.points,
        level=row.level,
        level_weight=row.level_weight,
    )


async def award_points(
    db: AsyncSession,
    device_id: str,
    points: int,
    action: str,
    reference_id=None,
    increment_submission_count: bool = False,
    increment_confirmation_count: bool = False,
) -> DeviceRow:
    """Add `points` to the device, record in point_history, return the fresh
    row. The compute_level trigger handles level recalculation."""
    set_clauses = ["points = points + :p", "last_seen = NOW()"]
    if increment_submission_count:
        set_clauses.append("submission_count = submission_count + 1")
    if increment_confirmation_count:
        set_clauses.append("confirmation_count = confirmation_count + 1")

    sql = f"""
        UPDATE devices
        SET {', '.join(set_clauses)}
        WHERE device_id = :id
        RETURNING device_id, points, level, level_weight
    """
    result = await db.execute(text(sql), {"id": device_id, "p": points})
    row = result.one()

    await db.execute(
        text(
            """
            INSERT INTO point_history (device_id, action, points, reference_id)
            VALUES (:device_id, :action, :points, :ref)
            """
        ),
        {
            "device_id": device_id,
            "action": action,
            "points": points,
            "ref": reference_id,
        },
    )
    return DeviceRow(
        device_id=row.device_id,
        points=row.points,
        level=row.level,
        level_weight=row.level_weight,
    )
