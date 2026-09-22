import assert from "node:assert/strict";
import { test } from "node:test";
import { formatMatchScore, formatMatchLabel, sortByMatchScore } from "./formatMatchScore.js";

test("formats 0.5 as 50%", () => {
  assert.equal(formatMatchScore(0.5), "50%");
});

test("formats 0.9933 as 99.33%", () => {
  assert.equal(formatMatchScore(0.9933), "99.33%");
});

test("formats 0.41 as 41%", () => {
  assert.equal(formatMatchScore(0.41), "41%");
});

test("formats null as Not available", () => {
  assert.equal(formatMatchScore(null), "Not available");
});

test("formats 0.8 as 80% ML score", () => {
  assert.equal(formatMatchLabel(0.8), "80% ML score");
});

test("formats 1 as 100% ML score", () => {
  assert.equal(formatMatchLabel(1), "100% ML score");
});

test("sorts matches highest percent first", () => {
  const ranked = sortByMatchScore([{ final_score: 0.41 }, { final_score: 0.8 }, { final_score: 0.2 }]);
  assert.deepEqual(
    ranked.map((item) => item.final_score),
    [0.8, 0.41, 0.2],
  );
});
