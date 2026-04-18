"""Integration tests for POST /submissions.

These hit the FastAPI app via httpx.AsyncClient + ASGITransport (no uvicorn)
and the real Postgres. Each test creates its own restaurant + device via
fixtures in conftest.py, so parallel test runs / other sessions on the dev
DB do not collide.
"""

from __future__ import annotations

from sqlalchemy import text


async def _submit(client, device_id, restaurant_id, menu_name, price_cents, source="gemini_photo"):
    return await client.post(
        "/submissions",
        headers={"X-Device-Id": device_id},
        json={
            "restaurant_id": str(restaurant_id),
            "menu_name": menu_name,
            "price_cents": price_cents,
            "source": source,
        },
    )


async def test_missing_device_id_returns_401(client, test_restaurant):
    resp = await client.post(
        "/submissions",
        json={
            "restaurant_id": str(test_restaurant),
            "menu_name": "Tacos",
            "price_cents": 500,
        },
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["detail"]["error"]["code"] == "DEVICE_ID_REQUIRED"


async def test_first_submission_awards_bonus(
    client, db_session, test_restaurant, test_device
):
    resp = await _submit(client, test_device, test_restaurant, "Falafel wrap", 699)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["is_first_submission"] is True
    assert body["points_awarded"] == 15
    assert body["bonus_message"] == "🎉 First to register this restaurant! +5 bonus"
    assert body["user_total_points"] == 15
    assert body["user_level"] == 1
    assert body["level_up"] is False

    # Sanity: menu_item actually inserted, ai_parsed, active.
    mi = (
        await db_session.execute(
            text(
                "SELECT name, price_cents, verification_status, is_active, source "
                "FROM menu_items WHERE id = :id"
            ),
            {"id": body["menu_item_id"]},
        )
    ).one()
    assert mi.name == "Falafel wrap"
    assert mi.price_cents == 699
    assert mi.verification_status == "ai_parsed"
    assert mi.is_active is True
    assert mi.source == "gemini_photo"


async def test_second_submission_skips_bonus(
    client, test_restaurant, test_device
):
    first = await _submit(client, test_device, test_restaurant, "Item A", 500)
    assert first.status_code == 201
    assert first.json()["is_first_submission"] is True

    second = await _submit(client, test_device, test_restaurant, "Item B", 700)
    assert second.status_code == 201
    body = second.json()
    assert body["is_first_submission"] is False
    assert body["points_awarded"] == 10
    assert body["bonus_message"] is None
    # Points should accumulate: 15 + 10 = 25
    assert body["user_total_points"] == 25


async def test_similar_name_near_price_becomes_confirmation(
    client, db_session, test_restaurant, test_device
):
    """Within $1 → no new row, existing row's confirmation_weight bumped."""
    first = await _submit(client, test_device, test_restaurant, "Falafel Wrap", 700)
    assert first.status_code == 201
    mi_id = first.json()["menu_item_id"]

    # Different device (no unique-confirmation constraint on submissions),
    # near-duplicate name + same price.
    second = await _submit(
        client, test_device + "-b", test_restaurant, "falafel  wrap ", 720
    )
    assert second.status_code == 201
    body = second.json()
    # Same menu_item_id returned → confirmation path fired.
    assert body["menu_item_id"] == mi_id
    assert body["is_first_submission"] is False

    row = (
        await db_session.execute(
            text(
                "SELECT confirmation_weight, confirmation_count, verification_status "
                "FROM menu_items WHERE id = :id"
            ),
            {"id": mi_id},
        )
    ).one()
    assert row.confirmation_weight == 1  # Newbie level_weight
    assert row.confirmation_count == 1
    assert row.verification_status == "ai_parsed"

    # Cleanup the second device (first fixture only cleans test_device).
    await db_session.execute(
        text("DELETE FROM submissions WHERE device_id = :d"),
        {"d": test_device + "-b"},
    )
    await db_session.execute(
        text("DELETE FROM point_history WHERE device_id = :d"),
        {"d": test_device + "-b"},
    )
    await db_session.execute(
        text("DELETE FROM devices WHERE device_id = :d"),
        {"d": test_device + "-b"},
    )
    await db_session.commit()


async def test_similar_name_mid_price_diff_marks_both_disputed(
    client, db_session, test_restaurant, test_device
):
    """$1–$3 gap → new row inserted, both flipped to 'disputed'."""
    first = await _submit(client, test_device, test_restaurant, "Burrito", 600)
    assert first.status_code == 201
    old_id = first.json()["menu_item_id"]

    second = await _submit(
        client, test_device + "-c", test_restaurant, "BURRITO", 850
    )
    assert second.status_code == 201
    new_id = second.json()["menu_item_id"]
    assert new_id != old_id

    rows = (
        await db_session.execute(
            text(
                "SELECT id, verification_status FROM menu_items "
                "WHERE id IN (:a, :b)"
            ),
            {"a": old_id, "b": new_id},
        )
    ).all()
    statuses = {str(r.id): r.verification_status for r in rows}
    assert statuses[old_id] == "disputed"
    assert statuses[new_id] == "disputed"

    # Cleanup the spare device.
    for stmt in (
        "DELETE FROM submissions WHERE device_id = :d",
        "DELETE FROM point_history WHERE device_id = :d",
        "DELETE FROM devices WHERE device_id = :d",
    ):
        await db_session.execute(text(stmt), {"d": test_device + "-c"})
    await db_session.commit()


async def test_large_price_diff_creates_new_row(
    client, db_session, test_restaurant, test_device
):
    """> $3 gap → brand-new menu_item, no dispute on the old row."""
    first = await _submit(client, test_device, test_restaurant, "Pizza", 600)
    old_id = first.json()["menu_item_id"]

    second = await _submit(client, test_device + "-d", test_restaurant, "pizza", 1200)
    assert second.status_code == 201
    new_id = second.json()["menu_item_id"]
    assert new_id != old_id

    old_status = (
        await db_session.execute(
            text("SELECT verification_status FROM menu_items WHERE id = :id"),
            {"id": old_id},
        )
    ).scalar_one()
    assert old_status == "ai_parsed"  # untouched

    for stmt in (
        "DELETE FROM submissions WHERE device_id = :d",
        "DELETE FROM point_history WHERE device_id = :d",
        "DELETE FROM devices WHERE device_id = :d",
    ):
        await db_session.execute(text(stmt), {"d": test_device + "-d"})
    await db_session.commit()


async def test_point_history_logged(
    client, db_session, test_restaurant, test_device
):
    resp = await _submit(client, test_device, test_restaurant, "Nachos", 800)
    assert resp.status_code == 201
    submission_id = resp.json()["id"]

    rows = (
        await db_session.execute(
            text(
                "SELECT action, points, reference_id FROM point_history "
                "WHERE device_id = :d ORDER BY created_at ASC"
            ),
            {"d": test_device},
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].action == "submit_photo"
    assert rows[0].points == 15
    assert str(rows[0].reference_id) == submission_id


async def test_level_up_detection(
    client, db_session, test_restaurant, test_device
):
    """Seed device at 45 points (level 1), one +10 submission crosses to
    level 2 at 50. Response must flag level_up."""
    # Seed the device directly so we don't have to perform 5+ submissions.
    await db_session.execute(
        text("INSERT INTO devices (device_id, points) VALUES (:d, 45)"),
        {"d": test_device},
    )
    await db_session.commit()

    resp = await _submit(client, test_device, test_restaurant, "Donut", 300)
    assert resp.status_code == 201
    body = resp.json()
    # Submission earns +15 (first submission on this restaurant).
    assert body["user_total_points"] == 60
    assert body["user_level"] == 2
    assert body["level_up"] is True
