from fastapi import APIRouter, Depends, HTTPException, Response, status
import json
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.audit import write_audit
from app.commerce import format_pricing_details, normalize_basis, normalize_currency, parse_money
from app.database import get_db
from app.deps import get_supplier_profile, require_roles
from app.matching import refresh_offering_matches
from app.webhooks import emit_n8n
from app.models import (
    Category,
    ClientRequirement,
    Match,
    SupplierDocument,
    SupplierOffering,
    SupplierProfile,
    User,
    utc_now,
)
from app.schemas import (
    OfferingCreateRequest,
    OfferingResponse,
    OfferingUpdateRequest,
    RequirementMatchSummary,
)
from app.states import EDITABLE_OFFERING_STATUSES, OFFERING_TRANSITIONS, can_transition
from app.taxonomy import resolve_category, stored_custom_category

router = APIRouter(prefix="/offerings", tags=["offerings"])


def _get_active_category(db: Session, category_id: int) -> Category:
    category = db.get(Category, category_id)
    if category is None or not category.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category")
    return category


def _owned_offering(db: Session, user: User, offering_id: int) -> SupplierOffering:
    profile = get_supplier_profile(user)
    offering = db.scalar(
        select(SupplierOffering)
        .options(
            joinedload(SupplierOffering.category),
            joinedload(SupplierOffering.supplier).joinedload(SupplierProfile.user),
            joinedload(SupplierOffering.matches)
            .joinedload(Match.requirement)
            .joinedload(ClientRequirement.category),
        )
        .where(SupplierOffering.id == offering_id)
    )
    if offering is None or offering.supplier_id != profile.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offering not found")
    return offering


def _resolved_pricing(payload, existing: SupplierOffering | None = None) -> tuple[str, int | None, str | None, str | None]:
    details = getattr(payload, "pricing_details", None)
    amount = getattr(payload, "price_amount", None)
    currency = normalize_currency(getattr(payload, "price_currency", None))
    basis = normalize_basis(getattr(payload, "price_basis", None))
    parsed = parse_money(details) if details else parse_money(None)
    existing_parsed = parse_money(existing.pricing_details) if existing is not None else parse_money(None)
    if amount is None:
        amount = parsed.amount if parsed.amount is not None else existing_parsed.amount
        if amount is None and existing is not None:
            amount = existing.price_amount
    if currency is None:
        currency = parsed.currency or existing_parsed.currency or (existing.price_currency if existing is not None else None)
    if basis is None:
        basis = parsed.basis or existing_parsed.basis or (existing.price_basis if existing is not None else None)
    generated = format_pricing_details(amount, currency, basis)
    if generated:
        details = generated
    elif not details:
        details = existing.pricing_details if existing is not None else ""
    if not details:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pricing details are required")
    return details, amount, currency, basis


def to_response(offering: SupplierOffering) -> OfferingResponse:
    matches = []
    ranked = sorted(offering.matches, key=lambda row: row.final_score or 0, reverse=True)
    for item in ranked:
        requirement = item.requirement
        reasons = []
        if item.explanation:
            try:
                parsed = json.loads(item.explanation)
                reasons = parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                reasons = []
        matches.append(
            RequirementMatchSummary(
                id=item.id,
                requirement_id=requirement.id,
                product_requirement=requirement.product_requirement,
                company_name=requirement.company_name,
                location=requirement.location,
                quantity=requirement.quantity,
                category_name=requirement.category.name if requirement.category else offering.category.name,
                status=requirement.status,
                semantic_score=item.semantic_score,
                ml_score=item.ml_score,
                final_score=item.final_score,
                match_status=item.match_status,
                explanation=reasons,
            )
        )
    return OfferingResponse(
        id=offering.id,
        supplier_name=offering.supplier_name,
        product_offered=offering.product_offered,
        category_id=offering.category_id,
        category_name=offering.category.name,
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
        match_count=len(offering.matches),
        created_at=offering.created_at,
        updated_at=offering.updated_at,
        matches=matches,
    )


@router.get("", response_model=list[OfferingResponse])
def list_offerings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("SUPPLIER")),
) -> list[OfferingResponse]:
    profile = get_supplier_profile(current_user)
    rows = db.scalars(
        select(SupplierOffering)
        .options(
            joinedload(SupplierOffering.category),
            joinedload(SupplierOffering.matches)
            .joinedload(Match.requirement)
            .joinedload(ClientRequirement.category),
        )
        .where(SupplierOffering.supplier_id == profile.id)
        .order_by(SupplierOffering.created_at.desc())
    ).unique().all()
    return [to_response(row) for row in rows]


