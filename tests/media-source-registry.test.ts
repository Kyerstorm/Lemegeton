import test from "node:test";
import assert from "node:assert/strict";
import {
  getMediaSource,
  listMediaSourcesByStatus,
  MEDIA_SOURCES,
  MEDIA_SOURCE_REGISTRY_REVIEWED_AT,
  searchMediaSources,
} from "../helpers/media/media-source-registry.js";

test("source registry covers every requested source exactly once", () => {
  const ids = MEDIA_SOURCES.map(source => source.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(ids.length, 60);
  assert.equal(MEDIA_SOURCE_REGISTRY_REVIEWED_AT, "2026-11-27");
});

test("implemented and restricted sources are explicitly distinguished", () => {
  assert.equal(getMediaSource("anilist")?.status, "implemented");
  assert.equal(getMediaSource("igdb"), null);
  assert.equal(getMediaSource("jikan")?.status, "retired");
  assert.equal(getMediaSource("comic-vine")?.status, "restricted-noncommercial");
  assert.equal(getMediaSource("tvmaze")?.status, "license-review");
  assert.equal(getMediaSource("worldcat")?.status, "licensed-access");
});

test("source lookup and search are normalized and deterministic", () => {
  assert.equal(getMediaSource(" ANILIST ")?.name, "AniList");
  assert.deepEqual(searchMediaSources("Wikidata").map(source => source.id), ["wikidata"]);
  assert.ok(searchMediaSources("mediawiki").length >= 10);
  assert.ok(listMediaSourcesByStatus("implemented").some(source => source.id === "tmdb"));
  assert.deepEqual(searchMediaSources("   "), [...MEDIA_SOURCES]);
});

test("restricted references never become automatic scraper targets", () => {
  const comicHerald = getMediaSource("comic-book-herald");
  assert.equal(comicHerald?.status, "manual-reference");
  assert.deepEqual(comicHerald?.method, ["feed", "public-reference", "manual"]);
  assert.match(comicHerald?.notes ?? "", /Do not scrape or automate site extraction/i);

  assert.equal(getMediaSource("chronocanon")?.homepage, null);
  assert.equal(getMediaSource("chronologeek")?.homepage, null);
  assert.equal(getMediaSource("chronocanon")?.status, "needs-review");
  assert.equal(getMediaSource("chronologeek")?.status, "needs-review");

  const mediaWikiSources = MEDIA_SOURCES.filter(source => source.method.includes("mediawiki"));
  assert.equal(mediaWikiSources.length, 16);
  assert.ok(mediaWikiSources.every(source => source.status === "mediawiki-conditional"));
});

});
