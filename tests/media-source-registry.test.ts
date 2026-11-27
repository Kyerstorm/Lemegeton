import test from "node:test";
import assert from "node:assert/strict";
import {
  getMediaSource,
  listMediaSourcesByStatus,
  MEDIA_SOURCES,
  MEDIA_SOURCE_REGISTRY_REVIEWED_AT,
  searchMediaSources,
} from "../helpers/media/media-source-registry.js";
import {
  getMediaSourceIntegrationCoverage,
  getMediaSourceIntegrationMode,
  MEDIA_SOURCE_INTEGRATION_MODES,
} from "../helpers/integration/media-source-clients.js";

test("source registry covers every requested source exactly once", () => {
  const ids = MEDIA_SOURCES.map(source => source.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(ids.length, 64);
  assert.equal(MEDIA_SOURCE_REGISTRY_REVIEWED_AT, "2026-11-27");
});

test("implemented and restricted sources are explicitly distinguished", () => {
  assert.equal(getMediaSource("anilist")?.status, "implemented");
  assert.equal(getMediaSource("igdb"), null);
  assert.equal(getMediaSource("jikan")?.status, "retired");
  assert.equal(getMediaSource("comic-vine")?.status, "restricted-noncommercial");
  assert.equal(getMediaSource("tvmaze")?.status, "license-review");
  assert.equal(getMediaSource("worldcat")?.status, "licensed-access");
  assert.equal(getMediaSource("setlist-fm")?.status, "credential-required");
  assert.equal(getMediaSource("shikimori")?.status, "implemented");
  assert.equal(getMediaSource("bookbrainz")?.status, "implemented");
  assert.equal(getMediaSource("novelfire")?.status, "terms-review");
  assert.equal(getMediaSource("novel-archive")?.status, "terms-review");
  assert.equal(getMediaSource("wuxia-click")?.status, "terms-review");
  assert.equal(getMediaSource("noveli-to")?.status, "terms-review");
  assert.equal(getMediaSourceIntegrationMode("novelfire"), "scrape");
  assert.equal(getMediaSourceIntegrationMode("novel-archive"), "scrape");
  assert.equal(getMediaSourceIntegrationMode("wuxia-click"), "scrape");
  assert.equal(getMediaSourceIntegrationMode("noveli-to"), "scrape");
  assert.equal(getMediaSource("the-canonicle")?.status, "manual-reference");
  assert.equal(getMediaSource("chronelines")?.status, "manual-reference");
  assert.equal(getMediaSource("order-of-book-series")?.status, "manual-reference");
  assert.equal(getMediaSource("fandom-wikis")?.status, "manual-reference");
});

test("source lookup and search are normalized and deterministic", () => {
  assert.equal(getMediaSource(" ANILIST ")?.name, "AniList");
  assert.deepEqual(searchMediaSources("Wikidata").map(source => source.id), ["wikidata"]);
  assert.ok(searchMediaSources("mediawiki").length >= 10);
  assert.ok(listMediaSourcesByStatus("implemented").some(source => source.id === "tmdb"));
  assert.deepEqual(searchMediaSources("   "), [...MEDIA_SOURCES]);
});

test("every inventory source has one explicit integration route", async () => {
  const { getMediaSourceIntegrationCoverage, getMediaSourceIntegrationMode } =
    await import("../helpers/integration/media-source-clients.js");
  const coverage = getMediaSourceIntegrationCoverage();
  assert.equal(coverage.length, MEDIA_SOURCES.length);
  assert.deepEqual(
    coverage.map(source => source.id).sort(),
    MEDIA_SOURCES.map(source => source.id).sort(),
  );
  assert.equal(getMediaSourceIntegrationMode("the-canonicle"), "manual");
  assert.equal(getMediaSourceIntegrationMode("chronelines"), "manual");
  assert.equal(getMediaSourceIntegrationMode("order-of-book-series"), "manual");
  assert.equal(getMediaSourceIntegrationMode("comic-book-herald"), "feed");
  assert.equal(getMediaSourceIntegrationMode("jikan"), "retired");
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

test("every inventory entry has exactly one explicit integration route", () => {
  const coverage = getMediaSourceIntegrationCoverage();
  assert.equal(Object.keys(MEDIA_SOURCE_INTEGRATION_MODES).length, MEDIA_SOURCES.length);
  assert.equal(coverage.length, MEDIA_SOURCES.length);
  assert.deepEqual(coverage.map(item => item.id).sort(), MEDIA_SOURCES.map(item => item.id).sort());
  assert.equal(getMediaSourceIntegrationMode("jikan"), "retired");
  assert.equal(getMediaSourceIntegrationMode("comic-vine"), "restricted-api");
  assert.equal(getMediaSourceIntegrationMode("worldcat"), "licensed-api");
  assert.equal(getMediaSourceIntegrationMode("chronocanon"), "manual");
});
