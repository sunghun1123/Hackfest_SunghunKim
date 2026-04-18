"""Integration tests for the Gemini routers.

Gemini itself is stubbed via `app.dependency_overrides[get_gemini_service]`
so these tests are hermetic — no network, no API key. The /recommend test
still hits the real dev DB (for nearby-menu lookup) through the shared
fixtures.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest_asyncio
from sqlalchemy import text

from app.routers.gemini import get_gemini_service
from app.schemas.gemini_responses import (
    ParsedMenuItem,
    ParsedMenuResponse,
    Recommendation,
    RecommendResponse,
)
from app.services.rate_limit import photo_parse_limiter


# ---------------------------------------------------------------------------
# Fakes + fixtures
# ---------------------------------------------------------------------------

class FakeGeminiService:
    """Drop-in stand-in for GeminiService. Tests configure responses and can
    inspect `calls` to verify what the router passed in."""

    def __init__(
        self,
        parse_photo_response: ParsedMenuResponse | None = None,
        recommend_response: RecommendResponse | None = None,
    ) -> None:
        self.parse_photo_response = parse_photo_response or ParsedMenuResponse(
            items=[], warnings=[]
        )
        self.recommend_response = recommend_response or RecommendResponse(
            recommendations=[]
        )
        self.calls: list[dict[str, Any]] = []

    async def parse_photo(self, image_bytes: bytes, mime_type: str = "image/jpeg"):
        self.calls.append(
            {"method": "parse_photo", "n_bytes": len(image_bytes), "mime": mime_type}
        )
        return self.parse_photo_response

    async def recommend(
        self, query: str, menus, lat: float | None = None, lng: float | None = None
    ):
        self.calls.append(
            {
                "method": "recommend",
                "query": query,
                "n_candidates": len(menus),
                "candidate_ids": [m["id"] for m in menus],
            }
        )
        return self.recommend_response


@pytest_asyncio.fixture
async def fake_gemini(client):
    """Install a FakeGeminiService into the FastAPI dep graph and reset the
    rate limiter so each test starts clean."""
    from app.main import app

    fake = FakeGeminiService()
    app.dependency_overrides[get_gemini_service] = lambda: fake
    photo_parse_limiter.reset()
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_gemini_service, None)
        photo_parse_limiter.reset()


# ---------------------------------------------------------------------------
# /parse-menu-image
# ---------------------------------------------------------------------------

async def test_parse_menu_image_missing_device_id_returns_401(client, fake_gemini):
    resp = await client.post(
        "/parse-menu-image",
        files={"image": ("x.jpg", b"\xff\xd8\xff\xe0 fake jpeg", "image/jpeg")},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"]["code"] == "DEVICE_ID_REQUIRED"
    # Gemini must NOT be called if auth failed.
    assert fake_gemini.calls == []


async def test_parse_menu_image_happy_path(client, fake_gemini):
    fake_gemini.parse_photo_response = ParsedMenuResponse(
        items=[
            ParsedMenuItem(
                name="Hummus pita",
                description="with tahini",
                price_cents=450,
                category="mediterranean",
                confidence=0.95,
            ),
            ParsedMenuItem(
                name="Falafel wrap",
                price_cents=699,
                confidence=0.88,
            ),
        ],
        warnings=[],
    )
    resp = await client.post(
        "/parse-menu-image",
        headers={"X-Device-Id": f"dev-{uuid.uuid4().hex[:8]}"},
        files={"image": ("menu.jpg", b"\xff\xd8\xff\xe0 menu bytes", "image/jpeg")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["items"][0]["name"] == "Hummus pita"
    assert body["items"][0]["price_cents"] == 450
    assert body["warnings"] == []
    # Gemini got the bytes + mime plumbed through.
    assert fake_gemini.calls == [
        {
            "method": "parse_photo",
            "n_bytes": len(b"\xff\xd8\xff\xe0 menu bytes"),
            "mime": "image/jpeg",
        }
    ]


async def test_parse_menu_image_rate_limit_after_5_calls(client, fake_gemini):
    device = f"dev-{uuid.uuid4().hex[:8]}"
    headers = {"X-Device-Id": device}
    payload = {"image": ("m.jpg", b"\xff\xd8\xff\xe0...", "image/jpeg")}
    # First 5 calls within the minute succeed.
    for i in range(5):
        r = await client.post("/parse-menu-image", headers=headers, files=payload)
        assert r.status_code == 200, f"call {i + 1} failed: {r.text}"
    # 6th is rate-limited.
    r6 = await client.post("/parse-menu-image", headers=headers, files=payload)
    assert r6.status_code == 429
    assert r6.json()["detail"]["error"]["code"] == "RATE_LIMITED"
    # A different device is unaffected (per-device window).
    other_headers = {"X-Device-Id": f"dev-{uuid.uuid4().hex[:8]}"}
    r_other = await client.post(
        "/parse-menu-image", headers=other_headers, files=payload
    )
    assert r_other.status_code == 200


async def test_parse_menu_image_empty_items_passes_through(client, fake_gemini):
    fake_gemini.parse_photo_response = ParsedMenuResponse(
        items=[], warnings=["unreadable"]
    )
    resp = await client.post(
        "/parse-menu-image",
        headers={"X-Device-Id": f"dev-{uuid.uuid4().hex[:8]}"},
        files={"image": ("blurry.jpg", b"\xff\xd8 blur", "image/jpeg")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert "unreadable" in body["warnings"]


# ---------------------------------------------------------------------------
# /recommend
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def recommend_setup(db_session, test_restaurant):
    """Seed two menu_items inside `test_restaurant` so /recommend has real
    candidates. Returns (menu_id_a, menu_id_b) — both in the same restaurant
    so we can reliably exercise the enrichment path."""
    rows = (
        await db_session.execute(
            text(
                """
                INSERT INTO menu_items
                    (restaurant_id, name, price_cents, source, verification_status)
                VALUES
                    (:rid, 'Lentil soup', 450, 'seed', 'human_verified'),
                    (:rid, 'Falafel wrap', 699, 'seed', 'ai_parsed')
                RETURNING id, name
                """
            ),
            {"rid": test_restaurant},
        )
    ).all()
    await db_session.commit()
    return {r.name: r.id for r in rows}


async def test_recommend_happy_path_enriches_from_db(
    client, fake_gemini, recommend_setup, test_restaurant
):
    soup_id = recommend_setup["Lentil soup"]
    fake_gemini.recommend_response = RecommendResponse(
        recommendations=[
            Recommendation(menu_item_id=str(soup_id), reason="warm and cheap"),
        ]
    )
    resp = await client.post(
        "/recommend",
        json={
            "lat": 42.96,
            "lng": -85.66,
            "query": "warm soup under $5",
            "max_results": 5,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["recommendations"]) == 1
    r0 = body["recommendations"][0]
    assert r0["menu_item_id"] == str(soup_id)
    assert r0["restaurant_id"] == str(test_restaurant)
    assert r0["restaurant_name"] == "TestResto"
    assert r0["menu_name"] == "Lentil soup"
    assert r0["price_cents"] == 450
    assert r0["verification_status"] == "human_verified"
    assert r0["reason"] == "warm and cheap"
    assert r0["distance_m"] >= 0


async def test_recommend_empty_area_returns_empty(client, fake_gemini):
    # Antarctica — no GR restaurants here.
    resp = await client.post(
        "/recommend",
        json={"lat": -75.0, "lng": 0.0, "query": "anything", "max_results": 5},
    )
    assert resp.status_code == 200
    assert resp.json()["recommendations"] == []
    # Gemini should be skipped entirely when there are no candidates.
    assert fake_gemini.calls == []


async def test_recommend_drops_hallucinated_ids(
    client, fake_gemini, recommend_setup
):
    soup_id = recommend_setup["Lentil soup"]
    hallucinated = str(uuid.uuid4())
    fake_gemini.recommend_response = RecommendResponse(
        recommendations=[
            Recommendation(menu_item_id=str(soup_id), reason="real match"),
            Recommendation(menu_item_id=hallucinated, reason="fake id"),
        ]
    )
    resp = await client.post(
        "/recommend",
        json={"lat": 42.96, "lng": -85.66, "query": "soup", "max_results": 5},
    )
    assert resp.status_code == 200
    recs = resp.json()["recommendations"]
    # Only the real ID survives; GeminiService filters the whitelist first,
    # and the enrichment step is a second safety net.
    assert [r["menu_item_id"] for r in recs] == [str(soup_id)]
