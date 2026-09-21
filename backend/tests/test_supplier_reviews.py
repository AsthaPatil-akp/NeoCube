from tests.test_modules import make_client, register_and_login
from tests.test_order_track import _accept_request
from tests.test_request_flow import _matched_pair


def _complete_order(ctx):
    rfq_id = ctx["rfq_id"]
    assert ctx["buyer"].post(f"/rfqs/{rfq_id}/payment/demo").status_code == 200
    assert ctx["supplier"].post(f"/rfqs/{rfq_id}/ship").status_code == 200
    otp = ctx["buyer"].get(f"/rfqs/{rfq_id}/tracking").json()["demo_otp"]
    received = ctx["buyer"].post(f"/rfqs/{rfq_id}/verify-otp", json={"otp": otp})
    assert received.status_code == 200, received.text
    assert received.json()["tracking"]["completed"] is True
    ctx["completed"] = received.json()
    return ctx


def test_profile_requires_auth_and_hides_missing_suppliers():
    ctx = _matched_pair("rev-authz")
    supplier_id = ctx["requirement"]["matches"][0]["supplier_id"]
    guest = make_client()
    assert guest.get(f"/suppliers/{supplier_id}/profile").status_code == 401
    assert guest.get(f"/suppliers/{supplier_id}/reviews").status_code == 401
    assert ctx["buyer"].get("/suppliers/999999/profile").status_code == 404
    visible = ctx["supplier"].get(f"/suppliers/{supplier_id}/profile")
    assert visible.status_code == 200
    assert ctx["supplier_email"] not in str(visible.json())


def test_client_can_view_supplier_profile_and_offerings():
    ctx = _matched_pair("rev-profile")
    supplier_id = ctx["requirement"]["matches"][0]["supplier_id"]
    assert supplier_id is not None
    profile = ctx["buyer"].get(f"/suppliers/{supplier_id}/profile")
    assert profile.status_code == 200, profile.text
    body = profile.json()
    assert body["id"] == supplier_id
    assert body["company_name"]
    assert body["offerings"]
    assert body["offerings"][0]["product_offered"] == ctx["offering"]["product_offered"]
    assert body["average_rating"] is None
    assert body["review_count"] == 0
    assert body["reviews"] == []
    dumped = str(body)
    assert ctx["supplier_email"] not in dumped
    assert ctx["client_email"] not in dumped
    reviews = ctx["buyer"].get(f"/suppliers/{supplier_id}/reviews")
    assert reviews.status_code == 200
    assert reviews.json() == []


def test_completed_order_allows_one_review_and_updates_average():
    first = _complete_order(_accept_request("rev-ok"))
    rfq_id = first["rfq_id"]
    supplier_id = first["completed"]["supplier_id"]
    created_resp = first["buyer"].post(f"/rfqs/{rfq_id}/review", json={"rating": 5})
    assert created_resp.status_code == 200, created_resp.text
    created = created_resp.json()
    assert created["can_review"] is False
    assert created["review"]["rating"] == 5
    assert created["review"]["rfq_id"] == rfq_id

    again = first["buyer"].post(f"/rfqs/{rfq_id}/review", json={"rating": 4, "feedback": "again"})
    assert again.status_code == 409
    assert "already reviewed" in again.json()["detail"].lower()

    listed = first["buyer"].get("/rfqs").json()
    assert listed[0]["review"]["rating"] == 5
    assert listed[0]["can_review"] is False

    profile = first["buyer"].get(f"/suppliers/{supplier_id}/profile").json()
    assert profile["review_count"] == 1
    assert profile["average_rating"] == 5.0
    assert profile["reviews"][0]["rating"] == 5
    assert profile["reviews"][0]["verified"] is True
    assert "email" not in profile["reviews"][0]
    assert first["client_email"] not in str(profile)
    assert first["supplier_email"] not in str(profile)

    second = _complete_order(_accept_request("rev-second"))
    other_id = second["completed"]["supplier_id"]
    assert other_id != supplier_id
    sent = second["buyer"].post(
        f"/rfqs/{second['rfq_id']}/review",
        json={"rating": 4, "feedback": "Good communication and support."},
    )
    assert sent.status_code == 200, sent.text
    other_profile = second["buyer"].get(f"/suppliers/{other_id}/profile").json()
    assert other_profile["review_count"] == 1
    assert other_profile["average_rating"] == 4.0


