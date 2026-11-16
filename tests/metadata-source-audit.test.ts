import test from "node:test";
import assert from "node:assert/strict";
import { auditMetadataSource } from "../helpers/media/metadata-source-audit.js";

test("metadata source audit reports present and missing provider fields without inferring freshness", () => {
  const audit = auditMetadataSource({
    provider: "AniList", category: "anime", id: 123, url: "https://anilist.co/anime/123",
    fields: { description: "A work", releaseDate: null, creators: ["Writer"], genres: [], image: "https://s4.anilist.co/cover.jpg" },
  });
  assert.deepEqual(audit.presentFields, ["description", "creators", "image"]);
  assert.deepEqual(audit.missingFields, ["releaseDate", "genres"]);
  assert.equal(audit.freshness, "not-reported");
});

test("metadata source audit treats empty arrays and blank values as missing", () => {
  const audit = auditMetadataSource({
    provider: "TMDB", category: "movie", id: "44", url: "https://www.themoviedb.org/movie/44",
    fields: { description: " ", releaseDate: "2026-01-01", creators: [], genres: ["Drama"], image: null },
  });
  assert.deepEqual(audit.presentFields, ["releaseDate", "genres"]);
  assert.deepEqual(audit.missingFields, ["description", "creators", "image"]);
});
