from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import ClinicVerificationStatus


class ClinicVerificationRejection(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        reason = value.strip()
        if not reason:
            raise ValueError("A rejection reason is required")
        return reason


class PendingClinicVerification(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_name: str
    address: str
    city: str
    license_number: str | None
    contact_number: str | None
    created_at: datetime


class ClinicVerificationResult(BaseModel):
    verification_status: ClinicVerificationStatus
    verification_decided_at: datetime
    verification_rejection_reason: str | None
