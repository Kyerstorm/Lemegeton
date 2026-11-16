import test from "node:test";
import assert from "node:assert/strict";
import { normalizeDailyPollOptions } from "../helpers/community/community-daily.js";

test("Daily Drop poll options are normalized, distinct and bounded", () => {
  assert.deepEqual(normalizeDailyPollOptions("  Anime | Manga | anime "), ["Anime", "Manga"]);
  assert.deepEqual(normalizeDailyPollOptions(["Choice A", "Choice B"]), ["Choice A", "Choice B"]);
  assert.throws(() => normalizeDailyPollOptions("Only one"), /two to five distinct options/);
  assert.throws(() => normalizeDailyPollOptions("A|B|C|D|E|F"), /two to five distinct options/);
});
