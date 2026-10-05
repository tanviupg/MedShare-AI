from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models import NotificationType


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    type: NotificationType
    title: str
    message: str
    related_entity_type: str | None
    related_entity_id: UUID | None
    is_read: bool
    created_at: datetime
    read_at: datetime | None


class NotificationPage(BaseModel):
    items: list[NotificationResponse]
    total: int
    limit: int
    offset: int
