from pathlib import Path

from app.config import settings
from app.ml.constraints import evaluate_constraints
from app.models import ClientRequirement, SupplierOffering
from tests.test_modules import (
    make_client,
    offering_payload,
    register_and_login,
    requirement_payload,
    unique_category_id,
)


def _pair(client_days="5 days", supplier_days="5 days", client_location="Pune", supplier_location="Pune"):
    requirement = ClientRequirement(
        client_id=1,
        category_id=1,
        company_name="A",
        product_requirement="steel brackets",
        quantity=1000,
        budget=800000,
        location=client_location,
        delivery_timeline=client_days,
    )
    offering = SupplierOffering(
        supplier_id=1,
        category_id=1,
        supplier_name="B",
        product_offered="steel brackets",
        available_quantity=5000,
        pricing_details="INR 50 per unit",
        location=supplier_location,
        delivery_capability=supplier_days,
        status="ACTIVE",
    )
    return requirement, offering


def test_hard_filter_accepts_declared_delivery_within_timeline():
    requirement, offering = _pair(client_days="5 days", supplier_days="5 days")
    result = evaluate_constraints(requirement, offering)
    assert result.passed is True
    assert result.delivery_ok is True
    assert result.client_days == 5
    assert result.supplier_days == 5


def test_hard_filter_rejects_slower_declared_delivery():
    requirement, offering = _pair(client_days="5 days", supplier_days="10 days")
    result = evaluate_constraints(requirement, offering)
    assert result.passed is False
    assert result.delivery_ok is False
    assert "Delivery capability is slower than the required timeline" in result.reasons_fail


def test_location_overlap_does_not_infer_delivery_time():
    requirement, offering = _pair(
        client_days="5 days",
        supplier_days="4 days",
        client_location="Mumbai",
        supplier_location="Delhi",
    )
    result = evaluate_constraints(requirement, offering)
    assert result.passed is True
    assert result.delivery_ok is True


def test_declared_delivery_within_timeline_is_eligible_match():
    supplier = make_client()
    register_and_login(supplier, "sup-deliv-ok@example.com", "SUPPLIER")
    category_id = unique_category_id()
    created = supplier.post(
        "/offerings",
        json=offering_payload(category_id, location="Pune", delivery_capability="5 days"),
    )
    assert created.status_code == 201

    buyer = make_client()
    register_and_login(buyer, "cli-deliv-ok@example.com")
    requirement = buyer.post(
        "/requirements",
        json=requirement_payload(category_id, location="Pune", delivery_timeline="5 days"),
    )
    assert requirement.status_code == 201, requirement.text
    body = requirement.json()
    assert body["match_count"] == 1
    match = body["matches"][0]
    assert match["location"] == "Pune"
    assert body["location"] == "Pune"
    assert "Delivery compatible" in match["explanation"]
    assert "Location compatible" in match["explanation"]
    assert "delivery_warning" not in match
    assert "estimated_transit_days" not in match
    assert "delivery_status" not in match
    assert match["ml_score"] is not None
    assert match["final_score"] == match["ml_score"]

    listed = buyer.get("/requirements").json()
    assert listed[0]["matches"][0]["location"] == "Pune"
    supplier_view = supplier.get(f"/offerings/{created.json()['id']}").json()
    assert supplier_view["location"] == "Pune"
    assert supplier_view["matches"][0]["location"] == "Pune"


def test_declared_delivery_slower_than_required_is_not_a_match():
    supplier = make_client()
    register_and_login(supplier, "sup-deliv-slow@example.com", "SUPPLIER")
    category_id = unique_category_id()
    supplier.post(
        "/offerings",
        json=offering_payload(category_id, location="Pune", delivery_capability="10 days"),
    )
    buyer = make_client()
    register_and_login(buyer, "cli-deliv-slow@example.com")
    requirement = buyer.post(
        "/requirements",
        json=requirement_payload(category_id, location="Pune", delivery_timeline="5 days"),
    )
    assert requirement.status_code == 201
    assert requirement.json()["match_count"] == 0


def test_distant_locations_still_match_when_declared_delivery_fits():
    supplier = make_client()
    register_and_login(supplier, "sup-deliv-dist@example.com", "SUPPLIER")
    category_id = unique_category_id()
    created = supplier.post(
        "/offerings",
        json=offering_payload(category_id, location="Delhi", delivery_capability="4 days"),
    )
    assert created.status_code == 201
    buyer = make_client()
    register_and_login(buyer, "cli-deliv-dist@example.com")
    requirement = buyer.post(
        "/requirements",
        json=requirement_payload(category_id, location="Mumbai", delivery_timeline="5 days"),
    )
    assert requirement.status_code == 201, requirement.text
    body = requirement.json()
    assert body["match_count"] == 1
    match = body["matches"][0]
    assert match["location"] == "Delhi"
    assert body["location"] == "Mumbai"
    assert "Delivery compatible" in match["explanation"]
    assert "delivery_warning" not in match
    joined = " ".join(match["explanation"]).lower()
    assert "google" not in joined
    assert "transit" not in joined
    assert "route" not in joined


def test_google_route_modules_are_removed():
    app_dir = Path(__file__).resolve().parents[1] / "app"
    assert not (app_dir / "maps_routes.py").exists()
    assert not (app_dir / "delivery.py").exists()
    dumped = settings.model_dump()
    assert "google_maps_api_key" not in dumped
    assert "GOOGLE_MAPS_API_KEY" not in dumped
