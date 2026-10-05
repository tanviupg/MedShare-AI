from datetime import date, datetime, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import CommonUseCategory, DonationReviewDecision, DonationStatus


class DonationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pickup_address: str = Field(min_length=1, max_length=500)
    donor_expiry_date: date | None = None

    @field_validator("pickup_address")
    @classmethod
    def non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Pickup address cannot be blank")
        return value

    @field_validator("donor_expiry_date")
    @classmethod
    def expiry_not_past(cls, value: date | None) -> date | None:
        if value is None:
            return value
        if value < datetime.now(timezone.utc).date():
            raise ValueError("Expiry date must be today or later")
        return value


class DonationImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime
    download_url: str = ""


class DonationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    donor_id: UUID
    medicine_name: str | None
    strength: str | None
    dosage_form: str | None
    packaging_type: str | None
    manufacturer: str | None
    batch_number: str | None
    expiry_date: date | None
    donor_expiry_date: date | None
    pickup_address: str | None
    quantity: int | None
    unit: str | None
    details_confirmed: bool
    status: DonationStatus
    created_at: datetime
    updated_at: datetime
    images: list[DonationImageResponse] = []


class DonorDonationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: DonationStatus
    created_at: datetime


class DonationVerifiedDetails(BaseModel):
    medicine_name: str = Field(min_length=1, max_length=200)
    strength: str | None = Field(default=None, max_length=100)
    dosage_form: str | None = Field(default=None, max_length=100)
    packaging_type: str | None = Field(default=None, max_length=100)
    manufacturer: str | None = Field(default=None, max_length=200)
    batch_number: str | None = Field(default=None, max_length=100)
    expiry_date: date
    quantity: int = Field(gt=0, le=1000000)
    unit: str = Field(min_length=1, max_length=40)
    common_use_category: CommonUseCategory

    @field_validator("medicine_name", "unit")
    @classmethod
    def verified_values_non_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank")
        return value

    @field_validator("expiry_date")
    @classmethod
    def verified_expiry_not_past(cls, value: date) -> date:
        if value < datetime.now(timezone.utc).date():
            raise ValueError("Expiry date must be today or later")
        return value


class DonationReviewCreate(BaseModel):
    decision: DonationReviewDecision
    reason: str | None = Field(default=None, max_length=2000)
    physical_package_checked: bool = False
    verified_details: DonationVerifiedDetails | None = None

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def require_rejection_reason(self):
        if self.decision == DonationReviewDecision.REJECTED and not self.reason:
            raise ValueError("A reason is required to reject a donation")
        if self.decision == DonationReviewDecision.APPROVED and (
            not self.physical_package_checked or self.verified_details is None
        ):
            raise ValueError("Physically check the package and submit verified medicine details before approval")
        return self


class DonationReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    donation_id: UUID
    pharmacist_id: UUID
    decision: DonationReviewDecision
    reason: str | None
    physical_package_checked: bool | None
    verified_details: dict | None
    reviewed_at: datetime
