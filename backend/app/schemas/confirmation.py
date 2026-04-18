"""Request/response models for POST /confirmations."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConfirmationCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    menu_item_id: UUID
    is_agreement: bool
    reported_price: int | None = Field(default=None, ge=1, le=1500)

    @model_validator(mode="after")
    def _reported_price_only_on_disagree(self) -> "ConfirmationCreate":
        if self.is_agreement and self.reported_price is not None:
            raise ValueError(
                "reported_price only applies when is_agreement is false"
            )
        return self


class MenuItemUpdated(BaseModel):
    id: UUID
    verification_status: str
    confirmation_weight: int
    confirmation_count: int


class ConfirmationResponse(BaseModel):
    id: UUID
    menu_item_updated: MenuItemUpdated
    points_awarded: int
    user_total_points: int
