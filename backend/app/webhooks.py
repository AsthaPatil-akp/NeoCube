from __future__ import annotations

import json
import logging
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.config import settings
from app.models import ClientProfile, ClientRequirement, Match, Rfq, SupplierOffering, SupplierProfile, User
from app.taxonomy import effective_category_name, is_other_name

logger = logging.getLogger("neocube")

MATCH_CREATED = "MATCH_CREATED"
CLIENT_REQUEST_SENT = "CLIENT_REQUEST_SENT"
SUPPLIER_ACCEPTED = "SUPPLIER_ACCEPTED"
SUPPLIER_DECLINED = "SUPPLIER_DECLINED"
PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
SHIPMENT_SHIPPED = "SHIPMENT_SHIPPED"
ORDER_RECEIVED = "ORDER_RECEIVED"
ORDER_COMPLETED = "ORDER_COMPLETED"

_SENT_EVENT_IDS: set[str] = set()

SUPPLIER_RECIPIENT_EVENTS = {MATCH_CREATED, CLIENT_REQUEST_SENT, PAYMENT_CONFIRMED, ORDER_RECEIVED, ORDER_COMPLETED}
CLIENT_RECIPIENT_EVENTS = {SUPPLIER_ACCEPTED, SUPPLIER_DECLINED, SHIPMENT_SHIPPED}


def reset_n8n_idempotency() -> None:
    _SENT_EVENT_IDS.clear()


