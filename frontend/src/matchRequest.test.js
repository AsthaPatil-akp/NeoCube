import assert from "node:assert/strict";
import { test } from "node:test";
import { canSendMatchRequest, notificationHref } from "./matchRequest.js";

test("allows sending a request for a matched supplier without an RFQ", () => {
  assert.equal(canSendMatchRequest({ id: 1, match_status: "VIEWED" }), true);
});

test("blocks sending a request when an RFQ already exists", () => {
  assert.equal(canSendMatchRequest({ id: 1, match_status: "VIEWED", rfq_id: 9 }), false);
});

test("blocks sending a request after RFQ_SENT", () => {
  assert.equal(canSendMatchRequest({ id: 1, match_status: "RFQ_SENT" }), false);
});

test("links RFQ notifications to the request", () => {
  assert.equal(notificationHref({ related_type: "rfq", related_id: 12 }), "/rfqs/12");
});
