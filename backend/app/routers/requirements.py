from fastapi import APIRouter, Depends, HTTPException, Response, status
import json
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.audit import write_audit
from app.commerce import normalize_basis, normalize_currency
from app.database import get_db
from app.deps import get_client_profile, require_roles
from app.matching import refresh_requirement_matches
from app.webhooks import emit_n8n
from app.models import (
    Category,
    ClientProfile,
    ClientRequirement,
    Match,
    RequirementDocument,
    SupplierOffering,
    User,
    utc_now,
)
from app.schemas import (
    MatchSummary,
    RequirementCreateRequest,
    RequirementResponse,
    RequirementUpdateRequest,
)
from app.states import (
    EDITABLE_REQUIREMENT_STATUSES,
    REQUIREMENT_TRANSITIONS,
    can_transition,
)
from app.taxonomy import effective_category_name, resolve_category, stored_custom_category

router = APIRouter(prefix="/requirements", tags=["requirements"])


def _get_active_category(db: Session, category_id: int) -> Category:
    category = db.get(Category, category_id)
    if category is None or not category.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category")
    return category


def _owned_requirement(db: Session, user: User, requirement_id: int) -> ClientRequirement:
    profile = get_client_profile(user)
    requirement = db.scalars(
        select(ClientRequirement)
        .options(
            joinedload(ClientRequirement.category),
            joinedload(ClientRequirement.client).joinedload(ClientProfile.user),
            joinedload(ClientRequirement.matches).joinedload(Match.offering).joinedload(SupplierOffering.category),
            joinedload(ClientRequirement.matches).joinedload(Match.rfqs),
        )
        .where(ClientRequirement.id == requirement_id)
    ).unique().first()
    if requirement is None or requirement.client_id != profile.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement not found")
    return requirement


def _duplicate_exists(db: Session, client_id: int, payload, exclude_id: int | None = None) -> bool:
    query = select(ClientRequirement.id).where(
        ClientRequirement.client_id == client_id,
        ClientRequirement.product_requirement == payload.product_requirement,
        ClientRequirement.category_id == payload.category_id,
        ClientRequirement.quantity == payload.quantity,
        ClientRequirement.location == payload.location,
        ClientRequirement.delivery_timeline == payload.delivery_timeline,
        ClientRequirement.status.notin_(("CLOSED", "CANCELLED")),
    )
    if exclude_id is not None:
        query = query.where(ClientRequirement.id != exclude_id)
    return db.scalar(query) is not None


def _match_reasons(item: Match) -> list[str]:
    if not item.explanation:
        return []
    try:
        value = json.loads(item.explanation)
        return value if isinstance(value, list) else []
    except json.JSONDecodeError:
        return []


def to_response(requirement: ClientRequirement, match_count: int | None = None) -> RequirementResponse:
    matches = []
    ranked = sorted(requirement.matches, key=lambda row: row.final_score or 0, reverse=True)
    for item in ranked:
        offering = item.offering
        rfq = item.rfqs[0] if item.rfqs else None
        category_name = effective_category_name(offering) or effective_category_name(requirement)
        matches.append(
            MatchSummary(
                id=item.id,
                offering_id=offering.id,
                product_offered=offering.product_offered,
                supplier_name=offering.supplier_name,
                location=offering.location,
                category_name=category_name or (offering.category.name if offering.category else requirement.category.name),
                available_quantity=offering.available_quantity,
                quantity_unit=offering.quantity_unit,
                pricing_details=offering.pricing_details,
                price_amount=offering.price_amount,
                price_currency=offering.price_currency,
                price_basis=offering.price_basis,
                delivery_capability=offering.delivery_capability,
                semantic_score=item.semantic_score,
                ml_score=item.ml_score,
                structured_score=item.structured_score,
                final_score=item.final_score,
                match_status=item.match_status,
                explanation=_match_reasons(item),
                model_version=item.model_version,
                rfq_id=rfq.id if rfq is not None else None,
                rfq_status=rfq.status if rfq is not None else None,
                supplier_id=offering.supplier_id,
            )
        )
    return RequirementResponse(
        id=requirement.id,
        company_name=requirement.company_name,
        product_requirement=requirement.product_requirement,
        category_id=requirement.category_id,
        category_name=requirement.category.name,
        custom_category=requirement.custom_category,
        quantity=requirement.quantity,
        quantity_unit=requirement.quantity_unit,
        budget=requirement.budget,
        budget_currency=requirement.budget_currency,
        budget_basis=requirement.budget_basis,
        location=requirement.location,
        delivery_timeline=requirement.delivery_timeline,
        additional_notes=requirement.additional_notes,
        status=requirement.status,
        match_count=match_count if match_count is not None else len(requirement.matches),
        created_at=requirement.created_at,
        updated_at=requirement.updated_at,
        matches=matches,
    )


@router.get("", response_model=list[RequirementResponse])
def list_requirements(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT")),
) -> list[RequirementResponse]:
    profile = get_client_profile(current_user)
    rows = db.scalars(
        select(ClientRequirement)
        .options(
            joinedload(ClientRequirement.category),
            joinedload(ClientRequirement.matches).joinedload(Match.offering).joinedload(SupplierOffering.category),
            joinedload(ClientRequirement.matches).joinedload(Match.rfqs),
        )
        .where(ClientRequirement.client_id == profile.id)
        .order_by(ClientRequirement.created_at.desc())
    ).unique().all()
    return [to_response(row) for row in rows]


