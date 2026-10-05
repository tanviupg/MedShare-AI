import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PrescriptionStatus(str, enum.Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Prescription(Base):
    """One immutable upload/review attempt for a medicine request."""
    __tablename__ = "prescriptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("medicine_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PrescriptionStatus] = mapped_column(Enum(PrescriptionStatus, name="prescription_status"), nullable=False, default=PrescriptionStatus.PENDING_REVIEW, server_default="PENDING_REVIEW")
    rejection_reason: Mapped[str | None] = mapped_column(String(1000))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
