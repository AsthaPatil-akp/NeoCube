from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Category, User
from app.schemas import CategoryResponse

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
def list_categories(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[Category]:
    rows = list(
        db.scalars(
            select(Category)
            .where(Category.is_active.is_(True), Category.is_predefined.is_(True))
            .order_by(Category.name)
        ).all()
    )
    rows.sort(key=lambda item: (item.name.lower() == "other", item.name.lower()))
    return rows
