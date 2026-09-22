"""Inference helpers for AI Product Finder search."""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import ProductImageEmbedding, SupplierOffering, SupplierProfile, User
from app.vision.config import MIN_VISUAL_SIMILARITY
from app.vision.embeddings import (
    VisionUnavailableError,
    cosine_similarity,
    deserialize_embedding,
    extract_image_embedding,
)
from app.vision.model_store import load_vision_model


@dataclass
class VisualMatch:
    offering: SupplierOffering
    visual_similarity: float
    model_version: str


def count_indexed_supplier_images(db: Session) -> int:
    bundle = load_vision_model()
    if bundle is None:
        return 0
    return int(
        db.scalar(
            select(func.count())
            .select_from(ProductImageEmbedding)
            .join(SupplierOffering, ProductImageEmbedding.supplier_offering_id == SupplierOffering.id)
            .join(SupplierProfile, SupplierOffering.supplier_id == SupplierProfile.id)
            .join(User, SupplierProfile.user_id == User.id)
            .where(
                ProductImageEmbedding.model_version == bundle.version,
                SupplierOffering.status == "ACTIVE",
                User.is_active.is_(True),
                SupplierOffering.product_image_path.is_not(None),
            )
        )
        or 0
    )


def search_by_image(db: Session, payload: bytes, *, limit: int = 20) -> list[VisualMatch]:
    bundle = load_vision_model()
    if bundle is None:
        raise VisionUnavailableError(
            "AI Product Finder is currently unavailable because the vision model has not been trained/deployed."
        )
    query_embedding = extract_image_embedding(payload, bundle)
    rows = db.scalars(
        select(ProductImageEmbedding)
        .options(
            joinedload(ProductImageEmbedding.offering).joinedload(SupplierOffering.category),
            joinedload(ProductImageEmbedding.offering)
            .joinedload(SupplierOffering.supplier)
            .joinedload(SupplierProfile.user),
        )
        .join(SupplierOffering, ProductImageEmbedding.supplier_offering_id == SupplierOffering.id)
        .join(SupplierProfile, SupplierOffering.supplier_id == SupplierProfile.id)
        .join(User, SupplierProfile.user_id == User.id)
        .where(
            ProductImageEmbedding.model_version == bundle.version,
            SupplierOffering.status == "ACTIVE",
            User.is_active.is_(True),
            SupplierOffering.product_image_path.is_not(None),
        )
    ).unique().all()

    matches: list[VisualMatch] = []
    for row in rows:
        offering = row.offering
        if offering is None:
            continue
        try:
            supplier_vec = deserialize_embedding(row.embedding)
            score = cosine_similarity(query_embedding, supplier_vec)
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
        if score < MIN_VISUAL_SIMILARITY:
            continue
        matches.append(
            VisualMatch(offering=offering, visual_similarity=score, model_version=row.model_version)
        )
    matches.sort(key=lambda item: item.visual_similarity, reverse=True)
    return matches[:limit]
