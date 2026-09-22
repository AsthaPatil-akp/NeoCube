from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import N8nEmittedEvent

router = APIRouter(prefix="/n8n", tags=["n8n"])


def _require_callback_token(x_n8n_callback_token: str | None) -> None:
    expected = (settings.n8n_callback_token or "").strip()
    if not expected:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not x_n8n_callback_token or x_n8n_callback_token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid callback token")


class RecordProcessedEventRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=160)
    event_type: str | None = None


@router.get("/events/{event_id}")
def get_processed_event(
    event_id: str,
    db: Session = Depends(get_db),
    x_n8n_callback_token: str | None = Header(default=None),
) -> dict:
    _require_callback_token(x_n8n_callback_token)
    row = db.get(N8nEmittedEvent, event_id)
    if row is None:
        return {"exists": False, "event_id": event_id, "duplicate_status": "new"}
    return {
        "exists": True,
        "event_id": row.event_id,
        "event_type": row.event_type,
        "duplicate_status": "duplicate",
    }


@router.post("/events", status_code=status.HTTP_200_OK)
def record_processed_event(
    body: RecordProcessedEventRequest,
    db: Session = Depends(get_db),
    x_n8n_callback_token: str | None = Header(default=None),
) -> dict:
    _require_callback_token(x_n8n_callback_token)
    event_id = body.event_id.strip()
    if not event_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="missing_event_id")
    existing = db.get(N8nEmittedEvent, event_id)
    if existing is None:
        db.add(N8nEmittedEvent(event_id=event_id, event_type=body.event_type))
        db.commit()
    return {"exists": True, "event_id": event_id, "duplicate_status": "duplicate"}
