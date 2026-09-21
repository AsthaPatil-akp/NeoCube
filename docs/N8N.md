# N8N

N8N is optional. Matching, match persistence, RFQs, and in-app notifications do not depend on it.

When `N8N_WEBHOOK_URL` is set, `app.webhooks.notify_n8n(payload)` POSTs JSON to that backend-only URL with a 5 second timeout. The URL is read from the environment (`backend/.env`); it is not hardcoded in Python, not sent to the frontend, and not returned in API responses.

Use **one** published workflow (Client Supplier Notification Hub). Do not create a separate workflow per event. Route with Switch/IF on `event_type`. n8n formats `match_score` for display; the backend keeps the decimal 0–1 value.

## Events

| Event | When | Email recipient |
| --- | --- | --- |
| `MATCH_CREATED` | A new match row is stored (one POST per new match), after the database commit | `supplier_email` |
| `CLIENT_REQUEST_SENT` | Client sent an RFQ/request for a matched supplier | `supplier_email` |
| `SUPPLIER_ACCEPTED` | Supplier accepted the request from SENT/VIEWED | `client_email` |
| `SUPPLIER_DECLINED` | Supplier declined the request from SENT/VIEWED | `client_email` |
| `quotation.created` | Supplier submitted a quotation (existing RFQ event, not emailed by default) | — |

`event_id` is stable (`MATCH_CREATED:<match_id>`, `CLIENT_REQUEST_SENT:<request_id>`, `SUPPLIER_ACCEPTED:<request_id>`, `SUPPLIER_DECLINED:<request_id>`). The backend skips a second POST for the same `event_id` after a successful send. Opening or refreshing a page does not emit these events.

## Workflow

```
Webhook
  → Switch / IF on event_type
      MATCH_CREATED        → Gmail To = supplier_email
      CLIENT_REQUEST_SENT  → Gmail To = supplier_email
      SUPPLIER_ACCEPTED    → Gmail To = client_email
      SUPPLIER_DECLINED    → Gmail To = client_email
```

Do not hardcode addresses. Use payload fields. Keep the existing Gmail credentials.

Simplest one-node mapping (recommended):

- To: `{{ $json.recipient_email }}`
- Subject: `{{ $json.email_subject }}`
- Message: `{{ $json.email_body }}`

## MATCH_CREATED payload

```json
{
  "event_type": "MATCH_CREATED",
  "event_id": "MATCH_CREATED:<match_id>",
  "match_id": 1,
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
  "match_score": 0.98,
  "match_explanation": "Category compatible · Quantity sufficient",
  "created_at": "2026-09-21T13:00:00+00:00",
  "recipient_email": "...",
  "email_subject": "New Supplier Match Found",
  "email_body": "..."
}
```

`product` is `supplier_offerings.product_offered`. `category` is the taxonomy name (`custom_category`, then `categories.name`; `"Other"` is not used as a stand-in). `event_id` is stable per match so n8n can ignore duplicates.

## CLIENT_REQUEST_SENT payload

```json
{
  "event_type": "CLIENT_REQUEST_SENT",
  "event_id": "CLIENT_REQUEST_SENT:<request_id>",
  "request_id": 123,
  "match_id": 456,
  "client_id": 1,
  "supplier_id": 2,
  "client_name": "...",
  "client_email": "...",
  "supplier_name": "...",
  "supplier_email": "...",
  "product": "...",
  "category": "...",
  "quantity": 80,
  "match_score": 0.94,
  "created_at": "...",
  "recipient_email": "<supplier_email>",
  "email_subject": "New Client Request",
  "email_body": "..."
}
```

## SUPPLIER_ACCEPTED / SUPPLIER_DECLINED payload

```json
{
  "event_type": "SUPPLIER_ACCEPTED",
  "event_id": "SUPPLIER_ACCEPTED:<request_id>",
  "request_id": 123,
  "client_id": 1,
  "supplier_id": 2,
  "client_name": "...",
  "client_email": "...",
  "supplier_name": "...",
  "supplier_email": "...",
  "product": "...",
  "category": "...",
  "quantity": 80,
  "created_at": "...",
  "recipient_email": "<client_email>",
  "email_subject": "Supplier Accepted Your Request",
  "email_body": "..."
}
```

`SUPPLIER_DECLINED` uses `event_type` / `event_id` `SUPPLIER_DECLINED:<request_id>` and subject `Supplier Declined Your Request`. Recipient is `client_email`. Email bodies omit empty fields.

## Environment

```
N8N_WEBHOOK_URL=
```

Leave it blank to skip outbound calls. Do not add `VITE_N8N_WEBHOOK_URL`. Do not use a `/webhook-test/` URL in production.

## Failure handling

- Missing URL: no outbound call; match creation and RFQs continue
- Timeout, connection error, or non-success HTTP status: warning log (no URL or secret), no rollback
- In-app `notifications` rows are written by FastAPI regardless of n8n
