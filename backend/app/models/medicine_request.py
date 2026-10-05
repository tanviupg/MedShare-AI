import enum
import uuid
from datetime import datetime

from decimal import Decimal
from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Integer, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MedicineRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    FULFILLED = "FULFILLED"


class MedicineRequest(Base):
    __tablename__ = "medicine_requests"
    __table_args__ = (CheckConstraint("requested_quantity > 0", name="ck_medicine_request_quantity_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    inventory_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("inventory.id", ondelete="RESTRICT"), nullable=False, index=True)
    requested_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    pickup_address: Mapped[str | None] = mapped_column(String(500))
    inventory_reserved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    status: Mapped[MedicineRequestStatus] = mapped_column(Enum(MedicineRequestStatus, name="medicine_request_status"), nullable=False, default=MedicineRequestStatus.PENDING, server_default="PENDING", index=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pickup_code: Mapped[str | None] = mapped_column(String(9), unique=True, index=True)
    price_original_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    discount_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    patient_price_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
