import enum
import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DonationStatus(str, enum.Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class DonationReviewDecision(str, enum.Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Donation(Base):
    __tablename__ = "donations"
    __table_args__ = (CheckConstraint("quantity > 0", name="ck_donations_quantity_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    donor_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    medicine_name: Mapped[str | None] = mapped_column(String(200))
    strength: Mapped[str | None] = mapped_column(String(100))
    dosage_form: Mapped[str | None] = mapped_column(String(100))
    packaging_type: Mapped[str | None] = mapped_column(String(100))
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    batch_number: Mapped[str | None] = mapped_column(String(100))
    expiry_date: Mapped[date | None] = mapped_column(Date)
    donor_expiry_date: Mapped[date | None] = mapped_column(Date)
    pickup_address: Mapped[str | None] = mapped_column(String(500))
    quantity: Mapped[int | None] = mapped_column(Integer)
    unit: Mapped[str | None] = mapped_column(String(40))
    donor_notes: Mapped[str | None] = mapped_column(Text)
    details_confirmed: Mapped[bool] = mapped_column(default=True, server_default="true", nullable=False)
    status: Mapped[DonationStatus] = mapped_column(Enum(DonationStatus, name="donation_status"), nullable=False, default=DonationStatus.PENDING_REVIEW, server_default="PENDING_REVIEW")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    images: Mapped[list["DonationImage"]] = relationship(back_populates="donation", cascade="all, delete-orphan", order_by="DonationImage.created_at")


class DonationImage(Base):
    __tablename__ = "donation_images"
    __table_args__ = (CheckConstraint("size_bytes > 0", name="ck_donation_images_size_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    donation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("donations.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    donation: Mapped[Donation] = relationship(back_populates="images")


class DonationReview(Base):
    __tablename__ = "donation_reviews"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    donation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("donations.id", ondelete="RESTRICT"), unique=True, nullable=False, index=True)
    pharmacist_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    decision: Mapped[DonationReviewDecision] = mapped_column(Enum(DonationReviewDecision, name="donation_review_decision"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    physical_package_checked: Mapped[bool | None] = mapped_column(default=None)
    verified_details: Mapped[dict | None] = mapped_column(JSON)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ExtractionStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class MedicineExtraction(Base):
    __tablename__ = "medicine_extractions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    donation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("donations.id", ondelete="CASCADE"), nullable=False, index=True)
    image_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("donation_images.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[ExtractionStatus] = mapped_column(Enum(ExtractionStatus, name="extraction_status"), nullable=False)
    extracted_fields: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    confidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    provider_name: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_version: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
