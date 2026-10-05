from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_role
from app.db.database import get_db
from app.models import Checkout, ClinicProfile, DispensingRecord, Inventory, InventoryStatus, MedicineRequest, MedicineRequestStatus, PaymentStatus, Prescription, PrescriptionStatus, User, UserRole
from app.schemas.dispensing import PatientDispensingResponse, PharmacistDispensingResponse
from app.models import NotificationType
from app.services.notifications import notify

pharmacist_router = APIRouter(prefix="/pharmacist", tags=["pharmacist dispensing"])
patient_router = APIRouter(prefix="/patient", tags=["patient dispensing"])


def _payload(db: Session, request: MedicineRequest, record: DispensingRecord | None = None, pharmacist_view: bool = False) -> dict:
    inventory = db.get(Inventory, request.inventory_id)
    profile = db.scalar(select(ClinicProfile).where(ClinicProfile.user_id == inventory.pharmacist_id))
    patient = db.get(User, request.patient_id)
    latest = db.scalar(select(Prescription).where(Prescription.request_id == request.id).order_by(Prescription.created_at.desc(), Prescription.id.desc()).limit(1))
    data = {
        "medicine_name": inventory.medicine_name,
        "strength": inventory.strength,
        "dosage_form": inventory.dosage_form,
        "clinic_name": profile.clinic_name if profile else "Clinic",
        "quantity": record.quantity_dispensed if record else request.requested_quantity,
        "unit": inventory.unit,
        "pickup_code": request.pickup_code,
        "status": request.status.value,
        "requested_at": request.created_at,
        "dispensed_at": record.dispensed_at if record else None,
    }
    if pharmacist_view:
        data.update(request_id=request.id, patient_name=patient.name, patient_city=patient.city, patient_phone=patient.phone,
                    prescription_required=inventory.prescription_required,
                    prescription_status=("NOT_REQUIRED" if inventory.prescription_required is False else latest.status.value if latest else None))
    return data


def _owned_request(db: Session, request_id: UUID, pharmacist: User, lock: bool = False) -> MedicineRequest:
    stmt = select(MedicineRequest).join(Inventory, Inventory.id == MedicineRequest.inventory_id).where(
        MedicineRequest.id == request_id, Inventory.pharmacist_id == pharmacist.id)
    if lock:
        stmt = stmt.with_for_update(of=MedicineRequest)
    row = db.scalar(stmt)
    if row is None:
        raise HTTPException(status_code=404, detail="Medicine request not found")
    return row


@pharmacist_router.get("/dispensing", response_model=list[PharmacistDispensingResponse])
def list_ready_for_pickup(db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    rows = db.scalars(select(MedicineRequest).join(Inventory, Inventory.id == MedicineRequest.inventory_id).where(
        Inventory.pharmacist_id == pharmacist.id, MedicineRequest.status == MedicineRequestStatus.APPROVED
    ).order_by(MedicineRequest.created_at)).all()
    return [_payload(db, row, pharmacist_view=True) for row in rows]


@pharmacist_router.get("/requests/{request_id}/dispensing", response_model=PharmacistDispensingResponse)
def get_pharmacist_dispensing(request_id: UUID, db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    row = _owned_request(db, request_id, pharmacist)
    if row.status not in (MedicineRequestStatus.APPROVED, MedicineRequestStatus.FULFILLED):
        raise HTTPException(status_code=404, detail="Dispensing information not found")
    record = db.scalar(select(DispensingRecord).where(DispensingRecord.request_id == row.id))
    return _payload(db, row, record, pharmacist_view=True)


@pharmacist_router.post("/requests/{request_id}/dispense", response_model=PharmacistDispensingResponse)
def dispense_request(request_id: UUID, db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    row = _owned_request(db, request_id, pharmacist, lock=True)
    inventory = db.scalar(select(Inventory).where(Inventory.id == row.inventory_id).with_for_update())
    if inventory is None or inventory.pharmacist_id != pharmacist.id:
        raise HTTPException(status_code=404, detail="Medicine request not found")
    if row.status != MedicineRequestStatus.APPROVED:
        raise HTTPException(status_code=409, detail="Only approved, reserved requests can be dispensed")
    if row.patient_price_snapshot is not None:
        payment = db.scalar(select(Checkout).where(Checkout.request_id == row.id).with_for_update())
        if payment is None or payment.payment_status != PaymentStatus.PAID:
            raise HTTPException(status_code=409, detail="Payment must be completed before dispensing")
    if inventory.status == InventoryStatus.EXPIRED or inventory.expiry_date < date.today():
        raise HTTPException(status_code=409, detail="Expired inventory cannot be dispensed")
    if row.requested_quantity <= 0 or row.pickup_code is None:
        raise HTTPException(status_code=409, detail="This request has no valid reserved quantity")
    if db.scalar(select(DispensingRecord.id).where(DispensingRecord.request_id == row.id)) is not None:
        raise HTTPException(status_code=409, detail="This request has already been dispensed")
    if inventory.prescription_required is None:
        raise HTTPException(status_code=409, detail="Prescription requirement is not classified for this medicine")
    if inventory.prescription_required:
        latest = db.scalar(select(Prescription).where(Prescription.request_id == row.id).order_by(
            Prescription.created_at.desc(), Prescription.id.desc()).limit(1).with_for_update())
        if latest is None or latest.status != PrescriptionStatus.APPROVED:
            raise HTTPException(status_code=409, detail="An approved prescription is required before dispensing")
    now = datetime.now(timezone.utc)
    record = DispensingRecord(request_id=row.id, inventory_id=inventory.id, pharmacist_id=pharmacist.id,
                              quantity_dispensed=row.requested_quantity, dispensed_at=now)
    db.add(record)
    row.status = MedicineRequestStatus.FULFILLED
    row.fulfilled_at = now
    notify(db, row.patient_id, NotificationType.REQUEST_FULFILLED, "Request fulfilled", "Your medicine request has been dispensed.", "medicine_request", row.id)
    db.commit()
    db.refresh(record)
    db.refresh(row)
    return _payload(db, row, record, pharmacist_view=True)


@patient_router.get("/dispensing", response_model=list[PatientDispensingResponse])
def list_patient_dispensing(db: Session = Depends(get_db), patient: User = Depends(require_role(UserRole.PATIENT))):
    rows = db.scalars(select(MedicineRequest).where(
        MedicineRequest.patient_id == patient.id,
        MedicineRequest.status.in_([MedicineRequestStatus.APPROVED, MedicineRequestStatus.FULFILLED]),
    ).order_by(MedicineRequest.created_at.desc())).all()
    return [_payload(db, row, db.scalar(select(DispensingRecord).where(DispensingRecord.request_id == row.id))) for row in rows]


@patient_router.get("/requests/{request_id}/dispensing", response_model=PatientDispensingResponse)
def get_patient_dispensing(request_id: UUID, db: Session = Depends(get_db), patient: User = Depends(require_role(UserRole.PATIENT))):
    row = db.scalar(select(MedicineRequest).where(MedicineRequest.id == request_id, MedicineRequest.patient_id == patient.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Medicine request not found")
    if row.status not in (MedicineRequestStatus.APPROVED, MedicineRequestStatus.FULFILLED):
        raise HTTPException(status_code=404, detail="Dispensing information not found")
    record = db.scalar(select(DispensingRecord).where(DispensingRecord.request_id == row.id))
    return _payload(db, row, record)


