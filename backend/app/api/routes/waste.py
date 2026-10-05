from datetime import date, datetime, timedelta, timezone
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.dependencies import require_role
from app.core.config import get_settings
from app.db.database import get_db
from app.models import Donation, DonationReview, DonationStatus, Inventory, InventoryStatus, User, UserRole, WasteRecord, WasteReason, WasteStatus
from app.schemas.waste import ExpiryInventoryResponse, WasteCreate, WasteEvent, WasteResponse
from app.models import NotificationType
from app.services.notifications import notify

router = APIRouter(prefix="/pharmacist", tags=["pharmacist expiry and waste"])


def expire_inventory_records(db: Session, today: date | None = None) -> int:
    """Synchronize expiry status while retaining inventory and quantity history."""
    today = today or date.today()
    changed_rows = db.scalars(select(Inventory).where(
        Inventory.expiry_date < today,
        Inventory.status.in_([InventoryStatus.AVAILABLE, InventoryStatus.RESERVED]),
    ).with_for_update()).all()
    for item in changed_rows:
        item.status = InventoryStatus.EXPIRED
        notify(db, item.pharmacist_id, NotificationType.MEDICINE_EXPIRED, "Medicine expired", f"{item.medicine_name} has passed its expiry date.", "inventory", item.id)
    soon = db.scalars(select(Inventory).where(
        Inventory.expiry_date >= today, Inventory.expiry_date <= today + timedelta(days=get_settings().expiry_warning_days),
        Inventory.status == InventoryStatus.AVAILABLE, Inventory.quantity_available > 0).with_for_update()).all()
    for item in soon:
        notify(db, item.pharmacist_id, NotificationType.MEDICINE_EXPIRING_SOON, "Medicine expiring soon", f"{item.medicine_name} has stock approaching its expiry date.", "inventory", item.id)
    changed = len(changed_rows)
    db.commit()
    return changed


def _waste_payload(db: Session, row: WasteRecord) -> dict:
    source = db.get(Inventory, row.inventory_id) if row.inventory_id else db.get(Donation, row.donation_id)
    return {**{c.name: getattr(row, c.name) for c in WasteRecord.__table__.columns},
            "medicine_name": source.medicine_name if source else None,
            "strength": source.strength if source else None,
            "unit": source.unit if source else None}


def _reference() -> str:
    return f"MW-{secrets.token_hex(3).upper()}"


def _new_record(**kwargs) -> WasteRecord:
    return WasteRecord(disposal_reference=_reference(), status=WasteStatus.DISPOSAL_PENDING, **kwargs)


def _inventory_lists(db: Session, pharmacist: User, expiring: bool):
    today = date.today()
    stmt = select(Inventory).where(Inventory.pharmacist_id == pharmacist.id, Inventory.quantity_available > 0)
    if expiring:
        stmt = stmt.where(Inventory.expiry_date > today, Inventory.expiry_date <= today + timedelta(days=get_settings().expiry_warning_days), Inventory.status == InventoryStatus.AVAILABLE)
    else:
        stmt = stmt.where(Inventory.expiry_date < today, Inventory.status == InventoryStatus.EXPIRED)
    items = db.scalars(stmt.order_by(Inventory.expiry_date)).all()
    return [ExpiryInventoryResponse(id=i.id, medicine_name=i.medicine_name, strength=i.strength,
        quantity_available=i.quantity_available, unit=i.unit, expiry_date=i.expiry_date,
        status=i.status.value, days_remaining=(i.expiry_date-today).days) for i in items]


