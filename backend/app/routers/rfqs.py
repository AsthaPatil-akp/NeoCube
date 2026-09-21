import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.audit import notify, write_audit
from app.database import get_db
from app.deps import get_client_profile, get_supplier_profile, require_roles
from app.models import (
    ClientProfile,
    ClientRequirement,
    Match,
    Quotation,
    Rfq,
    SupplierOffering,
    SupplierProfile,
    User,
    utc_now,
)
from app.order_track import (
    TRACKABLE_RFQ_STATUSES,
    assign_otp,
    ensure_track,
    generate_shipment_code,
    otp_is_expired,
    otp_matches,
    tracking_payload,
)
from app.schemas import (
    OrderTrackingResponse,
    QuotationCreateRequest,
    QuotationResponse,
    RfqCreateRequest,
    RfqResponse,
    VerifyOtpRequest,
)
from app.states import OPEN_REQUIREMENT_STATUSES
from app.taxonomy import effective_category_name
from app.webhooks import (
    CLIENT_REQUEST_SENT,
    ORDER_COMPLETED,
    ORDER_RECEIVED,
    PAYMENT_CONFIRMED,
    SHIPMENT_SHIPPED,
    SUPPLIER_ACCEPTED,
    SUPPLIER_DECLINED,
    emit_n8n,
    notify_n8n,
    request_event_payload,
)

router = APIRouter(prefix="/rfqs", tags=["rfqs"])

RFQ_TRANSITIONS = {
    "SENT": {"VIEWED", "RESPONDED", "ACCEPTED", "REJECTED", "CANCELLED", "EXPIRED"},
    "VIEWED": {"RESPONDED", "ACCEPTED", "REJECTED", "CANCELLED", "EXPIRED"},
    "RESPONDED": {"ACCEPTED", "REJECTED", "EXPIRED"},
    "ACCEPTED": {"PAID"},
    "PAID": {"SHIPPED"},
    "SHIPPED": {"RECEIVED"},
    "RECEIVED": set(),
    "REJECTED": set(),
    "EXPIRED": set(),
    "CANCELLED": set(),
}

_RFQ_LOAD = (
    joinedload(Rfq.quotations),
    joinedload(Rfq.match),
    joinedload(Rfq.track),
)


def _load_requirement(db: Session, requirement_id: int) -> ClientRequirement | None:
    return db.scalar(
        select(ClientRequirement)
        .options(
            joinedload(ClientRequirement.client).joinedload(ClientProfile.user),
            joinedload(ClientRequirement.category),
        )
        .where(ClientRequirement.id == requirement_id)
    )


def _load_offering(db: Session, offering_id: int) -> SupplierOffering | None:
    return db.scalar(
        select(SupplierOffering)
        .options(
            joinedload(SupplierOffering.supplier).joinedload(SupplierProfile.user),
            joinedload(SupplierOffering.category),
        )
        .where(SupplierOffering.id == offering_id)
    )


def _rfq_response(rfq: Rfq, requirement: ClientRequirement | None, offering: SupplierOffering | None) -> RfqResponse:
    quotes = [
        QuotationResponse(
            id=item.id,
            rfq_id=item.rfq_id,
            unit_price=item.unit_price,
            quantity=item.quantity,
            shipping=item.shipping,
            tax=item.tax,
            additional_charges=item.additional_charges,
            subtotal=item.subtotal,
            total=item.total,
            delivery=item.delivery,
            validity_days=item.validity_days,
            payment_terms=item.payment_terms,
            notes=item.notes,
            status=item.status,
            created_at=item.created_at,
        )
        for item in rfq.quotations
    ]
    match = rfq.match
    match_explanation = None
    if match is not None and match.explanation:
        try:
            parsed = json.loads(match.explanation)
            match_explanation = " · ".join(str(item) for item in parsed) if isinstance(parsed, list) else match.explanation
        except json.JSONDecodeError:
            match_explanation = match.explanation
    category_name = None
    if offering is not None:
        category_name = effective_category_name(offering) or None
    if not category_name and requirement is not None:
        category_name = effective_category_name(requirement) or None
    return RfqResponse(
        id=rfq.id,
        requirement_id=rfq.requirement_id,
        offering_id=rfq.offering_id,
        match_id=rfq.match_id,
        client_user_id=rfq.client_user_id,
        supplier_user_id=rfq.supplier_user_id,
        notes=rfq.notes,
        status=rfq.status,
        product_requirement=requirement.product_requirement if requirement else None,
        product_offered=offering.product_offered if offering else None,
        client_name=requirement.company_name if requirement else None,
        supplier_name=offering.supplier_name if offering else None,
        category_name=category_name,
        quantity=requirement.quantity if requirement else None,
        budget=requirement.budget if requirement else None,
        budget_currency=requirement.budget_currency if requirement else None,
        location=requirement.location if requirement else None,
        delivery_timeline=requirement.delivery_timeline if requirement else None,
        additional_notes=requirement.additional_notes if requirement else None,
        match_score=match.final_score if match is not None else None,
        match_explanation=match_explanation,
        created_at=rfq.created_at,
        quotations=quotes,
        tracking=None,
    )


