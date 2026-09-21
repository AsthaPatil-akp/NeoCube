from app.commerce import (
    CURRENCY_COMPARISON_UNAVAILABLE,
    compare_commercial,
    parse_money,
    required_supplier_cost,
)
from app.extract import extract_fields
from app.ml.constraints import evaluate_constraints
from app.ml.inference import score_pair
from app.ml.model_store import load_match_model
from app.ml.nlp import SemanticEncoder
from app.models import Category, ClientRequirement, SupplierOffering
from app.taxonomy import categories_compatible, product_compatibility, product_family
from tests.test_modules import (
    make_client,
    offering_payload,
    register_and_login,
    requirement_payload,
    unique_category_id,
)


def _categories():
    return [
        (1, "Steel & Metals"),
        (2, "Electronics"),
        (8, "Other"),
    ]


def _tagged(entity, name, category_id=1, predefined=True, custom=None):
    entity.category_id = category_id
    entity.category = Category(name=name, is_predefined=predefined)
    entity.custom_category = custom
    return entity


def _pair(**kwargs):
    requirement = ClientRequirement(
        client_id=1,
        category_id=kwargs.get("req_category_id", 1),
        company_name=kwargs.get("company_name", "A"),
        product_requirement=kwargs.get("product_requirement", "steel brackets"),
        quantity=kwargs.get("quantity", 80),
        budget=kwargs.get("budget", 960000),
        budget_currency=kwargs.get("budget_currency"),
        budget_basis=kwargs.get("budget_basis"),
        location=kwargs.get("location", "Nashik, Maharashtra"),
        delivery_timeline=kwargs.get("delivery_timeline", "18 days"),
        additional_notes=kwargs.get("notes"),
        custom_category=kwargs.get("req_custom"),
    )
    offering = SupplierOffering(
        supplier_id=1,
        category_id=kwargs.get("off_category_id", kwargs.get("req_category_id", 1)),
        supplier_name=kwargs.get("supplier_name", "B"),
        product_offered=kwargs.get("product_offered", "steel brackets"),
        available_quantity=kwargs.get("available", 200),
        pricing_details=kwargs.get("pricing_details", "INR 11200 per unit"),
        price_amount=kwargs.get("price_amount"),
        price_currency=kwargs.get("price_currency"),
        price_basis=kwargs.get("price_basis"),
        location=kwargs.get("off_location", "Nashik, Maharashtra"),
        delivery_capability=kwargs.get("delivery", "12 days"),
        additional_notes=kwargs.get("offering_notes"),
        status="ACTIVE",
        custom_category=kwargs.get("off_custom"),
    )
    _tagged(
        requirement,
        kwargs.get("req_category_name", "Steel & Metals"),
        requirement.category_id,
        kwargs.get("req_predefined", True),
        kwargs.get("req_custom"),
    )
    _tagged(
        offering,
        kwargs.get("off_category_name", kwargs.get("req_category_name", "Steel & Metals")),
        offering.category_id,
        kwargs.get("off_predefined", True),
        kwargs.get("off_custom"),
    )
    return requirement, offering


def other_id(client):
    return next(item["id"] for item in client.get("/categories").json() if item["name"] == "Other")


def electronics_id(client):
    return next(item["id"] for item in client.get("/categories").json() if item["name"] == "Electronics")


def test_known_compatible_categories():
    requirement, offering = _pair(req_category_name="Electronics", off_category_name="Electronics")
    assert categories_compatible(requirement, offering) is True
    assert evaluate_constraints(requirement, offering).category_ok is True


def test_known_incompatible_categories():
    requirement, offering = _pair(
        req_category_name="Renewable Energy Equipment",
        off_category_name="Medical Equipment",
        req_predefined=False,
        off_predefined=False,
        product_requirement="Commercial rooftop solar panels",
        product_offered="Digital patient monitoring devices",
    )
    result = evaluate_constraints(requirement, offering)
    assert result.category_ok is False
    assert result.passed is False


