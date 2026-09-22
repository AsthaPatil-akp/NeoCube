"""Persist and refresh supplier product-image embeddings."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ProductImageEmbedding, SupplierOffering, utc_now
from app.vision.embeddings import VisionUnavailableError, extract_image_embedding, serialize_embedding
from app.vision.model_store import load_vision_model


def _resolve_image_path(relative_or_name: str) -> Path:
    from app.config import settings

    root = Path(settings.upload_dir)
    if not root.is_absolute():
        root = Path.cwd() / root
    product_root = root / "product-images"
    return product_root / Path(relative_or_name).name


def upsert_offering_embedding(db: Session, offering: SupplierOffering) -> ProductImageEmbedding | None:
    """Generate and store an embedding for the offering's product image.

    Returns None when no image is present. Raises VisionUnavailableError when the
    model artifact is missing (callers may choose to store the image without indexing).
    """
    if not offering.product_image_path:
        existing = db.scalar(
            select(ProductImageEmbedding).where(ProductImageEmbedding.supplier_offering_id == offering.id)
        )
        if existing is not None:
            db.delete(existing)
        return None

    bundle = load_vision_model()
    if bundle is None:
        raise VisionUnavailableError(
            "AI Product Finder is currently unavailable because the vision model has not been trained/deployed."
        )

    path = _resolve_image_path(offering.product_image_path)
    if not path.exists():
        raise FileNotFoundError("Product image file is missing on disk")

    payload = path.read_bytes()
    vector = extract_image_embedding(payload, bundle)
    raw = serialize_embedding(vector)

    existing = db.scalar(
        select(ProductImageEmbedding).where(ProductImageEmbedding.supplier_offering_id == offering.id)
    )
    if existing is None:
        existing = ProductImageEmbedding(
            supplier_offering_id=offering.id,
            model_version=bundle.version,
            embedding=raw,
        )
        db.add(existing)
    else:
        existing.model_version = bundle.version
        existing.embedding = raw
        existing.updated_at = utc_now()
    return existing


def clear_offering_embedding(db: Session, offering_id: int) -> None:
    existing = db.scalar(
        select(ProductImageEmbedding).where(ProductImageEmbedding.supplier_offering_id == offering_id)
    )
    if existing is not None:
        db.delete(existing)
