from tests.test_modules import make_client


def test_n8n_event_routes_hidden_without_token(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "n8n_callback_token", "")
    client = make_client()
    missing = client.get("/n8n/events/MATCH_CREATED:1")
    assert missing.status_code == 404


def test_n8n_event_lookup_and_record(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "n8n_callback_token", "callback-secret")
    client = make_client()
    unauthorized = client.get("/n8n/events/MATCH_CREATED:1")
    assert unauthorized.status_code == 401
    headers = {"X-N8N-Callback-Token": "callback-secret"}
    missing = client.get("/n8n/events/MATCH_CREATED:bridge-1", headers=headers)
    assert missing.status_code == 200
    assert missing.json()["exists"] is False
    assert missing.json()["duplicate_status"] == "new"
    created = client.post(
        "/n8n/events",
        headers=headers,
        json={"event_id": "MATCH_CREATED:bridge-1", "event_type": "MATCH_CREATED"},
    )
    assert created.status_code == 200
    found = client.get("/n8n/events/MATCH_CREATED:bridge-1", headers=headers)
    assert found.json()["exists"] is True
    assert found.json()["duplicate_status"] == "duplicate"
