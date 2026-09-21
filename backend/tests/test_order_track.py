from datetime import timedelta

from app.database import SessionLocal
from app.models import OrderTrack, utc_now
from tests.test_modules import make_client, register_and_login
from tests.test_request_flow import _matched_pair


def _accept_request(prefix):
    ctx = _matched_pair(prefix)
    sent = ctx["buyer"].post("/rfqs", json={"match_id": ctx["match"]["id"]})
    assert sent.status_code == 201, sent.text
    rfq_id = sent.json()["id"]
    accepted = ctx["supplier"].post(f"/rfqs/{rfq_id}/accept")
    assert accepted.status_code == 200, accepted.text
    ctx["rfq_id"] = rfq_id
    ctx["accepted"] = accepted.json()
    return ctx


def test_accept_initializes_tracking_record():
    ctx = _accept_request("track-init")
    body = ctx["accepted"]
    assert body["status"] == "ACCEPTED"
    tracking = body["tracking"]
    assert tracking["current_status"] == "ACCEPTED"
    assert tracking["payment_status"] == "PENDING"
    assert tracking["shipment_status"] == "NOT_SHIPPED"
    assert tracking["received_status"] == "NOT_RECEIVED"
    assert tracking["completed"] is False
    fetched = ctx["buyer"].get(f"/rfqs/{ctx['rfq_id']}/tracking")
    assert fetched.status_code == 200
    assert fetched.json()["current_status"] == "ACCEPTED"
    again = ctx["supplier"].post(f"/rfqs/{ctx['rfq_id']}/accept")
    assert again.status_code == 409
    listed = ctx["buyer"].get("/rfqs").json()
    assert listed[0]["tracking"]["rfq_id"] == ctx["rfq_id"]


def test_demo_payment_and_duplicate_payment():
    ctx = _accept_request("track-pay")
    rfq_id = ctx["rfq_id"]
    too_early = _matched_pair("track-pay-early")
    sent = too_early["buyer"].post("/rfqs", json={"match_id": too_early["match"]["id"]})
    assert too_early["buyer"].post(f"/rfqs/{sent.json()['id']}/payment/demo").status_code == 409

    paid = ctx["buyer"].post(f"/rfqs/{rfq_id}/payment/demo")
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "PAID"
    assert paid.json()["tracking"]["payment_status"] == "CONFIRMED"
    assert paid.json()["tracking"]["current_status"] == "PAID"
    assert ctx["buyer"].post(f"/rfqs/{rfq_id}/payment/demo").status_code == 409
    assert ctx["supplier"].post(f"/rfqs/{rfq_id}/payment/demo").status_code == 403
    notes = ctx["supplier"].get("/notifications").json()
    assert any("You can now ship the order." in item["message"] for item in notes)
    reload = ctx["buyer"].get(f"/rfqs/{rfq_id}/tracking")
    assert reload.json()["payment_status"] == "CONFIRMED"


def test_supplier_cannot_ship_before_payment_and_can_after():
    ctx = _accept_request("track-ship")
    rfq_id = ctx["rfq_id"]
    assert ctx["supplier"].post(f"/rfqs/{rfq_id}/ship").status_code == 409
    ctx["buyer"].post(f"/rfqs/{rfq_id}/payment/demo")
    assert ctx["buyer"].post(f"/rfqs/{rfq_id}/ship").status_code == 403
    shipped = ctx["supplier"].post(f"/rfqs/{rfq_id}/ship")
    assert shipped.status_code == 200, shipped.text
    assert shipped.json()["status"] == "SHIPPED"
    tracking = shipped.json()["tracking"]
    assert tracking["shipment_status"] == "SHIPPED"
    assert tracking["shipment_code"].startswith("DEMO-SHP-")
    assert tracking["demo_otp"] is None
    assert ctx["supplier"].post(f"/rfqs/{rfq_id}/ship").status_code == 409
    client_track = ctx["buyer"].get(f"/rfqs/{rfq_id}/tracking").json()
    assert client_track["current_status"] == "SHIPPED"
    assert client_track["demo_otp"] and len(client_track["demo_otp"]) == 6


def test_otp_wrong_expired_and_success():
    ctx = _accept_request("track-otp")
    rfq_id = ctx["rfq_id"]
    ctx["buyer"].post(f"/rfqs/{rfq_id}/payment/demo")
    assert ctx["buyer"].post(f"/rfqs/{rfq_id}/verify-otp", json={"otp": "123456"}).status_code == 409
    ctx["supplier"].post(f"/rfqs/{rfq_id}/ship")
    otp = ctx["buyer"].get(f"/rfqs/{rfq_id}/tracking").json()["demo_otp"]
    wrong = ctx["buyer"].post(f"/rfqs/{rfq_id}/verify-otp", json={"otp": "000000"})
    assert wrong.status_code == 400
    assert wrong.json()["detail"] == "Invalid OTP."
    assert ctx["supplier"].post(f"/rfqs/{rfq_id}/verify-otp", json={"otp": otp}).status_code == 403

    db = SessionLocal()
    try:
        track = db.query(OrderTrack).filter(OrderTrack.rfq_id == rfq_id).one()
        track.otp_expires_at = utc_now() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()
    expired = ctx["buyer"].post(f"/rfqs/{rfq_id}/verify-otp", json={"otp": otp})
    assert expired.status_code == 409
    refreshed = ctx["buyer"].post(f"/rfqs/{rfq_id}/otp/refresh")
    assert refreshed.status_code == 200
    new_otp = refreshed.json()["tracking"]["demo_otp"]
    assert new_otp and new_otp != otp
    received = ctx["buyer"].post(f"/rfqs/{rfq_id}/verify-otp", json={"otp": new_otp})
    assert received.status_code == 200, received.text
    assert received.json()["status"] == "RECEIVED"
    assert received.json()["tracking"]["completed"] is True
    assert received.json()["tracking"]["received_status"] == "RECEIVED"
    assert ctx["buyer"].post(f"/rfqs/{rfq_id}/verify-otp", json={"otp": new_otp}).status_code == 409
    assert ctx["buyer"].post(f"/rfqs/{rfq_id}/payment/demo").status_code == 409
    assert ctx["supplier"].post(f"/rfqs/{rfq_id}/ship").status_code == 409
    persisted = ctx["buyer"].get(f"/rfqs/{rfq_id}/tracking").json()
    assert persisted["completed"] is True
    assert persisted["demo_otp"] is None


def test_unauthorized_users_cannot_access_or_mutate_tracking():
    ctx = _accept_request("track-auth")
    rfq_id = ctx["rfq_id"]
    other_client = make_client()
    register_and_login(other_client, "other-track-cli@example.com")
    other_supplier = make_client()
    register_and_login(other_supplier, "other-track-sup@example.com", "SUPPLIER")
    assert other_client.get(f"/rfqs/{rfq_id}/tracking").status_code == 404
    assert other_supplier.get(f"/rfqs/{rfq_id}/tracking").status_code == 404
    assert other_client.post(f"/rfqs/{rfq_id}/payment/demo").status_code == 404
    ctx["buyer"].post(f"/rfqs/{rfq_id}/payment/demo")
    assert other_supplier.post(f"/rfqs/{rfq_id}/ship").status_code == 404
    ctx["supplier"].post(f"/rfqs/{rfq_id}/ship")
    otp = ctx["buyer"].get(f"/rfqs/{rfq_id}/tracking").json()["demo_otp"]
    assert other_client.post(f"/rfqs/{rfq_id}/verify-otp", json={"otp": otp}).status_code == 404
