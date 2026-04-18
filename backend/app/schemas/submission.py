"""Request/response models for POST /submissions."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SubmissionSource = Literal[
    "gemini_photo", "gemini_web", "user_manual", "seed", "places_api"
]


class SubmissionCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    restaurant_id: UUID
    menu_name: str = Field(min_length=1, max_length=255)
    price_cents: int = Field(ge=1, le=1500)
    photo_url: str | None = None
    gemini_parsed: dict[str, Any] | None = None
    source: SubmissionSource = "gemini_photo"


class SubmissionResponse(BaseModel):
    id: UUID
    menu_item_id: UUID
    status: str
    points_awarded: int
    is_first_submission: bool
    bonus_message: str | None = None
    user_total_points: int
    user_level: int
    level_up: bool
