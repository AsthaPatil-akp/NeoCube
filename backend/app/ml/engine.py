from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.audit import notify, write_audit
from app.ml.inference import score_pair
from app.ml.model_store import load_match_model
from app.ml.nlp import SemanticEncoder
from app.models import Category, ClientProfile, ClientRequirement, Match, SupplierOffering, SupplierProfile, User, utc_now
from app.states import OPEN_REQUIREMENT_STATUSES
from app.webhooks import match_created_payload

logger = logging.getLogger("neocube")

PROTECTED_MATCH_STATUSES = {"RFQ_SENT", "RESPONDED", "ACCEPTED", "PAID", "SHIPPED", "RECEIVED"}


def _eligible_offerings(db: Session) -> list[SupplierOffering]:
    return list(
        db.scalars(
            select(SupplierOffering)
            .options(
                joinedload(SupplierOffering.supplier).joinedload(SupplierProfile.user),
                joinedload(SupplierOffering.category),
            )
            .join(SupplierProfile, SupplierOffering.supplier_id == SupplierProfile.id)
            .join(User, SupplierProfile.user_id == User.id)
            .where(
                SupplierOffering.status == "ACTIVE",
                SupplierOffering.available_quantity > 0,
                User.is_active.is_(True),
            )
        ).unique().all()
    )


def refresh_requirement_matches(db: Session, requirement: ClientRequirement) -> list[dict]:
    if requirement.status not in OPEN_REQUIREMENT_STATUSES | {"SUBMITTED"}:
        return []

    encoder = SemanticEncoder.load()
    model = load_match_model()
    if model is None:
        logger.warning(
            "Matching requirement %s without trained model; using documented non-ML fallback",
            requirement.id,
        )

    existing = {
        row.offering_id: row
        for row in db.scalars(select(Match).where(Match.requirement_id == requirement.id)).all()
    }
    created = 0
    kept_ids: set[int] = set()
    offering_by_id: dict[int, SupplierOffering] = {}
    newly_created: list[Match] = []

    for offering in _eligible_offerings(db):
        if requirement.category is None:
            requirement.category = db.get(Category, requirement.category_id)
        scored = score_pair(requirement, offering, encoder, model)
        if scored is None:
            continue
        offering_by_id[offering.id] = offering

        current = existing.get(offering.id)
        if current is None:
            current = Match(
                requirement_id=requirement.id,
                offering_id=offering.id,
                match_status="NEW",
            )
            db.add(current)
            db.flush()
            created += 1
            newly_created.append(current)
            notify(
                db,
                offering.supplier.user_id,
                "New requirement match",
                f"Your offering '{offering.product_offered}' matched '{requirement.product_requirement}'.",
                notification_type="MATCH",
                related_type="match",
                related_id=current.id,
            )
            if requirement.client is not None:
                notify(
                    db,
                    requirement.client.user_id,
                    "New supplier match found",
                    f"New supplier match found for your requirement: {offering.supplier_name}.",
                    notification_type="MATCH",
                    related_type="match",
                    related_id=current.id,
                )
        elif current.match_status in PROTECTED_MATCH_STATUSES:
            kept_ids.add(offering.id)
            continue

        current.semantic_score = scored["semantic_score"]
        current.ml_score = scored["ml_score"]
        current.structured_score = scored["structured_score"]
        current.final_score = scored["final_score"]
        current.explanation = json.dumps(scored["explanation"])
        current.model_version = scored["model_version"]
        current.updated_at = utc_now()
        if current.match_status not in PROTECTED_MATCH_STATUSES:
            current.match_status = "NEW"
        kept_ids.add(offering.id)

    for offering_id, row in existing.items():
        if offering_id not in kept_ids and row.match_status not in PROTECTED_MATCH_STATUSES:
            db.delete(row)

    db.flush()
    remaining = db.scalars(select(Match).where(Match.requirement_id == requirement.id)).all()
    remaining.sort(key=lambda item: item.final_score or 0, reverse=True)

    logger.info("Matching requirement %s stored %s ranked matches", requirement.id, len(remaining))
    if remaining and requirement.status in {"SUBMITTED", "PROCESSING"}:
        requirement.status = "MATCHED"
        notify(
            db,
            requirement.client.user_id,
            "Suppliers matched",
            f"Ranked matches were found for '{requirement.product_requirement}'.",
            notification_type="MATCH",
            related_type="requirement",
            related_id=requirement.id,
        )
        write_audit(db, "match.generated", requirement.client.user_id, "client_requirement", requirement.id)
    elif requirement.status == "SUBMITTED":
        requirement.status = "PROCESSING"
        notify(
            db,
            requirement.client.user_id,
            "Requirement submitted",
            f"'{requirement.product_requirement}' is being processed. No eligible suppliers yet.",
            notification_type="REQUIREMENT",
            related_type="requirement",
            related_id=requirement.id,
        )
    pending = []
    for row in newly_created:
        offering = offering_by_id.get(row.offering_id)
        if offering is None:
            continue
        pending.append(match_created_payload(requirement, offering, row, db=db))
    return pending


def refresh_offering_matches(db: Session, offering: SupplierOffering) -> list[dict]:
    if offering.status != "ACTIVE" or offering.available_quantity <= 0:
        return []
    if offering.supplier and offering.supplier.user and not offering.supplier.user.is_active:
        return []
    requirements = db.scalars(
        select(ClientRequirement)
        .options(
            joinedload(ClientRequirement.category),
            joinedload(ClientRequirement.client).joinedload(ClientProfile.user),
        )
        .where(ClientRequirement.status.in_(tuple(OPEN_REQUIREMENT_STATUSES)))
    ).all()
    pending: list[dict] = []
    for requirement in requirements:
        pending.extend(refresh_requirement_matches(db, requirement))
    return pending
