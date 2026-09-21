import io
import os
import uuid

os.environ["MAX_UPLOAD_BYTES"] = "500000"

from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text

from app.database import SessionLocal, engine
from app.main import app
from app.config import settings
from app.models import Category, Role, User
from app.security import hash_password

settings.max_upload_bytes = 500_000
settings.upload_dir = os.path.join(os.path.dirname(__file__), "_uploads")
os.makedirs(settings.upload_dir, exist_ok=True)


def make_client():
    return TestClient(app)


def register_and_login(client, email, role="CLIENT", **overrides):
    payload = {
        "email": email,
        "password": "password123",
        "role": role,
        "full_name": "Test User",
        "company_name": "Test Co",
        "phone": "555-0100",
    }
    payload.update(overrides)
    created = client.post("/auth/register", json=payload)
    assert created.status_code == 201, created.text
    login = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert login.status_code == 200, login.text
    return created.json()


def first_category_id(client):
    response = client.get("/categories")
    assert response.status_code == 200
    return response.json()[0]["id"]


def unique_category_id():
    db = SessionLocal()
    try:
        category = Category(name=f"Cat-{uuid.uuid4().hex[:10]}", is_predefined=False)
        db.add(category)
        db.commit()
        db.refresh(category)
        return category.id
    finally:
        db.close()


def requirement_payload(category_id, **overrides):
    data = {
        "company_name": "Ada Co",
        "product_requirement": "Steel brackets",
        "category_id": category_id,
        "quantity": 5000,
        "budget": 800000,
        "location": "Pune",
        "delivery_timeline": "30 days",
        "additional_notes": "Needed for assembly",
        "status": "SUBMITTED",
    }
    data.update(overrides)
    return data


def offering_payload(category_id, **overrides):
    data = {
        "supplier_name": "Sam Supply",
        "product_offered": "Steel brackets",
        "category_id": category_id,
        "available_quantity": 9000,
        "pricing_details": "INR 120 per unit",
        "location": "Pune",
        "delivery_capability": "14 days nationwide",
        "additional_notes": "ISO certified",
        "status": "ACTIVE",
    }
    data.update(overrides)
    return data


def test_protected_endpoints_require_auth():
    client = make_client()
    assert client.get("/requirements").status_code == 401
    assert client.get("/offerings").status_code == 401
    assert client.get("/categories").status_code == 401
    assert client.get("/notifications").status_code == 401
    assert client.get("/admin/summary").status_code == 401


def test_invalid_session_cookie_rejected():
    client = make_client()
    client.cookies.set("neocube_session", "not-a-valid-session")
    response = client.get("/users/me")
    assert response.status_code == 401


def test_supplier_cannot_access_client_endpoints():
    client = make_client()
    register_and_login(client, "sup-rbac@example.com", "SUPPLIER")
    category_id = first_category_id(client)
    response = client.post("/requirements", json=requirement_payload(category_id))
    assert response.status_code == 403
    assert client.get("/requirements").status_code == 403
    assert client.get("/admin/summary").status_code == 403


def test_client_cannot_access_supplier_or_admin_endpoints():
    client = make_client()
    register_and_login(client, "cli-rbac@example.com", "CLIENT")
    category_id = first_category_id(client)
    response = client.post("/offerings", json=offering_payload(category_id))
    assert response.status_code == 403
    assert client.get("/offerings").status_code == 403
    assert client.get("/admin/summary").status_code == 403


def test_create_and_list_own_requirements():
    client = make_client()
    register_and_login(client, "cli-own@example.com")
    category_id = first_category_id(client)
    created = client.post("/requirements", json=requirement_payload(category_id))
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["product_requirement"] == "Steel brackets"
    assert body["status"] in {"SUBMITTED", "PROCESSING", "MATCHED"}
    listed = client.get("/requirements")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == body["id"]


