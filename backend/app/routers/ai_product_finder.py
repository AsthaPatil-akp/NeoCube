"""AI Product Finder API — isolated from requirement-based matching."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.audit import write_audit
from app.config import settings
from app.database import get_db
from app.deps import require_roles
from app.models import User
from app.schemas import AiProductFinderStatus, AiProductFinderSearchResponse, AiVisualMatchResult
from app.vision.embeddings import VisionUnavailableError
from app.vision.inference import count_indexed_supplier_images, search_by_image
from app.vision.model_store import load_vision_model
from app.vision.product_images import validate_product_image_payload

router = APIRouter(prefix="/ai-product-finder", tags=["ai-product-finder"])


def _ensure_enabled() -> None:
    if not settings.ai_product_finder_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI Product Finder is disabled")


@router.get("/status", response_model=AiProductFinderStatus)
def product_finder_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT", "SUPPLIER", "ADMIN")),
) -> AiProductFinderStatus:
    _ensure_enabled()
    bundle = load_vision_model()
    indexed = count_indexed_supplier_images(db) if bundle else 0
    return AiProductFinderStatus(
        enabled=True,
        model_available=bundle is not None,
        model_version=None if bundle is None else bundle.version,
        embedding_dimension=None if bundle is None else bundle.embedding_dim,
        number_of_indexed_supplier_images=indexed,
        message=(
            None
            if bundle is not None
            else "AI Product Finder is currently unavailable because the vision model has not been trained/deployed."
        ),
    )


@router.post("/search", response_model=AiProductFinderSearchResponse)
async def product_finder_search(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT")),
) -> AiProductFinderSearchResponse:
    _ensure_enabled()
    payload = await file.read()
    validate_product_image_payload(payload)

    try:
        matches = search_by_image(db, payload)
    except VisionUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Inference error while running the vision model",
        ) from exc

    write_audit(db, "ai_product_finder.search", current_user.id, "ai_product_finder", None)
    db.commit()

    if not matches:
        indexed = count_indexed_supplier_images(db)
        message = (
            "No supplier product images are currently available for visual search."
            if indexed == 0
            else "No visually similar suppliers were found."
        )
        return AiProductFinderSearchResponse(results=[], message=message, result_count=0)

    results = [
        AiVisualMatchResult(
            supplier_id=item.offering.supplier_id,
            offering_id=item.offering.id,
            supplier_name=item.offering.supplier_name,
            product_offered=item.offering.product_offered,
            category_name=item.offering.category.name if item.offering.category else "",
            location=item.offering.location,
            available_quantity=item.offering.available_quantity,
            quantity_unit=item.offering.quantity_unit,
            visual_similarity=round(item.visual_similarity * 100, 1),
            model_version=item.model_version,
            product_image_url=f"/offerings/{item.offering.id}/product-image",
        )
        for item in matches
    ]
    return AiProductFinderSearchResponse(
        results=results,
        message=None,
        result_count=len(results),
    )
