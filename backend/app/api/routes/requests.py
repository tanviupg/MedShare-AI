from datetime import date, datetime, timezone
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.dependencies import require_role
from app.db.database import get_db
from app.models import Checkout, ClinicProfile, ClinicVerificationStatus, Donation, DonationStatus, Inventory, InventoryStatus, MedicineRequest, MedicineRequestStatus, Prescription, PrescriptionStatus, User, UserRole
from app.schemas.medicine_request import MedicineRequestCreate, MedicineRequestDecision, MedicineRequestPatientResponse, MedicineRequestPharmacistResponse
from app.models import NotificationType
from app.services.notifications import notify

patient_router = APIRouter(prefix="/patient/requests", tags=["patient requests"])
pharmacist_router = APIRouter(prefix="/pharmacist/requests", tags=["pharmacist requests"])


def _patient_payload(db: Session, request: MedicineRequest) -> dict:
    inventory = db.get(Inventory, request.inventory_id)
    profile = db.scalar(select(ClinicProfile).where(ClinicProfile.user_id == inventory.pharmacist_id))
    latest = db.scalar(select(Prescription).where(Prescription.request_id == request.id).order_by(Prescription.created_at.desc(), Prescription.id.desc()).limit(1))
    checkout = db.scalar(select(Checkout).where(Checkout.request_id == request.id))
    prescription_status = "NOT_REQUIRED" if inventory.prescription_required is False else (latest.status.value if latest else None)
    return {"id": request.id, "medicine_name": inventory.medicine_name,
            "common_use_category": inventory.common_use_category,
            "clinic_name": profile.clinic_name if profile else "Clinic", "requested_quantity": request.requested_quantity,
            "unit": inventory.unit, "pickup_address": request.pickup_address,
            "status": request.status, "rejection_reason": request.rejection_reason,
            "created_at": request.created_at, "reviewed_at": request.reviewed_at, "fulfilled_at": request.fulfilled_at,
            "pickup_code": request.pickup_code,
            "prescription_required": inventory.prescription_required, "prescription_status": prescription_status,
            "prescription_rejection_reason": latest.rejection_reason if latest and latest.status == PrescriptionStatus.REJECTED else None,
            "price_original_snapshot": request.price_original_snapshot,
            "discount_snapshot": request.discount_snapshot,
            "patient_price_snapshot": request.patient_price_snapshot,
            "payment_status": checkout.payment_status if checkout else None}


def _pharmacist_payload(db: Session, request: MedicineRequest) -> dict:
    payload = _patient_payload(db, request)
    inventory = db.get(Inventory, request.inventory_id)
    patient = db.get(User, request.patient_id)
    return {**payload, "patient_name": patient.name, "patient_city": patient.city, "patient_phone": patient.phone,
            "inventory_available": inventory.quantity_available, "expiry_date": inventory.expiry_date}


def _new_request(body: MedicineRequestCreate, db: Session, patient: User, require_prescription: bool = False) -> tuple[MedicineRequest, Inventory]:
    inventory = db.scalar(select(Inventory).where(Inventory.public_id == body.medicine_id).with_for_update())
    if inventory is None:
        raise HTTPException(status_code=404, detail="Available medicine not found")
    donation = db.get(Donation, inventory.donation_id)
    profile = db.scalar(select(ClinicProfile).where(ClinicProfile.user_id == inventory.pharmacist_id))
    pharmacist = db.get(User, inventory.pharmacist_id)
    if (donation is None or donation.status != DonationStatus.APPROVED
        or inventory.status != InventoryStatus.AVAILABLE or inventory.quantity_available <= 0 or inventory.expiry_date < date.today()
        or pharmacist is None or not pharmacist.is_active or profile is None or profile.verification_status != ClinicVerificationStatus.VERIFIED):
        raise HTTPException(status_code=409, detail="This medicine is no longer available")
    if body.requested_quantity > inventory.quantity_available:
        raise HTTPException(status_code=409, detail="Requested quantity exceeds current availability")
    if inventory.prescription_required is None:
        raise HTTPException(status_code=409, detail="Prescription requirement is not classified for this medicine")
    if inventory.prescription_required is not require_prescription:
        if inventory.prescription_required:
            raise HTTPException(status_code=409, detail="A prescription must be provided when submitting this request")
        raise HTTPException(status_code=409, detail="A prescription is not required for this medicine")
    request = MedicineRequest(
        patient_id=patient.id,
        inventory_id=inventory.id,
        requested_quantity=body.requested_quantity,
        inventory_reserved=True,
    )
    request.pickup_address = body.pickup_address
    request.price_original_snapshot = inventory.original_price
    request.discount_snapshot = inventory.discount_percentage
    request.patient_price_snapshot = inventory.patient_price
    db.add(request)
    db.flush()
    inventory.quantity_available -= body.requested_quantity
    notify(db, inventory.pharmacist_id, NotificationType.NEW_MEDICINE_REQUEST, "New medicine request", "A patient submitted a request for medicine in your clinic inventory.", "medicine_request", request.id)
    return request, inventory


@patient_router.post("", response_model=MedicineRequestPatientResponse, status_code=201)
def create_request(body: MedicineRequestCreate, db: Session = Depends(get_db), patient: User = Depends(require_role(UserRole.PATIENT))):
    request, _ = _new_request(body, db, patient)
    db.commit()
    db.refresh(request)
    return _patient_payload(db, request)


