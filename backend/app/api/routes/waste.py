from datetime import date, datetime, timedelta, timezone
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_role
from app.core.config import get_settings
from app.db.database import get_db
from app.models import ClinicProfile, ClinicVerificationStatus, Donation, DonationImage, DonationReview, DonationStatus, Inventory, InventoryStatus, User, UserRole, WasteRecord, WasteReason, WasteStatus
from app.schemas.waste import ExpiryInventoryResponse, RejectedDonationVerification, WasteCreate, WasteEvent, WasteResponse
from app.models import NotificationType
from app.services.notifications import notify
from app.services.business_time import business_today

router = APIRouter(prefix="/pharmacist", tags=["pharmacist expiry and waste"])


def expire_inventory_records(db: Session, pharmacist_id: UUID, today: date | None = None) -> int:
    """Synchronize expiry status while retaining inventory and quantity history."""
    today = today or business_today()
    changed_rows = db.scalars(select(Inventory).where(
        Inventory.pharmacist_id == pharmacist_id,
        Inventory.expiry_date < today,
        Inventory.status.in_([InventoryStatus.AVAILABLE, InventoryStatus.RESERVED]),
    ).with_for_update()).all()
    for item in changed_rows:
        item.status = InventoryStatus.EXPIRED
    changed = len(changed_rows)
    db.commit()
    return changed


def _waste_payload(db: Session, row: WasteRecord) -> dict:
    source = db.get(Inventory, row.inventory_id) if row.inventory_id else db.get(Donation, row.donation_id)
    return {**{c.name: getattr(row, c.name) for c in WasteRecord.__table__.columns},
            "medicine_name": source.medicine_name if source else None,
            "strength": source.strength if source else None,
            "unit": source.unit if source else None,
            "expiry_date": source.expiry_date if source else None}


def _reference() -> str:
    return f"MW-{secrets.token_hex(3).upper()}"


def _require_verified_clinic(db: Session, pharmacist: User) -> None:
    profile = db.scalar(select(ClinicProfile).where(ClinicProfile.user_id == pharmacist.id))
    if profile is None or profile.verification_status != ClinicVerificationStatus.VERIFIED:
        raise HTTPException(status_code=403, detail="A verified clinic is required to access inventory and waste records")


def _new_record(**kwargs) -> WasteRecord:
    return WasteRecord(disposal_reference=_reference(), status=WasteStatus.DISPOSAL_PENDING, **kwargs)


def _inventory_lists(db: Session, pharmacist: User, expiring: bool):
    today = business_today()
    stmt = select(Inventory).where(Inventory.pharmacist_id == pharmacist.id, Inventory.quantity_available > 0)
    if expiring:
        stmt = stmt.where(Inventory.expiry_date >= today, Inventory.expiry_date <= today + timedelta(days=get_settings().expiry_warning_days), Inventory.status == InventoryStatus.AVAILABLE)
    else:
        stmt = stmt.where(Inventory.expiry_date < today, Inventory.status == InventoryStatus.EXPIRED)
    items = db.scalars(stmt.order_by(Inventory.expiry_date)).all()
    return [ExpiryInventoryResponse(id=i.id, medicine_name=i.medicine_name, strength=i.strength,
        quantity_available=i.quantity_available, unit=i.unit, expiry_date=i.expiry_date,
        status=i.status.value, days_remaining=(i.expiry_date-today).days) for i in items]


