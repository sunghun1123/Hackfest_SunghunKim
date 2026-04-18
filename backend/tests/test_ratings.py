"""Integration tests for POST /ratings."""

from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy import text


async def _rate(client, device_id, restaurant_id, score, comment=None):
    body = {"restaurant_id": str(restaurant_id), "score": score}
    if comment is not None:
        body["comment"] = comment
    return await client.post(
        "/ratings",
        headers={"X-Device-Id": device_id},
        json=body,
    )


@pytest_asyncio.fixture
async def level3_device(db_session, test_device):
    """Seed the device at level 3 (200 points → L3 weight=1; the trigger
    jumps to L4 at 400, so we stay a bit under)."""
    await db_session.execute(
        text("INSERT INTO devices (device_id, points) VALUES (:d, 200)"),
        {"d": test_device},
    )
    await db_session.commit()
    return test_device


@pytest_asyncio.fixture
async def level5_device(db_session):
    """A second device seeded at Expert (weight=3) for weighted-average tests."""
    device_id = f"test-dev-{uuid.uuid4().hex[:12]}"
    await db_session.execute(
        text("INSERT INTO devices (device_id, points) VALUES (:d, 2000)"),
        {"d": device_id},
    )
    await db_session.commit()
    try:
        yield device_id
    finally:
        for stmt in (
            "DELETE FROM point_history WHERE device_id = :d",
            "DELETE FROM ratings WHERE device_id = :d",
            "DELETE FROM devices WHERE device_id = :d",
        ):
            await db_session.execute(text(stmt), {"d": device_id})
        await db_session.commit()


async def test_missing_device_id_returns_401(client, test_restaurant):
    resp = await client.post(
        "/ratings",
        json={"restaurant_id": str(test_restaurant), "score": 4},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"]["code"] == "DEVICE_ID_REQUIRED"


async def test_level_below_3_returns_403(client, test_restaurant, test_device):
    # test_device is fresh → auto-created at level 1.
    resp = await _rate(client, test_device, test_restaurant, 4)
    assert resp.status_code == 403
    err = resp.json()["detail"]["error"]
    assert err["code"] == "INSUFFICIENT_LEVEL"
    assert err["details"]["required_level"] == 3


async def test_level3_rating_succeeds_and_updates_restaurant(
    client, db_session, test_restaurant, level3_device
):
    resp = await _rate(client, level3_device, test_restaurant, 4, "solid")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["points_awarded"] == 2
    upd = body["restaurant_updated"]
    assert upd["id"] == str(test_restaurant)
    assert upd["rating_count"] == 1
    assert upd["app_rating"] == 4.0

    # Verify the restaurants row was actually updated (not just echoed).
    row = (
        await db_session.execute(
            text(
                "SELECT app_rating, rating_count FROM restaurants WHERE id = :id"
            ),
            {"id": test_restaurant},
        )
    ).one()
    assert float(row.app_rating) == 4.0
    assert row.rating_count == 1


async def test_duplicate_rating_returns_409(
    client, test_restaurant, level3_device
):
    first = await _rate(client, level3_device, test_restaurant, 4)
    assert first.status_code == 201
    second = await _rate(client, level3_device, test_restaurant, 5)
    assert second.status_code == 409
    assert second.json()["detail"]["error"]["code"] == "ALREADY_RATED"


async def test_weighted_average_combines_multiple_devices(
    client, db_session, test_restaurant, level3_device, level5_device
):
    """level3 (weight=1) scores 2; level5 (weight=3) scores 5.
    Expected app_rating = (2*1 + 5*3) / (1 + 3) = 17/4 = 4.25."""
    r1 = await _rate(client, level3_device, test_restaurant, 2)
    assert r1.status_code == 201, r1.text
    r2 = await _rate(client, level5_device, test_restaurant, 5)
    assert r2.status_code == 201, r2.text

    body = r2.json()
    assert body["restaurant_updated"]["rating_count"] == 2
    assert body["restaurant_updated"]["app_rating"] == 4.25


async def test_rating_awards_2_points_and_logs_history(
    client, db_session, test_restaurant, level3_device
):
    # Baseline points (400, seeded).
    before = (
        await db_session.execute(
            text("SELECT points FROM devices WHERE device_id = :d"),
            {"d": level3_device},
        )
    ).scalar_one()

    resp = await _rate(client, level3_device, test_restaurant, 5)
    assert resp.status_code == 201

    after = (
        await db_session.execute(
            text("SELECT points FROM devices WHERE device_id = :d"),
            {"d": level3_device},
        )
    ).scalar_one()
    assert after - before == 2

    history = (
        await db_session.execute(
            text(
                """
                SELECT action, points FROM point_history
                WHERE device_id = :d ORDER BY created_at ASC
                """
            ),
            {"d": level3_device},
        )
    ).all()
    assert ("rating", 2) in [(h.action, h.points) for h in history]
