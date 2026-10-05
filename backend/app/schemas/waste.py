from datetime import datetime, date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.waste import WasteReason, WasteStatus


class WasteCreate(BaseModel):
    reason: WasteReason
    quantity: int = Field(gt=0)
    notes: str | None = Field(default=None, max_length=2000)


class WasteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    inventory_id: UUID | None
    donation_id: UUID | None
    pharmacist_id: UUID
    reason: WasteReason
    quantity: int
    status: WasteStatus
    notes: str | None
    disposal_reference: str
    created_at: datetime
    collected_at: datetime | None
    collected_by: UUID | None
    handoff_reference: str | None
    disposed_at: datetime | None
    disposed_by: UUID | None
    disposal_notes: str | None
    medicine_name: str | None = None
    strength: str | None = None
    unit: str | None = None


class WasteEvent(BaseModel):
    reference: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class ExpiryInventoryResponse(BaseModel):
    id: UUID
    medicine_name: str
    strength: str | None
    quantity_available: int
    unit: str
    expiry_date: date
    status: str
    days_remaining: int
