import json
import uuid

import httpx

from app.config import settings
from tests.test_modules import (
    make_client,
    offering_payload,
    register_and_login,
    requirement_payload,
    unique_category_id,
)


def assert_decimal_match_score(value, expected=None):
    assert value is not None
    assert isinstance(value, (int, float))
    assert not isinstance(value, bool)
    assert 0 <= float(value) <= 1
    assert "%" not in json.dumps(value)
    if expected is not None:
        assert value == expected


def _install_post(monkeypatch, status_code=200, error=None):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append({"url": url, "json": json, "timeout": timeout})
        if error is not None:
            raise error
        request = httpx.Request("POST", url)
        return httpx.Response(status_code, request=request)

    monkeypatch.setattr(settings, "n8n_webhook_url", "https://n8n.example.test/webhook/supplier-match-created")
    monkeypatch.setattr("app.webhooks.httpx.post", fake_post)
    return calls


def test_match_created_sends_webhook_payload(monkeypatch):
    calls = _install_post(monkeypatch)
    supplier = make_client()
    register_and_login(supplier, "sup-match-hook@example.com", "SUPPLIER")
    category_id = unique_category_id()
    offering = supplier.post("/offerings", json=offering_payload(category_id))
    assert offering.status_code == 201

    buyer = make_client()
    register_and_login(buyer, "cli-match-hook@example.com")
    created = buyer.post("/requirements", json=requirement_payload(category_id))
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["match_count"] == 1
    match = body["matches"][0]
    dumped = json.dumps(body)
    assert "n8n.example.test" not in dumped
    assert "N8N_WEBHOOK_URL" not in dumped
    assert "supplier-match-created" not in dumped

    assert len(calls) == 1
    payload = calls[0]["json"]
    assert calls[0]["url"] == "https://n8n.example.test/webhook/supplier-match-created"
    assert "product/category" not in payload
    assert payload["event_type"] == "MATCH_CREATED"
    assert payload["event_id"]
    assert payload["event_id"] == f"MATCH_CREATED:{match['id']}"
    assert payload["match_id"] == match["id"]
    assert payload["request_id"] is None
    assert payload["supplier_email"] == "sup-match-hook@example.com"
    assert payload["client_email"] == "cli-match-hook@example.com"
    assert payload["product"] == offering.json()["product_offered"]
    assert payload["product"] is not None
    assert payload["category"] == body["category_name"]
    assert payload["category"] is not None
    assert payload["product"] != payload["category"]
    assert payload["client_name"] == body["company_name"]
    assert payload["supplier_name"] == offering.json()["supplier_name"]
    assert payload["quantity"] == body["quantity"]
    assert payload["match_score"] == match["final_score"]
    assert_decimal_match_score(payload["match_score"], match["final_score"])
    from app.n8n_workflow_logic import format_match_score_percent

    assert payload["match_score_percent"] == format_match_score_percent(match["final_score"])
    assert payload["has_recipient"] is True
    assert payload["recipient_email"] == "sup-match-hook@example.com"
    assert payload["requirement_id"] == body["id"]
    assert payload["offering_id"] == offering.json()["id"]
    assert calls[0]["timeout"] == 10.0
    assert payload["match_explanation"]
    assert payload["created_at"]
    assert payload["client_id"] is not None
    assert payload["supplier_id"] is not None

    notes = buyer.get("/notifications").json()
    assert any(item["notification_type"] == "MATCH" for item in notes)
    supplier_notes = supplier.get("/notifications").json()
    assert any(item["notification_type"] == "MATCH" for item in supplier_notes)


def test_n8n_http_error_does_not_break_match_creation(monkeypatch):
    _install_post(monkeypatch, status_code=500)
    supplier = make_client()
    register_and_login(supplier, "sup-n8n-500@example.com", "SUPPLIER")
    category_id = unique_category_id()
    supplier.post("/offerings", json=offering_payload(category_id))
    buyer = make_client()
    register_and_login(buyer, "cli-n8n-500@example.com")
    created = buyer.post("/requirements", json=requirement_payload(category_id))
    assert created.status_code == 201
    assert created.json()["match_count"] == 1
    notes = buyer.get("/notifications").json()
    assert any(item["notification_type"] == "MATCH" for item in notes)


