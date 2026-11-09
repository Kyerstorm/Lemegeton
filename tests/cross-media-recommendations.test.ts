import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizeGenreTokens,
  rankCrossMediaCandidates,
  recommendationGenreLabels,
} from "../helpers/media/cross-media-recommendations.js";

test("cross-media genre normalization maps provider vocabulary conservatively", () => {
  assert.deepEqual(
    [...normalizeGenreTokens(["Science Fiction", "Sci-Fi", "Slice of Life", "Historical", "War"])].sort(),
    ["historical", "sci-fi", "slice of life", "war"],
  );
  assert.equal(normalizeGenreTokens(["Stewardship"]).has("war"), false);
  assert.deepEqual(recommendationGenreLabels(["sci-fi", "slice of life", "fantasy", "unknown"]), [
    "Science Fiction", "Slice of Life", "Fantasy",
  ]);
});

test("cross-media ranking explains overlap, deduplicates results and excludes the seed", () => {
  const ranked = rankCrossMediaCandidates("Seed Title", "anime", ["Fantasy", "Drama"], [
    { title: "Seed Title", category: "anime", provider: "AniList", url: null, genres: ["Fantasy"] },
    { title: "Book One", category: "book", provider: "Google Books", url: "https://books.google.com/books?id=1", genres: ["Fantasy / Adventure"] },
    { title: "Book One", category: "book", provider: "Google Books", url: "https://books.google.com/books?id=2", genres: ["Fantasy", "Drama"] },
    { title: "Film One", category: "movie", provider: "TMDB", url: "https://www.themoviedb.org/movie/2", genres: ["Drama"] },
    { title: "Unrelated", category: "tv", provider: "TMDB", url: null, genres: ["Crime"] },
  ]);
  assert.equal(ranked.length, 2);
  assert.deepEqual(ranked[0]?.sharedGenres, ["drama", "fantasy"]);
  assert.equal(ranked[0]?.url, "https://books.google.com/books?id=2");
  assert.equal(ranked[1]?.title, "Film One");
});

test("cross-media ranking limits each category to three results and the requested total", () => {
  const candidates = Array.from({ length: 8 }, (_, index) => ({
    title: `Movie ${index}`,
    category: "movie" as const,
    provider: "TMDB",
    url: null,
    genres: ["Comedy"],
  }));
  assert.equal(rankCrossMediaCandidates("Seed", "anime", ["Comedy"], candidates, 10).length, 3);
  assert.equal(rankCrossMediaCandidates("Seed", "anime", ["Comedy"], candidates, 2).length, 2);
});
