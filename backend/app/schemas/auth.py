from datetime import datetime
import enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import ClinicVerificationStatus, UserRole


class PublicSignupRole(str, enum.Enum):
    DONOR = "DONOR"
    PATIENT = "PATIENT"
    CLINIC_PHARMACIST = "CLINIC_PHARMACIST"


class ClinicSignup(BaseModel):
    clinic_name: str = Field(min_length=1, max_length=160)
    address: str = Field(min_length=1, max_length=500)
    city: str = Field(min_length=1, max_length=120)
    license_number: str | None = Field(default=None, max_length=100)
    contact_number: str | None = Field(default=None, max_length=40)


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    role: PublicSignupRole
    phone: str | None = Field(default=None, max_length=40)
    city: str | None = Field(default=None, max_length=120)
    clinic_profile: ClinicSignup | None = None

    @field_validator("password")
    @classmethod
    def password_byte_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be no longer than 72 UTF-8 bytes")
        return value

    @model_validator(mode="after")
    def clinic_fields_match_role(self):
        if self.role == PublicSignupRole.CLINIC_PHARMACIST and self.clinic_profile is None:
            raise ValueError("Clinic profile is required for CLINIC_PHARMACIST accounts")
        if self.role != PublicSignupRole.CLINIC_PHARMACIST and self.clinic_profile is not None:
            raise ValueError("Clinic profile is only allowed for CLINIC_PHARMACIST accounts")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class ClinicProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    clinic_name: str
    address: str
    city: str
    license_number: str | None
    contact_number: str | None
    verification_status: ClinicVerificationStatus
    verification_decided_at: datetime | None
    verification_rejection_reason: str | None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    email: EmailStr
    role: UserRole
    phone: str | None
    city: str | None
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    clinic_profile: ClinicProfileResponse | None = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
