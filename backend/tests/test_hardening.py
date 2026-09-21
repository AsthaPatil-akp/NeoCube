from app.config import settings
from tests.test_modules import (
    make_client,
    offering_payload,
    register_and_login,
    requirement_payload,
    unique_category_id,
)


def test_missing_required_certification_is_hard_filtered():
    supplier = make_client()
    register_and_login(supplier, "sup-cert@example.com", "SUPPLIER")
    category_id = unique_category_id()
    supplier.post(
        "/offerings",
        json=offering_payload(category_id, additional_notes="In stock nationwide"),
    )
    buyer = make_client()
    register_and_login(buyer, "cli-cert@example.com")
    created = buyer.post(
        "/requirements",
        json=requirement_payload(
            category_id,
            additional_notes="ISO 9001 certification required",
        ),
    )
    assert created.status_code == 201
    assert created.json()["match_count"] == 0


def test_iso_certified_offering_matches_required_certification():
    supplier = make_client()
    register_and_login(supplier, "sup-iso@example.com", "SUPPLIER")
    category_id = unique_category_id()
    supplier.post("/offerings", json=offering_payload(category_id))
    buyer = make_client()
    register_and_login(buyer, "cli-iso@example.com")
    created = buyer.post(
        "/requirements",
        json=requirement_payload(
            category_id,
            additional_notes="ISO 9001 certification required",
        ),
    )
    assert created.status_code == 201, created.text
    assert created.json()["match_count"] == 1
    assert "Certification compatible" in created.json()["matches"][0]["explanation"]


def test_get_requirement_marks_match_viewed():
    supplier = make_client()
    register_and_login(supplier, "sup-viewed@example.com", "SUPPLIER")
    category_id = unique_category_id()
    supplier.post("/offerings", json=offering_payload(category_id))
    buyer = make_client()
    register_and_login(buyer, "cli-viewed@example.com")
    created = buyer.post("/requirements", json=requirement_payload(category_id))
    assert created.json()["matches"][0]["match_status"] == "NEW"
    fetched = buyer.get(f"/requirements/{created.json()['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["matches"][0]["match_status"] == "VIEWED"


def test_supplier_document_upload_and_idor():
    supplier = make_client()
    register_and_login(supplier, "sup-doc@example.com", "SUPPLIER")
    uploaded = supplier.post(
        "/supplier-documents",
        files={"file": ("catalog.txt", b"Steel brackets ISO certified 9000 units", "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["processing_status"] == "EXTRACTED"
    doc_id = uploaded.json()["id"]
    assert supplier.get(f"/supplier-documents/{doc_id}").status_code == 200

    other = make_client()
    register_and_login(other, "sup-doc-b@example.com", "SUPPLIER")
    assert other.get(f"/supplier-documents/{doc_id}").status_code == 404

    client = make_client()
    register_and_login(client, "cli-doc-sup@example.com")
    assert client.post(
        "/supplier-documents",
        files={"file": ("catalog.txt", b"hello", "text/plain")},
    ).status_code == 403


def test_n8n_unavailable_does_not_block_matching():
    original = settings.n8n_webhook_url
    settings.n8n_webhook_url = "http://127.0.0.1:1/webhook/neocube"
    try:
        supplier = make_client()
        register_and_login(supplier, "sup-n8n@example.com", "SUPPLIER")
        category_id = unique_category_id()
        supplier.post("/offerings", json=offering_payload(category_id))
        buyer = make_client()
        register_and_login(buyer, "cli-n8n@example.com")
        created = buyer.post("/requirements", json=requirement_payload(category_id))
        assert created.status_code == 201
        assert created.json()["match_count"] == 1
    finally:
        settings.n8n_webhook_url = original


def test_sql_injection_login_does_not_authenticate():
    client = make_client()
    response = client.post(
        "/auth/login",
        json={"email": "admin@example.com' OR '1'='1", "password": "password123"},
    )
    assert response.status_code in {401, 422}
    assert not response.cookies.get("neocube_session")


def test_xss_payload_is_stored_as_plain_text():
    supplier = make_client()
    register_and_login(supplier, "sup-xss@example.com", "SUPPLIER")
    category_id = unique_category_id()
    supplier.post("/offerings", json=offering_payload(category_id))
    buyer = make_client()
    register_and_login(buyer, "cli-xss@example.com")
    payload = requirement_payload(
        category_id,
        product_requirement="<script>alert(1)</script> steel brackets",
    )
    created = buyer.post("/requirements", json=payload)
    assert created.status_code == 201
    body = created.json()
    assert body["product_requirement"] == "<script>alert(1)</script> steel brackets"
    assert "<script>" in body["product_requirement"]


def test_health_reports_model_status():
    client = make_client()
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True
    assert body["encoder_loaded"] is True
    assert body["model_version"] == "supplier_match_model_v1"


def test_document_path_traversal_filename_is_rejected():
    client = make_client()
    register_and_login(client, "cli-trav@example.com")
    uploaded = client.post(
        "/documents",
        files={"file": ("../evil.txt", b"Need 10 steel brackets in 30 days budget 1000", "text/plain")},
    )
    assert uploaded.status_code == 400
    assert uploaded.json()["detail"] == "Invalid filename"


def test_offering_links_owned_supplier_document():
    supplier = make_client()
    register_and_login(supplier, "sup-link-doc@example.com", "SUPPLIER")
    uploaded = supplier.post(
        "/supplier-documents",
        files={"file": ("catalog.txt", b"Steel brackets ISO certified 9000 units", "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    doc_id = uploaded.json()["id"]
    category_id = unique_category_id()
    created = supplier.post("/offerings", json=offering_payload(category_id, document_id=doc_id))
    assert created.status_code == 201, created.text
    confirmed = supplier.get(f"/supplier-documents/{doc_id}")
    assert confirmed.status_code == 200
    assert confirmed.json()["processing_status"] == "CONFIRMED"
    reuse = supplier.post("/offerings", json=offering_payload(category_id, document_id=doc_id, product_offered="Extra steel stock"))
    assert reuse.status_code == 400

    other = make_client()
    register_and_login(other, "sup-link-doc-b@example.com", "SUPPLIER")
    foreign = other.post("/offerings", json=offering_payload(category_id, document_id=doc_id))
    assert foreign.status_code == 400

