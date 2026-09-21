import assert from "node:assert/strict";
import { test } from "node:test";
import { profileInitials } from "./profileDisplay.js";

test("uses two letters from a single name", () => {
  assert.equal(profileInitials("Ada"), "AD");
});

test("uses first and last initials", () => {
  assert.equal(profileInitials("Ada Client"), "AC");
});
