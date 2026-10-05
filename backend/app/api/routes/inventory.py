from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.dependencies import require_role
from app.db.database import get_db
from app.models import Donation, DonationReview, Inventory, InventoryStatus, User, UserRole, prescription_required_for
from app.schemas.inventory import InventoryResponse, InventoryPricingUpdate, PrescriptionRequirementUpdate
from app.models import NotificationType
from app.services.notifications import notify
from datetime import timedelta
from app.core.config import get_settings
from app.services.pricing import calculate_patient_price

router = APIRouter(prefix="/inventory", tags=["inventory"])


def expire_old_inventory(db: Session, pharmacist_id: UUID) -> None:
    today = datetime.now(timezone.utc).date()
    rows = db.scalars(select(Inventory).where(
        Inventory.pharmacist_id == pharmacist_id,
        Inventory.expiry_date < today,
        Inventory.status.in_([InventoryStatus.AVAILABLE, InventoryStatus.RESERVED]),
    ).with_for_update()).all()
    for item in rows:
        item.status = InventoryStatus.EXPIRED
        notify(db, pharmacist_id, NotificationType.MEDICINE_EXPIRED, "Medicine expired", f"{item.medicine_name} has passed its expiry date.", "inventory", item.id)
    soon = db.scalars(select(Inventory).where(Inventory.pharmacist_id == pharmacist_id, Inventory.expiry_date >= today,
        Inventory.expiry_date <= today + timedelta(days=get_settings().expiry_warning_days), Inventory.status == InventoryStatus.AVAILABLE,
        Inventory.quantity_available > 0)).all()
    for item in soon:
        notify(db, pharmacist_id, NotificationType.MEDICINE_EXPIRING_SOON, "Medicine expiring soon", f"{item.medicine_name} has stock approaching its expiry date.", "inventory", item.id)
    db.commit()


def inventory_response(item: Inventory, db: Session) -> InventoryResponse:
    donation = db.get(Donation, item.donation_id)
    review = db.scalar(select(DonationReview).where(DonationReview.donation_id == item.donation_id))
    return InventoryResponse.model_validate({
        **{column.name: getattr(item, column.name) for column in Inventory.__table__.columns},
        "source_donation": {"id": donation.id, "donor_id": donation.donor_id, "status": donation.status, "created_at": donation.created_at},
        "review": {"decision": review.decision, "reason": review.reason, "reviewed_at": review.reviewed_at, "pharmacist_id": review.pharmacist_id},
    })


@router.get("", response_model=list[InventoryResponse])
def list_inventory(db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))) -> list[InventoryResponse]:
    expire_old_inventory(db, user.id)
    items = db.scalars(select(Inventory).where(Inventory.pharmacist_id == user.id).order_by(Inventory.created_at.desc())).all()
    return [inventory_response(item, db) for item in items]


@router.get("/{inventory_id}", response_model=InventoryResponse)
def get_inventory(inventory_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))) -> InventoryResponse:
    expire_old_inventory(db, user.id)
    item = db.scalar(select(Inventory).where(Inventory.id == inventory_id, Inventory.pharmacist_id == user.id))
    if item is None:
        raise HTTPException(status_code=404, detail="Inventory record not found")
    return inventory_response(item, db)


@router.patch("/{inventory_id}/common-use-category", response_model=InventoryResponse)
def set_common_use_category(inventory_id: UUID, body: PrescriptionRequirementUpdate, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))) -> InventoryResponse:
    item = db.scalar(select(Inventory).where(Inventory.id == inventory_id, Inventory.pharmacist_id == user.id).with_for_update())
    if item is None:
        raise HTTPException(status_code=404, detail="Inventory record not found")
    item.common_use_category = body.common_use_category
    item.prescription_required = prescription_required_for(body.common_use_category)
    db.commit()
    db.refresh(item)
    return inventory_response(item, db)


@router.patch("/{inventory_id}/pricing", response_model=InventoryResponse)
def set_inventory_pricing(inventory_id: UUID, body: InventoryPricingUpdate, db: Session = Depends(get_db), user: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))) -> InventoryResponse:
    item = db.scalar(select(Inventory).where(Inventory.id == inventory_id, Inventory.pharmacist_id == user.id).with_for_update())
    if item is None:
        raise HTTPException(status_code=404, detail="Inventory record not found")
    if (body.original_price is None) != (body.discount_percentage is None):
        raise HTTPException(status_code=422, detail="Original price and discount must both be set or both be empty")
    item.original_price = body.original_price
    item.discount_percentage = body.discount_percentage
    item.patient_price = None if body.original_price is None else calculate_patient_price(body.original_price, body.discount_percentage)
    db.commit()
    db.refresh(item)
    return inventory_response(item, db)
