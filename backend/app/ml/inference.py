from __future__ import annotations

from app.ml.constraints import evaluate_constraints, structured_score
from app.ml.features import feature_vector, vector_to_list
from app.ml.model_store import MatchModel
from app.ml.nlp import SemanticEncoder
from app.models import ClientRequirement, SupplierOffering

FALLBACK_SEMANTIC_WEIGHT = 0.6
FALLBACK_STRUCTURED_WEIGHT = 0.4


def requirement_text(requirement: ClientRequirement) -> str:
    category = requirement.category.name if requirement.category else ""
    return " ".join(part for part in [requirement.product_requirement, requirement.additional_notes or "", category] if part)


def offering_text(offering: SupplierOffering) -> str:
    category = offering.category.name if offering.category else ""
    return " ".join(part for part in [offering.product_offered, offering.additional_notes or "", category] if part)


def explanations(constraints, semantic: float, location_overlap: float) -> list[str]:
    reasons = []
    if constraints.category_ok:
        reasons.append("Category compatible")
    if constraints.quantity_ok:
        reasons.append("Quantity sufficient")
    if constraints.budget_ok is True:
        reasons.append("Within budget")
    if constraints.delivery_ok is True:
        reasons.append("Delivery compatible")
    if constraints.certification_ok is True:
        reasons.append("Certification compatible")
    if location_overlap > 0:
        reasons.append("Location compatible")
    if constraints.product_ok and (
        getattr(constraints, "product_family_status", "") == "known_compatible" or semantic >= 0.35
    ):
        reasons.append("Product compatible")
    return reasons


def final_score(semantic: float, ml_score: float | None, structured: float) -> float:
    """Rank eligible suppliers by the trained model. The blend is only a fallback."""
    if ml_score is not None:
        return round(float(ml_score), 4)
    return round((FALLBACK_SEMANTIC_WEIGHT * semantic) + (FALLBACK_STRUCTURED_WEIGHT * structured), 4)


def score_pair(
    requirement: ClientRequirement,
    offering: SupplierOffering,
    encoder: SemanticEncoder,
    model: MatchModel | None,
) -> dict | None:
    constraints = evaluate_constraints(requirement, offering)
    if not constraints.passed:
        return None
    semantic = encoder.similarity(requirement_text(requirement), offering_text(offering))
    features = feature_vector(requirement, offering, semantic, constraints)
    ml_score = model.predict_proba(vector_to_list(features)) if model else None
    structured = structured_score(constraints, requirement, offering)
    return {
        "semantic_score": round(semantic, 4),
        "ml_score": None if ml_score is None else round(ml_score, 4),
        "structured_score": round(structured, 4),
        "final_score": final_score(semantic, ml_score, structured),
        "explanation": explanations(constraints, semantic, features["location_overlap"]),
        "model_version": model.version if model else "semantic-structured-only",
        "features": features,
    }
