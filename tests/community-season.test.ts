import test from "node:test";
import assert from "node:assert/strict";
import { normalizeSeasonItemType, validateSeasonWindow } from "../helpers/community/community-tournaments.js";

test("Community Seasons accept approved Challenge and Puzzle packs without accepting arbitrary item types", () => {
  assert.equal(normalizeSeasonItemType("challenge"), "challenge");
  assert.equal(normalizeSeasonItemType("puzzle"), "puzzle");
  assert.throws(() => normalizeSeasonItemType("draft-pack"), /supported season item/);
});


test("Community Season periods require a valid window of at most 180 days", () => {
  const now = new Date("2026-11-16T12:00:00.000Z");
  assert.doesNotThrow(() => validateSeasonWindow(
    new Date("2026-11-17T00:00:00.000Z"),
    new Date("2027-02-01T00:00:00.000Z"),
    now,
  ));
  assert.throws(() => validateSeasonWindow(new Date("bad"), new Date("2026-12-01T00:00:00.000Z"), now), /valid dates/);
  assert.throws(() => validateSeasonWindow(
    new Date("2026-11-15T00:00:00.000Z"),
    new Date("2026-12-01T00:00:00.000Z"),
    now,
  ), /cannot start in the past/);
  assert.throws(() => validateSeasonWindow(
    new Date("2026-11-17T00:00:00.000Z"),
    new Date("2027-06-01T00:00:00.000Z"),
    now,
  ), /180 days/);
});
