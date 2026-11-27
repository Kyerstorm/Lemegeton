import test from "node:test";
import assert from "node:assert/strict";
import {
  mediaAutomationEventKey,
  normalizeMediaAutomationCategories,
} from "../helpers/community/community-automation.js";

test("media automation categories are normalized, deduplicated and bounded to supported providers", () => {
  assert.deepEqual(normalizeMediaAutomationCategories([" Anime ", "tv", "anime"]), ["anime", "tv"]);
  assert.deepEqual(normalizeMediaAutomationCategories("movies, anime, movies"), ["movies", "anime"]);
  assert.throws(() => normalizeMediaAutomationCategories([]), /supported categories/i);
  assert.throws(() => normalizeMediaAutomationCategories(["games"]), /supported categories/i);
  assert.throws(() => normalizeMediaAutomationCategories("anime,,unknown"), /supported categories/i);
});

test("media automation event identity is stable and changes with provider evidence", () => {
  const release = {
    title: "Example release",
    provider: "TMDB Movies · IE",
    url: "https://www.themoviedb.org/movie/12345",
    when: new Date("2026-12-02T18:00:00.000Z"),
  };
  assert.equal(mediaAutomationEventKey(release), mediaAutomationEventKey({ ...release, when: new Date(release.when) }));
  assert.notEqual(mediaAutomationEventKey(release), mediaAutomationEventKey({ ...release, title: "Different title" }));
  assert.notEqual(mediaAutomationEventKey(release), mediaAutomationEventKey({ ...release, provider: "TMDB Movies · US" }));
  assert.notEqual(mediaAutomationEventKey(release), mediaAutomationEventKey({ ...release, url: "https://www.themoviedb.org/movie/12346" }));
  assert.notEqual(mediaAutomationEventKey(release), mediaAutomationEventKey({ ...release, when: new Date("2026-12-02T19:00:00.000Z") }));
  assert.throws(() => mediaAutomationEventKey({ ...release, when: new Date("invalid") }), /invalid/i);
});
