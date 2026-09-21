from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.database import get_db
from app.deps import load_user
from app.rate_limit import check_auth_rate
from app.models import ClientProfile, Role, SupplierProfile, User
from app.schemas import LoginRequest, RegisterRequest, UserResponse
from app.security import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID_CREDENTIALS = "Invalid email or password"


def user_to_response(user: User) -> UserResponse:
    company_name = None
    if user.client_profile is not None:
        company_name = user.client_profile.company_name
    elif user.supplier_profile is not None:
        company_name = user.supplier_profile.company_name

    photo_url = None
    if user.profile_photo:
        stamp = int(user.updated_at.timestamp()) if user.updated_at else user.id
        photo_url = f"/users/me/photo?v={stamp}"

    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role.name,
        full_name=user.full_name,
        phone=user.phone,
        company_name=company_name,
        profile_photo_url=photo_url,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> UserResponse:
    check_auth_rate(request)
    role = db.scalar(select(Role).where(Role.name == payload.role))
    if role is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")

    existing = db.scalar(select(User.id).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        role_id=role.id,
        full_name=payload.full_name,
        phone=payload.phone,
    )
    db.add(user)

    try:
        db.flush()
        if payload.role == "CLIENT":
            db.add(ClientProfile(user_id=user.id, company_name=payload.company_name))
        else:
            db.add(SupplierProfile(user_id=user.id, company_name=payload.company_name))
        write_audit(db, "auth.register", user.id, "user", user.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    created = load_user(db, user.id)
    assert created is not None
    return user_to_response(created)


@router.post("/login", response_model=UserResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> UserResponse:
    check_auth_rate(request)
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS)

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

    loaded = load_user(db, user.id)
    assert loaded is not None
    request.session.clear()
    request.session["user_id"] = loaded.id
    write_audit(db, "auth.login", loaded.id, "user", loaded.id)
    db.commit()
    return user_to_response(loaded)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, db: Session = Depends(get_db)) -> None:
    user_id = request.session.get("user_id")
    if user_id:
        write_audit(db, "auth.logout", user_id, "user", user_id)
        db.commit()
    request.session.clear()
