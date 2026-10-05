import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Checkout(Base):
    __tablename__ = "checkouts"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_checkouts_amount_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("medicine_requests.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True)
    patient_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR", server_default="INR")
    payment_status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus, name="payment_status"), nullable=False, default=PaymentStatus.PENDING, server_default="PENDING")
    payment_method: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
