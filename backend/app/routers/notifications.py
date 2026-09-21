from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.database import get_db
from app.deps import get_current_user
from app.models import Notification, User
from app.schemas import ClearNotificationsRequest, NotificationResponse

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationResponse])
def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.user_id == current_user.id)
            .order_by(Notification.created_at.desc())
        ).all()
    )


@router.post("/clear-all", status_code=status.HTTP_204_NO_CONTENT)
def clear_all_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    db.execute(delete(Notification).where(Notification.user_id == current_user.id))
    write_audit(db, "notification.clear_all", current_user.id, "notification", None)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/clear-selected", status_code=status.HTTP_204_NO_CONTENT)
def clear_selected_notifications(
    payload: ClearNotificationsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    unique_ids = sorted({int(item) for item in payload.ids})
    owned = list(
        db.scalars(
            select(Notification.id).where(
                Notification.user_id == current_user.id,
                Notification.id.in_(unique_ids),
            )
        ).all()
    )
    if len(owned) != len(unique_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    db.execute(
        delete(Notification).where(
            Notification.user_id == current_user.id,
            Notification.id.in_(unique_ids),
        )
    )
    write_audit(db, "notification.clear_selected", current_user.id, "notification", None)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{notification_id}/read", response_model=NotificationResponse)
def mark_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Notification:
    item = db.get(Notification, notification_id)
    if item is None or item.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    item.is_read = True
    db.commit()
    db.refresh(item)
    return item