@router.post("", response_model=OfferingResponse, status_code=status.HTTP_201_CREATED)
def create_offering(
    payload: OfferingCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("SUPPLIER")),
) -> OfferingResponse:
    profile = get_supplier_profile(current_user)
    category = resolve_category(db, payload.category_id, payload.custom_category)
    if payload.status == "ACTIVE" and payload.available_quantity <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active offerings need quantity greater than 0")

    details, amount, currency, basis = _resolved_pricing(payload)
    offering = SupplierOffering(
        supplier_id=profile.id,
        category_id=category.id,
        custom_category=stored_custom_category(category),
        supplier_name=payload.supplier_name,
        product_offered=payload.product_offered,
        available_quantity=payload.available_quantity,
        quantity_unit=payload.quantity_unit,
        pricing_details=details,
        price_amount=amount,
        price_currency=currency,
        price_basis=basis,
        location=payload.location,
        delivery_capability=payload.delivery_capability,
        additional_notes=payload.additional_notes,
        status=payload.status,
    )
    db.add(offering)
    db.flush()
    if payload.document_id is not None:
        document = db.get(SupplierDocument, payload.document_id)
        if document is None or document.user_id != current_user.id or document.offering_id is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid document")
        document.offering_id = offering.id
        document.processing_status = "CONFIRMED"
    write_audit(db, "offering.create", current_user.id, "supplier_offering", offering.id)
    pending: list[dict] = []
    if offering.status == "ACTIVE":
        pending = refresh_offering_matches(db, offering)
    db.commit()
    emit_n8n(pending)
    return to_response(_owned_offering(db, current_user, offering.id))


@router.get("/{offering_id}", response_model=OfferingResponse)
def get_offering(
    offering_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("SUPPLIER")),
) -> OfferingResponse:
    return to_response(_owned_offering(db, current_user, offering_id))


@router.put("/{offering_id}", response_model=OfferingResponse)
def update_offering(
    offering_id: int,
    payload: OfferingUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("SUPPLIER")),
) -> OfferingResponse:
    offering = _owned_offering(db, current_user, offering_id)
    data = payload.model_dump(exclude_unset=True)
    new_status = data.pop("status", None)

    if data and offering.status not in EDITABLE_OFFERING_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This offering can no longer be edited")

    if "category_id" in data or "custom_category" in data:
        category = resolve_category(
            db,
            data.get("category_id", offering.category_id),
            data.get("custom_category", offering.custom_category),
        )
        data["category_id"] = category.id
        data["custom_category"] = stored_custom_category(category)

    if any(key in data for key in ("pricing_details", "price_amount", "price_currency", "price_basis")):
        class _Price:
            pricing_details = data.get("pricing_details", offering.pricing_details)
            price_amount = data.get("price_amount", offering.price_amount)
            price_currency = data.get("price_currency", offering.price_currency)
            price_basis = data.get("price_basis", offering.price_basis)

        details, amount, currency, basis = _resolved_pricing(_Price(), offering)
        data["pricing_details"] = details
        data["price_amount"] = amount
        data["price_currency"] = currency
        data["price_basis"] = basis

    for field, value in data.items():
        setattr(offering, field, value)

    if new_status is not None:
        if not can_transition(OFFERING_TRANSITIONS, offering.status, new_status):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invalid status transition")
        offering.status = new_status

    if offering.status == "ACTIVE" and offering.available_quantity <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Active offerings need quantity greater than 0")

    offering.updated_at = utc_now()
    write_audit(db, "offering.update", current_user.id, "supplier_offering", offering.id)
    pending: list[dict] = []
    if offering.status == "ACTIVE":
        pending = refresh_offering_matches(db, offering)
    db.commit()
    emit_n8n(pending)
    return to_response(_owned_offering(db, current_user, offering.id))


@router.delete("/{offering_id}", response_model=None)
def deactivate_offering(
    offering_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("SUPPLIER")),
) -> OfferingResponse | Response:
    offering = _owned_offering(db, current_user, offering_id)
    if offering.status in {"DEACTIVATED", "EXPIRED"}:
        write_audit(db, "offering.delete", current_user.id, "supplier_offering", offering.id)
        db.delete(offering)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if not can_transition(OFFERING_TRANSITIONS, offering.status, "DEACTIVATED"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This offering cannot be deactivated")
    offering.status = "DEACTIVATED"
    offering.updated_at = utc_now()
    write_audit(db, "offering.deactivate", current_user.id, "supplier_offering", offering.id)
    db.commit()
    return to_response(_owned_offering(db, current_user, offering.id))
