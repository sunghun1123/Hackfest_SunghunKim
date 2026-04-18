"""HTTP request/response models for POST /recommend.

Kept separate from `gemini_responses` because those describe the raw LLM
payload; this module describes the enriched API contract we hand to clients.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RecommendRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    query: str = Field(min_length=1, max_length=500)
    max_results: int = Field(default=5, ge=1, le=20)


class RecommendedMenu(BaseModel):
    restaurant_id: UUID
    restaurant_name: str
    menu_item_id: UUID
    menu_name: str
    price_cents: int
    distance_m: int
    verification_status: str
    reason: str


class RecommendResponsePayload(BaseModel):
    recommendations: list[RecommendedMenu] = Field(default_factory=list)