def test_custom_category_is_stored_not_other():
    client = make_client()
    register_and_login(client, "cli-custom-cat@example.com")
    created = client.post(
        "/requirements",
        json=requirement_payload(
            other_id(client),
            custom_category="Renewable Energy Equipment",
            product_requirement="Commercial rooftop solar panels",
            quantity=80,
            budget=960000,
            budget_currency="INR",
            budget_basis="TOTAL",
        ),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["category_name"] == "Renewable Energy Equipment"
    assert body["category_name"] != "Other"
    listed = client.get("/categories").json()
    assert all(item["name"] != "Renewable Energy Equipment" or item["is_predefined"] is False for item in listed)
    assert all(item["is_predefined"] for item in listed)


def test_unknown_pdf_category_is_preserved():
    text = (
        "Client: BluePeak Retail Solutions Pvt. Ltd.\n"
        "Product: Commercial rooftop solar panels\n"
        "Category: Renewable Energy Equipment\n"
        "Quantity: 80\n"
        "Budget: 960000 INR\n"
        "Location: Nashik, Maharashtra\n"
        "Delivery: 18 days\n"
    )
    fields = extract_fields(text, _categories())
    assert fields["custom_category"] == "Renewable Energy Equipment"
    assert fields["category_id"] == 8
    assert fields["category_label"] == "Renewable Energy Equipment"


def test_other_is_not_a_wildcard():
    requirement, offering = _pair(
        req_category_name="Other",
        off_category_name="Other",
        product_requirement="Commercial rooftop solar panels",
        product_offered="Digital patient monitoring devices",
    )
    result = evaluate_constraints(requirement, offering)
    assert result.category_ok is False
    assert result.passed is False


def test_inr_total_budget_parse():
    money = parse_money("Budget: 960000 INR TOTAL")
    assert money.amount == 960000
    assert money.currency == "INR"
    assert money.basis == "TOTAL"


def test_inr_per_unit_budget_parse():
    money = parse_money("12000 INR per unit")
    assert money.amount == 12000
    assert money.currency == "INR"
    assert money.basis == "PER_UNIT"


def test_usd_total_budget_parse():
    money = parse_money("Budget: 12000 USD total")
    assert money.amount == 12000
    assert money.currency == "USD"
    assert money.basis == "TOTAL"


def test_usd_per_unit_budget_parse():
    money = parse_money("$12,000 per unit")
    assert money.amount == 12000
    assert money.currency == "USD"
    assert money.basis == "PER_UNIT"


def test_currency_mismatch_is_unavailable():
    requirement, offering = _pair(
        budget=900000,
        budget_currency="INR",
        budget_basis="TOTAL",
        price_amount=900000,
        price_currency="USD",
        price_basis="TOTAL",
        pricing_details="USD 900000 total",
    )
    result = evaluate_constraints(requirement, offering)
    assert result.passed is False
    assert result.currency_status == CURRENCY_COMPARISON_UNAVAILABLE
    assert "CURRENCY_COMPARISON_UNAVAILABLE" in result.reasons_fail


def test_budget_insufficient():
    requirement, offering = _pair(
        quantity=80,
        budget=10000,
        budget_currency="INR",
        budget_basis="TOTAL",
        price_amount=11200,
        price_currency="INR",
        price_basis="PER_UNIT",
        pricing_details="11200 INR per unit",
    )
    result = evaluate_constraints(requirement, offering)
    assert result.estimated_cost == 896000
    assert result.budget_ok is False
    assert result.passed is False


def test_budget_sufficient():
    requirement, offering = _pair(
        quantity=80,
        budget=960000,
        budget_currency="INR",
        budget_basis="TOTAL",
        price_amount=11200,
        price_currency="INR",
        price_basis="PER_UNIT",
        pricing_details="11200 INR per unit",
        product_requirement="Commercial rooftop solar panels",
        product_offered="Commercial rooftop solar panels",
        req_category_name="Renewable Energy Equipment",
        off_category_name="Renewable Energy Equipment",
        req_predefined=False,
        off_predefined=False,
    )
    result = evaluate_constraints(requirement, offering)
    assert result.estimated_cost == 896000
    assert result.budget_ok is True
    assert result.passed is True


def test_supplier_total_price():
    money = parse_money("900000 INR total")
    assert money.amount == 900000
    assert money.basis == "TOTAL"
    assert required_supplier_cost(80, money) == 900000


def test_supplier_per_unit_price():
    money = parse_money("11500 INR per unit")
    assert money.amount == 11500
    assert money.basis == "PER_UNIT"


def test_quantity_times_unit_price():
    money = parse_money("11200 INR per unit")
    assert required_supplier_cost(80, money) == 896000
    ok, cost, _status = compare_commercial(
        80,
        parse_money("960000 INR total"),
        money,
    )
    assert cost == 896000
    assert ok is True


def test_extract_inr_budget():
    fields = extract_fields("Budget: 960000 INR\nQuantity: 80", _categories())
    assert fields["budget"] == 960000
    assert fields["budget_amount"] == 960000
    assert fields["budget_currency"] == "INR"


def test_extract_usd_budget():
    fields = extract_fields("Budget: 12000 USD total", _categories())
    assert fields["budget"] == 12000
    assert fields["budget_currency"] == "USD"
    assert fields["budget_basis"] == "TOTAL"


def test_extract_per_unit_pricing():
    fields = extract_fields("Price: ₹11,200 per unit", _categories())
    assert fields["price_amount"] == 11200
    assert fields["price_currency"] == "INR"
    assert fields["price_basis"] == "PER_UNIT"


def test_extract_total_pricing():
    fields = extract_fields("Price: 900000 INR total", _categories())
    assert fields["price_amount"] == 900000
    assert fields["price_basis"] == "TOTAL"


def test_extract_custom_category_and_quantity_unit():
    fields = extract_fields("Category: Renewable Energy Equipment\nQuantity: 80 units", _categories())
    assert fields["custom_category"] == "Renewable Energy Equipment"
    assert fields["quantity"] == 80
    assert fields["quantity_unit"] == "units"


def test_extract_form_pdf_without_colons_client():
    text = (
        "Client Requirement Client—Supplier Matchmaking Platform Demo Field Value "
        "Company / Client Name Apex Facilities Management Pvt. Ltd. "
        "Category Renewable Energy Equipment "
        "Product Requirement Commercial rooftop solar panels "
        "Quantity Required 120 Quantity Unit units "
        "Budget Amount 1,200,000 Currency INR Budget Basis Total budget "
        "Location Pune, Maharashtra Delivery Timeline 20 days"
    )
    fields = extract_fields(text, _categories())
    assert fields["company_name"] == "Apex Facilities Management Pvt. Ltd"
    assert fields["custom_category"] == "Renewable Energy Equipment"
    assert fields["category_id"] == 8
    assert fields["product"] == "Commercial rooftop solar panels"
    assert fields["quantity"] == 120
    assert fields["quantity_unit"] == "units"
    assert fields["budget_amount"] == 1_200_000
    assert fields["budget"] == 1_200_000
    assert fields["budget_currency"] == "INR"
    assert fields["budget_basis"] == "TOTAL"
    assert fields["location"] == "Pune, Maharashtra"
    assert fields["delivery_timeline"] == "20 days"


def test_extract_pdf_pricing_amount_on_next_line():
    text = (
        "Supplier Name\nSunPeak Energy Solutions Pvt. Ltd.\n"
        "Category\nRenewable Energy Equipment\n"
        "Product Offered\nCommercial rooftop solar panels\n"
        "Available Quantity\n300\n"
        "Quantity Unit\nunits\n"
        "Pricing Amount\n11,000\n"
        "Currency\nINR\n"
        "Pricing Basis\nPer unit\n"
        "Location\nPune, Maharashtra\n"
        "Delivery Capability\n14 days"
    )
    fields = extract_fields(text, _categories())
    assert fields["price_amount"] == 11000
    assert fields["price_currency"] == "INR"
    assert fields["price_basis"] == "PER_UNIT"
    assert fields["quantity"] == 300
    assert fields["product"] == "Commercial rooftop solar panels"


def test_extract_form_pdf_without_colons_supplier():
    text = (
        "Supplier Offering Client—Supplier Matchmaking Platform Demo Field Value "
        "Company / Supplier Name Helios Solar Components Pvt. Ltd. "
        "Category Renewable Energy Equipment "
        "Product Offered Commercial rooftop solar panels "
        "Available Quantity 500 Quantity Unit units "
        "Price Amount 11,200 Currency INR Price Basis Per unit "
        "Location Nashik, Maharashtra Delivery Capability 14 days"
    )
    fields = extract_fields(text, _categories())
    assert fields["company_name"] == "Helios Solar Components Pvt. Ltd"
    assert fields["custom_category"] == "Renewable Energy Equipment"
    assert fields["category_id"] == 8
    assert fields["product"] == "Commercial rooftop solar panels"
    assert fields["quantity"] == 500
    assert fields["quantity_unit"] == "units"
    assert fields["price_amount"] == 11200
    assert fields["price_currency"] == "INR"
    assert fields["price_basis"] == "PER_UNIT"
    assert fields["location"] == "Nashik, Maharashtra"
    assert fields["delivery_timeline"] == "14 days"


def test_extract_predefined_category_not_other():
    fields = extract_fields("Category: Electronics\nQuantity: 10 boxes\nBudget Amount 50000", _categories())
    assert fields["category_id"] == 2
    assert "custom_category" not in fields
    assert fields["quantity"] == 10
    assert fields["quantity_unit"] == "boxes"
    assert fields["budget_amount"] == 50000


def test_solar_vs_medical_not_eligible():
    requirement, offering = _pair(
        product_requirement="Commercial rooftop solar panels",
        product_offered="Digital patient monitoring devices",
        req_category_name="Renewable Energy Equipment",
        off_category_name="Medical Equipment",
        req_predefined=False,
        off_predefined=False,
        budget_currency="INR",
        budget_basis="TOTAL",
        price_amount=11200,
        price_currency="INR",
        price_basis="PER_UNIT",
    )
    encoder = SemanticEncoder.load()
    model = load_match_model()
    result = evaluate_constraints(requirement, offering)
    assert result.passed is False
    assert result.product_ok is False or result.category_ok is False
    assert product_family(requirement.product_requirement) == "solar"
    assert product_family(offering.product_offered) == "medical"
    assert score_pair(requirement, offering, encoder, model) is None
    semantic = encoder.similarity(requirement.product_requirement, offering.product_offered)
    assert 0 <= semantic <= 1


def test_compatible_solar_pair_is_eligible():
    requirement, offering = _pair(
        product_requirement="Commercial rooftop solar panels",
        product_offered="Commercial rooftop solar panels",
        req_category_name="Renewable Energy Equipment",
        off_category_name="Renewable Energy Equipment",
        req_predefined=False,
        off_predefined=False,
        budget=960000,
        budget_currency="INR",
        budget_basis="TOTAL",
        price_amount=11200,
        price_currency="INR",
        price_basis="PER_UNIT",
        quantity=80,
        available=200,
        delivery_timeline="18 days",
        delivery="12 days",
    )
    result = evaluate_constraints(requirement, offering)
    assert result.passed is True
    assert result.category_ok is True
    assert result.product_ok is True
    assert product_compatibility(requirement.product_requirement, offering.product_offered)[1] == "known_compatible"


def test_insufficient_quantity_not_eligible():
    requirement, offering = _pair(quantity=80, available=10)
    result = evaluate_constraints(requirement, offering)
    assert result.quantity_ok is False
    assert result.passed is False


def test_delivery_incompatible_not_eligible():
    requirement, offering = _pair(delivery_timeline="18 days", delivery="30 days")
    result = evaluate_constraints(requirement, offering)
    assert result.delivery_ok is False
    assert result.passed is False


def test_custom_category_compatible_through_product_family():
    requirement, offering = _pair(
        product_requirement="commercial solar rooftop panels",
        product_offered="Commercial rooftop solar panel",
        req_category_name="Renewable Energy Equipment",
        off_category_name="Renewable Energy Equipment",
        req_predefined=False,
        off_predefined=False,
        budget_currency="INR",
        price_currency="INR",
        price_amount=11200,
        price_basis="PER_UNIT",
        budget_basis="TOTAL",
    )
    result = evaluate_constraints(requirement, offering)
    assert result.passed is True
    assert result.product_family_status == "known_compatible"


def test_ml_only_ranks_eligible_candidates():
    encoder = SemanticEncoder.load()
    model = load_match_model()
    bad_req, bad_off = _pair(
        product_requirement="Commercial rooftop solar panels",
        product_offered="Digital patient monitoring devices",
        req_category_name="Other",
        off_category_name="Other",
    )
    good_req, good_off = _pair(
        product_requirement="Commercial rooftop solar panels",
        product_offered="Commercial rooftop solar panels",
        req_category_name="Renewable Energy Equipment",
        off_category_name="Renewable Energy Equipment",
        req_predefined=False,
        off_predefined=False,
        budget_currency="INR",
        price_currency="INR",
        price_amount=11200,
        price_basis="PER_UNIT",
        budget_basis="TOTAL",
    )
    assert score_pair(bad_req, bad_off, encoder, model) is None
    scored = score_pair(good_req, good_off, encoder, model)
    assert scored is not None
    assert scored["final_score"] == scored["ml_score"]


def test_bluepeak_e2e_solar_eligible_medical_not():
    other = None
    medical = make_client()
    register_and_login(medical, "sup-medical-xyz@example.com", "SUPPLIER")
    other = other_id(medical)
    medical_offering = medical.post(
        "/offerings",
        json=offering_payload(
            other,
            supplier_name="xyz",
            product_offered="Digital patient monitoring devices",
            custom_category="Medical Equipment",
            available_quantity=200,
            price_amount=11200,
            price_currency="INR",
            price_basis="PER_UNIT",
            location="Ahmedabad, Gujarat",
            delivery_capability="12 days",
        ),
    )
    assert medical_offering.status_code == 201, medical_offering.text

    solar_supplier = make_client()
    register_and_login(solar_supplier, "sup-greengrid@example.com", "SUPPLIER")
    solar_offering = solar_supplier.post(
        "/offerings",
        json=offering_payload(
            other_id(solar_supplier),
            supplier_name="GreenGrid Solar Systems Pvt. Ltd.",
            product_offered="Commercial rooftop solar panels",
            custom_category="Renewable Energy Equipment",
            available_quantity=200,
            price_amount=11200,
            price_currency="INR",
            price_basis="PER_UNIT",
            location="Nashik, Maharashtra",
            delivery_capability="12 days",
        ),
    )
    assert solar_offering.status_code == 201, solar_offering.text

    buyer = make_client()
    register_and_login(buyer, "cli-bluepeak@example.com", company_name="BluePeak Retail Solutions Pvt. Ltd.")
    created = buyer.post(
        "/requirements",
        json=requirement_payload(
            other_id(buyer),
            company_name="BluePeak Retail Solutions Pvt. Ltd.",
            product_requirement="Commercial rooftop solar panels",
            custom_category="Renewable Energy Equipment",
            quantity=80,
            budget=960000,
            budget_currency="INR",
            budget_basis="TOTAL",
            location="Nashik, Maharashtra",
            delivery_timeline="18 days",
        ),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["category_name"] == "Renewable Energy Equipment"
    products = [item["product_offered"] for item in body["matches"]]
    assert "Digital patient monitoring devices" not in products
    assert "Commercial rooftop solar panels" in products
    assert body["match_count"] == 1
    match = body["matches"][0]
    assert match["supplier_name"] == "GreenGrid Solar Systems Pvt. Ltd."
    assert match["final_score"] == match["ml_score"]


def test_stale_matches_do_not_attach_to_unrelated_requirements():
    category_a = unique_category_id()
    supplier = make_client()
    register_and_login(supplier, "sup-stale-med@example.com", "SUPPLIER")
    created_offering = supplier.post(
        "/offerings",
        json=offering_payload(category_a, product_offered="Digital patient monitoring devices"),
    )
    assert created_offering.status_code == 201
    offering_id = created_offering.json()["id"]

    medical_buyer = make_client()
    register_and_login(medical_buyer, "cli-stale-med@example.com")
    medical_req = medical_buyer.post(
        "/requirements",
        json=requirement_payload(category_a, product_requirement="Digital patient monitoring devices"),
    )
    assert medical_req.status_code == 201
    assert medical_req.json()["match_count"] == 1
    assert medical_req.json()["matches"][0]["offering_id"] == offering_id

    solar_buyer = make_client()
    register_and_login(solar_buyer, "cli-stale-solar@example.com")
    solar_req = solar_buyer.post(
        "/requirements",
        json=requirement_payload(
            other_id(solar_buyer),
            product_requirement="Commercial rooftop solar panels",
            custom_category="Renewable Energy Equipment",
            quantity=80,
            budget=960000,
            budget_currency="INR",
            budget_basis="TOTAL",
        ),
    )
    assert solar_req.status_code == 201, solar_req.text
    solar_body = solar_req.json()
    assert all(item["offering_id"] != offering_id for item in solar_body["matches"])
    assert solar_body["id"] != medical_req.json()["id"]