def _format_explanation(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return " · ".join(str(item) for item in parsed)
    except json.JSONDecodeError:
        pass
    return raw


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.isoformat()


def _text_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _payload_product(offering: SupplierOffering) -> str | None:
    """Supplier offering product. Column: supplier_offerings.product_offered."""
    return _text_or_none(getattr(offering, "product_offered", None))


def _payload_category(requirement: ClientRequirement, offering: SupplierOffering) -> str | None:
    """Resolved category name from the current taxonomy, never a fabricated label.

    Prefers supplier_offerings.custom_category / client_requirements.custom_category,
    then categories.name via the offering or requirement relationship.
    "Other" is not sent as a stand-in for a missing custom name.
    """
    for entity in (offering, requirement):
        name = _text_or_none(effective_category_name(entity))
        if name and not is_other_name(name):
            return name
    return None


def _session_for(*objects, db: Session | None = None) -> Session | None:
    if db is not None:
        return db
    for obj in objects:
        if obj is None:
            continue
        session = object_session(obj)
        if session is not None:
            return session
    return None


def resolve_account_email(*, user_id: int | None, session: Session | None) -> str | None:
    """Canonical login email from users.email. Never invent a placeholder recipient."""
    if user_id is None:
        logger.warning("notification recipient unavailable: account user id missing")
        return None
    if session is None:
        logger.warning("notification recipient unavailable: no database session for user_id=%s", user_id)
        return None
    email = _text_or_none(session.scalar(select(User.email).where(User.id == int(user_id))))
    if not email:
        logger.warning("notification recipient unavailable: users.email missing for user_id=%s", user_id)
        return None
    return email


def _client_account_user_id(requirement: ClientRequirement, session: Session | None) -> int | None:
    if requirement is None:
        return None
    client = getattr(requirement, "client", None)
    if client is not None and getattr(client, "user_id", None):
        return client.user_id
    if session is None or not requirement.client_id:
        return None
    return session.scalar(select(ClientProfile.user_id).where(ClientProfile.id == requirement.client_id))


def _supplier_account_user_id(offering: SupplierOffering, session: Session | None) -> int | None:
    if offering is None:
        return None
    supplier = getattr(offering, "supplier", None)
    if supplier is not None and getattr(supplier, "user_id", None):
        return supplier.user_id
    if session is None or not offering.supplier_id:
        return None
    return session.scalar(select(SupplierProfile.user_id).where(SupplierProfile.id == offering.supplier_id))


def _recipient_for(payload: dict) -> str:
    existing = _text_or_none(payload.get("recipient_email"))
    if existing:
        return existing
    event_type = payload.get("event_type") or payload.get("event")
    if event_type in SUPPLIER_RECIPIENT_EVENTS:
        return _text_or_none(payload.get("supplier_email")) or ""
    if event_type in CLIENT_RECIPIENT_EVENTS:
        return _text_or_none(payload.get("client_email")) or ""
    return _text_or_none(payload.get("supplier_email")) or _text_or_none(payload.get("client_email")) or ""


def _omit_empty_lines(pairs: list[tuple[str, object]]) -> str:
    lines: list[str] = []
    for label, value in pairs:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        lines.append(f"{label}: {value}")
    return "\n".join(lines)


def _email_copy(event_type: str, payload: dict) -> tuple[str, str]:
    product = payload.get("product")
    category = payload.get("category")
    quantity = payload.get("quantity")
    if event_type == MATCH_CREATED:
        body = _omit_empty_lines(
            [
                ("Client", payload.get("client_name")),
                ("Product", product),
                ("Category", category),
                ("Quantity", quantity),
                ("Match Score", payload.get("match_score")),
                ("Match Explanation", payload.get("match_explanation")),
            ]
        )
        instruction = "Review this match in your NeoCube supplier portal."
        return "New Supplier Match Found", "\n".join(part for part in (body, instruction) if part)
    if event_type == CLIENT_REQUEST_SENT:
        body = _omit_empty_lines(
            [
                ("Client", payload.get("client_name")),
                ("Product", product),
                ("Category", category),
                ("Quantity", quantity),
                ("Required delivery", payload.get("delivery_timeline")),
                ("Match score", payload.get("match_score")),
            ]
        )
        instruction = "Review this request in your NeoCube supplier portal."
        return "New Client Request", "\n".join(part for part in (body, instruction) if part)
    if event_type == SUPPLIER_ACCEPTED:
        body = _omit_empty_lines(
            [
                ("Supplier", payload.get("supplier_name")),
                ("Product", product),
                ("Category", category),
                ("Quantity", quantity),
                ("Status", "ACCEPTED"),
            ]
        )
        instruction = "Review this request in your NeoCube client portal."
        return "Supplier Accepted Your Request", "\n".join(part for part in (body, instruction) if part)
    if event_type == SUPPLIER_DECLINED:
        body = _omit_empty_lines(
            [
                ("Supplier", payload.get("supplier_name")),
                ("Product", product),
                ("Category", category),
                ("Quantity", quantity),
                ("Status", "REJECTED"),
            ]
        )
        instruction = "Review this request in your NeoCube client portal."
        return "Supplier Declined Your Request", "\n".join(part for part in (body, instruction) if part)
    if event_type == PAYMENT_CONFIRMED:
        return "Demo payment confirmed", "A demo payment was confirmed. You can now mark this order as shipped in NeoCube."
    if event_type == SHIPMENT_SHIPPED:
        return "Demo shipment created", "Your order was marked as shipped. Confirm receipt in NeoCube using the demo OTP."
    if event_type == ORDER_RECEIVED:
        return "Order received", "The client confirmed receipt of this order."
    if event_type == ORDER_COMPLETED:
        return "Order completed", "This order is now completed in NeoCube."
    return event_type, ""


def _attach_email_routing(payload: dict) -> dict:
    payload["recipient_email"] = _recipient_for(payload)
    subject, body = _email_copy(payload.get("event_type"), payload)
    payload["email_subject"] = subject
    payload["email_body"] = body
    return payload


def match_created_payload(
    requirement: ClientRequirement,
    offering: SupplierOffering,
    match: Match,
    db: Session | None = None,
) -> dict:
    session = _session_for(requirement, offering, match, db=db)
    payload = {
        "event_type": MATCH_CREATED,
        "event_id": f"{MATCH_CREATED}:{match.id}",
        "match_id": match.id,
        "request_id": None,
        "client_id": requirement.client_id,
        "supplier_id": offering.supplier_id,
        "client_name": requirement.company_name,
        "client_email": resolve_account_email(
            user_id=_client_account_user_id(requirement, session),
            session=session,
        ),
        "supplier_name": offering.supplier_name,
        "supplier_email": resolve_account_email(
            user_id=_supplier_account_user_id(offering, session),
            session=session,
        ),
        "product": _payload_product(offering),
        "category": _payload_category(requirement, offering),
        "quantity": requirement.quantity,
        "match_score": match.final_score,
        "match_explanation": _format_explanation(match.explanation),
        "created_at": _iso(match.created_at),
    }
    return _attach_email_routing(payload)


def request_event_payload(
    event_type: str,
    rfq: Rfq,
    requirement: ClientRequirement,
    offering: SupplierOffering,
    match: Match | None = None,
    db: Session | None = None,
) -> dict:
    session = _session_for(rfq, requirement, offering, match, db=db)
    payload: dict = {
        "event_type": event_type,
        "event_id": f"{event_type}:{rfq.id}",
        "request_id": rfq.id,
        "match_id": rfq.match_id,
        "client_id": requirement.client_id,
        "supplier_id": offering.supplier_id,
        "client_name": requirement.company_name,
        "client_email": resolve_account_email(
            user_id=rfq.client_user_id or _client_account_user_id(requirement, session),
            session=session,
        ),
        "supplier_name": offering.supplier_name,
        "supplier_email": resolve_account_email(
            user_id=rfq.supplier_user_id or _supplier_account_user_id(offering, session),
            session=session,
        ),
        "product": _payload_product(offering) or _text_or_none(requirement.product_requirement),
        "category": _payload_category(requirement, offering),
        "quantity": requirement.quantity,
        "match_score": match.final_score if match is not None else None,
        "match_explanation": _format_explanation(match.explanation) if match is not None else "",
        "created_at": _iso(rfq.updated_at or rfq.created_at),
    }
    if event_type == CLIENT_REQUEST_SENT:
        payload["delivery_timeline"] = _text_or_none(requirement.delivery_timeline)
    return _attach_email_routing(payload)


def emit_n8n(payloads: list[dict] | None) -> None:
    for payload in payloads or []:
        notify_n8n(payload)


def notify_n8n(payload: dict) -> None:
    event = payload.get("event_type") or payload.get("event")
    event_id = payload.get("event_id")
    if event_id and event_id in _SENT_EVENT_IDS:
        logger.info("n8n webhook skipped: duplicate event_id=%s", event_id)
        return
    recipient = _recipient_for(payload)
    payload["recipient_email"] = recipient
    if not recipient:
        logger.warning(
            "n8n webhook skipped: notification recipient unavailable event=%s event_id=%s",
            event,
            event_id,
        )
        return
    if event == MATCH_CREATED:
        keys = ",".join(payload.keys())
        logger.info("MATCH_CREATED n8n webhook attempted keys=%s", keys)
    logger.info(
        "n8n payload recipients event=%s client_email=%s supplier_email=%s recipient_email=%s",
        event,
        payload.get("client_email"),
        payload.get("supplier_email"),
        recipient,
    )
    url = (settings.n8n_webhook_url or "").strip()
    if not url:
        logger.warning("n8n webhook skipped: URL not configured")
        return
    try:
        response = httpx.post(url, json=payload, timeout=5.0)
    except Exception:
        logger.warning("n8n webhook result: failure event=%s reason=network_or_timeout", event)
        return
    if response.status_code >= 400:
        logger.warning("n8n webhook result: failure event=%s status=%s", event, response.status_code)
        return
    if event_id:
        _SENT_EVENT_IDS.add(str(event_id))
    logger.info("n8n webhook result: success event=%s status=%s", event, response.status_code)
