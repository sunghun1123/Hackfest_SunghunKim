"""Round-trip tests for the restaurant response schemas — makes sure the
API.md contract stays in sync with what we actually serialize."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.restaurant import (
    CheapestMenu,
    MenuByTier,
    MenuItemOut,
    NearbyResponse,
    NearbyRestaurant,
    RestaurantDetail,
)


def _sample_cheapest() -> CheapestMenu:
    return CheapestMenu(
        id=uuid4(),
        name="8-corner slice",
        price_cents=450,
        tier="survive",
        verification_status="human_verified",
    )


def test_nearby_response_populated_shape():
    resp = NearbyResponse(
        restaurants=[
            NearbyRestaurant(
                id=uuid4(),
                name="Jet's Pizza",
                category="pizza",
                lat=42.9634,
                lng=-85.6681,
                distance_m=320,
                google_rating=4.3,
                app_rating=4.5,
                menu_status="populated_verified",
                cheapest_menu=_sample_cheapest(),
            )
        ],
        count=1,
    )
    payload = resp.model_dump(mode="json")
    assert payload["count"] == 1
    r0 = payload["restaurants"][0]
    assert r0["menu_status"] == "populated_verified"
    assert r0["cheapest_menu"]["price_cents"] == 450


def test_nearby_response_empty_restaurant_has_null_cheapest():
    r = NearbyRestaurant(
        id=uuid4(),
        name="Corner Deli",
        category="sandwich",
        lat=42.95,
        lng=-85.65,
        distance_m=450,
        menu_status="empty",
        cheapest_menu=None,
    )
    payload = r.model_dump(mode="json")
    assert payload["menu_status"] == "empty"
    assert payload["cheapest_menu"] is None


def test_restaurant_detail_groups_menu_by_tier():
    detail = RestaurantDetail(
        id=uuid4(),
        name="Pita House",
        address="456 Division Ave",
        phone=None,
        website=None,
        lat=42.95,
        lng=-85.66,
        google_rating=4.5,
        app_rating=4.2,
        rating_count=23,
        hours={"monday": "11:00-21:00"},
        menu=MenuByTier(
            survive=[
                MenuItemOut(
                    id=uuid4(),
                    name="Falafel 2p",
                    description="two pieces",
                    price_cents=399,
                    photo_url=None,
                    verification_status="human_verified",
                    confirmation_count=5,
                    source="gemini_web",
                    last_verified_at=None,
                )
            ],
            cost_effective=[],
            luxury=[],
        ),
    )
    p = detail.model_dump(mode="json")
    assert list(p["menu"].keys()) == ["survive", "cost_effective", "luxury"]
    assert len(p["menu"]["survive"]) == 1
    assert p["menu"]["cost_effective"] == []


def test_invalid_tier_rejected():
    with pytest.raises(ValidationError):
        CheapestMenu(
            id=uuid4(),
            name="x",
            price_cents=100,
            tier="bogus",  # type: ignore[arg-type]
            verification_status="ai_parsed",
        )


def test_invalid_verification_status_rejected():
    with pytest.raises(ValidationError):
        CheapestMenu(
            id=uuid4(),
            name="x",
            price_cents=100,
            tier="survive",
            verification_status="weird",  # type: ignore[arg-type]
        )
