import enum
import uuid
from datetime import date, datetime

from decimal import Decimal
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.db.base import Base


class InventoryStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    RESERVED = "RESERVED"
    EXPIRED = "EXPIRED"
    DEPLETED = "DEPLETED"
    REMOVED = "REMOVED"


class CommonUseCategory(str, enum.Enum):
    COLD = "COLD"
    COUGH = "COUGH"
    FLU = "FLU"
    FEVER = "FEVER"
    PAIN = "PAIN"
    ALLERGY = "ALLERGY"
    OTHER = "OTHER"
    UNCLASSIFIED = "UNCLASSIFIED"


DIRECT_REQUEST_CATEGORIES = {
    CommonUseCategory.COLD,
    CommonUseCategory.COUGH,
    CommonUseCategory.FLU,
    CommonUseCategory.FEVER,
}


def prescription_required_for(category: CommonUseCategory) -> bool:
    return category not in DIRECT_REQUEST_CATEGORIES


class Inventory(Base):
    __tablename__ = "inventory"
    __table_args__ = (
        CheckConstraint("quantity_available >= 0", name="ck_inventory_quantity_nonnegative"),
        CheckConstraint("original_quantity > 0", name="ck_inventory_original_quantity_positive"),
        CheckConstraint("quantity_available <= original_quantity", name="ck_inventory_quantity_lte_original"),
        CheckConstraint("(quantity_available = 0 AND status = 'DEPLETED') OR (quantity_available > 0 AND status <> 'DEPLETED')", name="ck_inventory_zero_quantity_depleted"),
        UniqueConstraint("donation_id", name="uq_inventory_donation_id"),
        CheckConstraint("original_price IS NULL OR original_price >= 0", name="ck_inventory_original_price_nonnegative"),
        CheckConstraint("discount_percentage IS NULL OR (discount_percentage >= 0 AND discount_percentage <= 100)", name="ck_inventory_discount_range"),
        CheckConstraint("patient_price IS NULL OR patient_price >= 0", name="ck_inventory_patient_price_nonnegative"),
        CheckConstraint(
            "prescription_required = (common_use_category NOT IN ('COLD', 'COUGH', 'FLU', 'FEVER'))",
            name="ck_inventory_category_prescription_rule",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    donation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("donations.id", ondelete="RESTRICT"), nullable=False)
    pharmacist_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    medicine_name: Mapped[str] = mapped_column(String(200), nullable=False)
    strength: Mapped[str | None] = mapped_column(String(100))
    dosage_form: Mapped[str | None] = mapped_column(String(100))
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    common_use_category: Mapped[CommonUseCategory] = mapped_column(
        String(32), nullable=False, default=CommonUseCategory.UNCLASSIFIED, server_default="UNCLASSIFIED"
    )
    prescription_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    public_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    batch_number: Mapped[str | None] = mapped_column(String(100))
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity_available: Mapped[int] = mapped_column(Integer, nullable=False)
    original_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    discount_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    patient_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[InventoryStatus] = mapped_column(Enum(InventoryStatus, name="inventory_status"), nullable=False, default=InventoryStatus.AVAILABLE, server_default="AVAILABLE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    @validates("quantity_available")
    def sync_depleted_status(self, _key: str, quantity: int) -> int:
        if quantity == 0:
            self.status = InventoryStatus.DEPLETED
        elif getattr(self, "status", None) == InventoryStatus.DEPLETED:
            self.status = InventoryStatus.AVAILABLE
        return quantity
