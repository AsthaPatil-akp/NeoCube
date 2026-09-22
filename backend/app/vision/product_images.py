"""Filesystem helpers for optional supplier product images."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import HTTPException, status

from app.config import settings

SOURCE_DIRECT_UPLOAD = "DIRECT_UPLOAD"
SOURCE_DOCUMENT_EXTRACTION = "DOCUMENT_EXTRACTION"
VALID_SOURCES = {SOURCE_DIRECT_UPLOAD, SOURCE_DOCUMENT_EXTRACTION}


def product_image_root() -> Path:
    path = Path(settings.upload_dir) / "product-images"
    if not path.is_absolute():
        path = Path.cwd() / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def candidate_root(folder_key: int | str) -> Path:
    path = Path(settings.upload_dir) / "product-image-candidates" / str(folder_key)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def document_candidate_key(document_id: int) -> str:
    return f"doc-{int(document_id)}"


def detect_product_image(payload: bytes) -> tuple[str, str] | None:
    if payload.startswith(b"\xff\xd8\xff"):
        return ".jpg", "image/jpeg"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png", "image/png"
    if len(payload) >= 12 and payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return ".webp", "image/webp"
    return None


def validate_product_image_payload(payload: bytes) -> tuple[str, str]:
    if not payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image is empty")
    if len(payload) > settings.max_product_image_bytes:
        raise HTTPException(status_code=413, detail="Image is too large")
    detected = detect_product_image(payload)
    if detected is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Image must be a JPEG, PNG, or WebP file",
        )
    from app.vision.preprocessing import load_rgb_image

    try:
        load_rgb_image(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return detected


def store_product_image(offering_id: int, payload: bytes, extension: str) -> str:
    stored_name = f"offering-{offering_id}-{uuid.uuid4().hex}{extension}"
    destination = product_image_root() / stored_name
    destination.write_bytes(payload)
    return stored_name


def delete_product_image_file(stored_name: str | None) -> None:
    if not stored_name:
        return
    path = product_image_root() / Path(stored_name).name
    if path.exists():
        path.unlink()


def resolve_product_image_path(stored_name: str) -> Path:
    return product_image_root() / Path(stored_name).name


def clear_candidates(folder_key: int | str) -> None:
    root = candidate_root(folder_key)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


def store_candidate(folder_key: int | str, payload: bytes, extension: str = ".png") -> str:
    candidate_id = uuid.uuid4().hex
    path = candidate_root(folder_key) / f"{candidate_id}{extension}"
    path.write_bytes(payload)
    return candidate_id


def resolve_candidate_path(folder_key: int | str, candidate_id: str) -> Path:
    safe_id = Path(candidate_id).name
    if safe_id != candidate_id or not all(c.isalnum() for c in safe_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid candidate id")
    matches = list(candidate_root(folder_key).glob(f"{safe_id}.*"))
    if not matches:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate image not found")
    return matches[0]