def test_non_completed_orders_cannot_be_rated():
    ctx = _accept_request("rev-early")
    rfq_id = ctx["rfq_id"]
    assert ctx["buyer"].post(f"/rfqs/{rfq_id}/review", json={"rating": 5}).status_code == 409
    ctx["buyer"].post(f"/rfqs/{rfq_id}/payment/demo")
    assert ctx["buyer"].post(f"/rfqs/{rfq_id}/review", json={"rating": 5}).status_code == 409
    ctx["supplier"].post(f"/rfqs/{rfq_id}/ship")
    assert ctx["buyer"].post(f"/rfqs/{rfq_id}/review", json={"rating": 5}).status_code == 409
    sent_only = _matched_pair("rev-sent-only")
    created = sent_only["buyer"].post("/rfqs", json={"match_id": sent_only["match"]["id"]})
    assert created.status_code == 201
    assert sent_only["buyer"].post(f"/rfqs/{created.json()['id']}/review", json={"rating": 5}).status_code == 409


def test_review_validation_and_authorization():
    ctx = _complete_order(_accept_request("rev-auth"))
    rfq_id = ctx["rfq_id"]
    assert ctx["buyer"].post(f"/rfqs/{rfq_id}/review", json={"rating": 0}).status_code == 422
    assert ctx["buyer"].post(f"/rfqs/{rfq_id}/review", json={"rating": 6}).status_code == 422
    assert ctx["supplier"].post(f"/rfqs/{rfq_id}/review", json={"rating": 5}).status_code == 403

    other = _matched_pair("rev-other-cli")
    stolen = other["buyer"].post(f"/rfqs/{rfq_id}/review", json={"rating": 5})
    assert stolen.status_code == 404

    ok = ctx["buyer"].post(f"/rfqs/{rfq_id}/review", json={"rating": 3, "feedback": "Fine."})
    assert ok.status_code == 200
    assert ok.json()["review"]["rating"] == 3
    profile = ctx["buyer"].get(f"/suppliers/{ctx['completed']['supplier_id']}/profile").json()
    assert profile["reviews"][0]["rating"] == 3
    assert profile["reviews"][0]["feedback"] == "Fine."
    assert other["client_email"] not in str(profile)
    assert "password" not in str(profile).lower()


def test_average_rating_uses_all_valid_reviews_for_same_supplier():
    ctx = _complete_order(_accept_request("rev-avg-a"))
    supplier_id = ctx["completed"]["supplier_id"]
    assert ctx["buyer"].post(f"/rfqs/{ctx['rfq_id']}/review", json={"rating": 5}).status_code == 200

    extra = make_client()
    register_and_login(extra, "rev-avg-b-cli@example.com", company_name="Second Buyer")
    from tests.test_modules import requirement_payload

    created = extra.post(
        "/requirements",
        json=requirement_payload(
            ctx["category_id"],
            company_name="Second Buyer",
            product_requirement=ctx["requirement"]["product_requirement"],
            quantity=40,
            budget=500000,
        ),
    )
    assert created.status_code == 201, created.text
    matches = created.json()["matches"]
    target = next(item for item in matches if item["supplier_id"] == supplier_id)
    sent = extra.post("/rfqs", json={"match_id": target["id"]})
    assert sent.status_code == 201, sent.text
    rfq_id = sent.json()["id"]
    assert ctx["supplier"].post(f"/rfqs/{rfq_id}/accept").status_code == 200
    assert extra.post(f"/rfqs/{rfq_id}/payment/demo").status_code == 200
    assert ctx["supplier"].post(f"/rfqs/{rfq_id}/ship").status_code == 200
    otp = extra.get(f"/rfqs/{rfq_id}/tracking").json()["demo_otp"]
    assert extra.post(f"/rfqs/{rfq_id}/verify-otp", json={"otp": otp}).status_code == 200
    assert extra.post(f"/rfqs/{rfq_id}/review", json={"rating": 3}).status_code == 200

    profile = extra.get(f"/suppliers/{supplier_id}/profile").json()
    assert profile["review_count"] == 2
    assert profile["average_rating"] == 4.0
    assert all(item.get("email") is None for item in profile["reviews"])
    assert all("@" not in item["client_name"] for item in profile["reviews"])