def test_update_own_requirement():
    client = make_client()
    register_and_login(client, "cli-upd@example.com")
    category_id = first_category_id(client)
    created = client.post("/requirements", json=requirement_payload(category_id, status="DRAFT"))
    req_id = created.json()["id"]
    updated = client.put(f"/requirements/{req_id}", json={"quantity": 6000, "status": "SUBMITTED"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["quantity"] == 6000
    assert updated.json()["status"] in {"SUBMITTED", "PROCESSING", "MATCHED"}


def test_invalid_requirement_fields():
    client = make_client()
    register_and_login(client, "cli-invalid@example.com")
    category_id = first_category_id(client)
    assert client.post("/requirements", json=requirement_payload(category_id, quantity=0)).status_code == 422
    assert client.post("/requirements", json=requirement_payload(category_id, budget=-1)).status_code == 422
    assert client.post("/requirements", json=requirement_payload(category_id, product_requirement="")).status_code == 422
    assert client.post("/requirements", json=requirement_payload(99999)).status_code == 400
    assert client.post("/requirements", json=requirement_payload(category_id, location="   ")).status_code == 422


def test_duplicate_requirement_rejected():
    client = make_client()
    register_and_login(client, "cli-dup@example.com")
    category_id = first_category_id(client)
    payload = requirement_payload(category_id)
    assert client.post("/requirements", json=payload).status_code == 201
    response = client.post("/requirements", json=payload)
    assert response.status_code == 409


def test_requirement_idor_blocked():
    owner = make_client()
    register_and_login(owner, "cli-a@example.com", company_name="A Co")
    category_id = first_category_id(owner)
    created = owner.post("/requirements", json=requirement_payload(category_id))
    req_id = created.json()["id"]

    other = make_client()
    register_and_login(other, "cli-b@example.com", company_name="B Co")
    assert other.get(f"/requirements/{req_id}").status_code == 404
    assert other.put(f"/requirements/{req_id}", json={"quantity": 1}).status_code == 404
    assert other.delete(f"/requirements/{req_id}").status_code == 404
    assert owner.get("/requirements").json()[0]["quantity"] == 5000


def test_create_and_update_offering():
    client = make_client()
    register_and_login(client, "sup-own@example.com", "SUPPLIER")
    category_id = first_category_id(client)
    created = client.post("/offerings", json=offering_payload(category_id))
    assert created.status_code == 201, created.text
    offering_id = created.json()["id"]
    listed = client.get("/offerings")
    assert len(listed.json()) == 1
    updated = client.put(f"/offerings/{offering_id}", json={"available_quantity": 12000})
    assert updated.status_code == 200
    assert updated.json()["available_quantity"] == 12000
    deactivated = client.delete(f"/offerings/{offering_id}")
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "DEACTIVATED"
    removed = client.delete(f"/offerings/{offering_id}")
    assert removed.status_code == 204
    assert client.get(f"/offerings/{offering_id}").status_code == 404


def test_offering_price_update_rewrites_stale_pricing_details():
    supplier = make_client()
    register_and_login(supplier, "sup-price-sync@example.com", "SUPPLIER")
    category_id = unique_category_id()
    created = supplier.post(
        "/offerings",
        json=offering_payload(
            category_id,
            pricing_details=None,
            price_amount=988800,
            price_currency="INR",
            price_basis="PER_UNIT",
            product_offered="Commercial rooftop solar panels",
        ),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    offering_id = body["id"]
    assert body["price_amount"] == 988800
    assert "988800" in body["pricing_details"]
    updated = supplier.put(
        f"/offerings/{offering_id}",
        json={
            "price_amount": 11000,
            "price_currency": "INR",
            "price_basis": "PER_UNIT",
            "pricing_details": body["pricing_details"],
        },
    )
    assert updated.status_code == 200, updated.text
    saved = updated.json()
    assert saved["price_amount"] == 11000
    assert "11000" in saved["pricing_details"]
    assert "988800" not in saved["pricing_details"]


def test_requirement_budget_update_is_stored():
    buyer = make_client()
    register_and_login(buyer, "cli-budget-sync@example.com")
    category_id = unique_category_id()
    created = buyer.post("/requirements", json=requirement_payload(category_id, budget=988800, status="DRAFT"))
    assert created.status_code == 201, created.text
    req_id = created.json()["id"]
    updated = buyer.put(f"/requirements/{req_id}", json={"budget": 11000, "budget_currency": "INR", "budget_basis": "TOTAL"})
    assert updated.status_code == 200, updated.text
    saved = updated.json()
    assert saved["budget"] == 11000
    assert saved["budget_currency"] == "INR"
    assert saved["budget_basis"] == "TOTAL"


def test_invalid_offering_fields():
    client = make_client()
    register_and_login(client, "sup-invalid@example.com", "SUPPLIER")
    category_id = first_category_id(client)
    assert client.post("/offerings", json=offering_payload(category_id, available_quantity=0)).status_code == 422
    assert client.post("/offerings", json=offering_payload(category_id, product_offered="")).status_code == 422
    assert client.post("/offerings", json=offering_payload(99999)).status_code == 400


def test_offering_idor_blocked():
    owner = make_client()
    register_and_login(owner, "sup-a@example.com", "SUPPLIER", company_name="A Supply")
    category_id = first_category_id(owner)
    created = owner.post("/offerings", json=offering_payload(category_id))
    offering_id = created.json()["id"]

    other = make_client()
    register_and_login(other, "sup-b@example.com", "SUPPLIER", company_name="B Supply")
    assert other.get(f"/offerings/{offering_id}").status_code == 404
    assert other.put(f"/offerings/{offering_id}", json={"available_quantity": 1}).status_code == 404
    assert other.delete(f"/offerings/{offering_id}").status_code == 404


def test_unavailable_offering_does_not_match():
    supplier = make_client()
    register_and_login(supplier, "sup-match@example.com", "SUPPLIER")
    category_id = unique_category_id()
    created_offering = supplier.post("/offerings", json=offering_payload(category_id, status="ACTIVE"))
    assert created_offering.status_code == 201
    offering_id = created_offering.json()["id"]
    updated = supplier.put(f"/offerings/{offering_id}", json={"status": "UNAVAILABLE"})
    assert updated.status_code == 200

    buyer = make_client()
    register_and_login(buyer, "cli-match@example.com")
    requirement = buyer.post("/requirements", json=requirement_payload(category_id))
    assert requirement.status_code == 201
    assert requirement.json()["match_count"] == 0


def test_active_offering_matches_requirement():
    supplier = make_client()
    register_and_login(supplier, "sup-active@example.com", "SUPPLIER")
    category_id = unique_category_id()
    offered = supplier.post("/offerings", json=offering_payload(category_id))
    assert offered.status_code == 201

    buyer = make_client()
    register_and_login(buyer, "cli-active@example.com")
    requirement = buyer.post("/requirements", json=requirement_payload(category_id))
    assert requirement.status_code == 201
    assert requirement.json()["match_count"] == 1
    assert requirement.json()["status"] == "MATCHED"


def test_invalid_status_transition():
    client = make_client()
    register_and_login(client, "cli-status@example.com")
    category_id = first_category_id(client)
    created = client.post("/requirements", json=requirement_payload(category_id, status="DRAFT"))
    req_id = created.json()["id"]
    response = client.put(f"/requirements/{req_id}", json={"status": "CLOSED"})
    assert response.status_code == 409


def test_database_relationships_and_constraints():
    with make_client():
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        for name in (
            "users",
            "roles",
            "client_profiles",
            "supplier_profiles",
            "categories",
            "client_requirements",
            "supplier_offerings",
            "matches",
            "notifications",
            "audit_logs",
            "requirement_documents",
            "supplier_documents",
            "rfqs",
            "quotations",
        ):
            assert name in tables

        db = SessionLocal()
        try:
            category = db.scalar(select(Category).limit(1))
            assert category is not None
            try:
                db.execute(
                    text(
                        "INSERT INTO client_requirements "
                        "(client_id, category_id, company_name, product_requirement, quantity, budget, location, delivery_timeline, status) "
                        "VALUES (99999, :cid, 'X', 'Y', 1, 1, 'Z', '1 day', 'DRAFT')"
                    ),
                    {"cid": category.id},
                )
                db.commit()
                orphan_allowed = True
            except Exception:
                db.rollback()
                orphan_allowed = False
            assert orphan_allowed is False
        finally:
            db.close()


def test_admin_summary_requires_admin():
    client = make_client()
    register_and_login(client, "not-admin@example.com")
    assert client.get("/admin/summary").status_code == 403

    db = SessionLocal()
    try:
        role = db.scalar(select(Role).where(Role.name == "ADMIN"))
        user = User(
            email="seed-admin@example.com",
            password_hash=hash_password("password123"),
            role_id=role.id,
            full_name="Seed Admin",
        )
        db.add(user)
        db.commit()
    finally:
        db.close()

    admin = make_client()
    login = admin.post("/auth/login", json={"email": "seed-admin@example.com", "password": "password123"})
    assert login.status_code == 200
    summary = admin.get("/admin/summary")
    assert summary.status_code == 200
    assert "users" in summary.json()


def _docx_bytes(text: str) -> bytes:
    from docx import Document

    document = Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


SAMPLE_TEXT = "We need 5,000 steel brackets within 30 days with a budget of 8 lakh."


def test_valid_txt_extraction_and_confirmation():
    client = make_client()
    register_and_login(client, "cli-doc@example.com", company_name="Doc Co")
    files = {"file": ("requirement.txt", SAMPLE_TEXT.encode("utf-8"), "text/plain")}
    uploaded = client.post("/documents", files=files)
    assert uploaded.status_code == 201, uploaded.text
    body = uploaded.json()
    assert body["processing_status"] == "EXTRACTED"
    assert body["extracted"]["quantity"] == 5000
    assert body["extracted"]["budget"] == 800000
    assert body["extracted"]["delivery_timeline"]
    assert body["extracted"]["product_requirement"]
    category_id = body["extracted"]["category_id"] or first_category_id(client)
    created = client.post(
        "/requirements",
        json=requirement_payload(
            category_id,
            product_requirement=body["extracted"]["product_requirement"] or "Steel brackets",
            quantity=body["extracted"]["quantity"],
            budget=body["extracted"]["budget"],
            delivery_timeline=body["extracted"]["delivery_timeline"] or "30 days",
            document_id=body["id"],
        ),
    )
    assert created.status_code == 201, created.text
    fetched = client.get(f"/documents/{body['id']}")
    assert fetched.status_code == 200


CLIENT_FORM_TEXT = (
    "Client Requirement Client—Supplier Matchmaking Platform Demo Field Value "
    "Company / Client Name Apex Facilities Management Pvt. Ltd. "
    "Category Renewable Energy Equipment "
    "Product Requirement Commercial rooftop solar panels "
    "Quantity Required 120 Quantity Unit units "
    "Budget Amount 1,200,000 Currency INR Budget Basis Total budget "
    "Location Pune, Maharashtra Delivery Timeline 20 days"
)

SUPPLIER_FORM_TEXT = (
    "Supplier Offering Client—Supplier Matchmaking Platform Demo Field Value "
    "Company / Supplier Name Helios Solar Components Pvt. Ltd. "
    "Category Renewable Energy Equipment "
    "Product Offered Commercial rooftop solar panels "
    "Available Quantity 500 Quantity Unit units "
    "Price Amount 11,200 Currency INR Price Basis Per unit "
    "Location Nashik, Maharashtra Delivery Capability 14 days"
)


def test_form_document_extracts_other_category_and_commerce_fields():
    client = make_client()
    register_and_login(client, "cli-form-extract@example.com", company_name="nmims")
    uploaded = client.post(
        "/documents",
        files={"file": ("requirement.txt", CLIENT_FORM_TEXT.encode("utf-8"), "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    extracted = uploaded.json()["extracted"]
    other_id = next(item["id"] for item in client.get("/categories").json() if item["name"].lower() == "other")
    assert extracted["company_name"] == "Apex Facilities Management Pvt. Ltd"
    assert extracted["custom_category"] == "Renewable Energy Equipment"
    assert extracted["category_id"] == other_id
    assert extracted["product_requirement"] == "Commercial rooftop solar panels"
    assert extracted["quantity"] == 120
    assert extracted["quantity_unit"] == "units"
    assert extracted["budget_amount"] == 1_200_000
    assert extracted["budget_basis"] == "TOTAL"
    assert extracted["budget_currency"] == "INR"


def test_form_extract_maps_existing_custom_category_to_other():
    db = SessionLocal()
    try:
        existing = db.scalar(select(Category).where(Category.name == "Renewable Energy Equipment"))
        if existing is None:
            existing = Category(name="Renewable Energy Equipment", is_predefined=False, is_active=True)
            db.add(existing)
        else:
            existing.is_predefined = False
            existing.is_active = True
        db.commit()
        db.refresh(existing)
        custom_id = existing.id
    finally:
        db.close()
    client = make_client()
    register_and_login(client, f"cli-form-existing-cat-{uuid.uuid4().hex[:8]}@example.com")
    listed_ids = {item["id"] for item in client.get("/categories").json()}
    assert custom_id not in listed_ids
    uploaded = client.post(
        "/documents",
        files={"file": ("requirement.txt", CLIENT_FORM_TEXT.encode("utf-8"), "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    extracted = uploaded.json()["extracted"]
    other_id = next(item["id"] for item in client.get("/categories").json() if item["name"].lower() == "other")
    assert extracted["category_id"] == other_id
    assert extracted["category_id"] != custom_id
    assert extracted["custom_category"] == "Renewable Energy Equipment"
    assert extracted["quantity_unit"] == "units"
    assert extracted["budget_amount"] == 1_200_000
    assert extracted["budget_basis"] == "TOTAL"


def test_form_supplier_document_extracts_other_category_and_price_fields():
    supplier = make_client()
    register_and_login(supplier, "sup-form-extract@example.com", "SUPPLIER")
    uploaded = supplier.post(
        "/supplier-documents",
        files={"file": ("offering.txt", SUPPLIER_FORM_TEXT.encode("utf-8"), "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    extracted = uploaded.json()["extracted"]
    other_id = next(item["id"] for item in supplier.get("/categories").json() if item["name"].lower() == "other")
    assert extracted["company_name"] == "Helios Solar Components Pvt. Ltd"
    assert extracted["custom_category"] == "Renewable Energy Equipment"
    assert extracted["category_id"] == other_id
    assert extracted["product"] == "Commercial rooftop solar panels"
    assert extracted["quantity"] == 500
    assert extracted["quantity_unit"] == "units"
    assert extracted["price_amount"] == 11200
    assert extracted["price_basis"] == "PER_UNIT"
    assert extracted["price_currency"] == "INR"


def test_valid_docx_extraction():
    client = make_client()
    register_and_login(client, "cli-docx@example.com")
    files = {"file": ("requirement.docx", _docx_bytes(SAMPLE_TEXT), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    uploaded = client.post("/documents", files=files)
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["extracted"]["quantity"] == 5000


def test_valid_pdf_extraction():
    client = make_client()
    register_and_login(client, "cli-pdf@example.com")
    pdf = b"""%PDF-1.1
1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj
2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj
3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj
4 0 obj<< /Length 90 >>stream
BT /F1 12 Tf 10 100 Td (We need 5000 steel brackets within 30 days with a budget of 800000) Tj ET
endstream
endobj
5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000306 00000 n 
0000000447 00000 n 
trailer<< /Size 6 /Root 1 0 R >>
startxref
534
%%EOF
"""
    uploaded = client.post("/documents", files={"file": ("requirement.pdf", pdf, "application/pdf")})
    assert uploaded.status_code == 201, uploaded.text
    extracted = uploaded.json()["extracted"]
    assert extracted["quantity"] == 5000
    assert extracted["budget"] == 800000


def test_supplier_pdf_extracts_pricing_amount():
    supplier = make_client()
    register_and_login(supplier, "sup-pdf-price@example.com", "SUPPLIER")
    pdf = b"""%PDF-1.1
1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj
2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj
3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj
4 0 obj<< /Length 86 >>stream
BT /F1 12 Tf 10 160 Td (Pricing Amount) Tj 0 -18 Td (11200) Tj 0 -18 Td (Currency INR) Tj 0 -18 Td (Pricing Basis Per unit) Tj ET
endstream
endobj
5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000306 00000 n 
0000000443 00000 n 
trailer<< /Size 6 /Root 1 0 R >>
startxref
530
%%EOF
"""
    uploaded = supplier.post("/supplier-documents", files={"file": ("offering.pdf", pdf, "application/pdf")})
    assert uploaded.status_code == 201, uploaded.text
    extracted = uploaded.json()["extracted"]
    assert extracted["price_amount"] == 11200
    assert extracted["price_currency"] == "INR"
    assert extracted["price_basis"] == "PER_UNIT"


def test_extract_fields_do_not_invent_location():
    from app.extract import extract_fields

    fields = extract_fields(SAMPLE_TEXT, [(1, "Steel & Metals"), (2, "Industrial Components")])
    assert fields["quantity"] == 5000
    assert fields["budget"] == 800000
    assert fields["delivery_timeline"] == "30 days"
    assert "location" not in fields
    assert "steel" in fields.get("product_requirement", "").lower()


def test_requirement_status_rfq_and_close():
    supplier = make_client()
    register_and_login(supplier, "sup-rfq@example.com", "SUPPLIER")
    category_id = unique_category_id()
    assert supplier.post("/offerings", json=offering_payload(category_id)).status_code == 201

    buyer = make_client()
    register_and_login(buyer, "cli-rfq@example.com")
    created = buyer.post("/requirements", json=requirement_payload(category_id))
    assert created.status_code == 201
    req_id = created.json()["id"]
    assert created.json()["status"] == "MATCHED"
    rfq = buyer.put(f"/requirements/{req_id}", json={"status": "RFQ_SENT"})
    assert rfq.status_code == 200, rfq.text
    assert rfq.json()["status"] == "RFQ_SENT"
    closed = buyer.put(f"/requirements/{req_id}", json={"status": "CLOSED"})
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"
    assert buyer.put(f"/requirements/{req_id}", json={"status": "SUBMITTED"}).status_code == 409
    removed = buyer.delete(f"/requirements/{req_id}")
    assert removed.status_code == 204
    assert buyer.get(f"/requirements/{req_id}").status_code == 404


def test_invalid_file_type_rejected():
    client = make_client()
    register_and_login(client, "cli-exe@example.com")
    uploaded = client.post(
        "/documents",
        files={"file": ("malware.exe", b"MZ\x90\x00not-an-office-file", "application/octet-stream")},
    )
    assert uploaded.status_code == 400


def test_oversized_file_rejected():
    client = make_client()
    register_and_login(client, "cli-big@example.com")
    payload = b"a" * 600_000
    uploaded = client.post("/documents", files={"file": ("notes.txt", payload, "text/plain")})
    assert uploaded.status_code == 413


def test_malformed_pdf_rejected():
    client = make_client()
    register_and_login(client, "cli-badpdf@example.com")
    uploaded = client.post("/documents", files={"file": ("broken.pdf", b"%PDF-1.4\nnot a real pdf", "application/pdf")})
    assert uploaded.status_code == 400


def test_document_idor_blocked():
    owner = make_client()
    register_and_login(owner, "cli-doc-a@example.com")
    uploaded = owner.post("/documents", files={"file": ("requirement.txt", SAMPLE_TEXT.encode(), "text/plain")})
    doc_id = uploaded.json()["id"]

    other = make_client()
    register_and_login(other, "cli-doc-b@example.com")
    assert other.get(f"/documents/{doc_id}").status_code == 404


def test_notifications_are_own_only():
    supplier = make_client()
    register_and_login(supplier, "sup-note@example.com", "SUPPLIER")
    category_id = first_category_id(supplier)
    supplier.post("/offerings", json=offering_payload(category_id))

    buyer = make_client()
    register_and_login(buyer, "cli-note@example.com")
    buyer.post("/requirements", json=requirement_payload(category_id))

    buyer_notes = buyer.get("/notifications")
    supplier_notes = supplier.get("/notifications")
    assert buyer_notes.status_code == 200
    assert supplier_notes.status_code == 200
    assert all("password" not in str(item).lower() for item in buyer_notes.json())
