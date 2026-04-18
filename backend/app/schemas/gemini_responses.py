"""Pydantic models for validating Gemini JSON responses.

`response_mime_type='application/json'` gives us JSON, but the field names and
types can still drift between calls. These models are the second line of
defense — they reject anything that doesn't match our contract so the rest of
the backend can trust the shape.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ParsedMenuItem(BaseModel):
    # Gemini occasionally adds fields we don't ask for; ignore instead of reject.
    model_config = ConfigDict(extra="ignore")

    name: str
    description: str | None = None
    price_cents: int = Field(ge=1, le=1500)  # $0.01 ~ $15 (app scope)
    category: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("name")
    @classmethod
    def _name_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("empty name")
        return stripped


class ParsedMenuResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[ParsedMenuItem] = Field(default_factory=list)
    restaurant_name_detected: str | None = None
    warnings: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    menu_item_id: str  # UUID string from the input whitelist
    reason: str = Field(max_length=120)


class RecommendResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    recommendations: list[Recommendation] = Field(default_factory=list)
