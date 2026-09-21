from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import ClientProfile, SupplierProfile, User


def load_user(db: Session, user_id: int) -> User | None:
    return db.scalar(
        select(User)
        .options(
            joinedload(User.role),
            joinedload(User.client_profile),
            joinedload(User.supplier_profile),
        )
        .where(User.id == user_id)
    )


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user = load_user(db, user_id)
    if user is None or not user.is_active:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def require_roles(*roles: str) -> Callable[..., User]:
    def _require(user: User = Depends(get_current_user)) -> User:
        if user.role.name not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        return user

    return _require


def get_client_profile(user: User) -> ClientProfile:
    if user.role.name != "CLIENT" or user.client_profile is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    return user.client_profile


def get_supplier_profile(user: User) -> SupplierProfile:
    if user.role.name != "SUPPLIER" or user.supplier_profile is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    return user.supplier_profile
