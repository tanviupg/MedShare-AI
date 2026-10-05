import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DispensingRecord(Base):
    __tablename__ = "dispensing_records"
    __table_args__ = (CheckConstraint("quantity_dispensed > 0", name="ck_dispensing_quantity_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("medicine_requests.id", ondelete="RESTRICT"), nullable=False, unique=True, index=True)
    inventory_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("inventory.id", ondelete="RESTRICT"), nullable=False, index=True)
    pharmacist_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    quantity_dispensed: Mapped[int] = mapped_column(Integer, nullable=False)
    dispensed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
