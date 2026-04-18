"""Request/response models for POST /ratings."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RatingCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    restaurant_id: UUID
    score: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class RestaurantRatingUpdated(BaseModel):
    id: UUID
    app_rating: float | None
    rating_count: int


class RatingResponse(BaseModel):
    id: UUID
    restaurant_updated: RestaurantRatingUpdated
    points_awarded: int
