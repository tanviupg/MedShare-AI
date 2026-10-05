from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import require_role
from app.db.database import get_db
from app.models import ClinicProfile, ClinicVerificationStatus, CommonUseCategory, Donation, DonationImage, DonationStatus, Inventory, InventoryStatus, User, UserRole
from app.schemas.patient import PatientMedicineImage, PatientMedicineOption, PatientMedicinePage
from app.api.routes.donations import storage

router = APIRouter(prefix="/patient", tags=["patient discovery"])


def available_inventory_query():
    return (
        select(Inventory, ClinicProfile)
        .join(Donation, Donation.id == Inventory.donation_id)
        .join(User, User.id == Inventory.pharmacist_id)
        .join(ClinicProfile, ClinicProfile.user_id == User.id)
        .where(
            Inventory.status == InventoryStatus.AVAILABLE,
            Donation.status == DonationStatus.APPROVED,
            Inventory.quantity_available > 0,
            Inventory.expiry_date >= date.today(),
            User.is_active.is_(True),
            ClinicProfile.verification_status == ClinicVerificationStatus.VERIFIED,
        )
    )


@router.get("/medicines", response_model=PatientMedicinePage)
def search_medicines(
    q: str | None = Query(default=None, max_length=200),
    strength: str | None = Query(default=None, max_length=100),
    dosage_form: str | None = Query(default=None, max_length=100),
    category: CommonUseCategory | None = Query(default=None),
    city: str | None = Query(default=None, max_length=120),
    clinic: str | None = Query(default=None, max_length=160),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=50),
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(UserRole.PATIENT)),
) -> PatientMedicinePage:
    query = available_inventory_query()
    if q and q.strip():
        query = query.where(Inventory.medicine_name.ilike(f"%{q.strip()}%"))
    if strength and strength.strip():
        query = query.where(Inventory.strength.ilike(f"%{strength.strip()}%"))
    if dosage_form and dosage_form.strip():
        query = query.where(Inventory.dosage_form.ilike(f"%{dosage_form.strip()}%"))
    if category is not None:
        query = query.where(Inventory.common_use_category == category)
    if city and city.strip():
        query = query.where(ClinicProfile.city.ilike(f"%{city.strip()}%"))
    if clinic and clinic.strip():
        query = query.where(ClinicProfile.clinic_name.ilike(f"%{clinic.strip()}%"))

    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total = db.scalar(count_query) or 0
    rows = db.execute(
        query.order_by(
            func.lower(Inventory.medicine_name),
            func.lower(ClinicProfile.city),
            func.lower(ClinicProfile.clinic_name),
            Inventory.expiry_date,
            Inventory.id,
        ).offset((page - 1) * page_size).limit(page_size)
    ).all()
    items = [
        PatientMedicineOption(
            medicine_id=item.public_id,
            medicine_name=item.medicine_name,
            common_use_category=item.common_use_category,
            expiry_date=item.expiry_date,
            availability=item.quantity_available,
            availability_unit=item.unit,
            clinic_name=profile.clinic_name,
            clinic_city=profile.city,
            prescription_required=item.prescription_required,
            images=[
                PatientMedicineImage(image_url=f"/patient/medicines/{item.public_id}/images/{index}")
                for index, _ in enumerate(
                    db.scalars(
                        select(DonationImage)
                        .where(DonationImage.donation_id == item.donation_id)
                        .order_by(DonationImage.created_at, DonationImage.id)
                    ).all()
                )
            ],
            original_price=item.original_price,
            discount_percentage=item.discount_percentage,
            patient_price=item.patient_price,
        )
        for item, profile in rows
    ]
    return PatientMedicinePage(items=items, total=total, page=page, page_size=page_size)


@router.get("/medicines/{medicine_id}/images/{image_index}")
def get_medicine_image(
    medicine_id: UUID,
    image_index: int,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(UserRole.PATIENT)),
) -> Response:
    inventory = db.scalar(available_inventory_query().where(Inventory.public_id == medicine_id))
    if inventory is None:
        raise HTTPException(status_code=404, detail="Available medicine not found")
    images = db.scalars(
        select(DonationImage)
        .where(DonationImage.donation_id == inventory.donation_id)
        .order_by(DonationImage.created_at, DonationImage.id)
    ).all()
    if image_index < 0 or image_index >= len(images):
        raise HTTPException(status_code=404, detail="Medicine image not found")
    image = images[image_index]
    try:
        content = storage.read(image.storage_key)
    except OSError as exc:
        raise HTTPException(status_code=404, detail="Medicine image not found") from exc
    return Response(
        content=content,
        media_type=image.content_type,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store", "Content-Disposition": "inline"},
    )