def test_n8n_timeout_does_not_break_match_creation(monkeypatch):
    _install_post(monkeypatch, error=httpx.TimeoutException("timed out"))
    supplier = make_client()
    register_and_login(supplier, "sup-n8n-timeout@example.com", "SUPPLIER")
    category_id = unique_category_id()
    supplier.post("/offerings", json=offering_payload(category_id))
    buyer = make_client()
    register_and_login(buyer, "cli-n8n-timeout@example.com")
    created = buyer.post("/requirements", json=requirement_payload(category_id))
    assert created.status_code == 201
    assert created.json()["match_count"] == 1


def test_missing_n8n_webhook_url_does_not_break_match_creation(monkeypatch):
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs)
        raise AssertionError("httpx.post should not be called when N8N_WEBHOOK_URL is empty")

    monkeypatch.setattr(settings, "n8n_webhook_url", "")
    monkeypatch.setattr("app.webhooks.httpx.post", fake_post)
    supplier = make_client()
    register_and_login(supplier, "sup-n8n-empty@example.com", "SUPPLIER")
    category_id = unique_category_id()
    supplier.post("/offerings", json=offering_payload(category_id))
    buyer = make_client()
    register_and_login(buyer, "cli-n8n-empty@example.com")
    created = buyer.post("/requirements", json=requirement_payload(category_id))
    assert created.status_code == 201
    assert created.json()["match_count"] == 1
    assert calls == []
    notes = buyer.get("/notifications").json()
    assert any(item["notification_type"] == "MATCH" for item in notes)


def test_new_match_on_already_matched_requirement_sends_webhook(monkeypatch):
    calls = _install_post(monkeypatch)
    category_id = unique_category_id()
    first = make_client()
    register_and_login(first, "sup-n8n-first@example.com", "SUPPLIER")
    created_first = first.post("/offerings", json=offering_payload(category_id, supplier_name="First Supply"))
    assert created_first.status_code == 201

    buyer = make_client()
    register_and_login(buyer, "cli-n8n-second@example.com")
    requirement = buyer.post("/requirements", json=requirement_payload(category_id))
    assert requirement.status_code == 201
    assert requirement.json()["match_count"] == 1
    assert len(calls) == 1

    second = make_client()
    register_and_login(second, "sup-n8n-later@example.com", "SUPPLIER")
    later = second.post(
        "/offerings",
        json=offering_payload(category_id, supplier_name="Later Supply"),
    )
    assert later.status_code == 201
    assert later.json()["match_count"] >= 1
    assert len(calls) == 2
    payload = calls[1]["json"]
    assert payload["event_type"] == "MATCH_CREATED"
    assert payload["supplier_email"] == "sup-n8n-later@example.com"
    assert payload["supplier_name"] == "Later Supply"
    assert "product" in payload and "category" in payload
    refreshed = buyer.get(f"/requirements/{requirement.json()['id']}")
    assert refreshed.status_code == 200
    assert refreshed.json()["match_count"] == 2
    notes = second.get("/notifications").json()
    assert any(item["notification_type"] == "MATCH" for item in notes)


