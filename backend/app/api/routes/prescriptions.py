from pathlib import Path
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_role
from app.api.routes.requests import _new_request, _patient_payload, _pharmacist_payload
from app.db.database import get_db
from app.models import Inventory, MedicineRequest, Prescription, PrescriptionStatus, User, UserRole
from app.schemas.medicine_request import MedicineRequestCreate, MedicineRequestPatientResponse
from app.services.prescription_storage import storage, store_upload
from app.models import NotificationType
from app.services.notifications import notify

patient_router = APIRouter(prefix="/patient/requests", tags=["patient prescriptions"])
pharmacist_router = APIRouter(prefix="/pharmacist", tags=["pharmacist prescriptions"])


def _latest(db: Session, request_id: UUID) -> Prescription | None:
    return db.scalar(select(Prescription).where(Prescription.request_id == request_id).order_by(Prescription.created_at.desc(), Prescription.id.desc()).limit(1))


def _metadata(record: Prescription) -> dict:
    return {"id": record.id, "original_filename": record.original_filename, "content_type": record.content_type,
            "size_bytes": record.size_bytes, "status": record.status, "rejection_reason": record.rejection_reason,
            "created_at": record.created_at, "reviewed_at": record.reviewed_at,
            "file_url": None}


def _patient_request(request_id: UUID, patient: User, db: Session) -> tuple[MedicineRequest, Inventory]:
    row = db.scalar(select(MedicineRequest).where(MedicineRequest.id == request_id, MedicineRequest.patient_id == patient.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Medicine request not found")
    inventory = db.get(Inventory, row.inventory_id)
    return row, inventory


def _pharmacist_request(request_id: UUID, pharmacist: User, db: Session) -> tuple[MedicineRequest, Inventory]:
    row = db.scalar(select(MedicineRequest).join(Inventory, Inventory.id == MedicineRequest.inventory_id).where(
        MedicineRequest.id == request_id, Inventory.pharmacist_id == pharmacist.id))
    if row is None:
        raise HTTPException(status_code=404, detail="Medicine request not found")
    return row, db.get(Inventory, row.inventory_id)


@patient_router.post("/{request_id}/prescription", status_code=201)
async def upload_prescription(request_id: UUID, file: UploadFile = File(...), db: Session = Depends(get_db), patient: User = Depends(require_role(UserRole.PATIENT))):
    row, inventory = _patient_request(request_id, patient, db)
    if inventory.prescription_required is not True:
        raise HTTPException(status_code=409, detail="This request is not explicitly classified as prescription-required")
    previous = _latest(db, row.id)
    if previous and previous.status != PrescriptionStatus.REJECTED:
        raise HTTPException(status_code=409, detail="A prescription can be replaced only after rejection")
    key, filename, content_type, size_bytes = await store_upload(file)
    try:
        record = Prescription(request_id=row.id, storage_key=key, original_filename=filename, content_type=content_type, size_bytes=size_bytes)
        db.add(record)
        db.flush()
        notify(db, inventory.pharmacist_id, NotificationType.PRESCRIPTION_AWAITING_VERIFICATION,
               "Prescription awaiting verification", "A prescription is ready for review for a medicine request.",
               "prescription", record.id)
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)
        raise
    db.refresh(record)
    return _metadata(record)


@patient_router.post("/with-prescription", response_model=MedicineRequestPatientResponse, status_code=201)
async def create_request_with_prescription(
    medicine_id: UUID = Form(...),
    requested_quantity: int = Form(..., gt=0, le=1000000),
    pickup_address: str = Form(..., min_length=1, max_length=500),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    patient: User = Depends(require_role(UserRole.PATIENT)),
):
    address = pickup_address.strip()
    if not address:
        raise HTTPException(status_code=422, detail="Pickup address is required")
    body = MedicineRequestCreate(
        medicine_id=medicine_id,
        requested_quantity=requested_quantity,
        pickup_address=address,
    )
    key, filename, content_type, size_bytes = await store_upload(file)
    try:
        row, inventory = _new_request(body, db, patient, require_prescription=True)
        record = Prescription(
            request_id=row.id,
            storage_key=key,
            original_filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
        )
        db.add(record)
        db.flush()
        notify(db, inventory.pharmacist_id, NotificationType.PRESCRIPTION_AWAITING_VERIFICATION,
               "Prescription awaiting verification", "A prescription is ready for review for a medicine request.",
               "prescription", record.id)
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)
        raise
    db.refresh(row)
    return _patient_payload(db, row)


