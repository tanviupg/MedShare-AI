from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models import CommonUseCategory, DonationReviewDecision, DonationStatus, InventoryStatus
from pydantic import Field
from decimal import Decimal


class InventorySourceDonation(BaseModel):
    id: UUID
    donor_id: UUID
    status: DonationStatus
    created_at: datetime


class InventoryReviewInfo(BaseModel):
    decision: DonationReviewDecision
    reason: str | None
    reviewed_at: datetime
    pharmacist_id: UUID


class InventoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    donation_id: UUID
    pharmacist_id: UUID
    medicine_name: str
    strength: str | None
    dosage_form: str | None
    manufacturer: str | None
    common_use_category: CommonUseCategory
    prescription_required: bool
    public_id: UUID
    batch_number: str | None
    expiry_date: date
    quantity_available: int
    original_quantity: int
    original_price: Decimal | None
    discount_percentage: Decimal | None
    patient_price: Decimal | None
    unit: str
    status: InventoryStatus
    created_at: datetime
    updated_at: datetime
    source_donation: InventorySourceDonation
    review: InventoryReviewInfo


class PrescriptionRequirementUpdate(BaseModel):
    common_use_category: CommonUseCategory


class InventoryPricingUpdate(BaseModel):
    original_price: Decimal | None = Field(..., ge=0, max_digits=12, decimal_places=2)
    discount_percentage: Decimal | None = Field(..., ge=0, le=100, max_digits=5, decimal_places=2)
