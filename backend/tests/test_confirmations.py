"""Integration tests for POST /confirmations."""

from __future__ import annotations

import uuid

from sqlalchemy import text


async def _confirm(
    client, device_id, menu_item_id, is_agreement=True, reported_price=None
):
    body: dict = {
        "menu_item_id": str(menu_item_id),
        "is_agreement": is_agreement,
    }
    if reported_price is not None:
        body["reported_price"] = reported_price
    return await client.post(
        "/confirmations",
        headers={"X-Device-Id": device_id},
        json=body,
    )


async def test_missing_device_id_returns_401(client, test_menu_item):
    resp = await client.post(
        "/confirmations",
        json={"menu_item_id": str(test_menu_item), "is_agreement": True},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"]["code"] == "DEVICE_ID_REQUIRED"


async def test_unknown_menu_item_returns_404(client, test_device):
    resp = await _confirm(client, test_device, uuid.uuid4(), True)
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "MENU_ITEM_NOT_FOUND"


async def test_agreement_bumps_weight_and_awards_points(
    client, db_session, test_menu_item, test_device
):
    resp = await _confirm(client, test_device, test_menu_item, True)
    assert resp.status_code == 201, resp.text
    body = resp.json()

    assert body["points_awarded"] == 3
    assert body["user_total_points"] == 3
    mi = body["menu_item_updated"]
    assert mi["confirmation_weight"] == 1
    assert mi["confirmation_count"] == 1
    # Still ai_parsed — one weight-1 confirmation is below the threshold.
    assert mi["verification_status"] == "ai_parsed"

    # point_history was written with action=confirm.
    history = (
        await db_session.execute(
            text(
                "SELECT action, points FROM point_history "
                "WHERE device_id = :d ORDER BY created_at ASC"
            ),
            {"d": test_device},
        )
    ).all()
    assert [(h.action, h.points) for h in history] == [("confirm", 3)]


async def test_duplicate_confirmation_returns_409(
    client, test_menu_item, test_device
):
    first = await _confirm(client, test_device, test_menu_item, True)
    assert first.status_code == 201

    second = await _confirm(client, test_device, test_menu_item, True)
    assert second.status_code == 409
    assert second.json()["detail"]["error"]["code"] == "ALREADY_CONFIRMED"


async def test_agreement_triggers_human_verified_when_weight_reaches_five(
    client, db_session, test_menu_item, test_device
):
    """Seed the device at Expert level (weight=3 at points >= 1000) so one
    confirmation bumps weight from 3 to... wait, we need weight 5+ to flip.
    Easier: seed weight directly via points >= 2500 (Veteran, weight=5)."""
    await db_session.execute(
        text("INSERT INTO devices (device_id, points) VALUES (:d, 2500)"),
        {"d": test_device},
    )
    await db_session.commit()

    resp = await _confirm(client, test_device, test_menu_item, True)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    mi = body["menu_item_updated"]
    assert mi["confirmation_weight"] == 5
    assert mi["confirmation_count"] == 1
    # Trigger flipped the status.
    assert mi["verification_status"] == "human_verified"


async def test_weight_applied_snapshots_at_time_of_confirmation(
    client, db_session, test_menu_item, test_device
):
    """Confirmations.weight_applied must freeze at the level_weight in
    effect when the row was inserted — subsequent level-ups must not
    retroactively change the stored weight."""
    # Start the device as Newbie (weight=1).
    await _confirm(client, test_device, test_menu_item, True)

    stored_weight = (
        await db_session.execute(
            text(
                "SELECT weight_applied FROM confirmations "
                "WHERE device_id = :d"
            ),
            {"d": test_device},
        )
    ).scalar_one()
    assert stored_weight == 1

    # Promote device way past the Expert threshold — weight should now be 5
    # on the device row, but the historical confirmation row must be frozen.
    await db_session.execute(
        text("UPDATE devices SET points = 3000 WHERE device_id = :d"),
        {"d": test_device},
    )
    await db_session.commit()

    current_weight = (
        await db_session.execute(
            text("SELECT level_weight FROM devices WHERE device_id = :d"),
            {"d": test_device},
        )
    ).scalar_one()
    assert current_weight == 5

    historical = (
        await db_session.execute(
            text(
                "SELECT weight_applied FROM confirmations "
                "WHERE device_id = :d"
            ),
            {"d": test_device},
        )
    ).scalar_one()
    assert historical == 1  # unchanged — snapshot preserved


async def test_disagreement_with_reported_price_creates_new_row(
    client, db_session, test_menu_item, test_device, test_restaurant
):
    resp = await _confirm(client, test_device, test_menu_item, False, reported_price=900)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["menu_item_updated"]["verification_status"] == "disputed"

    # There must now be exactly two menu_items for the restaurant: the
    # original (disputed) + the reported_price row (ai_parsed, user_manual).
    rows = (
        await db_session.execute(
            text(
                """
                SELECT price_cents, verification_status, source
                FROM menu_items
                WHERE restaurant_id = :rid AND is_active = TRUE
                ORDER BY price_cents ASC
                """
            ),
            {"rid": test_restaurant},
        )
    ).all()
    assert len(rows) == 2
    # Original: 700, now disputed.
    assert (rows[0].price_cents, rows[0].verification_status, rows[0].source) == (
        700,
        "disputed",
        "seed",
    )
    # New user-reported row: 900, ai_parsed, user_manual source.
    assert (rows[1].price_cents, rows[1].verification_status, rows[1].source) == (
        900,
        "ai_parsed",
        "user_manual",
    )


async def test_disagreement_without_reported_price_only_disputes_original(
    client, db_session, test_menu_item, test_device, test_restaurant
):
    resp = await _confirm(client, test_device, test_menu_item, False)
    assert resp.status_code == 201, resp.text
    assert resp.json()["menu_item_updated"]["verification_status"] == "disputed"

    count = (
        await db_session.execute(
            text(
                "SELECT COUNT(*)::int AS n FROM menu_items "
                "WHERE restaurant_id = :rid AND is_active = TRUE"
            ),
            {"rid": test_restaurant},
        )
    ).scalar_one()
    assert count == 1  # no new row created
