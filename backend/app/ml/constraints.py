from __future__ import annotations

import re
from dataclasses import dataclass

from app.commerce import (
    CURRENCY_COMPARISON_UNAVAILABLE,
    compare_commercial,
    offering_money,
    requirement_money,
)
from app.ml.parse import location_overlap, parse_days
from app.models import ClientRequirement, SupplierOffering
from app.taxonomy import categories_compatible, product_compatibility

ISO_RE = re.compile(r"\biso(?:\s*\d+)?\b", re.IGNORECASE)
CERT_WORD_RE = re.compile(r"\b(certification|certificate|certified)\b", re.IGNORECASE)


def required_certification_tags(notes: str | None) -> set[str]:
    if not notes:
        return set()
    if not re.search(r"\b(require[sd]?|mandatory|must)\b", notes, flags=re.IGNORECASE):
        return set()
    tags: set[str] = set()
    if ISO_RE.search(notes):
        tags.add("iso")
    if CERT_WORD_RE.search(notes) or "iso" in tags:
        tags.add("certification")
    return tags


def offering_certification_tags(notes: str | None) -> set[str]:
    if not notes:
        return set()
    tags: set[str] = set()
    if ISO_RE.search(notes):
        tags.add("iso")
    if CERT_WORD_RE.search(notes):
        tags.add("certification")
    return tags


@dataclass
class ConstraintResult:
    passed: bool
    quantity_ok: bool
    budget_ok: bool | None
    delivery_ok: bool | None
    category_ok: bool
    product_ok: bool
    product_family_status: str
    active_ok: bool
    certification_ok: bool | None
    reasons_fail: list[str]
    unit_price: int | None
    estimated_cost: int | None
    client_days: int | None
    supplier_days: int | None
    currency_status: str | None


def evaluate_constraints(requirement: ClientRequirement, offering: SupplierOffering) -> ConstraintResult:
    fails: list[str] = []
    active_ok = offering.status == "ACTIVE" and offering.available_quantity > 0
    if not active_ok:
        fails.append("Offering is not active or has no available quantity")

    category_ok = categories_compatible(requirement, offering)
    if not category_ok:
        fails.append("Category does not match")

    product_ok, product_family_status = product_compatibility(
        requirement.product_requirement,
        offering.product_offered,
    )
    if not product_ok:
        fails.append("Product families are incompatible")

    quantity_ok = offering.available_quantity >= requirement.quantity
    if not quantity_ok:
        fails.append("Available quantity is below the required quantity")

    client = requirement_money(requirement)
    supplier = offering_money(offering)
    budget_ok, estimated_cost, currency_status = compare_commercial(requirement.quantity, client, supplier)
    unit_price = supplier.amount if supplier.basis == "PER_UNIT" else None
    if currency_status == CURRENCY_COMPARISON_UNAVAILABLE:
        fails.append("CURRENCY_COMPARISON_UNAVAILABLE")
    elif budget_ok is False:
        fails.append("Estimated cost exceeds client budget")

    client_days = parse_days(requirement.delivery_timeline)
    supplier_days = parse_days(offering.delivery_capability)
    delivery_ok = None
    if client_days is not None and supplier_days is not None:
        delivery_ok = supplier_days <= client_days
        if not delivery_ok:
            fails.append("Delivery capability is slower than the required timeline")

    required_certs = required_certification_tags(requirement.additional_notes)
    certification_ok = None
    if required_certs:
        offered_certs = offering_certification_tags(offering.additional_notes)
        certification_ok = required_certs.issubset(offered_certs)
        if not certification_ok:
            fails.append("Required certification is missing")

    passed = not fails
    return ConstraintResult(
        passed=passed,
        quantity_ok=quantity_ok,
        budget_ok=budget_ok,
        delivery_ok=delivery_ok,
        category_ok=category_ok,
        product_ok=product_ok,
        product_family_status=product_family_status,
        active_ok=active_ok,
        certification_ok=certification_ok,
        reasons_fail=fails,
        unit_price=unit_price,
        estimated_cost=estimated_cost,
        client_days=client_days,
        supplier_days=supplier_days,
        currency_status=currency_status,
    )


def structured_score(result: ConstraintResult, requirement: ClientRequirement, offering: SupplierOffering) -> float:
    parts = [1.0 if result.quantity_ok else 0.0, 1.0 if result.category_ok else 0.0]
    if result.product_ok is not None:
        parts.append(1.0 if result.product_ok else 0.0)
    if result.budget_ok is not None:
        parts.append(1.0 if result.budget_ok else 0.0)
    if result.delivery_ok is not None:
        parts.append(1.0 if result.delivery_ok else 0.0)
    if result.certification_ok is not None:
        parts.append(1.0 if result.certification_ok else 0.0)
    overlap = location_overlap(requirement.location, offering.location)
    parts.append(overlap)
    return sum(parts) / len(parts)
