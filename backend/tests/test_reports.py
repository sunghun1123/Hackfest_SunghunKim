"""Integration tests for POST /reports."""

from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy import text

from app.services.rate_limit import reports_limiter


@pytest_asyncio.fixture(autouse=True)
def _reset_reports_limiter():
    """Reports limiter is module-global; clear it between tests so quotas
    from one test don't leak into another."""
    reports_limiter.reset()
    yield
    reports_limiter.reset()


async def _report(client, device_id, menu_item_id, reason="wrong_price", comment=None):
    body = {"menu_item_id": str(menu_item_id), "reason": reason}
    if comment is not None:
        body["comment"] = comment
    return await client.post(
        "/reports",
        headers={"X-Device-Id": device_id},
        json=body,
    )


@pytest_asyncio.fixture
async def three_devices(db_session):
    """Three fresh devices for the auto-dispute test (3 reports = trigger)."""
    ids = [f"test-dev-{uuid.uuid4().hex[:12]}" for _ in range(3)]
    try:
        yield ids
    finally:
        for d in ids:
            for stmt in (
                "DELETE FROM reports WHERE device_id = :d",
                "DELETE FROM devices WHERE device_id = :d",
            ):
                await db_session.execute(text(stmt), {"d": d})
        await db_session.commit()


async def test_missing_device_id_returns_401(client, test_menu_item):
    resp = await client.post(
        "/reports",
        json={"menu_item_id": str(test_menu_item), "reason": "wrong_price"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"]["code"] == "DEVICE_ID_REQUIRED"


async def test_unknown_menu_item_returns_404(client, test_device):
    resp = await _report(client, test_device, uuid.uuid4())
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"]["code"] == "MENU_ITEM_NOT_FOUND"


async def test_happy_path_creates_pending_report(
    client, test_menu_item, test_device
):
    resp = await _report(
        client, test_device, test_menu_item, "wrong_price", "it's $12 not $7"
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["menu_item_auto_disputed"] is False


async def test_duplicate_report_returns_409(
    client, test_menu_item, test_device
):
    first = await _report(client, test_device, test_menu_item)
    assert first.status_code == 201
    second = await _report(client, test_device, test_menu_item, "spam")
    assert second.status_code == 409
    assert second.json()["detail"]["error"]["code"] == "ALREADY_REPORTED"


async def test_third_report_auto_disputes_menu(
    client, db_session, test_menu_item, three_devices
):
    r1 = await _report(client, three_devices[0], test_menu_item)
    r2 = await _report(client, three_devices[1], test_menu_item)
    r3 = await _report(client, three_devices[2], test_menu_item)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r3.status_code == 201

    # First two don't flip the menu.
    assert r1.json()["menu_item_auto_disputed"] is False
    assert r2.json()["menu_item_auto_disputed"] is False
    # Third one crosses the threshold via the auto_dispute trigger.
    assert r3.json()["menu_item_auto_disputed"] is True

    status = (
        await db_session.execute(
            text("SELECT verification_status FROM menu_items WHERE id = :id"),
            {"id": test_menu_item},
        )
    ).scalar_one()
    assert status == "disputed"


async def test_rate_limit_after_10_reports_per_day(
    client, db_session, test_restaurant, test_device
):
    """Seed 10 distinct menu_items and let one device report all of them.
    The 11th should be 429 even against a brand-new menu_item."""
    menu_ids: list = []
    for i in range(11):
        row = (
            await db_session.execute(
                text(
                    """
                    INSERT INTO menu_items
                        (restaurant_id, name, price_cents, source, verification_status)
                    VALUES (:rid, :name, 500, 'seed', 'ai_parsed')
                    RETURNING id
                    """
                ),
                {"rid": test_restaurant, "name": f"rl-item-{i}"},
            )
        ).one()
        menu_ids.append(row.id)
    await db_session.commit()

    for i, mid in enumerate(menu_ids[:10]):
        resp = await _report(client, test_device, mid)
        assert resp.status_code == 201, f"call {i + 1} failed: {resp.text}"

    over = await _report(client, test_device, menu_ids[10])
    assert over.status_code == 429
    assert over.json()["detail"]["error"]["code"] == "RATE_LIMITED"