@patient_router.get("/{request_id}/prescription")
def get_patient_prescription(request_id: UUID, db: Session = Depends(get_db), patient: User = Depends(require_role(UserRole.PATIENT))):
    row, _ = _patient_request(request_id, patient, db)
    record = _latest(db, row.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return _metadata(record)


def _file_response(record: Prescription) -> Response:
    try:
        content = storage.read(record.storage_key)
    except OSError as exc:
        raise HTTPException(status_code=404, detail="Prescription file not found") from exc
    safe_name = Path(record.original_filename).name.replace('"', "")
    return Response(content=content, media_type=record.content_type, headers={
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store",
        "Content-Disposition": f'inline; filename="{safe_name}"',
    })


@patient_router.get("/{request_id}/prescription/file")
def get_patient_prescription_file(request_id: UUID, db: Session = Depends(get_db), patient: User = Depends(require_role(UserRole.PATIENT))):
    row, _ = _patient_request(request_id, patient, db)
    record = _latest(db, row.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return _file_response(record)


@pharmacist_router.get("/prescriptions/pending")
def list_pending_prescriptions(db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    rows = db.execute(select(MedicineRequest, Prescription).join(Inventory, Inventory.id == MedicineRequest.inventory_id)
        .join(Prescription, Prescription.request_id == MedicineRequest.id)
        .where(Inventory.pharmacist_id == pharmacist.id, Prescription.status == PrescriptionStatus.PENDING_REVIEW)
        .order_by(Prescription.created_at)).all()
    return [{**_pharmacist_payload(db, request), "prescription": _metadata(record)} for request, record in rows]


@pharmacist_router.get("/requests/{request_id}/prescription")
def get_pharmacist_prescription(request_id: UUID, db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    row, _ = _pharmacist_request(request_id, pharmacist, db)
    record = _latest(db, row.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return _metadata(record)


@pharmacist_router.get("/requests/{request_id}/prescription/file")
def get_pharmacist_prescription_file(request_id: UUID, db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    row, _ = _pharmacist_request(request_id, pharmacist, db)
    record = _latest(db, row.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return _file_response(record)


def _decide(request_id: UUID, pharmacist: User, db: Session, decision: PrescriptionStatus, reason: str | None = None):
    row, _ = _pharmacist_request(request_id, pharmacist, db)
    record = db.scalar(select(Prescription).where(Prescription.request_id == row.id).order_by(Prescription.created_at.desc(), Prescription.id.desc()).limit(1).with_for_update())
    if record is None or record.status != PrescriptionStatus.PENDING_REVIEW:
        raise HTTPException(status_code=409, detail="No pending prescription is available for review")
    record.status = decision
    record.reviewed_by = pharmacist.id
    record.reviewed_at = datetime.now(timezone.utc)
    record.rejection_reason = reason
    kind = NotificationType.PRESCRIPTION_APPROVED if decision == PrescriptionStatus.APPROVED else NotificationType.PRESCRIPTION_REJECTED
    notify(db, row.patient_id, kind, "Prescription approved" if kind == NotificationType.PRESCRIPTION_APPROVED else "Prescription rejected",
           "Your prescription has been verified." if kind == NotificationType.PRESCRIPTION_APPROVED else "Your prescription was not approved.", "prescription", record.id)
    db.commit()
    db.refresh(record)
    return _metadata(record)


@pharmacist_router.post("/requests/{request_id}/prescription/approve")
def approve_prescription(request_id: UUID, db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    return _decide(request_id, pharmacist, db, PrescriptionStatus.APPROVED)


@pharmacist_router.post("/requests/{request_id}/prescription/reject")
def reject_prescription(request_id: UUID, payload: dict, db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    reason = str(payload.get("reason", "")).strip()[:1000]
    if not reason:
        raise HTTPException(status_code=422, detail="A rejection reason is required")
    return _decide(request_id, pharmacist, db, PrescriptionStatus.REJECTED, reason)
