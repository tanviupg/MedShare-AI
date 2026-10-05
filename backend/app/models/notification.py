import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationType(str, enum.Enum):
    DONATION_AWAITING_REVIEW = "DONATION_AWAITING_REVIEW"
    NEW_MEDICINE_REQUEST = "NEW_MEDICINE_REQUEST"
    PRESCRIPTION_AWAITING_VERIFICATION = "PRESCRIPTION_AWAITING_VERIFICATION"
    MEDICINE_EXPIRING_SOON = "MEDICINE_EXPIRING_SOON"
    MEDICINE_EXPIRED = "MEDICINE_EXPIRED"
    WASTE_DISPOSAL_PENDING = "WASTE_DISPOSAL_PENDING"
    REQUEST_APPROVED = "REQUEST_APPROVED"
    REQUEST_REJECTED = "REQUEST_REJECTED"
    PRESCRIPTION_APPROVED = "PRESCRIPTION_APPROVED"
    PRESCRIPTION_REJECTED = "PRESCRIPTION_REJECTED"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    REQUEST_FULFILLED = "REQUEST_FULFILLED"
    DONATION_APPROVED = "DONATION_APPROVED"
    DONATION_REJECTED = "DONATION_REJECTED"


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("uq_notifications_event_recipient", "recipient_user_id", "type", "related_entity_type", "related_entity_id", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type: Mapped[NotificationType] = mapped_column(Enum(NotificationType, name="notification_type"), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    related_entity_type: Mapped[str | None] = mapped_column(String(40))
    related_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
