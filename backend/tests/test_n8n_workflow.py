import json
from pathlib import Path

from app.n8n_workflow_logic import (
    check_duplicate,
    format_match_score_percent,
    mark_processed,
    normalize_event,
    simulate_n8n_data_table_get_by_id,
)


def _sample_match_event(**overrides):
    payload = {
        "event_type": "MATCH_CREATED",
        "event_id": "MATCH_CREATED:30",
        "match_id": 30,
        "requirement_id": 12,
        "offering_id": 8,
        "client_id": 4,
        "supplier_id": 7,
        "client_email": "client@example.com",
        "supplier_email": "supplier@example.com",
        "supplier_name": "FreshHarvest Foods",
        "product": "Image",
        "category": "Food & Beverages / Honey",
        "quantity": 600,
        "match_score": 0.5942,
        "match_explanation": "Category compatible · Quantity sufficient · Within budget · Delivery compatible · Location compatible",
        "recipient_email": "supplier@example.com",
        "has_recipient": True,
        "email_subject": "New Supplier Match Found",
        "email_body": "Match Score: 0.5942 (59.42%)",
    }
    payload.update(overrides)
    return payload


def test_check_duplicate_get_by_id_returns_empty_for_business_event_id():
    rows_by_pk = {"9f3c1e2a-aaaa-bbbb-cccc-ddddeeeeffff": {"event_id": "MATCH_CREATED:30"}}
    assert simulate_n8n_data_table_get_by_id("MATCH_CREATED:30", rows_by_pk) == []
    assert simulate_n8n_data_table_get_by_id("event_id", rows_by_pk) == []


def test_normalize_preserves_score_and_restores_recipient():
    raw = _sample_match_event(recipient_email="", has_recipient=False, match_score_percent=None)
    normalized = normalize_event(raw)
    assert normalized["event_id"] == "MATCH_CREATED:30"
    assert normalized["match_score"] == 0.5942
    assert normalized["match_score_percent"] == "59.42%"
    assert normalized["recipient_email"] == "supplier@example.com"
    assert normalized["has_recipient"] is True
    assert normalized["supplier_name"] == "FreshHarvest Foods"
    assert normalized["match_explanation"]


def test_new_event_is_processed_once():
    processed = {}
    first = check_duplicate(normalize_event(_sample_match_event()), processed)
    assert first["duplicate_status"] == "new"
    assert first["should_send_email"] is True
    mark_processed(first, processed)
    second = check_duplicate(normalize_event(_sample_match_event()), processed)
    assert second["duplicate_status"] == "duplicate"
    assert second["should_send_email"] is False


def test_missing_event_id_fails_safely():
    result = check_duplicate(normalize_event(_sample_match_event(event_id="")), {})
    assert result["duplicate_status"] == "invalid"
    assert result["duplicate_reason"] == "missing_event_id"
    assert result["should_send_email"] is False


def test_invalid_party_ids_fail_clearly():
    result = check_duplicate(
        normalize_event(
            _sample_match_event(
                client_id=None,
                supplier_id=None,
                client_email=None,
                supplier_email=None,
                recipient_email="",
            )
        ),
        {},
    )
    assert result["duplicate_status"] == "invalid"
    assert "supplier_or_client" in result["duplicate_reason"]
    assert result["should_send_email"] is False


def test_lookup_error_is_not_treated_as_new():
    result = check_duplicate(normalize_event(_sample_match_event()), {}, lookup_error=RuntimeError("db down"))
    assert result["duplicate_status"] == "error"
    assert result["duplicate_reason"] == "database_unavailable"
    assert result["should_send_email"] is False


def test_missing_recipient_does_not_send_email():
    result = check_duplicate(
        normalize_event(
            _sample_match_event(
                recipient_email="",
                supplier_email=None,
                client_email=None,
            )
        ),
        {},
    )
    assert result["has_recipient"] is False
    assert result["recipient_email"] is None
    assert result["should_send_email"] is False
    assert result["duplicate_status"] in {"new", "invalid"}


def test_match_score_percent_formatting():
    assert format_match_score_percent(0.5942) == "59.42%"
    assert format_match_score_percent(0.98) == "98%"


def test_imported_workflow_replaces_get_row_by_id():
    workflow = json.loads(
        (Path(__file__).resolve().parents[2] / "n8n" / "client-supplier-notification-hub.json").read_text(
            encoding="utf-8"
        )
    )
    names = {node["name"] for node in workflow["nodes"]}
    assert names >= {
        "Webhook",
        "Normalize Event",
        "Check Duplicate",
        "Already Processed?",
        "Has Recipient?",
        "Route by Event Type",
        "Log processed event",
        "Fail Database Lookup",
        "Fail Invalid Event",
        "Skip Missing Recipient",
    }
    check = next(node for node in workflow["nodes"] if node["name"] == "Check Duplicate")
    assert check["type"] == "n8n-nodes-base.code"
    code = check["parameters"]["jsCode"]
    assert "Get" not in code or "processedEvents" in code
    assert "processedEvents" in code
    assert "$getWorkflowStaticData" in code
    webhook = next(node for node in workflow["nodes"] if node["name"] == "Webhook")
    assert webhook["parameters"]["httpMethod"] == "POST"
    assert webhook["parameters"]["responseMode"] == "onReceived"
    assert webhook["parameters"]["path"] == "client-supplier-notifications"
