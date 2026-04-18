"""Integration tests for GET /me."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import text

from app.routers.me import _today_pt


async def test_missing_device_id_returns_401(client):
    resp = await client.get("/me")
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"]["code"] == "DEVICE_ID_REQUIRED"


async def test_new_device_auto_created_with_daily_bonus(
    client, db_session, test_device
):
    resp = await client.get("/me", headers={"X-Device-Id": test_device})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["device_id"] == test_device
    # First visit: daily bonus granted → 1 point, streak 1, level still 1.
    assert body["points"] == 1
    assert body["level"] == 1
    assert body["level_name"] == "Newbie"
    assert body["level_weight"] == 1
    assert body["next_level_points"] == 50
    assert body["daily_streak"] == 1
    assert body["can_rate_restaurants"] is False
    assert body["submission_count"] == 0
    assert body["confirmation_count"] == 0
    assert body["display_name"] is None

    # DB actually recorded the bonus.
    last_bonus = (
        await db_session.execute(
            text("SELECT last_daily_bonus FROM devices WHERE device_id = :d"),
            {"d": test_device},
        )
    ).scalar_one()
    assert last_bonus == _today_pt()


async def test_second_call_same_day_skips_bonus(
    client, db_session, test_device
):
    first = await client.get("/me", headers={"X-Device-Id": test_device})
    second = await client.get("/me", headers={"X-Device-Id": test_device})
    assert first.status_code == 200
    assert second.status_code == 200
    # Points unchanged on the 2nd call.
    assert first.json()["points"] == second.json()["points"] == 1
    assert second.json()["daily_streak"] == 1


async def test_streak_increments_when_yesterday_claimed(
    client, db_session, test_device
):
    """Manually seed yesterday's bonus, then call /me → streak goes to 2."""
    yesterday = _today_pt() - timedelta(days=1)
    await db_session.execute(
        text(
            """
            INSERT INTO devices (device_id, points, last_daily_bonus, daily_streak)
            VALUES (:d, 0, :y, 1)
            """
        ),
        {"d": test_device, "y": yesterday},
    )
    await db_session.commit()

    resp = await client.get("/me", headers={"X-Device-Id": test_device})
    assert resp.status_code == 200
    body = resp.json()
    assert body["daily_streak"] == 2
    assert body["points"] == 1  # yesterday had 0 + today's +1


async def test_streak_resets_after_a_gap(client, db_session, test_device):
    three_days_ago = _today_pt() - timedelta(days=3)
    await db_session.execute(
        text(
            """
            INSERT INTO devices (device_id, points, last_daily_bonus, daily_streak)
            VALUES (:d, 10, :d3, 5)
            """
        ),
        {"d": test_device, "d3": three_days_ago},
    )
    await db_session.commit()

    resp = await client.get("/me", headers={"X-Device-Id": test_device})
    assert resp.status_code == 200
    assert resp.json()["daily_streak"] == 1  # reset, not +1


@pytest.mark.parametrize(
    "points,expected_level,expected_name,expected_next",
    [
        (0,      1, "Newbie",   50),
        (100,    2, "Scout",    150),
        (300,    3, "Regular",  400),
        (800,    4, "Explorer", 1000),
        (2000,   5, "Expert",   2500),
        (5000,   7, "Veteran",  10_000),
        (15000, 10, "Legend",   -1),
    ],
)
async def test_level_name_and_next_points_mapping(
    client, db_session, test_device, points, expected_level, expected_name, expected_next
):
    # Pre-seed the device and claim today's bonus so /me skips the +1 and
    # the assertions see the exact `points` value we set.
    await db_session.execute(
        text(
            """
            INSERT INTO devices (device_id, points, last_daily_bonus, daily_streak)
            VALUES (:d, :p, :today, 1)
            """
        ),
        {"d": test_device, "p": points, "today": _today_pt()},
    )
    await db_session.commit()

    resp = await client.get("/me", headers={"X-Device-Id": test_device})
    assert resp.status_code == 200
    body = resp.json()
    assert body["points"] == points
    assert body["level"] == expected_level
    assert body["level_name"] == expected_name
    assert body["next_level_points"] == expected_next
    assert body["can_rate_restaurants"] is (expected_level >= 3)


async def test_legend_next_level_is_minus_one(
    client, db_session, test_device
):
    await db_session.execute(
        text(
            """
            INSERT INTO devices (device_id, points, last_daily_bonus)
            VALUES (:d, 20000, :t)
            """
        ),
        {"d": test_device, "t": _today_pt()},
    )
    await db_session.commit()
    resp = await client.get("/me", headers={"X-Device-Id": test_device})
    assert resp.status_code == 200
    assert resp.json()["next_level_points"] == -1
