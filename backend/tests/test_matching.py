from app.ml.constraints import evaluate_constraints
from app.ml.model_store import clear_model_cache, load_match_model
from app.ml.nlp import FEATURE_COLUMNS, SemanticEncoder
from app.ml.parse import parse_days, parse_unit_price
from app.models import ClientRequirement, SupplierOffering
from tests.test_modules import (
    make_client,
    offering_payload,
    register_and_login,
    requirement_payload,
    unique_category_id,
)


def test_parse_helpers():
    assert parse_days("within 30 days") == 30
    assert parse_days("2 weeks") == 14
    assert parse_unit_price("INR 120 per unit") == 120
    assert parse_unit_price("8 lakh") == 800000


def test_hard_filter_rejects_insufficient_quantity():
    requirement = ClientRequirement(
        client_id=1,
        category_id=1,
        company_name="A",
        product_requirement="steel brackets",
        quantity=5000,
        budget=800000,
        location="Pune",
        delivery_timeline="30 days",
    )
    offering = SupplierOffering(
        supplier_id=1,
        category_id=1,
        supplier_name="B",
        product_offered="steel brackets",
        available_quantity=100,
        pricing_details="INR 50 per unit",
        location="Pune",
        delivery_capability="7 days",
        status="ACTIVE",
    )
    result = evaluate_constraints(requirement, offering)
    assert result.passed is False
    assert result.quantity_ok is False


def test_empty_text_similarity_is_zero_or_low():
    encoder = SemanticEncoder().fit(["steel brackets industrial metal", "printed circuit boards"])
    score = encoder.similarity("", "")
    assert 0 <= score <= 1


def test_lsa_related_products_outrank_unrelated():
    encoder = SemanticEncoder.load()
    if encoder.pipeline is None:
        encoder = SemanticEncoder().fit(
            [
                "steel brackets industrial metal",
                "steel and aluminum mechanical parts",
                "printed circuit boards electronics",
            ]
        )
    related = encoder.similarity("industrial metal components", "steel and aluminum mechanical parts")
    unrelated = encoder.similarity("industrial metal components", "printed circuit boards")
    assert related > unrelated


def test_trained_model_predicts_probability():
    clear_model_cache()
    model = load_match_model()
    assert model is not None
    features = [0.8, 1.2, 0.7, 0.5, 0.5]
    assert len(features) == len(FEATURE_COLUMNS)
    score = model.predict_proba(features)
    assert 0.0 <= score <= 1.0


def test_matching_stores_real_scores():
    supplier = make_client()
    register_and_login(supplier, "sup-ai@example.com", "SUPPLIER")
    category_id = unique_category_id()
    created = supplier.post("/offerings", json=offering_payload(category_id))
    assert created.status_code == 201

    buyer = make_client()
    register_and_login(buyer, "cli-ai@example.com")
    requirement = buyer.post("/requirements", json=requirement_payload(category_id))
    assert requirement.status_code == 201, requirement.text
    body = requirement.json()
    assert body["match_count"] == 1
    match = body["matches"][0]
    assert match["final_score"] is not None
    assert 0 <= match["final_score"] <= 1
    assert match["semantic_score"] is not None
    assert match["ml_score"] is not None
    assert match["location"]
    assert "Quantity sufficient" in match["explanation"]
    assert "Location compatible" in match["explanation"]
    assert "delivery_warning" not in match
    notes = buyer.get("/notifications").json()
    assert any(item["notification_type"] == "MATCH" for item in notes)
    supplier_notes = supplier.get("/notifications").json()
    assert any(item["notification_type"] == "MATCH" for item in supplier_notes)


def test_no_match_when_over_budget():
    supplier = make_client()
    register_and_login(supplier, "sup-budget@example.com", "SUPPLIER")
    category_id = unique_category_id()
    supplier.post(
        "/offerings",
        json=offering_payload(category_id, pricing_details="INR 900 per unit"),
    )
    buyer = make_client()
    register_and_login(buyer, "cli-budget@example.com")
    requirement = buyer.post(
        "/requirements",
        json=requirement_payload(category_id, quantity=1000, budget=10000),
    )
    assert requirement.status_code == 201
    assert requirement.json()["match_count"] == 0


def test_notification_mark_read_idor():
    owner = make_client()
    register_and_login(owner, "cli-note-owner@example.com")
    category_id = unique_category_id()
    owner.post("/requirements", json=requirement_payload(category_id))
    notes = owner.get("/notifications").json()
    assert notes
    note_id = notes[0]["id"]
    other = make_client()
    register_and_login(other, "cli-note-other@example.com")
    assert other.post(f"/notifications/{note_id}/read").status_code == 404
    marked = owner.post(f"/notifications/{note_id}/read")
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True


def test_rfq_and_quotation_totals():
    supplier = make_client()
    register_and_login(supplier, "sup-rfq2@example.com", "SUPPLIER")
    category_id = unique_category_id()
    supplier.post("/offerings", json=offering_payload(category_id))

    buyer = make_client()
    register_and_login(buyer, "cli-rfq2@example.com")
    created = buyer.post("/requirements", json=requirement_payload(category_id))
    match_id = created.json()["matches"][0]["id"]
    rfq = buyer.post("/rfqs", json={"match_id": match_id, "notes": "Please quote"})
    assert rfq.status_code == 201, rfq.text
    rfq_id = rfq.json()["id"]
    assert buyer.get("/rfqs").json()[0]["id"] == rfq_id
    assert supplier.get(f"/rfqs/{rfq_id}").status_code == 200

    quote = supplier.post(
        f"/rfqs/{rfq_id}/quotations",
        json={
            "unit_price": 100,
            "quantity": 10,
            "shipping": 50,
            "tax": 18,
            "additional_charges": 7,
            "delivery": "10 days",
            "validity_days": 14,
            "payment_terms": "Net 30",
        },
    )
    assert quote.status_code == 201, quote.text
    assert quote.json()["subtotal"] == 1000
    assert quote.json()["total"] == 1075

    other = make_client()
    register_and_login(other, "cli-rfq-idor@example.com")
    assert other.get(f"/rfqs/{rfq_id}").status_code == 404
    assert other.post("/rfqs", json={"match_id": match_id}).status_code == 404
    assert other.post(
        f"/rfqs/{rfq_id}/quotations",
        json={
            "unit_price": 1,
            "quantity": 1,
            "delivery": "1 day",
            "validity_days": 7,
            "payment_terms": "Cash",
        },
    ).status_code == 403
    accepted = buyer.post(f"/rfqs/{rfq_id}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "ACCEPTED"