@router.get("/inventory/expiring", response_model=list[ExpiryInventoryResponse])
def expiring_inventory(db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    return _inventory_lists(db, pharmacist, True)


@router.get("/inventory/expired", response_model=list[ExpiryInventoryResponse])
def expired_inventory(db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    expire_inventory_records(db)
    return _inventory_lists(db, pharmacist, False)


@router.post("/inventory/{inventory_id}/waste", response_model=WasteResponse, status_code=201)
def move_inventory_to_waste(inventory_id: UUID, body: WasteCreate, db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    try:
        item = db.scalar(select(Inventory).where(Inventory.id == inventory_id).with_for_update())
        if item is None or item.pharmacist_id != pharmacist.id:
            raise HTTPException(status_code=404, detail="Inventory record not found")
        today = date.today()
        if item.expiry_date < today and item.status in (InventoryStatus.AVAILABLE, InventoryStatus.RESERVED):
            item.status = InventoryStatus.EXPIRED
        if item.status in (InventoryStatus.DEPLETED, InventoryStatus.REMOVED) or item.quantity_available <= 0:
            raise HTTPException(status_code=409, detail="Inventory has no eligible quantity")
        if body.reason == WasteReason.EXPIRED and not (item.expiry_date < today or item.status == InventoryStatus.EXPIRED):
            raise HTTPException(status_code=409, detail="Only expired inventory can be recorded as expired waste")
        if body.quantity > item.quantity_available:
            raise HTTPException(status_code=409, detail="Waste quantity exceeds unreserved available quantity")
        item.quantity_available -= body.quantity
        row = _new_record(inventory_id=item.id, pharmacist_id=pharmacist.id, reason=body.reason, quantity=body.quantity, notes=body.notes)
        db.add(row)
        db.flush()
        notify(db, pharmacist.id, NotificationType.WASTE_DISPOSAL_PENDING, "Waste disposal pending", "A waste record is awaiting disposal.", "waste_record", row.id)
        db.commit()
        db.refresh(row)
        return _waste_payload(db, row)
    except Exception:
        db.rollback()
        raise


@router.get("/donations/rejected-for-disposal")
def rejected_for_disposal(db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    recorded = select(func.coalesce(func.sum(WasteRecord.quantity), 0)).where(WasteRecord.donation_id == Donation.id).scalar_subquery()
    donations = db.scalars(select(Donation).join(DonationReview, DonationReview.donation_id == Donation.id).where(
        Donation.status == DonationStatus.REJECTED, DonationReview.pharmacist_id == pharmacist.id,
        recorded < Donation.quantity
    ).order_by(Donation.updated_at.desc())).all()
    return [{"id": d.id, "medicine_name": d.medicine_name, "strength": d.strength,
             "quantity": d.quantity - (db.scalar(select(func.coalesce(func.sum(WasteRecord.quantity), 0)).where(WasteRecord.donation_id == d.id)) or 0),
             "unit": d.unit, "created_at": d.created_at} for d in donations]


@router.post("/donations/{donation_id}/waste", response_model=WasteResponse, status_code=201)
def rejected_donation_to_waste(donation_id: UUID, body: WasteCreate, db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    donation = db.scalar(select(Donation).where(Donation.id == donation_id).with_for_update())
    review = db.scalar(select(DonationReview).where(DonationReview.donation_id == donation_id))
    if donation is None or donation.status != DonationStatus.REJECTED or review is None or review.pharmacist_id != pharmacist.id:
        raise HTTPException(status_code=404, detail="Rejected donation not found")
    if body.reason != WasteReason.REJECTED_DONATION:
        raise HTTPException(status_code=422, detail="Rejected donations must use REJECTED_DONATION reason")
    if donation.quantity is None:
        raise HTTPException(status_code=409, detail="A pharmacist-verified donation quantity is required before waste can be recorded")
    already_recorded = db.scalar(select(func.coalesce(func.sum(WasteRecord.quantity), 0)).where(WasteRecord.donation_id == donation.id)) or 0
    if body.quantity > donation.quantity - already_recorded:
        raise HTTPException(status_code=409, detail="Waste quantity exceeds unrecorded donation quantity")
    row = _new_record(donation_id=donation.id, pharmacist_id=pharmacist.id, reason=body.reason, quantity=body.quantity, notes=body.notes)
    db.add(row)
    db.flush()
    notify(db, pharmacist.id, NotificationType.WASTE_DISPOSAL_PENDING, "Waste disposal pending", "A waste record is awaiting disposal.", "waste_record", row.id)
    db.commit()
    db.refresh(row)
    return _waste_payload(db, row)


@router.get("/waste", response_model=list[WasteResponse])
def list_waste(db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    rows = db.scalars(select(WasteRecord).where(WasteRecord.pharmacist_id == pharmacist.id).order_by(WasteRecord.created_at.desc())).all()
    return [_waste_payload(db, row) for row in rows]


@router.get("/waste/{waste_id}", response_model=WasteResponse)
def get_waste(waste_id: UUID, db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    row = db.scalar(select(WasteRecord).where(WasteRecord.id == waste_id, WasteRecord.pharmacist_id == pharmacist.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Waste record not found")
    return _waste_payload(db, row)


def _transition(waste_id: UUID, target: WasteStatus, db: Session, pharmacist: User, event: WasteEvent):
    row = db.scalar(select(WasteRecord).where(WasteRecord.id == waste_id).with_for_update())
    if row is None or row.pharmacist_id != pharmacist.id:
        raise HTTPException(status_code=404, detail="Waste record not found")
    expected = WasteStatus.DISPOSAL_PENDING if target == WasteStatus.COLLECTED else WasteStatus.COLLECTED
    if row.status != expected:
        raise HTTPException(status_code=409, detail=f"Cannot transition {row.status.value} to {target.value}")
    now = datetime.now(timezone.utc)
    row.status = target
    if target == WasteStatus.COLLECTED:
        row.collected_at, row.collected_by = now, pharmacist.id
        row.handoff_reference = event.reference
    else:
        row.disposed_at, row.disposed_by = now, pharmacist.id
        row.disposal_notes = event.notes
        if event.reference:
            row.handoff_reference = row.handoff_reference or event.reference
    db.commit()
    db.refresh(row)
    return _waste_payload(db, row)


@router.post("/waste/{waste_id}/collect", response_model=WasteResponse)
def collect_waste(waste_id: UUID, event: WasteEvent = WasteEvent(), db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    return _transition(waste_id, WasteStatus.COLLECTED, db, pharmacist, event)


@router.post("/waste/{waste_id}/dispose", response_model=WasteResponse)
def dispose_waste(waste_id: UUID, event: WasteEvent = WasteEvent(), db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    return _transition(waste_id, WasteStatus.DISPOSED, db, pharmacist, event)