def _with_tracking(db, rfq: Rfq, response: RfqResponse, viewer: User | None) -> RfqResponse:
    if rfq.status in TRACKABLE_RFQ_STATUSES:
        ensure_track(db, rfq)
        db.commit()
        db.refresh(rfq)
    payload = tracking_payload(rfq, viewer)
    if payload is not None:
        response.tracking = OrderTrackingResponse.model_validate(payload)
    return response


def _owned_rfq(db, rfq_id: int, current_user: User) -> Rfq:
    rfq = _load_rfq(db, rfq_id)
    if rfq is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
    if current_user.role.name == "CLIENT" and rfq.client_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
    if current_user.role.name == "SUPPLIER" and rfq.supplier_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
    return rfq


def _lifecycle_event(event_type: str, rfq: Rfq, db, current_user: User) -> list[dict]:
    requirement = _load_requirement(db, rfq.requirement_id)
    offering = _load_offering(db, rfq.offering_id)
    if requirement is None or offering is None:
        return []
    return [request_event_payload(event_type, rfq, requirement, offering, rfq.match, db=db)]


def _load_rfq(db: Session, rfq_id: int) -> Rfq | None:
    return db.scalar(
        select(Rfq)
        .options(*_RFQ_LOAD)
        .where(Rfq.id == rfq_id)
    )


def _set_rfq_status(
    db: Session,
    rfq: Rfq,
    target: str,
    current_user: User,
    *,
    title: str | None = None,
    message: str | None = None,
) -> Rfq:
    allowed = RFQ_TRANSITIONS.get(rfq.status, set())
    if target not in allowed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invalid RFQ status transition")
    rfq.status = target
    rfq.updated_at = utc_now()
    if rfq.match_id:
        match = db.get(Match, rfq.match_id)
        if match is not None:
            match.match_status = target
    for quote in rfq.quotations:
        quote.status = target
    write_audit(db, f"rfq.{target.lower()}", current_user.id, "rfq", rfq.id)
    notify(
        db,
        rfq.supplier_user_id if current_user.id == rfq.client_user_id else rfq.client_user_id,
        title or f"RFQ {target.lower()}",
        message or f"RFQ #{rfq.id} is now {target}.",
        notification_type="RFQ",
        related_type="rfq",
        related_id=rfq.id,
    )
    db.commit()
    db.refresh(rfq)
    return rfq