@patient_router.get("", response_model=list[MedicineRequestPatientResponse])
def list_patient_requests(db: Session = Depends(get_db), patient: User = Depends(require_role(UserRole.PATIENT))):
    requests = db.scalars(select(MedicineRequest).where(MedicineRequest.patient_id == patient.id).order_by(MedicineRequest.created_at.desc())).all()
    return [_patient_payload(db, row) for row in requests]


@patient_router.get("/{request_id}", response_model=MedicineRequestPatientResponse)
def get_patient_request(request_id: UUID, db: Session = Depends(get_db), patient: User = Depends(require_role(UserRole.PATIENT))):
    row = db.scalar(select(MedicineRequest).where(MedicineRequest.id == request_id, MedicineRequest.patient_id == patient.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Medicine request not found")
    return _patient_payload(db, row)


@pharmacist_router.get("", response_model=list[MedicineRequestPharmacistResponse])
def list_pharmacist_requests(db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    rows = db.scalars(select(MedicineRequest).join(Inventory, Inventory.id == MedicineRequest.inventory_id).where(Inventory.pharmacist_id == pharmacist.id).order_by(MedicineRequest.status, MedicineRequest.created_at)).all()
    return [_pharmacist_payload(db, row) for row in rows]


@pharmacist_router.get("/{request_id}", response_model=MedicineRequestPharmacistResponse)
def get_pharmacist_request(request_id: UUID, db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    row = db.scalar(select(MedicineRequest).join(Inventory, Inventory.id == MedicineRequest.inventory_id).where(MedicineRequest.id == request_id, Inventory.pharmacist_id == pharmacist.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Medicine request not found")
    return _pharmacist_payload(db, row)


def _review(request_id: UUID, db: Session, pharmacist: User, decision: MedicineRequestStatus, reason: str | None):
    row = db.scalar(select(MedicineRequest).where(MedicineRequest.id == request_id).with_for_update())
    if row is None:
        raise HTTPException(status_code=404, detail="Medicine request not found")
    inventory = db.scalar(select(Inventory).where(Inventory.id == row.inventory_id).with_for_update())
    if inventory is None or inventory.pharmacist_id != pharmacist.id:
        raise HTTPException(status_code=404, detail="Medicine request not found")
    if row.status != MedicineRequestStatus.PENDING:
        raise HTTPException(status_code=409, detail="Only pending requests can be reviewed")
    if decision == MedicineRequestStatus.APPROVED:
        if inventory.prescription_required is None:
            raise HTTPException(status_code=409, detail="Prescription requirement is not classified for this medicine")
        if inventory.prescription_required is True:
            latest = db.scalar(select(Prescription).where(Prescription.request_id == row.id).order_by(Prescription.created_at.desc(), Prescription.id.desc()).limit(1).with_for_update())
            if latest is None or latest.status != PrescriptionStatus.APPROVED:
                raise HTTPException(status_code=409, detail="An approved prescription is required before this request can be approved")
        if inventory.expiry_date < date.today():
            raise HTTPException(status_code=409, detail="Expired inventory cannot be approved")
        if row.inventory_reserved:
            if inventory.status not in (InventoryStatus.AVAILABLE, InventoryStatus.DEPLETED):
                raise HTTPException(status_code=409, detail="This inventory is no longer available")
        else:
            if inventory.status != InventoryStatus.AVAILABLE or inventory.quantity_available < row.requested_quantity:
                raise HTTPException(status_code=409, detail="Insufficient available quantity to approve this request")
            inventory.quantity_available -= row.requested_quantity
            row.inventory_reserved = True
        row.pickup_code = f"MS-{secrets.token_hex(3).upper()}"
    elif row.inventory_reserved:
        inventory.quantity_available += row.requested_quantity
        if inventory.expiry_date < date.today():
            inventory.status = InventoryStatus.EXPIRED
        row.inventory_reserved = False
    row.status = decision
    row.rejection_reason = reason
    row.reviewed_at = datetime.now(timezone.utc)
    kind = NotificationType.REQUEST_APPROVED if decision == MedicineRequestStatus.APPROVED else NotificationType.REQUEST_REJECTED
    notify(db, row.patient_id, kind, "Request approved" if kind == NotificationType.REQUEST_APPROVED else "Request rejected",
           "Your medicine request was approved." if kind == NotificationType.REQUEST_APPROVED else "Your medicine request was rejected.", "medicine_request", row.id)
    if decision == MedicineRequestStatus.APPROVED:
        notify(db, row.patient_id, NotificationType.READY_FOR_PICKUP, "Medicine ready for pickup", "Your approved medicine request is ready for dispensing.", "medicine_request", row.id)
    db.commit()
    db.refresh(row)
    return _pharmacist_payload(db, row)


@pharmacist_router.post("/{request_id}/approve", response_model=MedicineRequestPharmacistResponse)
def approve_request(request_id: UUID, db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    return _review(request_id, db, pharmacist, MedicineRequestStatus.APPROVED, None)


@pharmacist_router.post("/{request_id}/reject", response_model=MedicineRequestPharmacistResponse)
def reject_request(request_id: UUID, body: MedicineRequestDecision, db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    reason = (body.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="A rejection reason is required")
    return _review(request_id, db, pharmacist, MedicineRequestStatus.REJECTED, reason)