def test_match_created_payload_uses_offering_product_and_category(monkeypatch):
    calls = _install_post(monkeypatch)
    supplier = make_client()
    register_and_login(supplier, "sup-n8n-product@example.com", "SUPPLIER")
    category_id = unique_category_id()
    offering = supplier.post(
        "/offerings",
        json=offering_payload(category_id, product_offered="Galvanized steel fasteners"),
    )
    assert offering.status_code == 201
    offering_body = offering.json()

    buyer = make_client()
    register_and_login(buyer, "cli-n8n-product@example.com")
    created = buyer.post(
        "/requirements",
        json=requirement_payload(category_id, product_requirement="Steel brackets", quantity=80),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["match_count"] == 1
    match = body["matches"][0]
    assert len(calls) == 1
    payload = calls[0]["json"]
    assert payload["event_type"] == "MATCH_CREATED"
    assert payload["product"] == "Galvanized steel fasteners"
    assert payload["product"] == offering_body["product_offered"]
    assert payload["product"] != body["product_requirement"]
    assert payload["category"] == body["category_name"]
    assert payload["category"] is not None
    assert payload["category"] != "Other"
    assert payload["supplier_email"] == "sup-n8n-product@example.com"
    assert payload["quantity"] == 80
    assert payload["quantity"] == body["quantity"]
    assert payload["match_score"] == match["final_score"]
    assert_decimal_match_score(payload["match_score"], match["final_score"])
    assert payload["match_score"] is not None


def test_match_created_payload_sends_custom_category(monkeypatch):
    calls = _install_post(monkeypatch)
    custom_name = f"N8N Custom Energy {uuid.uuid4().hex[:8]}"
    product_name = f"Custom solar array {uuid.uuid4().hex[:8]}"
    supplier = make_client()
    register_and_login(supplier, "sup-n8n-custom-cat@example.com", "SUPPLIER")
    categories = supplier.get("/categories").json()
    other_id = next(item["id"] for item in categories if item["name"] == "Other")
    offering = supplier.post(
        "/offerings",
        json=offering_payload(
            other_id,
            product_offered=product_name,
            custom_category=custom_name,
            available_quantity=200,
            price_amount=11200,
            price_currency="INR",
            price_basis="PER_UNIT",
            location="Nashik, Maharashtra",
            delivery_capability="12 days",
        ),
    )
    assert offering.status_code == 201, offering.text
    assert offering.json()["category_name"] == custom_name
    assert offering.json()["category_name"] != "Other"

    buyer = make_client()
    register_and_login(buyer, "cli-n8n-custom-cat@example.com")
    created = buyer.post(
        "/requirements",
        json=requirement_payload(
            other_id,
            product_requirement=product_name,
            custom_category=custom_name,
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
    assert body["match_count"] == 1
    match = body["matches"][0]
    payloads = [
        call["json"]
        for call in calls
        if call["json"].get("supplier_email") == "sup-n8n-custom-cat@example.com"
        and call["json"].get("product") == product_name
        and call["json"].get("match_id") == match["id"]
    ]
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["event_type"] == "MATCH_CREATED"
    assert payload["product"] == product_name
    assert payload["category"] == custom_name
    assert payload["category"] != "Other"
    assert payload["supplier_email"] == "sup-n8n-custom-cat@example.com"
    assert payload["quantity"] == 80
    assert payload["match_score"] == match["final_score"]
    assert payload["match_score"] is not None
    assert_decimal_match_score(payload["match_score"], match["final_score"])
    assert payload["request_id"] is None
    assert payload["client_name"] == body["company_name"]
    assert payload["supplier_name"] == offering.json()["supplier_name"]


def test_n8n_payloads_resolve_registered_account_emails(monkeypatch):
    calls = _install_post(monkeypatch)
    token = uuid.uuid4().hex[:10]
    supplier_email = f"acct-sup-{token}@example.com"
    client_email = f"acct-cli-{token}@example.com"
    supplier = make_client()
    register_and_login(supplier, supplier_email, "SUPPLIER")
    category_id = unique_category_id()
    offering = supplier.post("/offerings", json=offering_payload(category_id))
    assert offering.status_code == 201

    buyer = make_client()
    register_and_login(buyer, client_email)
    created = buyer.post("/requirements", json=requirement_payload(category_id))
    assert created.status_code == 201, created.text
    match = created.json()["matches"][0]

    match_payloads = [call["json"] for call in calls if call["json"].get("event_type") == "MATCH_CREATED"]
    assert len(match_payloads) == 1
    match_payload = match_payloads[0]
    assert match_payload["supplier_email"] == supplier_email
    assert match_payload["client_email"] == client_email
    assert match_payload["recipient_email"] == supplier_email
    assert match_payload["supplier_email"] != "supplier@example.com"
    assert match_payload["client_email"] != "client@example.com"

    sent = buyer.post("/rfqs", json={"match_id": match["id"]})
    assert sent.status_code == 201, sent.text
    rfq_id = sent.json()["id"]
    request_payloads = [call["json"] for call in calls if call["json"].get("event_type") == "CLIENT_REQUEST_SENT"]
    assert len(request_payloads) == 1
    assert request_payloads[0]["supplier_email"] == supplier_email
    assert request_payloads[0]["client_email"] == client_email
    assert request_payloads[0]["recipient_email"] == supplier_email

    accepted = supplier.post(f"/rfqs/{rfq_id}/accept")
    assert accepted.status_code == 200, accepted.text
    accepted_payloads = [call["json"] for call in calls if call["json"].get("event_type") == "SUPPLIER_ACCEPTED"]
    assert len(accepted_payloads) == 1
    assert accepted_payloads[0]["client_email"] == client_email
    assert accepted_payloads[0]["recipient_email"] == client_email
    assert accepted_payloads[0]["supplier_email"] == supplier_email


def test_n8n_declined_payload_uses_client_account_email(monkeypatch):
    calls = _install_post(monkeypatch)
    token = uuid.uuid4().hex[:10]
    supplier_email = f"decl-sup-{token}@example.com"
    client_email = f"decl-cli-{token}@example.com"
    supplier = make_client()
    register_and_login(supplier, supplier_email, "SUPPLIER")
    category_id = unique_category_id()
    supplier.post("/offerings", json=offering_payload(category_id))
    buyer = make_client()
    register_and_login(buyer, client_email)
    created = buyer.post("/requirements", json=requirement_payload(category_id))
    match = created.json()["matches"][0]
    sent = buyer.post("/rfqs", json={"match_id": match["id"]})
    rfq_id = sent.json()["id"]
    declined = supplier.post(f"/rfqs/{rfq_id}/reject")
    assert declined.status_code == 200, declined.text
    payloads = [call["json"] for call in calls if call["json"].get("event_type") == "SUPPLIER_DECLINED"]
    assert len(payloads) == 1
    assert payloads[0]["client_email"] == client_email
    assert payloads[0]["recipient_email"] == client_email
    assert payloads[0]["client_email"] != "client@example.com"
    assert payloads[0]["supplier_email"] == supplier_email


def test_match_created_resolves_users_email_when_profile_user_unloaded(monkeypatch):
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload, noload

    from app.database import SessionLocal
    from app.models import ClientProfile, ClientRequirement, Match, SupplierOffering, SupplierProfile
    from app.webhooks import match_created_payload

    calls = _install_post(monkeypatch)
    token = uuid.uuid4().hex[:10]
    supplier_email = f"noload-sup-{token}@example.com"
    client_email = f"noload-cli-{token}@example.com"
    supplier = make_client()
    register_and_login(supplier, supplier_email, "SUPPLIER")
    category_id = unique_category_id()
    offering_resp = supplier.post("/offerings", json=offering_payload(category_id))
    buyer = make_client()
    register_and_login(buyer, client_email)
    created = buyer.post("/requirements", json=requirement_payload(category_id))
    assert created.status_code == 201
    match_id = created.json()["matches"][0]["id"]
    assert calls

    db = SessionLocal()
    try:
        requirement = db.scalar(
            select(ClientRequirement)
            .options(joinedload(ClientRequirement.client).noload(ClientProfile.user))
            .where(ClientRequirement.id == created.json()["id"])
        )
        offering = db.scalar(
            select(SupplierOffering)
            .options(joinedload(SupplierOffering.supplier).noload(SupplierProfile.user))
            .where(SupplierOffering.id == offering_resp.json()["id"])
        )
        match = db.get(Match, match_id)
        assert requirement is not None and offering is not None and match is not None
        assert requirement.client is not None
        assert requirement.client.user is None
        assert offering.supplier is not None
        assert offering.supplier.user is None
        payload = match_created_payload(requirement, offering, match, db=db)
    finally:
        db.close()

    assert payload["supplier_email"] == supplier_email
    assert payload["client_email"] == client_email
    assert payload["recipient_email"] == supplier_email
    assert payload["supplier_email"] != "supplier@example.com"
    assert payload["client_email"] != "client@example.com"


def test_n8n_posts_when_recipient_unavailable_with_flag(monkeypatch):
    calls = _install_post(monkeypatch)
    from app.webhooks import notify_n8n

    notify_n8n(
        {
            "event_type": "MATCH_CREATED",
            "event_id": "MATCH_CREATED:missing-recipient",
            "supplier_email": None,
            "client_email": None,
            "recipient_email": "",
        }
    )
    assert len(calls) == 1
    payload = calls[0]["json"]
    assert payload["has_recipient"] is False
    assert payload["recipient_email"] is None


def test_n8n_skips_post_when_event_id_missing(monkeypatch):
    calls = _install_post(monkeypatch)
    from app.webhooks import notify_n8n

    notify_n8n(
        {
            "event_type": "MATCH_CREATED",
            "supplier_email": "sup@example.com",
            "client_email": "cli@example.com",
        }
    )
    assert calls == []
