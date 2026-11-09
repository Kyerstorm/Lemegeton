import test from "node:test";
import assert from "node:assert/strict";
import {
  nextReleaseOccurrence,
  normalizeReleaseCategories,
} from "../helpers/community-releases.js";

test("daily release digest uses the selected timezone and next local time", () => {
  const next = nextReleaseOccurrence("Europe/Dublin", "18:30", "daily", 1, new Date("2026-11-09T17:00:00.000Z"));
  assert.equal(next.toISOString(), "2026-11-09T18:30:00.000Z");
});

test("weekly release digest advances to the selected local weekday", () => {
  const next = nextReleaseOccurrence("Europe/Dublin", "09:15", "weekly", 4, new Date("2026-11-09T10:00:00.000Z"));
  assert.equal(next.toISOString(), "2026-11-12T09:15:00.000Z");
});

test("release digest schedule rejects invalid timezones, local times and weekdays", () => {
  assert.throws(() => nextReleaseOccurrence("Mars/Olympus", "09:15", "daily", 1), /timezone/i);
  assert.throws(() => nextReleaseOccurrence("Europe/Dublin", "25:00", "daily", 1), /HH:MM/);
  assert.throws(() => nextReleaseOccurrence("Europe/Dublin", "09:15", "weekly", 7), /weekday/i);
});

test("release digest categories are deduplicated and restricted to provider-backed types", () => {
  assert.deepEqual(normalizeReleaseCategories(["anime", "tv", "anime"]), ["anime", "tv"]);
  assert.throws(() => normalizeReleaseCategories([]), /supported categories/i);
  assert.throws(() => normalizeReleaseCategories(["anime", "unknown"]), /supported categories/i);
});
