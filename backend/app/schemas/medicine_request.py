from datetime import date, datetime
from uuid import UUID
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import CommonUseCategory, MedicineRequestStatus, PaymentStatus


class MedicineRequestCreate(BaseModel):
    medicine_id: UUID
    requested_quantity: int = Field(gt=0, le=1000000)
    pickup_address: str = Field(min_length=1, max_length=500)

    @field_validator("pickup_address")
    @classmethod
    def pickup_address_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Pickup address is required")
        return value


class MedicineRequestDecision(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class MedicineRequestPatientResponse(BaseModel):
    id: UUID
    medicine_name: str
    common_use_category: CommonUseCategory
    clinic_name: str
    requested_quantity: int
    unit: str
    pickup_address: str | None
    status: MedicineRequestStatus
    rejection_reason: str | None
    created_at: datetime
    reviewed_at: datetime | None
    fulfilled_at: datetime | None
    pickup_code: str | None
    prescription_required: bool | None
    prescription_status: str | None
    prescription_rejection_reason: str | None
    price_original_snapshot: Decimal | None
    discount_snapshot: Decimal | None
    patient_price_snapshot: Decimal | None
    payment_status: PaymentStatus | None = None


class MedicineRequestPharmacistResponse(MedicineRequestPatientResponse):
    patient_name: str
    patient_city: str | None
    patient_phone: str | None
    inventory_available: int
    expiry_date: date


class MedicineRequestCreateResponse(MedicineRequestPatientResponse):
    pass
