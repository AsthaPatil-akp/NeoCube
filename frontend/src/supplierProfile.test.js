import test from "node:test";
import assert from "node:assert/strict";
import { formatAverageRating, supplierProfilePath } from "./supplierProfile.js";

test("does not invent a rating when none exists", () => {
  assert.equal(formatAverageRating(null), null);
  assert.equal(formatAverageRating(undefined), null);
});

test("formats stored averages to one decimal", () => {
  assert.equal(formatAverageRating(4.6), "4.6");
  assert.equal(formatAverageRating(5), "5.0");
});

test("builds a supplier profile path from a match without selecting it", () => {
  assert.equal(supplierProfilePath(9, { id: 3, rfq_id: null }), "/suppliers/9?match=3");
  assert.equal(supplierProfilePath(9, { id: 3, rfq_id: 12 }), "/suppliers/9");
  assert.equal(supplierProfilePath(null, { id: 3 }), null);
});
