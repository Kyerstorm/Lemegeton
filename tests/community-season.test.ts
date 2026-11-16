import test from "node:test";
import assert from "node:assert/strict";
import { normalizeSeasonItemType } from "../helpers/community/community-tournaments.js";

test("Community Seasons accept approved Challenge and Puzzle packs without accepting arbitrary item types", () => {
  assert.equal(normalizeSeasonItemType("challenge"), "challenge");
  assert.equal(normalizeSeasonItemType("puzzle"), "puzzle");
  assert.throws(() => normalizeSeasonItemType("draft-pack"), /supported season item/);
});