@router.post("", response_model=RfqResponse, status_code=status.HTTP_201_CREATED)
def create_rfq(
    payload: RfqCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT")),
) -> RfqResponse:
    profile = get_client_profile(current_user)
    match = db.get(Match, payload.match_id)
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    requirement = _load_requirement(db, match.requirement_id)
    offering = _load_offering(db, match.offering_id)
    supplier_user = offering.supplier.user if offering is not None and offering.supplier is not None else None
    if (
        requirement is None
        or offering is None
        or offering.supplier is None
        or supplier_user is None
        or not supplier_user.is_active
        or requirement.client_id != profile.id
        or match.requirement_id != requirement.id
        or match.offering_id != offering.id
        or offering.supplier_id != offering.supplier.id
        or requirement.status not in OPEN_REQUIREMENT_STATUSES
        or offering.status != "ACTIVE"
        or offering.available_quantity <= 0
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")

    existing = db.scalar(
        select(Rfq).where(Rfq.requirement_id == requirement.id, Rfq.offering_id == offering.id)
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An RFQ already exists for this match")

    rfq = Rfq(
        requirement_id=requirement.id,
        offering_id=offering.id,
        match_id=match.id,
        client_user_id=current_user.id,
        supplier_user_id=offering.supplier.user_id,
        notes=payload.notes,
        status="SENT",
    )
    db.add(rfq)
    match.match_status = "RFQ_SENT"
    if requirement.status == "MATCHED":
        requirement.status = "RFQ_SENT"
        requirement.updated_at = utc_now()
    db.flush()
    write_audit(db, "rfq.create", current_user.id, "rfq", rfq.id)
    notify(
        db,
        offering.supplier.user_id,
        "New client request",
        f"{requirement.company_name} sent you a request for {requirement.product_requirement}.",
        notification_type="RFQ",
        related_type="rfq",
        related_id=rfq.id,
    )
    pending = [request_event_payload(CLIENT_REQUEST_SENT, rfq, requirement, offering, match, db=db)]
    db.commit()
    emit_n8n(pending)
    loaded = _load_rfq(db, rfq.id)
    assert loaded is not None
    return _with_tracking(db, loaded, _rfq_response(loaded, requirement, offering), current_user)


@router.get("", response_model=list[RfqResponse])
def list_rfqs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT", "SUPPLIER")),
) -> list[RfqResponse]:
    query = select(Rfq).options(*_RFQ_LOAD)
    if current_user.role.name == "CLIENT":
        query = query.where(Rfq.client_user_id == current_user.id)
    else:
        query = query.where(Rfq.supplier_user_id == current_user.id)
    rows = db.scalars(query.order_by(Rfq.created_at.desc())).unique().all()
    results = []
    for rfq in rows:
        requirement = _load_requirement(db, rfq.requirement_id)
        offering = _load_offering(db, rfq.offering_id)
        results.append(_with_tracking(db, rfq, _rfq_response(rfq, requirement, offering), current_user))
    return results


@router.get("/{rfq_id}", response_model=RfqResponse)
def get_rfq(
    rfq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT", "SUPPLIER")),
) -> RfqResponse:
    rfq = _load_rfq(db, rfq_id)
    if rfq is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
    if current_user.id not in {rfq.client_user_id, rfq.supplier_user_id}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
    if current_user.role.name == "SUPPLIER" and rfq.status == "SENT":
        rfq.status = "VIEWED"
        rfq.updated_at = utc_now()
        db.commit()
        db.refresh(rfq)
    requirement = _load_requirement(db, rfq.requirement_id)
    offering = _load_offering(db, rfq.offering_id)
    return _with_tracking(db, rfq, _rfq_response(rfq, requirement, offering), current_user)


@router.post("/{rfq_id}/quotations", response_model=QuotationResponse, status_code=status.HTTP_201_CREATED)
def create_quotation(
    rfq_id: int,
    payload: QuotationCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("SUPPLIER")),
) -> QuotationResponse:
    get_supplier_profile(current_user)
    rfq = _load_rfq(db, rfq_id)
    if rfq is None or rfq.supplier_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
    if rfq.status not in {"SENT", "VIEWED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This RFQ cannot accept a quotation")

    subtotal = payload.unit_price * payload.quantity
    total = subtotal + payload.shipping + payload.tax + payload.additional_charges
    quote = Quotation(
        rfq_id=rfq.id,
        unit_price=payload.unit_price,
        quantity=payload.quantity,
        shipping=payload.shipping,
        tax=payload.tax,
        additional_charges=payload.additional_charges,
        subtotal=subtotal,
        total=total,
        delivery=payload.delivery,
        validity_days=payload.validity_days,
        payment_terms=payload.payment_terms,
        notes=payload.notes,
        status="SENT",
    )
    db.add(quote)
    rfq.status = "RESPONDED"
    rfq.updated_at = utc_now()
    if rfq.match_id:
        match = db.get(Match, rfq.match_id)
        if match is not None:
            match.match_status = "RESPONDED"
    write_audit(db, "quotation.create", current_user.id, "quotation")
    notify(
        db,
        rfq.client_user_id,
        "Quotation received",
        "A supplier submitted a quotation for your RFQ.",
        notification_type="QUOTATION",
        related_type="rfq",
        related_id=rfq.id,
    )
    db.commit()
    db.refresh(quote)
    notify_n8n({"event": "quotation.created", "event_type": "quotation.created", "rfq_id": rfq.id, "quotation_total": total})
    return QuotationResponse(
        id=quote.id,
        rfq_id=quote.rfq_id,
        unit_price=quote.unit_price,
        quantity=quote.quantity,
        shipping=quote.shipping,
        tax=quote.tax,
        additional_charges=quote.additional_charges,
        subtotal=quote.subtotal,
        total=quote.total,
        delivery=quote.delivery,
        validity_days=quote.validity_days,
        payment_terms=quote.payment_terms,
        notes=quote.notes,
        status=quote.status,
        created_at=quote.created_at,
    )


