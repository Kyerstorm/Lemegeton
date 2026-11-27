import test from "node:test";
import assert from "node:assert/strict";
import { mediaAutomationEventKey, normalizeMediaAutomationCategories } from "../helpers/community/community-automation.js";

test("automation categories are normalized, de-duplicated and bounded to provider-supported release types", () => {
  assert.deepEqual(normalizeMediaAutomationCategories(" Anime, tv,ANIME "), ["anime", "tv"]);
  assert.deepEqual(normalizeMediaAutomationCategories(["movies", "anime"]), ["movies", "anime"]);
  assert.throws(() => normalizeMediaAutomationCategories("anime,books"), /supported categories/);
  assert.throws(() => normalizeMediaAutomationCategories(" "), /supported categories/);
});

test("automation event keys are stable and change when provider release identity changes", () => {
  const release = { title: "Example Episode 2", provider: "AniList", url: "https://anilist.co/anime/1", when: new Date("2026-12-01T12:00:00Z") };
  assert.equal(mediaAutomationEventKey(release), mediaAutomationEventKey({ ...release, when: new Date(release.when.getTime()) }));
  assert.notEqual(mediaAutomationEventKey(release), mediaAutomationEventKey({ ...release, title: "Example Episode 3" }));
});
