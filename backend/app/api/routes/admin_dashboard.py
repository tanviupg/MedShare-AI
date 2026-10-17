from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import require_role
from app.db.database import get_db
from app.models import (
    ClinicProfile,
    ClinicVerificationStatus,
    Donation,
    DonationStatus,
    Inventory,
    InventoryStatus,
    MedicineRequest,
    MedicineRequestStatus,
    User,
    UserRole,
    WasteRecord,
    WasteStatus,
)
from app.schemas.admin_dashboard import AdminPlatformDashboard
from app.services.business_time import business_today

router = APIRouter(prefix="/admin", tags=["admin dashboard"])


def _enum_counts(db: Session, status_column, enum_type) -> dict[str, int]:
    counts = {item.value: 0 for item in enum_type}
    rows = db.execute(select(status_column, func.count()).group_by(status_column)).all()
    for status, count in rows:
        counts[status.value] = int(count)
    return counts


@router.get("/dashboard", response_model=AdminPlatformDashboard)
def admin_platform_dashboard(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.ADMIN)),
) -> AdminPlatformDashboard:
    """Return aggregate platform counts only; this endpoint is read-only."""
    clinic_counts = {status.value: int(db.scalar(
        select(func.count(ClinicProfile.id)).where(ClinicProfile.verification_status == status)
    ) or 0) for status in ClinicVerificationStatus}

    role_counts = {role.value: int(db.scalar(
        select(func.count(User.id)).where(User.role == role)
    ) or 0) for role in UserRole}

    donation_counts = _enum_counts(db, Donation.status, DonationStatus)
    request_counts = _enum_counts(db, MedicineRequest.status, MedicineRequestStatus)
    waste_counts = _enum_counts(db, WasteRecord.status, WasteStatus)

    available_quantity = int(db.scalar(select(func.coalesce(func.sum(Inventory.quantity_available), 0)).where(
        Inventory.status == InventoryStatus.AVAILABLE,
        Inventory.quantity_available > 0,
        Inventory.expiry_date >= business_today(),
    )) or 0)
    # Reserved units have already been removed from quantity_available. Sum their
    # active request reservations separately so the dashboard never counts them twice.
    reserved_quantity = int(db.scalar(select(func.coalesce(func.sum(MedicineRequest.requested_quantity), 0)).where(
        MedicineRequest.inventory_reserved.is_(True),
        MedicineRequest.status.in_([MedicineRequestStatus.PENDING, MedicineRequestStatus.APPROVED]),
    )) or 0)

    return AdminPlatformDashboard(
        clinics={
            "total": sum(clinic_counts.values()),
            "pending": clinic_counts[ClinicVerificationStatus.PENDING.value],
            "verified": clinic_counts[ClinicVerificationStatus.VERIFIED.value],
            "rejected": clinic_counts[ClinicVerificationStatus.REJECTED.value],
        },
        users={"total": sum(role_counts.values()), "by_role": role_counts},
        donations={"total": sum(donation_counts.values()), "by_status": donation_counts},
        inventory={"available": available_quantity, "reserved": reserved_quantity},
        requests={"total": sum(request_counts.values()), "by_status": request_counts},
        waste={"total": sum(waste_counts.values()), "by_status": waste_counts},
    )
