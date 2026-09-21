from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_roles
from app.models import (
    AuditLog,
    ClientProfile,
    ClientRequirement,
    Match,
    Quotation,
    Rfq,
    SupplierOffering,
    SupplierProfile,
    User,
)
from app.schemas import AdminSummaryResponse, AuditLogResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/summary", response_model=AdminSummaryResponse)
def admin_summary(
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("ADMIN")),
) -> AdminSummaryResponse:
    return AdminSummaryResponse(
        users=db.scalar(select(func.count(User.id))) or 0,
        clients=db.scalar(select(func.count(ClientProfile.id))) or 0,
        suppliers=db.scalar(select(func.count(SupplierProfile.id))) or 0,
        requirements=db.scalar(select(func.count(ClientRequirement.id))) or 0,
        offerings=db.scalar(select(func.count(SupplierOffering.id))) or 0,
        matches=db.scalar(select(func.count(Match.id))) or 0,
        rfqs=db.scalar(select(func.count(Rfq.id))) or 0,
        quotations=db.scalar(select(func.count(Quotation.id))) or 0,
        audit_logs=db.scalar(select(func.count(AuditLog.id))) or 0,
    )


@router.get("/audit-logs", response_model=list[AuditLogResponse])
def admin_audit_logs(
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("ADMIN")),
) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(50)).all())
