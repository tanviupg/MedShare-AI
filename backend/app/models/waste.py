import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WasteReason(str, enum.Enum):
    EXPIRED = "EXPIRED"
    REJECTED_DONATION = "REJECTED_DONATION"
    DAMAGED = "DAMAGED"


class WasteStatus(str, enum.Enum):
    DISPOSAL_PENDING = "DISPOSAL_PENDING"
    COLLECTED = "COLLECTED"
    DISPOSED = "DISPOSED"


class WasteRecord(Base):
    __tablename__ = "waste_records"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_waste_quantity_positive"),
        CheckConstraint("(inventory_id IS NOT NULL AND donation_id IS NULL) OR (inventory_id IS NULL AND donation_id IS NOT NULL)", name="ck_waste_single_source"),
        UniqueConstraint("disposal_reference", name="uq_waste_records_disposal_reference"),
        Index("ix_waste_records_disposal_reference", "disposal_reference"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inventory_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("inventory.id", ondelete="RESTRICT"), index=True)
    donation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("donations.id", ondelete="RESTRICT"), index=True)
    pharmacist_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    reason: Mapped[WasteReason] = mapped_column(Enum(WasteReason, name="waste_reason"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[WasteStatus] = mapped_column(Enum(WasteStatus, name="waste_status"), nullable=False, default=WasteStatus.DISPOSAL_PENDING, server_default="DISPOSAL_PENDING")
    notes: Mapped[str | None] = mapped_column(Text)
    disposal_reference: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    handoff_reference: Mapped[str | None] = mapped_column(String(120))
    disposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disposed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    disposal_notes: Mapped[str | None] = mapped_column(Text)
