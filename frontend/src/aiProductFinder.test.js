import assert from "node:assert/strict";
import { test } from "node:test";
import { formatVisualSimilarity, isAllowedProductImage } from "./aiProductFinder.js";

test("isAllowedProductImage accepts jpeg/png/webp under size limit", () => {
  assert.equal(isAllowedProductImage({ name: "a.jpg", type: "image/jpeg", size: 100 }), true);
  assert.equal(isAllowedProductImage({ name: "a.png", type: "image/png", size: 100 }), true);
  assert.equal(isAllowedProductImage({ name: "a.webp", type: "image/webp", size: 100 }), true);
});

test("isAllowedProductImage rejects unsupported or oversized files", () => {
  assert.equal(isAllowedProductImage({ name: "a.gif", type: "image/gif", size: 100 }), false);
  assert.equal(isAllowedProductImage({ name: "a.jpg", type: "image/jpeg", size: 6_000_000 }), false);
  assert.equal(isAllowedProductImage(null), false);
});

test("formatVisualSimilarity formats percentages", () => {
  assert.equal(formatVisualSimilarity(91.4), "91.4%");
  assert.equal(formatVisualSimilarity("87.8"), "87.8%");
  assert.equal(formatVisualSimilarity(null), "—");
});