@router.post("/{rfq_id}/accept", response_model=RfqResponse)
def accept_rfq(
    rfq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT", "SUPPLIER")),
) -> RfqResponse:
    rfq = _load_rfq(db, rfq_id)
    if rfq is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    if current_user.role.name == "CLIENT":
        if rfq.client_user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
        if rfq.status != "RESPONDED":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invalid RFQ status transition")
        updated = _set_rfq_status(db, rfq, "ACCEPTED", current_user)
        requirement = _load_requirement(db, updated.requirement_id)
        offering = _load_offering(db, updated.offering_id)
        if requirement is not None:
            requirement.status = "CLOSED"
            requirement.updated_at = utc_now()
            db.commit()
        ensure_track(db, updated)
        db.commit()
        return _with_tracking(db, updated, _rfq_response(updated, requirement, offering), current_user)

    if rfq.supplier_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
    if rfq.status not in {"SENT", "VIEWED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This request cannot be accepted")
    requirement = _load_requirement(db, rfq.requirement_id)
    offering = _load_offering(db, rfq.offering_id)
    supplier_name = offering.supplier_name if offering is not None else "A supplier"
    match_row = rfq.match
    updated = _set_rfq_status(
        db,
        rfq,
        "ACCEPTED",
        current_user,
        title="Supplier accepted your request",
        message=f"{supplier_name} accepted your supplier request.",
    )
    ensure_track(db, updated)
    db.commit()
    pending = []
    if requirement is not None and offering is not None:
        pending.append(request_event_payload(SUPPLIER_ACCEPTED, updated, requirement, offering, match_row, db=db))
    emit_n8n(pending)
    return _with_tracking(db, updated, _rfq_response(updated, requirement, offering), current_user)


@router.post("/{rfq_id}/reject", response_model=RfqResponse)
def reject_rfq(
    rfq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT", "SUPPLIER")),
) -> RfqResponse:
    rfq = _load_rfq(db, rfq_id)
    if rfq is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")

    if current_user.role.name == "CLIENT":
        if rfq.client_user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
        updated = _set_rfq_status(db, rfq, "REJECTED", current_user)
        requirement = _load_requirement(db, updated.requirement_id)
        offering = _load_offering(db, updated.offering_id)
        return _rfq_response(updated, requirement, offering)

    if rfq.supplier_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
    if rfq.status not in {"SENT", "VIEWED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This request cannot be declined")
    requirement = _load_requirement(db, rfq.requirement_id)
    offering = _load_offering(db, rfq.offering_id)
    supplier_name = offering.supplier_name if offering is not None else "A supplier"
    match_row = rfq.match
    updated = _set_rfq_status(
        db,
        rfq,
        "REJECTED",
        current_user,
        title="Supplier declined your request",
        message=f"{supplier_name} declined your supplier request.",
    )
    pending = []
    if requirement is not None and offering is not None:
        pending.append(request_event_payload(SUPPLIER_DECLINED, updated, requirement, offering, match_row, db=db))
    emit_n8n(pending)
    return _rfq_response(updated, requirement, offering)


def _respond_lifecycle(db: Session, rfq: Rfq, current_user: User) -> RfqResponse:
    requirement = _load_requirement(db, rfq.requirement_id)
    offering = _load_offering(db, rfq.offering_id)
    return _with_tracking(db, rfq, _rfq_response(rfq, requirement, offering), current_user)


@router.get("/{rfq_id}/tracking", response_model=OrderTrackingResponse)
def get_rfq_tracking(
    rfq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT", "SUPPLIER", "ADMIN")),
) -> OrderTrackingResponse:
    rfq = _load_rfq(db, rfq_id)
    if rfq is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
    if current_user.role.name != "ADMIN" and current_user.id not in {rfq.client_user_id, rfq.supplier_user_id}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RFQ not found")
    if rfq.status not in TRACKABLE_RFQ_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tracking is not available until the supplier accepts the request.")
    ensure_track(db, rfq)
    db.commit()
    db.refresh(rfq)
    payload = tracking_payload(rfq, current_user)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tracking is not available until the supplier accepts the request.")
    return OrderTrackingResponse.model_validate(payload)


@router.post("/{rfq_id}/payment/demo", response_model=RfqResponse)
def confirm_demo_payment(
    rfq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT")),
) -> RfqResponse:
    rfq = _owned_rfq(db, rfq_id, current_user)
    if rfq.status not in TRACKABLE_RFQ_STATUSES and rfq.status != "ACCEPTED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment is not available until the supplier accepts the request.")
    if rfq.status == "RECEIVED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order has already been completed.")
    if rfq.status in {"PAID", "SHIPPED"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment has already been completed.")
    if rfq.status != "ACCEPTED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment is not available until the supplier accepts the request.")
    track = ensure_track(db, rfq)
    updated = _set_rfq_status(
        db,
        rfq,
        "PAID",
        current_user,
        title="Demo payment confirmed",
        message="Payment confirmed. You can now ship the order.",
    )
    notify(
        db,
        updated.client_user_id,
        "Demo payment completed",
        "Demo payment completed for your order.",
        notification_type="RFQ",
        related_type="rfq",
        related_id=updated.id,
    )
    if track is not None:
        now = utc_now()
        track.current_status = "PAID"
        track.payment_status = "CONFIRMED"
        track.payment_at = now
        track.updated_at = now
    db.commit()
    emit_n8n(_lifecycle_event(PAYMENT_CONFIRMED, updated, db, current_user))
    return _respond_lifecycle(db, updated, current_user)


