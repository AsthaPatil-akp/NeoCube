from sqlalchemy.orm import Session

from app.models import AuditLog, Notification


def write_audit(
    db: Session,
    action: str,
    user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
        )
    )


def notify(
    db: Session,
    user_id: int,
    title: str,
    message: str,
    notification_type: str = "INFO",
    related_type: str | None = None,
    related_id: int | None = None,
) -> None:
    db.add(
        Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            related_type=related_type,
            related_id=related_id,
        )
    )
