# N8N

N8N is optional automation. Matching, match persistence, RFQs, and in-app notifications do not depend on it. The application database remains the source of truth for suppliers, clients, requirements, match scores, quotations, and orders.

When `N8N_WEBHOOK_URL` is set, `app.webhooks.notify_n8n(payload)` POSTs JSON to that backend-only URL. The URL is read from the environment (`backend/.env`); it is not hardcoded in Python, not sent to the frontend, and not returned in API responses.

Use **one** published workflow. Import `n8n/client-supplier-notification-hub.json`, attach the existing Gmail credentials, activate the workflow, and point `N8N_WEBHOOK_URL` at the **production** webhook (not `/webhook-test/`).

n8n formats `match_score` for display only. The backend keeps the decimal 0–1 ML value unchanged.

## Why Check Duplicate was empty

The live node was **Data Table → Row → Get → By ID = event_id**.

n8n Data Table **Get By ID** looks up the table’s internal primary `id` (usually a UUID), not a business column named `event_id`. Values such as `MATCH_CREATED:30` are not that primary key, so the node returns **no item**.

That empty item is not the same as “no duplicate”:

| Result | Meaning | Next step |
| --- | --- | --- |
| One item, `duplicate_status=duplicate` | Event already processed | Skip email |
| One item, `duplicate_status=new` | First time | Continue |
| One item, `duplicate_status=invalid` | Missing `event_id` or invalid party | Fail |
| One item, `duplicate_status=error` | Lookup/runtime failure | Fail (do not send) |
| **Zero items** | Broken node (this bug) | Downstream `$json.recipient_email` becomes null |

n8n Cloud cannot read the app SQLite file. Do not point Check Duplicate at a different database and expect to find application rows. Duplicate prevention in n8n is keyed on the deterministic `event_id` in **workflow static data** (the imported Code node). The app also persists successful outbound `event_id`s in `n8n_emitted_events`.

Do **not** use Get Row By ID with `event_id`. If you use a Data Table at all, filter `event_id` **equals** the string from Normalize Event, and always pass the Normalize Event fields through a Code node so the output is never empty.

## Flow

```
Application commit
  → notify_n8n (deterministic event_id, POST JSON, 10s timeout)
  → Webhook (respond immediately)
  → Normalize Event (preserve fields; restore recipient_email from supplier/client email)
  → Check Duplicate (always one item; static data keyed by event_id)
  → Lookup Failed? / Invalid Event? / Already Processed? / Has Recipient?
  → Route by Event Type → Gmail
  → Log processed event (record event_id in static data)
```

Webhook method: `POST`. No auth header is required on the public webhook URL; keep the URL secret in `N8N_WEBHOOK_URL`. Optional app callback: `GET/POST /n8n/events` with `X-N8N-Callback-Token` when `N8N_CALLBACK_TOKEN` is set (for a self-hosted n8n that can reach the API). Do not enable those routes without a token.

## Events

| Event | When | Email recipient |
| --- | --- | --- |
| `MATCH_CREATED` | A new match row is stored (one POST per new match), after the database commit | `supplier_email` |
| `CLIENT_REQUEST_SENT` | Client sent an RFQ/request for a matched supplier | `supplier_email` |
| `SUPPLIER_ACCEPTED` | Supplier accepted the request from SENT/VIEWED | `client_email` |
| `SUPPLIER_DECLINED` | Supplier declined the request from SENT/VIEWED | `client_email` |
| `quotation.created` | Supplier submitted a quotation | not emailed by default |

`event_id` is deterministic (`MATCH_CREATED:<match_id>`, `CLIENT_REQUEST_SENT:<request_id>`, `SUPPLIER_ACCEPTED:<request_id>`, `SUPPLIER_DECLINED:<request_id>`). After a successful webhook HTTP status, the backend stores that id so a retry does not POST again.

## MATCH_CREATED payload

```json
{
  "event_type": "MATCH_CREATED",
  "event_id": "MATCH_CREATED:<match_id>",
  "match_id": 1,
  "requirement_id": 1,
  "offering_id": 1,
  "request_id": null,
  "client_id": 1,
  "supplier_id": 1,
  "client_name": "...",
  "supplier_name": "...",
  "supplier_email": "...",
  "client_email": "...",
  "product": "...",
  "category": "...",
  "quantity": 5000,
  "match_score": 0.5942,
  "match_score_percent": "59.42%",
  "match_explanation": "Category compatible · Quantity sufficient",
  "created_at": "2026-09-21T13:00:00+00:00",
  "recipient_email": "...",
  "has_recipient": true,
  "email_subject": "New Supplier Match Found",
  "email_body": "..."
}
```

Gmail mapping:

- To: `{{ $json.recipient_email }}`
- Subject: `{{ $json.email_subject }}`
- Message: `{{ $json.email_body }}`

Do not send when `has_recipient` is false.

## Environment

```
N8N_WEBHOOK_URL=
N8N_CALLBACK_TOKEN=
```

Leave `N8N_WEBHOOK_URL` blank to skip outbound calls. Do not add `VITE_N8N_WEBHOOK_URL`.

## Failure handling

- Missing URL: no outbound call; match creation and RFQs continue
- Timeout, connection error, or non-success HTTP status: warning log (no URL or secret), no rollback, event_id is **not** stored so a later retry may POST again
- Missing `event_id`: backend does not POST
- Missing recipient: backend still POSTs with `has_recipient=false`; n8n must not call Gmail
- In-app `notifications` rows are written by FastAPI regardless of n8n
