from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import ClinicProfile, ClinicVerificationStatus, Notification, NotificationType, User, UserRole


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
