import uuid

from app.webhooks import CLIENT_REQUEST_SENT, MATCH_CREATED, SUPPLIER_ACCEPTED, SUPPLIER_DECLINED, notify_n8n
from tests.test_modules import (
    make_client,
    offering_payload,
    register_and_login,
    requirement_payload,
    unique_category_id,
)
from tests.test_n8n import _install_post, assert_decimal_match_score


def _matched_pair(prefix, monkeypatch=None):
    calls = _install_post(monkeypatch) if monkeypatch is not None else None
    supplier = make_client()
    supplier_email = f"{prefix}-sup@example.com"
    register_and_login(supplier, supplier_email, "SUPPLIER", company_name="GreenGrid Solar Systems", full_name="GreenGrid")
    category_id = unique_category_id()
    offering = supplier.post(
        "/offerings",
        json=offering_payload(
            category_id,
            supplier_name="GreenGrid Solar Systems",
            product_offered="Commercial rooftop solar panels",
            available_quantity=200,
            pricing_details="INR 11200 per unit",
            price_amount=11200,
            price_currency="INR",
            price_basis="PER_UNIT",
            delivery_capability="12 days",
        ),
    )
    assert offering.status_code == 201, offering.text

    buyer = make_client()
    client_email = f"{prefix}-cli@example.com"
    register_and_login(buyer, client_email, company_name="BluePeak Retail Solutions", full_name="BluePeak")
    created = buyer.post(
        "/requirements",
        json=requirement_payload(
            category_id,
            company_name="BluePeak Retail Solutions",
            product_requirement="Commercial rooftop solar panels",
            quantity=80,
            budget=960000,
            budget_currency="INR",
            budget_basis="TOTAL",
            delivery_timeline="18 days",
            additional_notes="Need installation support",
        ),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["match_count"] >= 1
    return {
        "calls": calls,
        "supplier": supplier,
        "buyer": buyer,
        "supplier_email": supplier_email,
        "client_email": client_email,
        "category_id": category_id,
        "offering": offering.json(),
        "requirement": body,
        "match": body["matches"][0],
    }


def test_client_sees_eligible_matches_with_commercial_fields():
    ctx = _matched_pair("see-matches")
    fetched = ctx["buyer"].get(f"/requirements/{ctx['requirement']['id']}")
    assert fetched.status_code == 200
    matches = fetched.json()["matches"]
    assert matches
    match = matches[0]
    assert match["id"] == ctx["match"]["id"]
    assert match["supplier_name"] == "GreenGrid Solar Systems"
    assert match["product_offered"] == "Commercial rooftop solar panels"
    assert match["available_quantity"] == 200
    assert match["price_amount"] == 11200
    assert match["price_currency"] == "INR"
    assert match["price_basis"] == "PER_UNIT"
    assert match["delivery_capability"] == "12 days"
    assert match["final_score"] is not None
    assert match["explanation"]
    assert match["match_status"] in {"NEW", "VIEWED"}
    assert match["location"]


def test_client_selects_matched_supplier_and_sends_request(monkeypatch):
    ctx = _matched_pair("select-match", monkeypatch)
    match_hooks = len(ctx["calls"])
    sent = ctx["buyer"].post("/rfqs", json={"match_id": ctx["match"]["id"], "notes": "Please supply"})
    assert sent.status_code == 201, sent.text
    body = sent.json()
    assert body["status"] == "SENT"
    assert body["match_id"] == ctx["match"]["id"]
    assert body["requirement_id"] == ctx["requirement"]["id"]
    assert body["offering_id"] == ctx["offering"]["id"]
    assert body["client_name"] == "BluePeak Retail Solutions"
    assert body["supplier_name"] == "GreenGrid Solar Systems"
    assert body["product_requirement"] == "Commercial rooftop solar panels"
    assert body["quantity"] == 80
    assert body["budget"] == 960000
    assert body["match_score"] == ctx["match"]["final_score"]

    listed = ctx["supplier"].get("/rfqs")
    assert listed.status_code == 200
    assert any(item["id"] == body["id"] for item in listed.json())

    request_calls = [call["json"] for call in ctx["calls"][match_hooks:] if call["json"].get("event_type") == CLIENT_REQUEST_SENT]
    assert len(request_calls) == 1
    payload = request_calls[0]
    assert payload["event_id"] == f"{CLIENT_REQUEST_SENT}:{body['id']}"
    assert payload["request_id"] == body["id"]
    assert payload["supplier_email"] == ctx["supplier_email"]
    assert payload["client_email"] == ctx["client_email"]
    assert payload["recipient_email"] == ctx["supplier_email"]
    assert payload["product"] == "Commercial rooftop solar panels"
    assert payload["quantity"] == 80
    assert payload["match_score"] == ctx["match"]["final_score"]
    assert_decimal_match_score(payload["match_score"], ctx["match"]["final_score"])

    notes = ctx["supplier"].get("/notifications").json()
    assert any("BluePeak Retail Solutions sent you a request" in item["message"] for item in notes)


def test_client_cannot_select_unrelated_supplier():
    first = _matched_pair("unrelated-a")
    second = _matched_pair("unrelated-b")
    response = first["buyer"].post("/rfqs", json={"match_id": second["match"]["id"]})
    assert response.status_code == 404


def test_client_cannot_send_request_for_another_clients_requirement():
    owner = _matched_pair("owner-req")
    other = make_client()
    register_and_login(other, "other-req-owner@example.com")
    response = other.post("/rfqs", json={"match_id": owner["match"]["id"]})
    assert response.status_code == 404
    assert owner["supplier"].get("/rfqs").json() == []


def test_supplier_receives_client_request_sent_notification(monkeypatch):
    ctx = _matched_pair("req-sent", monkeypatch)
    sent = ctx["buyer"].post("/rfqs", json={"match_id": ctx["match"]["id"]})
    assert sent.status_code == 201
    notes = ctx["supplier"].get("/notifications").json()
    assert any(item["notification_type"] == "RFQ" for item in notes)
    assert any("Commercial rooftop solar panels" in item["message"] for item in notes)
    payloads = [call["json"] for call in ctx["calls"] if call["json"].get("event_type") == CLIENT_REQUEST_SENT]
    assert payloads and payloads[0]["supplier_email"] == ctx["supplier_email"]
    assert payloads[0]["recipient_email"] == ctx["supplier_email"]
    assert_decimal_match_score(payloads[0]["match_score"], ctx["match"]["final_score"])


def test_client_receives_supplier_accepted_notification(monkeypatch):
    ctx = _matched_pair("sup-accept", monkeypatch)
    sent = ctx["buyer"].post("/rfqs", json={"match_id": ctx["match"]["id"]})
    rfq_id = sent.json()["id"]
    accepted = ctx["supplier"].post(f"/rfqs/{rfq_id}/accept")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "ACCEPTED"

    notes = ctx["buyer"].get("/notifications").json()
    assert any("GreenGrid Solar Systems accepted your supplier request." in item["message"] for item in notes)
    payloads = [call["json"] for call in ctx["calls"] if call["json"].get("event_type") == SUPPLIER_ACCEPTED]
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["event_id"] == f"{SUPPLIER_ACCEPTED}:{rfq_id}"
    assert payload["request_id"] == rfq_id
    assert payload["client_email"] == ctx["client_email"]
    assert payload["recipient_email"] == ctx["client_email"]
    assert payload["supplier_email"] == ctx["supplier_email"]
    assert payload["product"] == "Commercial rooftop solar panels"
    assert payload["quantity"] == 80
    assert_decimal_match_score(payload["match_score"], ctx["match"]["final_score"])

    other = make_client()
    register_and_login(other, "other-sup-accept@example.com", "SUPPLIER")
    assert other.post(f"/rfqs/{rfq_id}/accept").status_code == 404


def test_client_receives_supplier_declined_notification(monkeypatch):
    ctx = _matched_pair("sup-decline", monkeypatch)
    sent = ctx["buyer"].post("/rfqs", json={"match_id": ctx["match"]["id"]})
    rfq_id = sent.json()["id"]
    declined = ctx["supplier"].post(f"/rfqs/{rfq_id}/reject")
    assert declined.status_code == 200, declined.text
    assert declined.json()["status"] == "REJECTED"

    notes = ctx["buyer"].get("/notifications").json()
    assert any("GreenGrid Solar Systems declined your supplier request." in item["message"] for item in notes)
    payloads = [call["json"] for call in ctx["calls"] if call["json"].get("event_type") == SUPPLIER_DECLINED]
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["event_id"] == f"{SUPPLIER_DECLINED}:{rfq_id}"
    assert payload["recipient_email"] == ctx["client_email"]
    assert payload["client_email"] == ctx["client_email"]
    assert_decimal_match_score(payload["match_score"], ctx["match"]["final_score"])

    other = make_client()
    register_and_login(other, "other-sup-decline@example.com", "SUPPLIER")
    assert other.post(f"/rfqs/{rfq_id}/reject").status_code == 404


def test_match_created_contains_required_payload_fields(monkeypatch):
    ctx = _matched_pair("payload-fields", monkeypatch)
    payloads = [call["json"] for call in ctx["calls"] if call["json"].get("event_type") == MATCH_CREATED]
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["product"] == "Commercial rooftop solar panels"
    assert payload["category"]
    assert payload["supplier_email"] == ctx["supplier_email"]
    assert payload["client_email"] == ctx["client_email"]
    assert payload["quantity"] == 80
    assert payload["match_score"] == ctx["match"]["final_score"]
    assert_decimal_match_score(payload["match_score"], ctx["match"]["final_score"])
    assert payload["request_id"] is None
    assert payload["recipient_email"] == ctx["supplier_email"]


def test_custom_category_included_on_match_and_request(monkeypatch):
    calls = _install_post(monkeypatch)
    custom_name = f"Flow Custom Energy {uuid.uuid4().hex[:8]}"
    product_name = f"Custom solar array {uuid.uuid4().hex[:8]}"
    supplier = make_client()
    register_and_login(supplier, "flow-custom-sup@example.com", "SUPPLIER")
    other_id = next(item["id"] for item in supplier.get("/categories").json() if item["name"] == "Other")
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
    buyer = make_client()
    register_and_login(buyer, "flow-custom-cli@example.com")
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
    match = created.json()["matches"][0]
    assert match["category_name"] == custom_name
    created_payloads = [
        call["json"]
        for call in calls
        if call["json"].get("event_type") == MATCH_CREATED and call["json"].get("match_id") == match["id"]
    ]
    assert created_payloads and created_payloads[0]["category"] == custom_name
    sent = buyer.post("/rfqs", json={"match_id": match["id"]})
    assert sent.status_code == 201, sent.text
    request_payloads = [call["json"] for call in calls if call["json"].get("event_type") == CLIENT_REQUEST_SENT]
    assert request_payloads and request_payloads[0]["category"] == custom_name


def test_duplicate_request_is_rejected_and_does_not_resend_webhook(monkeypatch):
    ctx = _matched_pair("dup-rfq", monkeypatch)
    first = ctx["buyer"].post("/rfqs", json={"match_id": ctx["match"]["id"]})
    assert first.status_code == 201
    second = ctx["buyer"].post("/rfqs", json={"match_id": ctx["match"]["id"]})
    assert second.status_code == 409
    request_payloads = [call["json"] for call in ctx["calls"] if call["json"].get("event_type") == CLIENT_REQUEST_SENT]
    assert len(request_payloads) == 1


def test_duplicate_webhook_event_id_is_skipped(monkeypatch):
    calls = _install_post(monkeypatch)
    payload = {
        "event_type": CLIENT_REQUEST_SENT,
        "event_id": "CLIENT_REQUEST_SENT:idempotency-test",
        "request_id": 1,
        "supplier_email": "sup@example.com",
        "client_email": "cli@example.com",
        "product": "Panels",
        "category": "Solar",
        "quantity": 80,
    }
    notify_n8n(payload)
    notify_n8n(payload)
    assert len(calls) == 1


def test_refreshing_matches_does_not_resend_match_created(monkeypatch):
    ctx = _matched_pair("no-refresh-hook", monkeypatch)
    assert len([call for call in ctx["calls"] if call["json"].get("event_type") == MATCH_CREATED]) == 1
    fetched = ctx["buyer"].get(f"/requirements/{ctx['requirement']['id']}")
    assert fetched.status_code == 200
    ctx["buyer"].get(f"/requirements/{ctx['requirement']['id']}")
    assert len([call for call in ctx["calls"] if call["json"].get("event_type") == MATCH_CREATED]) == 1


def test_existing_rfq_quotation_accept_still_works(monkeypatch):
    ctx = _matched_pair("quote-still", monkeypatch)
    sent = ctx["buyer"].post("/rfqs", json={"match_id": ctx["match"]["id"]})
    rfq_id = sent.json()["id"]
    quote = ctx["supplier"].post(
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
    assert quote.json()["total"] == 1075
    accepted = ctx["buyer"].post(f"/rfqs/{rfq_id}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "ACCEPTED"
    assert not any(call["json"].get("event_type") == SUPPLIER_ACCEPTED for call in ctx["calls"])


def test_accepted_request_tracks_payment_shipped_and_received():
    ctx = _matched_pair("track-flow")
    sent = ctx["buyer"].post("/rfqs", json={"match_id": ctx["match"]["id"]})
    rfq_id = sent.json()["id"]
    accepted = ctx["supplier"].post(f"/rfqs/{rfq_id}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "ACCEPTED"

    assert ctx["supplier"].post(f"/rfqs/{rfq_id}/pay").status_code == 403
    paid = ctx["buyer"].post(f"/rfqs/{rfq_id}/payment/demo")
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "PAID"
    notes = ctx["supplier"].get("/notifications").json()
    assert any("Payment confirmed. You can now ship the order." in item["message"] for item in notes)

    assert ctx["buyer"].post(f"/rfqs/{rfq_id}/ship").status_code == 403
    shipped = ctx["supplier"].post(f"/rfqs/{rfq_id}/ship")
    assert shipped.status_code == 200, shipped.text
    assert shipped.json()["status"] == "SHIPPED"
    otp = shipped.json()["tracking"]["demo_otp"]
    assert otp is None
    client_view = ctx["buyer"].get(f"/rfqs/{rfq_id}/tracking")
    assert client_view.status_code == 200
    otp = client_view.json()["demo_otp"]
    assert otp and len(otp) == 6

    assert ctx["buyer"].post(f"/rfqs/{rfq_id}/receive").status_code == 409
    received = ctx["buyer"].post(f"/rfqs/{rfq_id}/verify-otp", json={"otp": otp})
    assert received.status_code == 200, received.text
    assert received.json()["status"] == "RECEIVED"
    assert received.json()["tracking"]["completed"] is True
    assert ctx["buyer"].post(f"/rfqs/{rfq_id}/verify-otp", json={"otp": otp}).status_code == 409
