import assert from "node:assert/strict";
import test from "node:test";
import { formatUtc } from "../lib/format-utc.ts";

test("UTC formatter renders valid dates without conflicting Intl options", () => {
  const result = formatUtc("2026-09-12T14:32:01Z");
  assert.match(result, /14:32:01/);
  assert.match(result, /UTC|GMT/);
  assert.match(result, /2026/);
});

test("UTC formatter normalizes timezone offsets rather than using browser local time", () => {
  assert.equal(formatUtc("2026-09-12T16:32:01+02:00"), formatUtc("2026-09-12T14:32:01Z"));
});

test("invalid source timestamps remain visible instead of crashing the panel", () => {
  assert.equal(formatUtc("not-a-valid-timestamp"), "not-a-valid-timestamp");
});
