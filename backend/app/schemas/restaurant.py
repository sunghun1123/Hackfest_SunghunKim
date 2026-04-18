"""Pydantic request/response models for the restaurants router."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Tier = Literal["survive", "cost_effective", "luxury"]
VerificationStatus = Literal[
    "ai_parsed", "human_verified", "disputed", "needs_verification"
]
MenuStatus = Literal["populated_verified", "populated_ai", "empty"]


class CheapestMenu(BaseModel):
    id: UUID
    name: str
    price_cents: int
    tier: Tier
    verification_status: VerificationStatus


class NearbyRestaurant(BaseModel):
    id: UUID
    name: str
    category: str | None = None
    lat: float
    lng: float
    distance_m: int
    google_rating: float | None = None
    app_rating: float | None = None
    menu_status: MenuStatus
    cheapest_menu: CheapestMenu | None = None


class NearbyResponse(BaseModel):
    restaurants: list[NearbyRestaurant]
    count: int


class MenuItemOut(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    price_cents: int
    photo_url: str | None = None
    verification_status: VerificationStatus
    confirmation_count: int
    source: str
    last_verified_at: datetime | None = None


class MenuByTier(BaseModel):
    survive: list[MenuItemOut] = Field(default_factory=list)
    cost_effective: list[MenuItemOut] = Field(default_factory=list)
    luxury: list[MenuItemOut] = Field(default_factory=list)


class RestaurantDetail(BaseModel):
    id: UUID
    name: str
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    lat: float
    lng: float
    google_rating: float | None = None
    app_rating: float | None = None
    rating_count: int = 0
    hours: dict | None = None
    menu: MenuByTier
