"""Request/response models for POST /reports."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ReportReason = Literal[
    "wrong_price", "not_on_menu", "spam", "inappropriate", "other"
]


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    menu_item_id: UUID
    reason: ReportReason
    comment: str | None = Field(default=None, max_length=1000)


class ReportResponse(BaseModel):
    id: UUID
    status: str
    menu_item_auto_disputed: bool
