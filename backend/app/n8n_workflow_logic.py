"""Deterministic n8n workflow semantics used by the importable hub and by tests.

n8n cloud cannot query the application SQLite file. Duplicate detection therefore
keys on event_id in workflow static data (or an event_id column filter), never
n8n Data Table Get Row By ID.
"""

from __future__ import annotations

SUPPLIER_RECIPIENT_EVENTS = {
    "MATCH_CREATED",
    "CLIENT_REQUEST_SENT",
    "PAYMENT_CONFIRMED",
    "ORDER_RECEIVED",
    "ORDER_COMPLETED",
}
CLIENT_RECIPIENT_EVENTS = {"SUPPLIER_ACCEPTED", "SUPPLIER_DECLINED", "SHIPMENT_SHIPPED"}


def format_match_score_percent(score) -> str | None:
    if score is None or score == "":
        return None
    try:
        numeric = float(score)
    except (TypeError, ValueError):
        return None
    percent = round(numeric * 10000) / 100
    if percent == int(percent):
        return f"{int(percent)}%"
    text = f"{percent:.2f}".rstrip("0").rstrip(".")
    return f"{text}%"


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def resolve_recipient_email(event_type: str, raw: dict) -> str:
    existing = _text(raw.get("recipient_email"))
    if existing:
        return existing
    supplier = _text(raw.get("supplier_email"))
    client = _text(raw.get("client_email"))
    if event_type in SUPPLIER_RECIPIENT_EVENTS:
        return supplier
    if event_type in CLIENT_RECIPIENT_EVENTS:
        return client
    return supplier or client


def normalize_event(raw: dict | None) -> dict:
    source = dict(raw or {})
    if isinstance(source.get("body"), dict) and source.get("body"):
        nested = dict(source["body"])
        nested.setdefault("headers", source.get("headers"))
        source = nested
    event_type = _text(source.get("event_type") or source.get("event"))
    event_id = _text(source.get("event_id"))
    match_score = source.get("match_score")
    match_score_percent = source.get("match_score_percent") or format_match_score_percent(match_score)
    recipient = resolve_recipient_email(event_type, source)
    has_recipient = bool(recipient)
    status = "ok"
    error = None
    if not event_id:
        status = "invalid"
        error = "missing_event_id"
    elif event_type and event_type != "quotation.created":
        if source.get("supplier_id") in (None, "") and source.get("client_id") in (None, ""):
            status = "invalid_party"
            error = "invalid_or_missing_supplier_or_client_id"
        elif not has_recipient:
            status = "missing_recipient"
            error = "recipient_email_unavailable"
    normalized = {
        **source,
        "event_type": event_type,
        "event_id": event_id,
        "recipient_email": recipient or None,
        "has_recipient": has_recipient,
        "match_score": match_score,
        "match_score_percent": match_score_percent,
        "workflow_status": status,
        "workflow_error": error,
    }
    return normalized


def check_duplicate(
    normalized: dict,
    processed_event_ids: dict[str, bool],
    lookup_error: Exception | None = None,
) -> dict:
    """Always returns one item. Empty n8n Get-Row output is a defect, not 'no duplicate'."""
    if lookup_error is not None:
        return {
            **normalized,
            "duplicate_status": "error",
            "duplicate_reason": "database_unavailable",
            "is_duplicate": False,
            "should_send_email": False,
        }
    event_id = _text(normalized.get("event_id"))
    if not event_id:
        return {
            **normalized,
            "duplicate_status": "invalid",
            "duplicate_reason": "missing_event_id",
            "is_duplicate": False,
            "should_send_email": False,
        }
    if normalized.get("workflow_status") == "invalid_party":
        return {
            **normalized,
            "duplicate_status": "invalid",
            "duplicate_reason": normalized.get("workflow_error") or "invalid_party",
            "is_duplicate": False,
            "should_send_email": False,
        }
    if event_id in processed_event_ids:
        return {
            **normalized,
            "duplicate_status": "duplicate",
            "duplicate_reason": "event_id_already_processed",
            "is_duplicate": True,
            "should_send_email": False,
        }
    if not normalized.get("has_recipient"):
        return {
            **normalized,
            "duplicate_status": "new",
            "duplicate_reason": None,
            "is_duplicate": False,
            "should_send_email": False,
        }
    return {
        **normalized,
        "duplicate_status": "new",
        "duplicate_reason": None,
        "is_duplicate": False,
        "should_send_email": True,
    }


def mark_processed(result: dict, processed_event_ids: dict[str, bool]) -> dict:
    event_id = _text(result.get("event_id"))
    if event_id and result.get("duplicate_status") == "new" and result.get("should_send_email"):
        processed_event_ids[event_id] = True
        return {**result, "processed_logged": True}
    return {**result, "processed_logged": False}


def simulate_n8n_data_table_get_by_id(event_id: str, rows_by_pk: dict[str, dict]) -> list[dict]:
    """n8n Data Table Get Row uses the table primary `id`, not an event_id column."""
    row = rows_by_pk.get(event_id)
    if row is None:
        return []
    return [row]
