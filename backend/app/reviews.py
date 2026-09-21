from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ClientProfile, Rfq, SupplierReview


def order_is_completed(rfq: Rfq) -> bool:
    track = getattr(rfq, "track", None)
    if track is not None and bool(track.completed):
        return True
    if rfq.status == "RECEIVED":
        return True
    return False


def review_stats(db: Session, supplier_id: int) -> tuple[float | None, int]:
    total, count = db.execute(
        select(func.coalesce(func.sum(SupplierReview.rating), 0), func.count(SupplierReview.id)).where(
            SupplierReview.supplier_id == supplier_id
        )
    ).one()
    if not count:
        return None, 0
    average = round(float(total) / float(count), 1)
    return average, int(count)


def reviewer_display_name(db: Session, client_user_id: int) -> str:
    company = db.scalar(select(ClientProfile.company_name).where(ClientProfile.user_id == client_user_id))
    if company and str(company).strip():
        return str(company).strip()
    return "Verified Client"


def public_review_payload(db: Session, review: SupplierReview) -> dict:
    return {
        "id": review.id,
        "rating": review.rating,
        "feedback": review.feedback,
        "client_name": reviewer_display_name(db, review.client_user_id),
        "verified": True,
        "created_at": review.created_at,
    }


def own_review_payload(review: SupplierReview) -> dict:
    return {
        "id": review.id,
        "rfq_id": review.rfq_id,
        "rating": review.rating,
        "feedback": review.feedback,
        "created_at": review.created_at,
    }
