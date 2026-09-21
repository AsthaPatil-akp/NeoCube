from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.deps import get_current_user
from app.models import SupplierOffering, SupplierProfile, SupplierReview, User
from app.reviews import public_review_payload, review_stats
from app.schemas import ReviewPublicResponse, SupplierOfferingPublic, SupplierPublicProfile
from app.taxonomy import effective_category_name

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


def _public_offering(offering: SupplierOffering) -> SupplierOfferingPublic:
    return SupplierOfferingPublic(
        id=offering.id,
        product_offered=offering.product_offered,
        category_name=effective_category_name(offering) or (offering.category.name if offering.category else ""),
        custom_category=offering.custom_category,
        available_quantity=offering.available_quantity,
        quantity_unit=offering.quantity_unit,
        pricing_details=offering.pricing_details,
        price_amount=offering.price_amount,
        price_currency=offering.price_currency,
        price_basis=offering.price_basis,
        location=offering.location,
        delivery_capability=offering.delivery_capability,
        additional_notes=offering.additional_notes,
        status=offering.status,
    )


def _profile_payload(db: Session, profile: SupplierProfile) -> SupplierPublicProfile:
    offerings = [
        item
        for item in profile.offerings
        if item.status == "ACTIVE"
    ]
    offerings.sort(key=lambda item: item.created_at or item.id, reverse=True)
    categories: list[str] = []
    for item in offerings:
        name = effective_category_name(item) or (item.category.name if item.category else None)
        if name and name not in categories:
            categories.append(name)
    average, count = review_stats(db, profile.id)
    reviews = db.scalars(
        select(SupplierReview)
        .where(SupplierReview.supplier_id == profile.id)
        .order_by(SupplierReview.created_at.desc())
    ).all()
    return SupplierPublicProfile(
        id=profile.id,
        company_name=profile.company_name,
        categories=categories,
        offerings=[_public_offering(item) for item in offerings],
        average_rating=average,
        review_count=count,
        reviews=[ReviewPublicResponse.model_validate(public_review_payload(db, item)) for item in reviews],
    )


def _load_public_supplier(db: Session, supplier_id: int) -> SupplierProfile:
    profile = db.scalar(
        select(SupplierProfile)
        .options(
            joinedload(SupplierProfile.offerings).joinedload(SupplierOffering.category),
        )
        .where(SupplierProfile.id == supplier_id)
    )
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    return profile


@router.get("/{supplier_id}/profile", response_model=SupplierPublicProfile)
def get_supplier_profile(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SupplierPublicProfile:
    del current_user
    return _profile_payload(db, _load_public_supplier(db, supplier_id))


@router.get("/{supplier_id}/reviews", response_model=list[ReviewPublicResponse])
def list_supplier_reviews(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ReviewPublicResponse]:
    del current_user
    _load_public_supplier(db, supplier_id)
    reviews = db.scalars(
        select(SupplierReview)
        .where(SupplierReview.supplier_id == supplier_id)
        .order_by(SupplierReview.created_at.desc())
    ).all()
    return [ReviewPublicResponse.model_validate(public_review_payload(db, item)) for item in reviews]
