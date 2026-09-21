from __future__ import annotations

from app.ml.constraints import ConstraintResult
from app.ml.nlp import FEATURE_COLUMNS
from app.ml.parse import location_overlap
from app.models import ClientRequirement, SupplierOffering


def clip(value: float, low: float = 0.0, high: float = 3.0) -> float:
    return max(low, min(high, value))


def feature_vector(
    requirement: ClientRequirement,
    offering: SupplierOffering,
    semantic: float,
    constraints: ConstraintResult,
) -> dict[str, float]:
    quantity_ratio = clip(offering.available_quantity / max(requirement.quantity, 1))
    if constraints.estimated_cost is None or requirement.budget <= 0:
        budget_ratio = 1.0
        within_budget = 0.5
    else:
        budget_ratio = clip(constraints.estimated_cost / max(requirement.budget, 1))
        within_budget = 1.0 if constraints.budget_ok else 0.0
    if constraints.client_days and constraints.supplier_days:
        delivery_ratio = clip(constraints.supplier_days / max(constraints.client_days, 1))
        delivery_ok = 1.0 if constraints.delivery_ok else 0.0
    else:
        delivery_ratio = 1.0
        delivery_ok = 0.5
    return {
        "semantic_similarity": float(semantic),
        "quantity_ratio": float(quantity_ratio),
        "budget_ratio": float(budget_ratio),
        "delivery_ratio": float(delivery_ratio),
        "location_overlap": float(location_overlap(requirement.location, offering.location)),
    }


def vector_to_list(features: dict[str, float]) -> list[float]:
    return [features[name] for name in FEATURE_COLUMNS]
