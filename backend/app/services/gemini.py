"""Gemini service layer.

Three use cases (see docs/GEMINI_PROMPTS.md):
  1. Web menu parsing (HTML text → structured items) — batch pipeline
  2. Photo menu parsing (image bytes → structured items) — live user submit
  3. Natural-language recommendation (query + candidate menus → ranked subset)

All outputs go through Pydantic validation with safe defaults. If Gemini
returns malformed JSON, the call fails, or the payload fails schema
validation, we return an empty response with a warning rather than crash the
request — the app must keep working even when Gemini misbehaves.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.schemas.gemini_responses import (
    ParsedMenuItem,
    ParsedMenuResponse,
    Recommendation,
    RecommendResponse,
)

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-2.5-flash"

# ---------------------------------------------------------------------------
# Prompts (verbatim from docs/GEMINI_PROMPTS.md)
# ---------------------------------------------------------------------------

_WEB_MENU_SYSTEM = (
    "You are a menu data extractor. You receive HTML text content from a "
    "restaurant's menu page and must extract all menu items with prices.\n\n"
    "You MUST respond with valid JSON only. No prose, no markdown code fences."
)

_WEB_MENU_USER_TEMPLATE = """Below is HTML/text content from a restaurant's menu page.
Extract all food items with clearly stated prices.

Rules:
- Only include items priced $15.00 or less (our app scope).
- Skip drinks unless they're the main item (coffee/tea shops OK).
- Skip "market price" or "varies" items.
- For items with multiple sizes, create separate entries (e.g., "Pizza (small)", "Pizza (medium)").
- Translate prices to cents: $4.50 -> 450, $10 -> 1000.
- Categorize each item: burger, pizza, sandwich, pasta, salad, soup,
  mexican, asian, mediterranean, breakfast, dessert, drink, other.

Output schema:
{{
  "items": [
    {{
      "name": "string (clean item name)",
      "description": "string or null (short description if shown)",
      "price_cents": integer,
      "category": "string",
      "confidence": float (0.0 to 1.0)
    }}
  ],
  "restaurant_name_detected": "string or null",
  "warnings": ["string", ...]
}}

Content:
---
{html_text}
---"""

_PHOTO_SYSTEM = (
    "You are a menu parser specialized in reading restaurant menu photos taken "
    "with a phone camera. The images may be blurry, angled, or in varied "
    "lighting.\n\n"
    "Focus on accuracy over completeness - if you can't clearly read a price, "
    "skip that item rather than guessing.\n\n"
    "You MUST respond with valid JSON only."
)

_PHOTO_USER = """This is a photo of a restaurant menu board or menu card.

Extract all menu items where you can clearly read both the name AND the price.

Rules:
- Only include items priced $15 or less.
- Skip items where the price is unclear, smudged, or cut off.
- If a single item has multiple sizes/options listed (Small/Medium/Large),
  create separate entries.
- Translate prices to cents.
- Confidence should reflect how sure you are about reading the price correctly.

Output schema:
{
  "items": [
    {
      "name": "string",
      "description": "string or null",
      "price_cents": integer,
      "category": "string",
      "confidence": float (0.0 to 1.0)
    }
  ],
  "warnings": ["string", ...]
}

If the image is unreadable, return {"items": [], "warnings": ["unreadable"]}.
If the image does not appear to be a menu, return {"items": [], "warnings": ["not_a_menu"]}."""

_RECOMMEND_SYSTEM = (
    "You are a restaurant recommendation assistant for \"Broken Lunch GR\", "
    "an app that helps students and low-budget diners find cheap meals ($15 "
    "or less) in Grand Rapids, Michigan.\n\n"
    "You will be given:\n"
    "1. A user's natural language request (may be in Korean or English).\n"
    "2. A list of available menu items with restaurant, price, distance, "
    "verification status.\n\n"
    "Return the top 5 best matches as JSON. Reasoning must be concise (under "
    "80 chars) and in the same language as the user's query.\n\n"
    "Guidelines:\n"
    "- Match the intent of the query, not just keywords.\n"
    "  - \"warm food\" -> exclude salads, ice cream\n"
    "  - \"quick\" -> prefer closer restaurants\n"
    "  - \"healthy\" -> prefer salads, soups, grilled items\n"
    "  - \"cheap\" -> prefer sub-$7 items\n"
    "- Prefer verified items (verified=true) over AI-parsed ones.\n"
    "- Sort by relevance first, then price ascending.\n"
    "- If nothing matches well, return fewer than 5 items."
)

_RECOMMEND_USER_TEMPLATE = """User query: "{query}"
User location: ({lat}, {lng})

Available menus (JSON):
{menus_json}

