from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.models import Notification, User
from app.schemas.notification import NotificationPage, NotificationResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationPage)
def list_notifications(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), unread_only: bool = False,
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Notification).where(Notification.recipient_user_id == user.id)
    count = select(func.count(Notification.id)).where(Notification.recipient_user_id == user.id)
    if unread_only:
        stmt, count = stmt.where(Notification.is_read.is_(False)), count.where(Notification.is_read.is_(False))
    items = db.scalars(stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).offset(offset)).all()
    return {"items": items, "total": db.scalar(count) or 0, "limit": limit, "offset": offset}


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    count = db.scalar(select(func.count(Notification.id)).where(Notification.recipient_user_id == user.id, Notification.is_read.is_(False)))
    return {"count": count or 0}


@router.post("/{notification_id}/read", response_model=NotificationResponse)
def mark_read(notification_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.recipient_user_id == user.id).with_for_update())
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    if not row.is_read:
        row.is_read, row.read_at = True, datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
    return row


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    result = db.execute(update(Notification).where(Notification.recipient_user_id == user.id, Notification.is_read.is_(False)).values(is_read=True, read_at=datetime.now(timezone.utc)))
    db.commit()
    return {"updated": result.rowcount or 0}