@router.post("", response_model=RequirementResponse, status_code=status.HTTP_201_CREATED)
def create_requirement(
    payload: RequirementCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT")),
) -> RequirementResponse:
    profile = get_client_profile(current_user)
    category = resolve_category(db, payload.category_id, payload.custom_category)
    if _duplicate_exists(db, profile.id, payload):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A matching requirement already exists")

    document = None
    if payload.document_id is not None:
        document = db.get(RequirementDocument, payload.document_id)
        if (
            document is None
            or document.user_id != current_user.id
            or document.requirement_id is not None
        ):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid document")

    requirement = ClientRequirement(
        client_id=profile.id,
        category_id=category.id,
        custom_category=stored_custom_category(category),
        company_name=payload.company_name,
        product_requirement=payload.product_requirement,
        quantity=payload.quantity,
        quantity_unit=payload.quantity_unit,
        budget=payload.budget,
        budget_currency=normalize_currency(payload.budget_currency),
        budget_basis=normalize_basis(payload.budget_basis) or payload.budget_basis,
        location=payload.location,
        delivery_timeline=payload.delivery_timeline,
        additional_notes=payload.additional_notes,
        status=payload.status,
    )
    db.add(requirement)
    db.flush()
    if document is not None:
        document.requirement_id = requirement.id
        document.processing_status = "CONFIRMED"
    write_audit(db, "requirement.create", current_user.id, "client_requirement", requirement.id)
    pending: list[dict] = []
    if requirement.status == "SUBMITTED":
        pending = refresh_requirement_matches(db, requirement)
    db.commit()
    emit_n8n(pending)
    return to_response(_owned_requirement(db, current_user, requirement.id))


@router.get("/{requirement_id}", response_model=RequirementResponse)
def get_requirement(
    requirement_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT")),
) -> RequirementResponse:
    requirement = _owned_requirement(db, current_user, requirement_id)
    changed = False
    for item in requirement.matches:
        if item.match_status == "NEW":
            item.match_status = "VIEWED"
            item.updated_at = utc_now()
            changed = True
    if changed:
        write_audit(db, "match.viewed", current_user.id, "client_requirement", requirement.id)
        db.commit()
        requirement = _owned_requirement(db, current_user, requirement_id)
    return to_response(requirement)


@router.put("/{requirement_id}", response_model=RequirementResponse)
def update_requirement(
    requirement_id: int,
    payload: RequirementUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT")),
) -> RequirementResponse:
    requirement = _owned_requirement(db, current_user, requirement_id)
    data = payload.model_dump(exclude_unset=True)
    new_status = data.pop("status", None)
    document_id = data.pop("document_id", None)

    if data and requirement.status not in EDITABLE_REQUIREMENT_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This requirement can no longer be edited")

    if "category_id" in data or "custom_category" in data:
        category = resolve_category(
            db,
            data.get("category_id", requirement.category_id),
            data.get("custom_category", requirement.custom_category),
        )
        data["category_id"] = category.id
        data["custom_category"] = stored_custom_category(category)
    if "budget_currency" in data:
        data["budget_currency"] = normalize_currency(data.get("budget_currency"))
    if "budget_basis" in data:
        data["budget_basis"] = normalize_basis(data.get("budget_basis")) or data.get("budget_basis")

    for field, value in data.items():
        setattr(requirement, field, value)

    if document_id is not None:
        document = db.get(RequirementDocument, document_id)
        if document is None or document.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid document")
        document.requirement_id = requirement.id
        document.processing_status = "CONFIRMED"

    if new_status is not None:
        if not can_transition(REQUIREMENT_TRANSITIONS, requirement.status, new_status):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invalid status transition")
        requirement.status = new_status

    merged = type("Dup", (), {
        "product_requirement": requirement.product_requirement,
        "category_id": requirement.category_id,
        "quantity": requirement.quantity,
        "location": requirement.location,
        "delivery_timeline": requirement.delivery_timeline,
    })()
    if _duplicate_exists(db, requirement.client_id, merged, exclude_id=requirement.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A matching requirement already exists")

    requirement.updated_at = utc_now()
    write_audit(db, "requirement.update", current_user.id, "client_requirement", requirement.id)
    pending: list[dict] = []
    if requirement.status in {"SUBMITTED", "PROCESSING", "MATCHED"}:
        pending = refresh_requirement_matches(db, requirement)
    db.commit()
    emit_n8n(pending)
    return to_response(_owned_requirement(db, current_user, requirement.id))


@router.delete("/{requirement_id}", response_model=None)
def cancel_requirement(
    requirement_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT")),
) -> RequirementResponse | Response:
    requirement = _owned_requirement(db, current_user, requirement_id)
    if requirement.status in {"CLOSED", "CANCELLED"}:
        write_audit(db, "requirement.delete", current_user.id, "client_requirement", requirement.id)
        db.delete(requirement)
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if not can_transition(REQUIREMENT_TRANSITIONS, requirement.status, "CANCELLED"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This requirement cannot be cancelled")
    requirement.status = "CANCELLED"
    requirement.updated_at = utc_now()
    write_audit(db, "requirement.cancel", current_user.id, "client_requirement", requirement.id)
    db.commit()
    return to_response(_owned_requirement(db, current_user, requirement.id))
