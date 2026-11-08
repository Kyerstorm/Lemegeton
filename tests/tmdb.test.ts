import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizeTmdbMedia,
  normalizeTmdbVideos,
  normalizeTmdbWatchAvailability,
} from "../helpers/tmdb.js";

test("TMDB media normalization accepts valid movie and TV records", () => {
  const movie = normalizeTmdbMedia({
    id: 12,
    title: "Example Film",
    overview: "A film.",
    poster_path: "/poster.jpg",
    release_date: "2026-01-02",
    vote_average: 7.5,
  }, "movie");
  assert.equal(movie?.title, "Example Film");
  assert.equal(movie?.sourceUrl, "https://www.themoviedb.org/movie/12");
  assert.equal(movie?.image, "https://image.tmdb.org/t/p/w500/poster.jpg");
  assert.equal(movie?.releaseDate, "2026-01-02");

  const series = normalizeTmdbMedia({ id: 13, name: "Example Series" }, "tv");
  assert.equal(series?.title, "Example Series");
  assert.equal(series?.sourceUrl, "https://www.themoviedb.org/tv/13");
});

test("TMDB media normalization rejects invalid identifiers and missing titles", () => {
  assert.equal(normalizeTmdbMedia({ id: -1, title: "Bad" }, "movie"), null);
  assert.equal(normalizeTmdbMedia({ id: 3, name: "TV name" }, "movie"), null);
  assert.equal(normalizeTmdbMedia({ id: 3, title: " " }, "movie"), null);
});

test("TMDB watch availability deduplicates provider names and validates the provider link", () => {
  const result = normalizeTmdbWatchAvailability({
    flatrate: [
      { provider_name: "Stream A" },
      { provider_name: "Stream A" },
      { provider_name: "Stream B" },
      { provider_name: "" },
    ],
    rent: [{ provider_name: "Rent Store" }],
    link: "https://www.themoviedb.org/movie/12/watch",
  }, "IE");

  assert.equal(result?.region, "IE");
  assert.equal(result?.link, "https://www.themoviedb.org/movie/12/watch");
  assert.deepEqual(result?.groups.map((group) => [group.type, group.providers]), [
    ["streaming", ["Stream A", "Stream B"]],
    ["rent", ["Rent Store"]],
  ]);

  const unsafe = normalizeTmdbWatchAvailability({ link: "javascript:alert(1)" }, "US");
  assert.equal(unsafe?.link, null);
  assert.deepEqual(unsafe?.groups, []);
});

test("TMDB availability distinguishes a missing regional record", () => {
  assert.equal(normalizeTmdbWatchAvailability(undefined, "IE"), null);
});

test("TMDB videos only exposes safe YouTube and Vimeo links", () => {
  const videos = normalizeTmdbVideos({
    results: [
      { id: "yt-1", name: "Official Trailer", site: "YouTube", key: "abc123", type: "Trailer", official: true },
      { id: "vm-1", name: "Teaser", site: "Vimeo", key: "clip-7", type: "Teaser", official: false },
      { id: "bad", name: "Unsupported", site: "Other", key: "untrusted", type: "Trailer" },
      { id: "empty", name: "Missing key", site: "YouTube", key: "" },
    ],
  });

  assert.equal(videos.length, 2);
  assert.equal(videos[0]?.url, "https://www.youtube.com/watch?v=abc123");
  assert.equal(videos[0]?.official, true);
  assert.equal(videos[1]?.url, "https://vimeo.com/clip-7");
});

test("TMDB video normalization limits results and removes duplicate records", () => {
  const results = Array.from({ length: 15 }, (_, index) => ({
    id: "video-" + index,
    name: "Video " + index,
    site: "YouTube",
    key: "key-" + index,
    type: "Trailer",
  }));
  results.push(results[0]!);
  const videos = normalizeTmdbVideos({ results });
  assert.equal(videos.length, 12);
});
