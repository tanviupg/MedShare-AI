import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserRole(str, enum.Enum):
    DONOR = "DONOR"
    PATIENT = "PATIENT"
    CLINIC_PHARMACIST = "CLINIC_PHARMACIST"
    ADMIN = "ADMIN"


class ClinicVerificationStatus(str, enum.Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40))
    city: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    clinic_profile: Mapped["ClinicProfile | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="ClinicProfile.user_id",
        uselist=False,
    )


class ClinicProfile(Base):
    __tablename__ = "clinic_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    clinic_name: Mapped[str] = mapped_column(String(160), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    city: Mapped[str] = mapped_column(String(120), nullable=False)
    license_number: Mapped[str | None] = mapped_column(String(100))
    contact_number: Mapped[str | None] = mapped_column(String(40))
    verification_status: Mapped[ClinicVerificationStatus] = mapped_column(Enum(ClinicVerificationStatus, name="clinic_verification_status"), nullable=False, default=ClinicVerificationStatus.PENDING, server_default="PENDING")
    verification_reviewer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    verification_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_rejection_reason: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    user: Mapped[User] = relationship(back_populates="clinic_profile", foreign_keys=[user_id])