@router.get("/inventory/expiring", response_model=list[ExpiryInventoryResponse])
def expiring_inventory(db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    _require_verified_clinic(db, pharmacist)
    return _inventory_lists(db, pharmacist, True)


@router.get("/inventory/expired", response_model=list[ExpiryInventoryResponse])
def expired_inventory(db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    _require_verified_clinic(db, pharmacist)
    expire_inventory_records(db, pharmacist.id)
    return _inventory_lists(db, pharmacist, False)


@router.post("/inventory/{inventory_id}/waste", response_model=WasteResponse, status_code=201)
def move_inventory_to_waste(inventory_id: UUID, body: WasteCreate, db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    _require_verified_clinic(db, pharmacist)
    try:
        item = db.scalar(select(Inventory).where(Inventory.id == inventory_id).with_for_update())
        if item is None or item.pharmacist_id != pharmacist.id:
            raise HTTPException(status_code=404, detail="Inventory record not found")
        today = business_today()
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
    _require_verified_clinic(db, pharmacist)
    rows = db.execute(select(Donation, DonationReview).join(
        DonationReview, DonationReview.donation_id == Donation.id
    ).where(
        Donation.status == DonationStatus.REJECTED,
        DonationReview.pharmacist_id == pharmacist.id,
        ~select(WasteRecord.id).where(WasteRecord.donation_id == Donation.id).exists(),
    ).order_by(Donation.updated_at.desc())).all()
    return [{"id": donation.id, "medicine_name": donation.medicine_name, "strength": donation.strength,
             "quantity": donation.quantity, "quantity_verified": review.verified_details is not None,
             "unit": donation.unit, "expiry_date": donation.expiry_date,
             "created_at": donation.created_at} for donation, review in rows]


@router.post("/donations/{donation_id}/waste", response_model=WasteResponse, status_code=201)
def rejected_donation_to_waste(donation_id: UUID, body: WasteCreate, db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    _require_verified_clinic(db, pharmacist)
    donation = db.scalar(select(Donation).where(Donation.id == donation_id).with_for_update())
    review = db.scalar(select(DonationReview).where(DonationReview.donation_id == donation_id))
    if donation is None or donation.status != DonationStatus.REJECTED or review is None or review.pharmacist_id != pharmacist.id:
        raise HTTPException(status_code=404, detail="Rejected donation not found")
    if body.reason != WasteReason.REJECTED_DONATION:
        raise HTTPException(status_code=422, detail="Rejected donations must use REJECTED_DONATION reason")
    if (review.verified_details is None or donation.quantity is None or not donation.medicine_name
            or not donation.unit or donation.expiry_date is None):
        raise HTTPException(status_code=409, detail="Pharmacist-verified medicine details and quantity are required before waste can be recorded")
    existing = db.scalar(select(WasteRecord.id).where(WasteRecord.donation_id == donation.id))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Waste has already been recorded for this rejected donation")
    already_recorded = db.scalar(select(func.coalesce(func.sum(WasteRecord.quantity), 0)).where(WasteRecord.donation_id == donation.id)) or 0
    if body.quantity > donation.quantity - already_recorded:
        raise HTTPException(status_code=409, detail="Waste quantity exceeds unrecorded donation quantity")
    row = _new_record(donation_id=donation.id, pharmacist_id=pharmacist.id, reason=body.reason, quantity=body.quantity, notes=body.notes)
    try:
        db.add(row)
        db.flush()
        notify(db, pharmacist.id, NotificationType.WASTE_DISPOSAL_PENDING, "Waste disposal pending", "A waste record is awaiting disposal.", "waste_record", row.id)
        db.commit()
        db.refresh(row)
    except IntegrityError as exc:
        db.rollback()
        if db.scalar(select(WasteRecord.id).where(WasteRecord.donation_id == donation.id)) is not None:
            raise HTTPException(status_code=409, detail="Waste has already been recorded for this rejected donation") from exc
        raise
    return _waste_payload(db, row)


@router.get("/donations/{donation_id}/verification")
def rejected_donation_verification_details(donation_id: UUID, db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    _require_verified_clinic(db, pharmacist)
    row = db.execute(select(Donation, DonationReview).join(DonationReview, DonationReview.donation_id == Donation.id).where(
        Donation.id == donation_id, Donation.status == DonationStatus.REJECTED, DonationReview.pharmacist_id == pharmacist.id
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Rejected donation not found")
    donation, review = row
    images = db.scalars(select(DonationImage).where(DonationImage.donation_id == donation.id).order_by(DonationImage.created_at)).all()
    return {"id": donation.id, "medicine_name": donation.medicine_name, "strength": donation.strength,
        "dosage_form": donation.dosage_form, "packaging_type": donation.packaging_type, "manufacturer": donation.manufacturer,
        "batch_number": donation.batch_number, "expiry_date": donation.expiry_date, "quantity": donation.quantity,
        "unit": donation.unit, "verified_details": review.verified_details,
        "images": [{"id": image.id, "download_url": f"/donations/{donation.id}/images/{image.id}"} for image in images]}


@router.post("/donations/{donation_id}/verification")
def verify_rejected_donation(donation_id: UUID, body: RejectedDonationVerification, db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    _require_verified_clinic(db, pharmacist)
    row = db.execute(select(Donation, DonationReview).join(DonationReview, DonationReview.donation_id == Donation.id).where(
        Donation.id == donation_id, Donation.status == DonationStatus.REJECTED, DonationReview.pharmacist_id == pharmacist.id
    ).with_for_update()).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Rejected donation not found")
    donation, review = row
    verified = body.verified_details
    for key, value in verified.model_dump(exclude={"common_use_category"}).items():
        setattr(donation, key, value)
    review.verified_details = {**verified.model_dump(mode="json"), "verified_by": str(pharmacist.id),
        "verified_at": datetime.now(timezone.utc).isoformat()}
    review.physical_package_checked = True
    review.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return {"id": donation.id, "quantity": donation.quantity, "unit": donation.unit, "expiry_date": donation.expiry_date,
        "medicine_name": donation.medicine_name, "quantity_verified": True}


@router.get("/waste", response_model=list[WasteResponse])
def list_waste(db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    _require_verified_clinic(db, pharmacist)
    rows = db.scalars(select(WasteRecord).where(WasteRecord.pharmacist_id == pharmacist.id).order_by(WasteRecord.created_at.desc())).all()
    return [_waste_payload(db, row) for row in rows]


@router.get("/waste/{waste_id}", response_model=WasteResponse)
def get_waste(waste_id: UUID, db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    _require_verified_clinic(db, pharmacist)
    row = db.scalar(select(WasteRecord).where(WasteRecord.id == waste_id, WasteRecord.pharmacist_id == pharmacist.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Waste record not found")
    return _waste_payload(db, row)


def _transition(waste_id: UUID, target: WasteStatus, db: Session, pharmacist: User, event: WasteEvent):
    _require_verified_clinic(db, pharmacist)
    if not event.confirmed:
        raise HTTPException(status_code=422, detail="Explicit confirmation is required to record collection or disposal")
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
