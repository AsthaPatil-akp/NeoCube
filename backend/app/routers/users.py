from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import User, utc_now
from app.routers.auth import user_to_response
from app.schemas import ProfileUpdateRequest, UserResponse

router = APIRouter(prefix="/users", tags=["users"])

_MAX_PHOTO_BYTES = 2_000_000


def _photo_root() -> Path:
    path = Path(settings.upload_dir) / "profile-photos"
    if not path.is_absolute():
        path = Path.cwd() / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _detect_image(payload: bytes) -> tuple[str, str] | None:
    if payload.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return ".webp", "image/webp"
    return None


def _photo_path(stored_name: str) -> Path:
    return _photo_root() / Path(stored_name).name


@router.get("/me", response_model=UserResponse)
def read_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return user_to_response(current_user)


@router.put("/me", response_model=UserResponse)
def update_me(
    payload: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.phone is not None:
        current_user.phone = payload.phone
    if payload.company_name is not None:
        if current_user.client_profile is not None:
            current_user.client_profile.company_name = payload.company_name
            current_user.client_profile.updated_at = utc_now()
        elif current_user.supplier_profile is not None:
            current_user.supplier_profile.company_name = payload.company_name
            current_user.supplier_profile.updated_at = utc_now()

    current_user.updated_at = utc_now()
    write_audit(db, "profile.update", current_user.id, "user", current_user.id)
    db.commit()
    db.refresh(current_user)
    return user_to_response(current_user)


@router.post("/me/photo", response_model=UserResponse)
async def upload_profile_photo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Photo is empty")
    if len(payload) > _MAX_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Photo is too large")
    detected = _detect_image(payload)
    if detected is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Photo must be a JPEG, PNG, or WebP image")
    extension, _media_type = detected
    stored_name = f"user-{current_user.id}{extension}"
    previous = current_user.profile_photo
    destination = _photo_path(stored_name)
    destination.write_bytes(payload)
    if previous and previous != stored_name:
        old_path = _photo_path(previous)
        if old_path.exists():
            old_path.unlink()
    current_user.profile_photo = stored_name
    current_user.updated_at = utc_now()
    write_audit(db, "profile.photo", current_user.id, "user", current_user.id)
    db.commit()
    db.refresh(current_user)
    return user_to_response(current_user)


@router.get("/me/photo")
def read_profile_photo(current_user: User = Depends(get_current_user)) -> FileResponse:
    if not current_user.profile_photo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No profile photo")
    path = _photo_path(current_user.profile_photo)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No profile photo")
    media_types = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
    media_type = media_types.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type)
