from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.config import settings
from app.database import get_db
from app.deps import require_roles
from app.extract import ExtractError, detect_kind, dumps_extracted, extract_fields, extract_text
from app.models import Category, RequirementDocument, SupplierDocument, User
from app.schemas import (
    DocumentExtractResponse,
    ExtractedFields,
    ExtractProductImagesResponse,
    ProductImageCandidate,
)
from app.vision.document_images import extract_embedded_images
from app.vision.product_images import (
    clear_candidates,
    document_candidate_key,
    resolve_candidate_path,
    store_candidate,
)

logger = logging.getLogger("neocube")
router = APIRouter(prefix="/documents", tags=["documents"])


def _safe_original_name(filename: str | None) -> str:
    raw = filename or "upload"
    if ".." in raw.replace("\\", "/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    cleaned = Path(raw).name
    if not cleaned or cleaned in {".", ".."}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    return cleaned


def _upload_root() -> Path:
    path = Path(settings.upload_dir)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _to_response(document: RequirementDocument) -> DocumentExtractResponse:
    extracted = ExtractedFields()
    if document.extracted_json:
        try:
            extracted = ExtractedFields.model_validate_json(document.extracted_json)
        except (ValueError, json.JSONDecodeError):
            extracted = ExtractedFields()
    return DocumentExtractResponse(
        id=document.id,
        original_filename=document.original_filename,
        file_type=document.file_type,
        processing_status=document.processing_status,
        extracted=extracted,
        error_message=document.error_message,
    )


@router.post("", response_model=DocumentExtractResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT")),
) -> DocumentExtractResponse:
    payload = await file.read()
    if len(payload) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File is too large")
    original = _safe_original_name(file.filename)
    try:
        kind = detect_kind(original, file.content_type, payload)
        text = extract_text(kind, payload)
    except ExtractError as exc:
        document = RequirementDocument(
            user_id=current_user.id,
            original_filename=original,
            stored_name="",
            file_type=Path(original).suffix.lower().lstrip(".") or "unknown",
            file_size=len(payload),
            processing_status="FAILED",
            error_message=exc.message,
        )
        db.add(document)
        db.flush()
        write_audit(db, "document.upload_failed", current_user.id, "requirement_document", document.id)
        db.commit()
        db.refresh(document)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc

    stored_name = f"{uuid.uuid4().hex}.{kind}"
    stored_path = _upload_root() / stored_name
    stored_path.write_bytes(payload)

    categories = list(
        db.execute(
            select(Category.id, Category.name).where(
                Category.is_active.is_(True),
                Category.is_predefined.is_(True),
            )
        ).all()
    )
    fields = extract_fields(text, [(row[0], row[1]) for row in categories])
    if not fields.get("company_name"):
        fields["company_name"] = (
            current_user.client_profile.company_name if current_user.client_profile else None
        )

    document = RequirementDocument(
        user_id=current_user.id,
        original_filename=original,
        stored_name=stored_name,
        file_type=kind,
        file_size=len(payload),
        processing_status="EXTRACTED",
        extracted_json=dumps_extracted(fields),
    )
    db.add(document)
    db.flush()
    write_audit(db, "document.upload", current_user.id, "requirement_document", document.id)
    logger.info("Processed requirement document %s for user %s", document.id, current_user.id)
    db.commit()
    db.refresh(document)
    return _to_response(document)


@router.get("/{document_id}", response_model=DocumentExtractResponse)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT")),
) -> DocumentExtractResponse:
    document = db.get(RequirementDocument, document_id)
    if document is None or document.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return _to_response(document)


supplier_router = APIRouter(prefix="/supplier-documents", tags=["supplier-documents"])


def _supplier_doc_response(document: SupplierDocument) -> DocumentExtractResponse:
    extracted = ExtractedFields()
    if document.extracted_json:
        try:
            extracted = ExtractedFields.model_validate_json(document.extracted_json)
        except (ValueError, json.JSONDecodeError):
            extracted = ExtractedFields()
    return DocumentExtractResponse(
        id=document.id,
        original_filename=document.original_filename,
        file_type=document.file_type,
        processing_status=document.processing_status,
        extracted=extracted,
        error_message=document.error_message,
    )


