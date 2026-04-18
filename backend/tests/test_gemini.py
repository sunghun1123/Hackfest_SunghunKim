"""Unit tests for the Gemini service layer.

We mock the google-genai client so these tests are hermetic — no network,
no API key required.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.schemas.gemini_responses import ParsedMenuResponse, RecommendResponse
from app.services.gemini import GeminiService


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModels:
    """Stand-in for `genai.Client().models`. Records the last call and returns
    whatever text was configured by the test."""

    def __init__(self, response_text: str | Exception) -> None:
        self._response = response_text
        self.last_call: dict[str, Any] | None = None

    def generate_content(self, *, model, config, contents, **kwargs):
        self.last_call = {"model": model, "config": config, "contents": contents}
        if isinstance(self._response, Exception):
            raise self._response
        return _FakeResponse(self._response)


def _fake_client(response_text: str | Exception) -> tuple[Any, _FakeModels]:
    models = _FakeModels(response_text)
    client = SimpleNamespace(models=models)
    return client, models


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# ParsedMenuResponse — happy path
# ---------------------------------------------------------------------------

def test_parse_web_menu_happy_path():
    payload = {
        "items": [
            {
                "name": "Hummus pita",
                "description": "with tahini",
                "price_cents": 450,
                "category": "mediterranean",
                "confidence": 0.95,
            },
            {
                "name": "Falafel wrap",
                "description": None,
                "price_cents": 699,
                "category": "mediterranean",
                "confidence": 0.88,
            },
        ],
        "restaurant_name_detected": "Pita House",
        "warnings": [],
    }
    client, models = _fake_client(json.dumps(payload))
    svc = GeminiService(client=client)

    result = _run(svc.parse_web_menu("<html>some menu</html>"))

    assert isinstance(result, ParsedMenuResponse)
    assert len(result.items) == 2
    assert result.items[0].name == "Hummus pita"
    assert result.items[0].price_cents == 450
    assert result.restaurant_name_detected == "Pita House"
    # Sanity: system instruction + JSON mime were plumbed through.
    assert models.last_call is not None
    assert models.last_call["config"].response_mime_type == "application/json"


# ---------------------------------------------------------------------------
# Malformed JSON / non-JSON prose → safe default
# ---------------------------------------------------------------------------

def test_parse_web_menu_malformed_json_returns_safe_default():
    client, _ = _fake_client("sorry, I can't help with that.")
    svc = GeminiService(client=client)

    result = _run(svc.parse_web_menu("..."))

    assert result.items == []
    assert "parse_error" in result.warnings


def test_parse_photo_api_error_returns_safe_default():
    client, _ = _fake_client(RuntimeError("boom: simulated 500"))
    svc = GeminiService(client=client)

    result = _run(svc.parse_photo(b"\x89PNG..."))

    assert isinstance(result, ParsedMenuResponse)
    assert result.items == []
    assert "api_error" in result.warnings


# ---------------------------------------------------------------------------
# Out-of-range items → salvage the rest
# ---------------------------------------------------------------------------

def test_parse_web_menu_filters_out_of_range_items():
    payload = {
        "items": [
            # Keep: $4.50 is in-range
            {
                "name": "Cheap taco",
                "price_cents": 450,
                "confidence": 0.9,
            },
            # Drop: $20 exceeds app scope
            {
                "name": "Steak dinner",
                "price_cents": 2000,
                "confidence": 0.95,
            },
            # Drop: zero price
            {
                "name": "Water",
                "price_cents": 0,
                "confidence": 0.5,
            },
            # Drop: blank name
            {
                "name": "   ",
                "price_cents": 500,
                "confidence": 0.8,
            },
            # Keep: $7 in range
            {
                "name": "Burrito",
                "price_cents": 700,
                "confidence": 0.92,
            },
        ],
        "warnings": [],
    }
    client, _ = _fake_client(json.dumps(payload))
    svc = GeminiService(client=client)

    result = _run(svc.parse_web_menu("..."))

    assert [it.name for it in result.items] == ["Cheap taco", "Burrito"]
    assert any(w.startswith("dropped_") for w in result.warnings)


def test_parse_web_menu_all_items_invalid_returns_empty_with_warning():
    payload = {
        "items": [
            {"name": "overpriced", "price_cents": 9999, "confidence": 0.5},
        ],
        "warnings": [],
    }
    client, _ = _fake_client(json.dumps(payload))
    svc = GeminiService(client=client)

    result = _run(svc.parse_web_menu("..."))

    assert result.items == []
    assert any(w.startswith("dropped_") for w in result.warnings)


def test_parse_web_menu_preserves_existing_warnings():
    payload = {
        "items": [],
        "warnings": ["not_a_menu"],
    }
    client, _ = _fake_client(json.dumps(payload))
    svc = GeminiService(client=client)

    result = _run(svc.parse_web_menu("..."))

    assert result.items == []
    assert "not_a_menu" in result.warnings


# ---------------------------------------------------------------------------
# Recommend whitelist
# ---------------------------------------------------------------------------

def test_recommend_whitelist_filters_invalid_ids():
    menus = [
        {"id": "11111111-1111-1111-1111-111111111111", "name": "Lentil soup"},
        {"id": "22222222-2222-2222-2222-222222222222", "name": "Falafel"},
    ]
    payload = {
        "recommendations": [
            {
                "menu_item_id": "11111111-1111-1111-1111-111111111111",
                "reason": "warm and cheap",
            },
            # Gemini hallucinated a fake UUID — must be dropped.
            {
                "menu_item_id": "99999999-9999-9999-9999-999999999999",
                "reason": "not in the whitelist",
            },
            {
                "menu_item_id": "22222222-2222-2222-2222-222222222222",
                "reason": "also good",
            },
        ],
    }
    client, _ = _fake_client(json.dumps(payload))
    svc = GeminiService(client=client)

    result = _run(svc.recommend("warm cheap food", menus, lat=42.96, lng=-85.66))

    assert isinstance(result, RecommendResponse)
    ids = [r.menu_item_id for r in result.recommendations]
    assert ids == [
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    ]


def test_recommend_malformed_json_returns_empty_recommendations():
    client, _ = _fake_client("no json here, sorry")
    svc = GeminiService(client=client)

    result = _run(svc.recommend("hi", [{"id": "x"}]))

    assert result.recommendations == []


def test_parse_pdf_menu_is_deferred():
    client, _ = _fake_client("{}")
    svc = GeminiService(client=client)

    with pytest.raises(NotImplementedError):
        _run(svc.parse_pdf_menu(b"%PDF-1.4..."))
