from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.business_time import business_today
from app.models import ClinicProfile, ClinicVerificationStatus, Inventory, InventoryStatus, Notification, NotificationType, User, UserRole


def notify(db: Session, recipient_id: UUID, kind: NotificationType, title: str, message: str, entity_type: str, entity_id: UUID) -> None:
    stmt = insert(Notification).values(recipient_user_id=recipient_id, type=kind, title=title, message=message,
        related_entity_type=entity_type, related_entity_id=entity_id).on_conflict_do_nothing(index_elements=[
            "recipient_user_id", "type", "related_entity_type", "related_entity_id"])
    db.execute(stmt)


def notify_verified_pharmacists(db: Session, kind: NotificationType, title: str, message: str, entity_type: str, entity_id: UUID) -> None:
    recipients = db.scalars(select(User.id).join(ClinicProfile, ClinicProfile.user_id == User.id).where(
        User.role == UserRole.CLINIC_PHARMACIST, User.is_active.is_(True),
        ClinicProfile.verification_status == ClinicVerificationStatus.VERIFIED)).all()
    for recipient_id in recipients:
        notify(db, recipient_id, kind, title, message, entity_type, entity_id)


def notify_admins(db: Session, kind: NotificationType, title: str, message: str, entity_type: str, entity_id: UUID) -> None:
    recipients = db.scalars(select(User.id).where(User.role == UserRole.ADMIN, User.is_active.is_(True))).all()
    for recipient_id in recipients:
        notify(db, recipient_id, kind, title, message, entity_type, entity_id)


def notify_expiry_reminders(db: Session, today: date | None = None, pharmacist_id: UUID | None = None) -> int:
    """Persist idempotent expiry reminders for dashboard delivery.

    Dashboard requests pass the authenticated pharmacist ID to keep the work
    and recipient scope local to that clinic. The optional unscoped form is
    retained for administrative maintenance runs.
    """
    today = today or business_today()
    warning_date = today + timedelta(days=get_settings().expiry_warning_days)
    conditions = [
        Inventory.quantity_available > 0,
        Inventory.status.in_([InventoryStatus.AVAILABLE, InventoryStatus.RESERVED, InventoryStatus.EXPIRED]),
        Inventory.expiry_date <= warning_date,
    ]
    if pharmacist_id is not None:
        conditions.append(Inventory.pharmacist_id == pharmacist_id)
    rows = db.scalars(select(Inventory).where(*conditions)).all()
    for item in rows:
        if item.expiry_date < today or item.status == InventoryStatus.EXPIRED:
            notify(db, item.pharmacist_id, NotificationType.MEDICINE_EXPIRED, "Medicine expired", f"{item.medicine_name} has passed its expiry date.", "inventory", item.id)
        elif item.status == InventoryStatus.AVAILABLE:
            notify(db, item.pharmacist_id, NotificationType.MEDICINE_EXPIRING_SOON, "Medicine expiring soon", f"{item.medicine_name} has stock approaching its expiry date.", "inventory", item.id)
    db.commit()
    return len(rows)