@supplier_router.post("", response_model=DocumentExtractResponse, status_code=status.HTTP_201_CREATED)
async def upload_supplier_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("SUPPLIER")),
) -> DocumentExtractResponse:
    payload = await file.read()
    if len(payload) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File is too large")
    original = _safe_original_name(file.filename)
    try:
        kind = detect_kind(original, file.content_type, payload)
        text = extract_text(kind, payload)
    except ExtractError as exc:
        document = SupplierDocument(
            user_id=current_user.id,
            original_filename=original,
            stored_name="",
            file_type=Path(original).suffix.lower().lstrip(".") or "unknown",
            file_size=len(payload),
            processing_status="FAILED",
            error_message=exc.message,
        )
        db.add(document)
        db.flush()
        write_audit(db, "document.upload_failed", current_user.id, "supplier_document", document.id)
        db.commit()
        db.refresh(document)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc

    stored_name = f"{uuid.uuid4().hex}.{kind}"
    stored_path = _upload_root() / stored_name
    stored_path.write_bytes(payload)
    categories = list(
        db.execute(
            select(Category.id, Category.name).where(
                Category.is_active.is_(True),
                Category.is_predefined.is_(True),
            )
        ).all()
    )
    fields = extract_fields(text, [(row[0], row[1]) for row in categories])
    if not fields.get("company_name") and current_user.supplier_profile is not None:
        fields["company_name"] = current_user.supplier_profile.company_name
    document = SupplierDocument(
        user_id=current_user.id,
        original_filename=original,
        stored_name=stored_name,
        file_type=kind,
        file_size=len(payload),
        processing_status="EXTRACTED",
        extracted_json=dumps_extracted(fields),
    )
    db.add(document)
    db.flush()
    write_audit(db, "document.upload", current_user.id, "supplier_document", document.id)
    logger.info("Processed supplier document %s for user %s", document.id, current_user.id)
    db.commit()
    db.refresh(document)
    return _supplier_doc_response(document)


@supplier_router.get("/{document_id}", response_model=DocumentExtractResponse)
def get_supplier_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("SUPPLIER")),
) -> DocumentExtractResponse:
    document = db.get(SupplierDocument, document_id)
    if document is None or document.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return _supplier_doc_response(document)


def _owned_supplier_document(db: Session, current_user: User, document_id: int) -> SupplierDocument:
    document = db.get(SupplierDocument, document_id)
    if document is None or document.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@supplier_router.post("/{document_id}/extract-product-images", response_model=ExtractProductImagesResponse)
def extract_supplier_document_images(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("SUPPLIER")),
) -> ExtractProductImagesResponse:
    if not settings.ai_product_finder_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI Product Finder is disabled")
    document = _owned_supplier_document(db, current_user, document_id)
    if not document.stored_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Document file is missing")
    path = _upload_root() / Path(document.stored_name).name
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Document file is missing")
    try:
        images = extract_embedded_images(document.file_type, path.read_bytes())
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to extract images from this document",
        ) from exc

    folder_key = document_candidate_key(document.id)
    clear_candidates(folder_key)
    candidates: list[ProductImageCandidate] = []
    for image in images:
        candidate_id = store_candidate(folder_key, image.payload, image.extension)
        candidates.append(
            ProductImageCandidate(
                candidate_id=candidate_id,
                preview_url=f"/supplier-documents/{document.id}/product-image-candidates/{candidate_id}",
                width=image.width,
                height=image.height,
                source_hint=image.source_hint,
            )
        )
    write_audit(db, "document.extract_product_images", current_user.id, "supplier_document", document.id)
    db.commit()
    message = None
    if not candidates:
        message = "No product image was found in this document. You can upload a product image manually."
    return ExtractProductImagesResponse(document_id=document.id, candidates=candidates, message=message)


@supplier_router.get("/{document_id}/product-image-candidates/{candidate_id}")
def read_supplier_document_candidate(
    document_id: int,
    candidate_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("SUPPLIER")),
) -> FileResponse:
    if not settings.ai_product_finder_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI Product Finder is disabled")
    _owned_supplier_document(db, current_user, document_id)
    path = resolve_candidate_path(document_candidate_key(document_id), candidate_id)
    return FileResponse(path, media_type="image/png")
