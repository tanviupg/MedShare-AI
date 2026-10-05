from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_role
from app.db.database import get_db
from app.models import Checkout, ClinicProfile, Inventory, InventoryStatus, MedicineRequest, MedicineRequestStatus, PaymentStatus, Prescription, PrescriptionStatus, User, UserRole
from app.schemas.checkout import CheckoutResponse

router = APIRouter(prefix="/patient/checkout", tags=["simulated checkout"])


def _owned_approved_request(db: Session, request_id: UUID, patient: User, lock: bool = False) -> tuple[MedicineRequest, Inventory]:
    stmt = select(MedicineRequest).where(MedicineRequest.id == request_id, MedicineRequest.patient_id == patient.id)
    if lock:
        stmt = stmt.with_for_update()
    request = db.scalar(stmt)
    if request is None:
        raise HTTPException(status_code=404, detail="Medicine request not found")
    if request.status != MedicineRequestStatus.APPROVED:
        raise HTTPException(status_code=409, detail="Only approved requests can proceed to checkout")
    inventory = db.scalar(select(Inventory).where(Inventory.id == request.inventory_id).with_for_update() if lock else select(Inventory).where(Inventory.id == request.inventory_id))
    if inventory is None:
        raise HTTPException(status_code=409, detail="Reserved medicine is unavailable")
    if inventory.expiry_date < date.today() or inventory.status == InventoryStatus.EXPIRED:
        raise HTTPException(status_code=409, detail="Expired medicine cannot proceed to checkout")
    if inventory.prescription_required is None:
        raise HTTPException(status_code=409, detail="Prescription requirement is not classified")
    if inventory.prescription_required:
        prescription = db.scalar(select(Prescription).where(Prescription.request_id == request.id).order_by(Prescription.created_at.desc(), Prescription.id.desc()).limit(1))
        if prescription is None or prescription.status != PrescriptionStatus.APPROVED:
            raise HTTPException(status_code=409, detail="An approved prescription is required before checkout")
    return request, inventory


def _payload(db: Session, row: Checkout, request: MedicineRequest, inventory: Inventory) -> dict:
    profile = db.scalar(select(ClinicProfile).where(ClinicProfile.user_id == inventory.pharmacist_id))
    return {"id": row.id, "request_id": request.id, "medicine_name": inventory.medicine_name,
            "quantity": request.requested_quantity, "unit": inventory.unit,
            "clinic_name": profile.clinic_name if profile else "Clinic",
            "original_price": request.price_original_snapshot, "discount_percentage": request.discount_snapshot,
            "patient_price": request.patient_price_snapshot, "amount": row.amount, "currency": row.currency,
            "payment_status": row.payment_status, "payment_method": row.payment_method,
            "created_at": row.created_at, "paid_at": row.paid_at,
            "is_free": row.payment_method == "FREE", "demo_payment": True}


def _get_or_create(db: Session, request: MedicineRequest, patient: User) -> Checkout:
    row = db.scalar(select(Checkout).where(Checkout.request_id == request.id).with_for_update())
    if row:
        return row
    if request.patient_price_snapshot is None or request.price_original_snapshot is None or request.discount_snapshot is None:
        raise HTTPException(status_code=409, detail="Price was not configured when this request was created")
    unit_price = request.patient_price_snapshot
    amount = (unit_price * request.requested_quantity).quantize(Decimal("0.01"))
    free = amount == 0
    row = Checkout(request_id=request.id, patient_user_id=patient.id, amount=amount,
                   payment_status=PaymentStatus.PAID if free else PaymentStatus.PENDING,
                   payment_method="FREE" if free else None, paid_at=datetime.now(timezone.utc) if free else None)
    db.add(row)
    db.flush()
    return row


@router.get("/{request_id}", response_model=CheckoutResponse)
def get_checkout(request_id: UUID, db: Session = Depends(get_db), patient: User = Depends(require_role(UserRole.PATIENT))):
    request, inventory = _owned_approved_request(db, request_id, patient, lock=True)
    row = _get_or_create(db, request, patient)
    db.commit()
    db.refresh(row)
    return _payload(db, row, request, inventory)


@router.post("/{request_id}/demo-pay", response_model=CheckoutResponse)
def complete_demo_payment(request_id: UUID, db: Session = Depends(get_db), patient: User = Depends(require_role(UserRole.PATIENT))):
    request, inventory = _owned_approved_request(db, request_id, patient, lock=True)
    row = _get_or_create(db, request, patient)
    if row.payment_status == PaymentStatus.PAID:
        db.commit()
        return _payload(db, row, request, inventory)
    if row.payment_status != PaymentStatus.PENDING:
        raise HTTPException(status_code=409, detail="This checkout cannot be paid")
    row.payment_status = PaymentStatus.PAID
    row.payment_method = "DEMO"
    row.paid_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _payload(db, row, request, inventory)
