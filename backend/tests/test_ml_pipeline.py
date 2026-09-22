import json

import pytest

from app.ml.constraints import evaluate_constraints
from app.ml.features import feature_vector, vector_to_list
from app.ml.inference import final_score, score_pair
from app.ml.model_store import clear_model_cache, load_match_model
from app.ml.nlp import FEATURE_COLUMNS, SemanticEncoder, artifacts_dir
from app.models import ClientRequirement, SupplierOffering
from ml_pipeline.dataset import REQUIRED_COLUMNS, load_training_pairs
from tests.test_modules import (
    make_client,
    offering_payload,
    register_and_login,
    requirement_payload,
    unique_category_id,
)


def _pair(quantity=5000, available=9000, budget=800000, pricing="INR 120 per unit", timeline="30 days", delivery="14 days", notes=None, offering_notes="ISO certified"):
    requirement = ClientRequirement(
        client_id=1,
        category_id=1,
        company_name="A",
        product_requirement="steel brackets",
        quantity=quantity,
        budget=budget,
        location="Pune",
        delivery_timeline=timeline,
        additional_notes=notes,
    )
    offering = SupplierOffering(
        supplier_id=1,
        category_id=1,
        supplier_name="B",
        product_offered="steel brackets",
        available_quantity=available,
        pricing_details=pricing,
        location="Pune",
        delivery_capability=delivery,
        additional_notes=offering_notes,
        status="ACTIVE",
    )
    return requirement, offering


def test_dataset_loader_uses_curated_not_company_history():
    frame, provenance = load_training_pairs()
    assert len(frame) > 0
    assert all(column in frame.columns for column in REQUIRED_COLUMNS)
    assert "Not historical company data" in provenance
    assert frame["match_label"].isin([0, 1]).all()


def test_feature_vector_order_matches_training_schema():
    requirement, offering = _pair()
    constraints = evaluate_constraints(requirement, offering)
    features = feature_vector(requirement, offering, 0.72, constraints)
    assert list(features) == FEATURE_COLUMNS
    values = vector_to_list(features)
    assert values[0] == 0.72
    assert values[1] == pytest.approx(9000 / 5000)
    schema = json.loads((artifacts_dir() / "feature_schema.json").read_text(encoding="utf-8"))
    assert schema["feature_columns"] == FEATURE_COLUMNS


def test_unparseable_pricing_does_not_invent_a_budget_check():
    requirement, offering = _pair(pricing="contact for quote")
    constraints = evaluate_constraints(requirement, offering)
    assert constraints.passed is True
    assert constraints.budget_ok is None
    features = feature_vector(requirement, offering, 0.5, constraints)
    assert features["budget_ratio"] == 1.0


def test_missing_delivery_text_does_not_fail_hard_filter():
    requirement, offering = _pair(timeline="ASAP", delivery="standard shipping")
    constraints = evaluate_constraints(requirement, offering)
    assert constraints.passed is True
    assert constraints.delivery_ok is None


def test_score_pair_returns_none_when_hard_filter_fails():
    encoder = SemanticEncoder.load()
    model = load_match_model()
    requirement, offering = _pair(available=10)
    assert score_pair(requirement, offering, encoder, model) is None


def test_score_pair_uses_model_probability_as_final_score():
    encoder = SemanticEncoder.load()
    model = load_match_model()
    assert model is not None
    requirement, offering = _pair()
    scored = score_pair(requirement, offering, encoder, model)
    assert scored is not None
    assert scored["ml_score"] == scored["final_score"]
    assert scored["model_version"] == "supplier_match_model_v1"
    assert "Quantity sufficient" in scored["explanation"]
    assert "Within budget" in scored["explanation"]


def test_fallback_score_is_only_used_without_a_model():
    assert final_score(0.5, 0.91, 0.8) == 0.91
    assert final_score(0.5, None, 1.0) == 0.7


def test_model_rejects_wrong_feature_width():
    model = load_match_model()
    assert model is not None
    with pytest.raises(ValueError):
        model.predict_proba([0.1, 0.2])


def test_model_handles_nan_features_without_crashing():
    model = load_match_model()
    assert model is not None
    score = model.predict_proba([float("nan")] * len(FEATURE_COLUMNS))
    assert 0.0 <= score <= 1.0


def test_persisted_model_version_matches_loader():
    clear_model_cache()
    model = load_match_model()
    assert model is not None
    metadata = json.loads((artifacts_dir() / "model_metadata.json").read_text(encoding="utf-8"))
    assert model.version == metadata["model_version"] == "supplier_match_model_v1"
    assert metadata["feature_columns"] == FEATURE_COLUMNS


def test_matches_are_ranked_descending_and_persisted():
    category_id = unique_category_id()
    first = make_client()
    register_and_login(first, "sup-rank-a@example.com", "SUPPLIER")
    first.post("/offerings", json=offering_payload(category_id, product_offered="Steel brackets"))
    second = make_client()
    register_and_login(second, "sup-rank-b@example.com", "SUPPLIER")
    second.post("/offerings", json=offering_payload(category_id, product_offered="Galvanized steel fasteners"))

    buyer = make_client()
    register_and_login(buyer, "cli-rank@example.com")
    created = buyer.post("/requirements", json=requirement_payload(category_id, product_requirement="Steel brackets"))
    assert created.status_code == 201, created.text
    matches = created.json()["matches"]
    assert len(matches) == 2
    scores = [item["final_score"] for item in matches]
    assert scores == sorted(scores, reverse=True)
    assert all(item["ml_score"] is not None for item in matches)
    assert all(item["model_version"] == "supplier_match_model_v1" for item in matches)
    assert all(item["final_score"] == item["ml_score"] for item in matches)
    detail = buyer.get(f"/requirements/{created.json()['id']}")
    persisted = detail.json()["matches"]
    assert [item["id"] for item in persisted] == [item["id"] for item in matches]


def test_explanations_are_not_emitted_for_failed_checks():
    encoder = SemanticEncoder.load()
    model = load_match_model()
    requirement, offering = _pair(pricing="contact for quote")
    scored = score_pair(requirement, offering, encoder, model)
    assert scored is not None
    assert "Within budget" not in scored["explanation"]


def test_placeholder_image_product_name_is_not_rejected():
    encoder = SemanticEncoder.load()
    model = load_match_model()
    requirement, offering = _pair()
    offering.product_offered = "Image"
    scored = score_pair(requirement, offering, encoder, model)
    assert scored is not None
    assert scored["final_score"] == scored["ml_score"]
    assert scored["model_version"] == "supplier_match_model_v1"


def test_product_compatible_requires_known_family():
    encoder = SemanticEncoder.load()
    model = load_match_model()
    requirement, offering = _pair()
    offering.product_offered = "Image"
    scored = score_pair(requirement, offering, encoder, model)
    assert scored is not None
    assert "Product compatible" not in scored["explanation"]
    requirement, offering = _pair()
    scored = score_pair(requirement, offering, encoder, model)
    assert "Product compatible" in scored["explanation"]