Return this schema:
{{
  "recommendations": [
    {{
      "menu_item_id": "uuid from input (must match exactly)",
      "reason": "short explanation, under 80 chars, same language as query"
    }}
  ]
}}"""


# ---------------------------------------------------------------------------
# Safe-default + salvage helpers
# ---------------------------------------------------------------------------

def _safe_default(schema: type[BaseModel], warning: str = "parse_error") -> BaseModel:
    if schema is ParsedMenuResponse:
        return ParsedMenuResponse(items=[], warnings=[warning])
    if schema is RecommendResponse:
        return RecommendResponse(recommendations=[])
    raise ValueError(f"no safe default for {schema}")


def _salvage_parsed_menu(raw: dict[str, Any]) -> ParsedMenuResponse:
    """Keep items that pass schema, drop those that don't. Prevents one bad
    item from nuking an otherwise-good batch (common when a single price is
    out-of-range or a name is blank)."""
    raw_items = raw.get("items") or []
    good: list[ParsedMenuItem] = []
    dropped = 0
    for item in raw_items:
        try:
            good.append(ParsedMenuItem.model_validate(item))
        except ValidationError:
            dropped += 1
    warnings = list(raw.get("warnings") or [])
    if dropped:
        warnings.append(f"dropped_{dropped}_invalid_items")
    return ParsedMenuResponse(
        items=good,
        restaurant_name_detected=raw.get("restaurant_name_detected"),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class GeminiService:
    """Thin async wrapper around google-genai. Each method returns a validated
    Pydantic model; any upstream failure collapses to a safe default."""

    def __init__(self, client: Any = None, model_name: str = MODEL_NAME) -> None:
        self._client = client or genai.Client(api_key=settings.gemini_api_key)
        self._model_name = model_name

    async def _call_and_validate(
        self,
        contents: list,
        response_schema: type[BaseModel],
        system_instruction: str | None = None,
    ) -> BaseModel:
        config_kwargs: dict[str, Any] = {"response_mime_type": "application/json"}
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        config = types.GenerateContentConfig(**config_kwargs)

        # google-genai's generate_content is sync; run off the event loop.
        try:
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=self._model_name,
                config=config,
                contents=contents,
            )
        except Exception as e:  # network, auth, quota, etc.
            logger.warning("Gemini call failed: %s", e)
            return _safe_default(response_schema, warning="api_error")

        text = getattr(response, "text", None) or ""
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning("Gemini returned non-JSON (%s): %r", e, text[:200])
            return _safe_default(response_schema)

        try:
            return response_schema.model_validate(raw)
        except ValidationError as e:
            logger.warning("Gemini schema validation failed: %s", e)
            if response_schema is ParsedMenuResponse and isinstance(raw, dict):
                return _salvage_parsed_menu(raw)
            return _safe_default(response_schema)

    # -- Use Case 1-A: HTML web menu ----------------------------------------
    async def parse_web_menu(self, html_text: str) -> ParsedMenuResponse:
        user_prompt = _WEB_MENU_USER_TEMPLATE.format(html_text=html_text)
        result = await self._call_and_validate(
            contents=user_prompt,
            response_schema=ParsedMenuResponse,
            system_instruction=_WEB_MENU_SYSTEM,
        )
        return result  # type: ignore[return-value]

    # -- Use Case 1-B: PDF menu (Vision) ------------------------------------
    # Deferred per task spec — the batch pipeline (scripts/02_*) handles PDFs.
    # Leaving a stub so callers get a clear signal.
    async def parse_pdf_menu(self, pdf_bytes: bytes) -> ParsedMenuResponse:
        raise NotImplementedError(
            "PDF menu parsing lives in the batch pipeline (Task 1.4). "
            "The live API path uses parse_photo()."
        )

    # -- Use Case 2: user photo ---------------------------------------------
    async def parse_photo(
        self, image_bytes: bytes, mime_type: str = "image/jpeg"
    ) -> ParsedMenuResponse:
        contents = [
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            _PHOTO_USER,
        ]
        result = await self._call_and_validate(
            contents=contents,
            response_schema=ParsedMenuResponse,
            system_instruction=_PHOTO_SYSTEM,
        )
        return result  # type: ignore[return-value]

    # -- Use Case 3: recommendation -----------------------------------------
    async def recommend(
        self,
        query: str,
        menus: list[dict[str, Any]],
        lat: float | None = None,
        lng: float | None = None,
    ) -> RecommendResponse:
        user_prompt = _RECOMMEND_USER_TEMPLATE.format(
            query=query,
            lat=lat if lat is not None else "unknown",
            lng=lng if lng is not None else "unknown",
            menus_json=json.dumps(menus, ensure_ascii=False),
        )
        result: RecommendResponse = await self._call_and_validate(  # type: ignore[assignment]
            contents=user_prompt,
            response_schema=RecommendResponse,
            system_instruction=_RECOMMEND_SYSTEM,
        )
        # Whitelist: Gemini sometimes hallucinates IDs. Drop anything not
        # in the candidate set we supplied.
        valid_ids = {str(m["id"]) for m in menus if "id" in m}
        filtered: list[Recommendation] = [
            r for r in result.recommendations if r.menu_item_id in valid_ids
        ]
        return RecommendResponse(recommendations=filtered)
