from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Inventory,
    InventoryStatus,
    MedicineRequest,
    MedicineRequestStatus,
    Notification,
    NotificationType,
)
from app.services.business_time import business_today
from app.services.notifications import notify


EXPIRED_RESERVATION_REASON = "Reserved medicine no longer meets the minimum remaining shelf-life requirement."


def minimum_eligible_expiry_date(today: date | None = None) -> date:
    today = today or business_today()
    return today + timedelta(days=get_settings().minimum_remaining_shelf_life_days)


def expiry_is_eligible(expiry_date: date, today: date | None = None) -> bool:
    return expiry_date >= minimum_eligible_expiry_date(today)


def expiry_warning_days() -> int:
    return get_settings().expiry_warning_days


def synchronize_expired_reservations(
    db: Session,
    pharmacist_id: UUID | None = None,
    patient_id: UUID | None = None,
    request_id: UUID | None = None,
    today: date | None = None,
) -> int:
    """Release active reservations that no longer meet the shelf-life policy."""
    today = today or business_today()
    minimum_date = minimum_eligible_expiry_date(today)
    expired_inventory = select(Inventory).where(
        Inventory.expiry_date < today,
        Inventory.status.in_([InventoryStatus.AVAILABLE, InventoryStatus.RESERVED]),
    )
    if pharmacist_id is not None:
        expired_inventory = expired_inventory.where(Inventory.pharmacist_id == pharmacist_id)
    for item in db.scalars(expired_inventory.with_for_update()).all():
        item.status = InventoryStatus.EXPIRED

    requests = select(MedicineRequest).join(
        Inventory, Inventory.id == MedicineRequest.inventory_id
    ).where(
        Inventory.expiry_date < minimum_date,
        MedicineRequest.inventory_reserved.is_(True),
        MedicineRequest.status.in_([MedicineRequestStatus.PENDING, MedicineRequestStatus.APPROVED]),
    )
    if pharmacist_id is not None:
        requests = requests.where(Inventory.pharmacist_id == pharmacist_id)
    if patient_id is not None:
        requests = requests.where(MedicineRequest.patient_id == patient_id)
    if request_id is not None:
        requests = requests.where(MedicineRequest.id == request_id)

    changed = 0
    for request in db.scalars(requests.order_by(MedicineRequest.id).with_for_update()).all():
        inventory = db.scalar(
            select(Inventory).where(Inventory.id == request.inventory_id).with_for_update()
        )
        if (inventory is None or not request.inventory_reserved
                or request.status not in (MedicineRequestStatus.PENDING, MedicineRequestStatus.APPROVED)
                or inventory.expiry_date >= minimum_date):
            continue

        inventory.quantity_available += request.requested_quantity
        if inventory.expiry_date < today:
            inventory.status = InventoryStatus.EXPIRED
        request.inventory_reserved = False
        request.status = MedicineRequestStatus.REJECTED
        request.rejection_reason = EXPIRED_RESERVATION_REASON
        request.reviewed_at = datetime.now(timezone.utc)
        request.pickup_code = None
        if inventory.status == InventoryStatus.RESERVED:
            other_reservation = db.scalar(select(MedicineRequest.id).where(
                MedicineRequest.inventory_id == inventory.id,
                MedicineRequest.id != request.id,
                MedicineRequest.inventory_reserved.is_(True),
                MedicineRequest.status.in_([MedicineRequestStatus.PENDING, MedicineRequestStatus.APPROVED]),
            ).limit(1))
            if other_reservation is None:
                inventory.status = InventoryStatus.AVAILABLE
        ready_notification = db.scalar(select(Notification).where(
            Notification.recipient_user_id == request.patient_id,
            Notification.type == NotificationType.READY_FOR_PICKUP,
            Notification.related_entity_type == "medicine_request",
            Notification.related_entity_id == request.id,
        ).with_for_update())
        if ready_notification is not None:
            db.delete(ready_notification)
        notify(
            db,
            request.patient_id,
            NotificationType.REQUEST_REJECTED,
            "Medicine reservation released",
            "The reserved medicine no longer meets the minimum remaining shelf-life requirement. Contact the clinic if you need help.",
            "medicine_request",
            request.id,
        )
        changed += 1

    db.commit()
    return changed
