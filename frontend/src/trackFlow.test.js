import assert from "node:assert/strict";
import { test } from "node:test";
import { isTrackable, nextTrackAction, sortTrackItems, trackStatus, trackStepIndex } from "./trackFlow.js";

test("maps accepted fulfillment statuses onto the track flow", () => {
  assert.equal(trackStepIndex("ACCEPTED"), 0);
  assert.equal(trackStepIndex("PAID"), 1);
  assert.equal(trackStepIndex("PAYMENT_CONFIRMED"), 1);
  assert.equal(trackStepIndex("SHIPPED"), 2);
  assert.equal(trackStepIndex("RECEIVED"), 3);
  assert.equal(trackStepIndex("SENT"), -1);
  assert.equal(isTrackable("ACCEPTED"), true);
  assert.equal(isTrackable("SENT"), false);
});

test("offers the next fulfillment action to the right role", () => {
  assert.equal(nextTrackAction("ACCEPTED", "CLIENT").method, "pay");
  assert.equal(nextTrackAction("ACCEPTED", "SUPPLIER"), null);
  assert.equal(nextTrackAction("PAID", "SUPPLIER").method, "ship");
  assert.equal(nextTrackAction("PAID", "CLIENT"), null);
  assert.equal(nextTrackAction("SHIPPED", "CLIENT"), null);
  assert.equal(nextTrackAction("RECEIVED", "CLIENT"), null);
});

test("prefers persisted tracking status from the backend", () => {
  assert.equal(trackStatus({ status: "ACCEPTED", tracking: { current_status: "PAID" } }), "PAID");
});

test("keeps received orders after open ones", () => {
  const sorted = sortTrackItems([
    { id: 1, status: "RECEIVED", created_at: "2026-09-21T00:00:00Z" },
    { id: 2, status: "PAID", created_at: "2026-09-20T00:00:00Z" },
    { id: 3, status: "ACCEPTED", created_at: "2026-09-22T00:00:00Z" },
  ]);
  assert.deepEqual(
    sorted.map((item) => item.id),
    [3, 2, 1],
  );
});
