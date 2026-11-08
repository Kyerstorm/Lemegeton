import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizeReadingCategory,
  parseReadingScheduleTime,
  READING_CATEGORIES,
} from "../helpers/community-reading.js";

test("community reading accepts the supported legacy publication categories", () => {
  assert.deepEqual(READING_CATEGORIES, [
    "manga",
    "manhwa",
    "manhua",
    "webtoon",
    "light novel",
    "webnovel",
    "book",
  ]);
  assert.equal(normalizeReadingCategory(" Light Novel "), "light novel");
  assert.equal(normalizeReadingCategory("MANHWA"), "manhwa");
  assert.equal(normalizeReadingCategory("anime"), null);
  assert.equal(normalizeReadingCategory(""), null);
});

test("Reading Club schedule requires explicit timezone and a valid future instant", () => {
  const now = new Date("2026-11-08T12:00:00.000Z");
  assert.equal(
    parseReadingScheduleTime("2026-12-12T19:00:00+00:00", now).toISOString(),
    "2026-12-12T19:00:00.000Z",
  );
  assert.equal(
    parseReadingScheduleTime("2026-12-12T19:00:00Z", now).toISOString(),
    "2026-12-12T19:00:00.000Z",
  );
  assert.throws(
    () => parseReadingScheduleTime("2026-12-12T19:00:00", now),
    /must include a timezone/,
  );
  assert.throws(
    () => parseReadingScheduleTime("not-a-date+00:00", now),
    /valid ISO-8601/,
  );
  assert.throws(
    () => parseReadingScheduleTime("2026-11-08T11:59:00+00:00", now),
    /must be scheduled in the future/,
  );
});
