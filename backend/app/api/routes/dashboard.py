from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.api.dependencies import require_role
from app.api.routes.inventory import expire_old_inventory
from app.core.config import get_settings
from app.db.database import get_db
from app.models import (Checkout, Donation, DonationStatus, ExtractionStatus, Inventory,
    InventoryStatus, MedicineExtraction, MedicineRequest, MedicineRequestStatus,
    Notification, PaymentStatus, Prescription, PrescriptionStatus, User, UserRole,
    WasteRecord, WasteStatus)

router = APIRouter(prefix="/pharmacist", tags=["pharmacist dashboard"])


@router.get("/dashboard")
def pharmacist_dashboard(db: Session = Depends(get_db), pharmacist: User = Depends(require_role(UserRole.CLINIC_PHARMACIST))):
    """Return a bounded operational snapshot, scoped to the authenticated pharmacist."""
    expire_old_inventory(db, pharmacist.id)
    today = datetime.now(timezone.utc).date()
    warning_end = today + timedelta(days=get_settings().expiry_warning_days)
    active = (Inventory.pharmacist_id == pharmacist.id, Inventory.quantity_available > 0)
    live = (*active, Inventory.status.in_([InventoryStatus.AVAILABLE, InventoryStatus.RESERVED]))

    def count(model, *conditions):
        return int(db.scalar(select(func.count(model.id)).where(*conditions)) or 0)

    inventory_stats = db.execute(select(
        func.count(Inventory.id).filter(*live, Inventory.status == InventoryStatus.AVAILABLE, Inventory.expiry_date >= today).label("available"),
        func.count(Inventory.id).filter(*live, Inventory.status == InventoryStatus.RESERVED, Inventory.expiry_date >= today).label("reserved"),
        func.count(Inventory.id).filter(*active, Inventory.status == InventoryStatus.EXPIRED).label("expired"),
        func.count(Inventory.id).filter(Inventory.pharmacist_id == pharmacist.id, Inventory.status == InventoryStatus.DEPLETED).label("depleted"),
        func.count(Inventory.id).filter(*live, Inventory.status == InventoryStatus.AVAILABLE, Inventory.expiry_date >= today, Inventory.expiry_date <= warning_end).label("expiring_soon"),
        func.count(Inventory.id).filter(*live, Inventory.expiry_date >= today, Inventory.original_price.is_not(None), Inventory.discount_percentage.is_not(None)).label("pricing_configured"),
        func.count(Inventory.id).filter(*live, Inventory.expiry_date >= today, (Inventory.original_price.is_(None) | Inventory.discount_percentage.is_(None))).label("pricing_missing"),
    )).mappings().one()

    clinic_request = MedicineRequest.id.in_(select(MedicineRequest.id).join(Inventory, Inventory.id == MedicineRequest.inventory_id).where(Inventory.pharmacist_id == pharmacist.id))
    pending_donations = select(Donation).where(Donation.status == DonationStatus.PENDING_REVIEW, Donation.details_confirmed.is_(True)).order_by(Donation.created_at.asc()).limit(6)
    donations = db.scalars(pending_donations).all()
    donation_ids = [row.id for row in donations]
    extraction_states = {}
    if donation_ids:
        extraction_states = dict(db.execute(select(MedicineExtraction.donation_id, MedicineExtraction.status)
            .where(MedicineExtraction.donation_id.in_(donation_ids)).order_by(MedicineExtraction.created_at.desc())).all())
    latest_prescription_status = (select(Prescription.status).where(Prescription.request_id == MedicineRequest.id)
        .order_by(Prescription.created_at.desc(), Prescription.id.desc()).limit(1).scalar_subquery())
    pending_rows = db.execute(select(MedicineRequest, Inventory, latest_prescription_status, Checkout.payment_status)
        .join(Inventory, Inventory.id == MedicineRequest.inventory_id)
        .outerjoin(Checkout, Checkout.request_id == MedicineRequest.id)
        .where(Inventory.pharmacist_id == pharmacist.id, MedicineRequest.status == MedicineRequestStatus.PENDING)
        .order_by(MedicineRequest.created_at.asc()).limit(8)).all()
    prescription_rows = db.execute(select(MedicineRequest, Inventory, Prescription)
        .join(Inventory, Inventory.id == MedicineRequest.inventory_id)
        .join(Prescription, Prescription.request_id == MedicineRequest.id)
        .where(Inventory.pharmacist_id == pharmacist.id, Prescription.status == PrescriptionStatus.PENDING_REVIEW)
        .order_by(Prescription.created_at.asc()).limit(8)).all()
    ready_rows = db.execute(select(MedicineRequest, Inventory, Checkout.payment_status)
        .join(Inventory, Inventory.id == MedicineRequest.inventory_id)
        .outerjoin(Checkout, Checkout.request_id == MedicineRequest.id)
        .where(Inventory.pharmacist_id == pharmacist.id, MedicineRequest.status == MedicineRequestStatus.APPROVED)
        .order_by(MedicineRequest.created_at.asc()).limit(8)).all()
    expiry_rows = db.scalars(select(Inventory).where(*active,
        ((Inventory.expiry_date < today) | ((Inventory.expiry_date <= warning_end) & (Inventory.status == InventoryStatus.AVAILABLE))))
        .order_by(Inventory.expiry_date.asc()).limit(8)).all()
    waste_counts = db.execute(select(
        func.count(WasteRecord.id).filter(WasteRecord.status == WasteStatus.DISPOSAL_PENDING).label("pending"),
        func.count(WasteRecord.id).filter(WasteRecord.status == WasteStatus.COLLECTED).label("collected"),
        func.count(WasteRecord.id).filter(WasteRecord.status == WasteStatus.DISPOSED).label("disposed"),
    ).where(WasteRecord.pharmacist_id == pharmacist.id)).mappings().one()
    waste_pending_rows = db.execute(select(WasteRecord, Inventory.medicine_name, Donation.medicine_name)
        .outerjoin(Inventory, Inventory.id == WasteRecord.inventory_id)
        .outerjoin(Donation, Donation.id == WasteRecord.donation_id)
        .where(WasteRecord.pharmacist_id == pharmacist.id, WasteRecord.status == WasteStatus.DISPOSAL_PENDING)
        .order_by(WasteRecord.created_at.asc()).limit(5)).all()
    unread = count(Notification, Notification.recipient_user_id == pharmacist.id, Notification.is_read.is_(False))

    pending_donation_count = count(Donation, Donation.status == DonationStatus.PENDING_REVIEW, Donation.details_confirmed.is_(True))
    pending_request_count = count(MedicineRequest, clinic_request, MedicineRequest.status == MedicineRequestStatus.PENDING)
    pending_prescription_count = count(Prescription, Prescription.status == PrescriptionStatus.PENDING_REVIEW,
        Prescription.request_id.in_(select(MedicineRequest.id).join(Inventory, Inventory.id == MedicineRequest.inventory_id).where(Inventory.pharmacist_id == pharmacist.id)))
    ready_count = count(MedicineRequest, clinic_request, MedicineRequest.status == MedicineRequestStatus.APPROVED)
    soon_count = int(inventory_stats["expiring_soon"] or 0)
    expired_count = int(inventory_stats["expired"] or 0)
    waste_pending_count = int(waste_counts["pending"] or 0)
    inventory = {key: int(inventory_stats[key] or 0) for key in inventory_stats.keys()}

    return {
        "summary": {"pending_donations": pending_donation_count, "pending_requests": pending_request_count,
            "pending_prescriptions": pending_prescription_count, "ready_for_dispensing": ready_count,
            "expiring_soon": soon_count, "expired": expired_count, "waste_pending": waste_pending_count,
            "unread_notifications": unread},
        "inventory": inventory,
        "recent_donations": [{"medicine_name": row.medicine_name, "created_at": row.created_at,
            "extraction_status": extraction_states.get(row.id).value if extraction_states.get(row.id) else "NOT_STARTED",
            "details_confirmed": row.details_confirmed, "review_status": row.status.value} for row in donations],
        "pending_requests": [{"medicine_name": inv.medicine_name, "strength": inv.strength,
            "quantity": req.requested_quantity, "unit": inv.unit, "created_at": req.created_at,
            "prescription_status": prescription_status.value if prescription_status else None,
            "status": req.status.value, "payment_status": payment.value if payment else None} for req, inv, prescription_status, payment in pending_rows],
        "prescription_queue": [{"medicine_name": inv.medicine_name, "strength": inv.strength,
            "created_at": req.created_at, "verification_status": rx.status.value} for req, inv, rx in prescription_rows],
        "dispensing_queue": [{"medicine_name": inv.medicine_name, "strength": inv.strength,
            "quantity": req.requested_quantity, "unit": inv.unit, "created_at": req.created_at,
            "payment_status": payment.value if payment else ("NOT_REQUIRED" if req.patient_price_snapshot is None else "UNPAID"),
            "pickup_readiness": "READY" if req.patient_price_snapshot is None or payment == PaymentStatus.PAID else "PAYMENT_REQUIRED"} for req, inv, payment in ready_rows],
        "expiry_alerts": [{"medicine_name": row.medicine_name, "strength": row.strength,
            "quantity": row.quantity_available, "unit": row.unit, "expiry_date": row.expiry_date,
            "status": "Expired" if row.expiry_date < today or row.status == InventoryStatus.EXPIRED else "Expiring Soon"} for row in expiry_rows],
        "waste_summary": {"disposal_pending": waste_pending_count, "collected": int(waste_counts["collected"] or 0),
            "disposed": int(waste_counts["disposed"] or 0), "pending_items": [{"medicine_name": inventory_name or donation_name,
                "quantity": row.quantity, "status": row.status.value, "created_at": row.created_at} for row, inventory_name, donation_name in waste_pending_rows]},
    }