@router.post("/{rfq_id}/pay", response_model=RfqResponse)
def mark_rfq_paid(
    rfq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT")),
) -> RfqResponse:
    return confirm_demo_payment(rfq_id, db, current_user)


@router.post("/{rfq_id}/ship", response_model=RfqResponse)
def mark_rfq_shipped(
    rfq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("SUPPLIER")),
) -> RfqResponse:
    rfq = _owned_rfq(db, rfq_id, current_user)
    if rfq.status == "RECEIVED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order has already been completed.")
    if rfq.status == "SHIPPED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order has already been shipped.")
    if rfq.status != "PAID":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order cannot be shipped until payment is confirmed.")
    track = ensure_track(db, rfq)
    updated = _set_rfq_status(
        db,
        rfq,
        "SHIPPED",
        current_user,
        title="Demo shipment created",
        message="Your order has been marked as shipped. Please confirm receipt using the OTP when it arrives.",
    )
    if track is not None:
        now = utc_now()
        track.current_status = "SHIPPED"
        track.payment_status = "CONFIRMED"
        track.shipment_status = "SHIPPED"
        track.shipped_at = now
        track.shipment_code = track.shipment_code or generate_shipment_code()
        track.updated_at = now
        assign_otp(track)
    db.commit()
    emit_n8n(_lifecycle_event(SHIPMENT_SHIPPED, updated, db, current_user))
    return _respond_lifecycle(db, updated, current_user)


@router.post("/{rfq_id}/otp/refresh", response_model=RfqResponse)
def refresh_demo_otp(
    rfq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT")),
) -> RfqResponse:
    rfq = _owned_rfq(db, rfq_id, current_user)
    if rfq.status != "SHIPPED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="OTP verification is not available yet.")
    track = ensure_track(db, rfq)
    if track is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="OTP verification is not available yet.")
    if track.otp_verified or track.completed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order has already been completed.")
    assign_otp(track)
    db.commit()
    return _respond_lifecycle(db, rfq, current_user)


@router.post("/{rfq_id}/verify-otp", response_model=RfqResponse)
def verify_receipt_otp(
    rfq_id: int,
    payload: VerifyOtpRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT")),
) -> RfqResponse:
    rfq = _owned_rfq(db, rfq_id, current_user)
    if rfq.status == "RECEIVED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order has already been completed.")
    if rfq.status != "SHIPPED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="OTP verification is not available yet.")
    track = ensure_track(db, rfq)
    if track is None or track.payment_status != "CONFIRMED" or track.shipment_status != "SHIPPED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="OTP verification is not available yet.")
    if track.otp_verified or track.completed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Order has already been completed.")
    if otp_is_expired(track):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="OTP has expired. Please generate a new OTP.")
    code = (payload.otp or "").strip()
    if not otp_matches(code, track.otp_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP.")
    now = utc_now()
    track.otp_verified = True
    track.otp_code = None
    track.received_status = "RECEIVED"
    track.received_at = now
    track.completed = True
    track.completed_at = now
    track.current_status = "RECEIVED"
    track.updated_at = now
    updated = _set_rfq_status(
        db,
        rfq,
        "RECEIVED",
        current_user,
        title="Order completed",
        message="Client has confirmed receipt of the order.",
    )
    notify(
        db,
        updated.client_user_id,
        "Order completed",
        "Order completed successfully.",
        notification_type="RFQ",
        related_type="rfq",
        related_id=updated.id,
    )
    db.commit()
    emit_n8n(_lifecycle_event(ORDER_RECEIVED, updated, db, current_user))
    emit_n8n(_lifecycle_event(ORDER_COMPLETED, updated, db, current_user))
    return _respond_lifecycle(db, updated, current_user)


@router.post("/{rfq_id}/receive", response_model=RfqResponse)
def mark_rfq_received(
    rfq_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("CLIENT")),
) -> RfqResponse:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="OTP verification is required to mark this order received.")
