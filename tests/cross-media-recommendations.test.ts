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

test("cross-media matching compares provider-native genres, tags and subjects", () => {
  const ranked = rankCrossMediaCandidates("Seed", "anime", {
    genres: ["Fantasy"],
    tags: ["Magic"],
  }, [
    { title: "Book by subject", category: "book", provider: "Open Library", url: "https://openlibrary.org/works/OL1W", genres: [], subjects: ["Fantasy"] },
    { title: "Manga by tag", category: "manga", provider: "MangaDex", url: "https://mangadex.org/title/1", genres: [], tags: ["Magic"] },
    { title: "Unrelated book", category: "book", provider: "Google Books", url: "https://books.google.com/books?id=2", genres: [], categories: ["Fiction"] },
  ]);
  assert.equal(ranked.length, 2);
  assert.deepEqual(ranked[0]?.sharedLabels, ["fantasy"]);
  assert.deepEqual(ranked[0]?.sharedLabelGroups, [{ kind: "subjects", matchedAgainst: ["genres"], values: ["Fantasy"] }]);
  assert.deepEqual(ranked[0]?.sharedGenres, []);
  const manga = ranked.find(item => item.provider === "MangaDex");
  assert.deepEqual(manga?.sharedTags, ["magic"]);
  assert.deepEqual(manga?.sharedLabelGroups, [{ kind: "tags", matchedAgainst: ["tags"], values: ["Magic"] }]);
});

test("cross-media search labels normalize source display names and aliases", () => {
  assert.deepEqual(
    recommendationGenreLabels(["Science Fiction", "Fantasy", "Historical", "Unknown"]),
    ["Science Fiction", "Fantasy", "History"],
  );
});

test("cross-media matches retain both metadata dimensions in an overlap", () => {
  const ranked = rankCrossMediaCandidates("Seed", "anime", {
    genres: ["Fantasy"],
    subjects: ["Space Opera"],
  }, [
    {
      title: "Subject match", category: "book", provider: "Open Library", url: null,
      genres: [], subjects: ["Fantasy"],
    },
    {
      title: "Genre match", category: "movie", provider: "TMDB", url: null,
      genres: ["Space Opera"],
    },
  ]);
  assert.deepEqual(ranked.map(item => item.sharedLabelGroups), [
    [{ kind: "subjects", matchedAgainst: ["genres"], values: ["Fantasy"] }],
    [{ kind: "genres", matchedAgainst: ["subjects"], values: ["Space Opera"] }],
  ]);
});

test("cross-media ranking returns no matches for missing or non-overlapping metadata", () => {
  const candidate = {
    title: "Candidate", category: "book" as const, provider: "Google Books",
    url: null, genres: [], categories: ["Fiction"],
  };
  assert.deepEqual(rankCrossMediaCandidates("Seed", "anime", {}, [candidate]), []);
  assert.deepEqual(rankCrossMediaCandidates("Seed", "anime", { genres: ["Fantasy"] }, [candidate]), []);
  assert.deepEqual(rankCrossMediaCandidates("Seed", "anime", { genres: ["Fantasy"] }, [
    { ...candidate, categories: [] },
  ]), []);
});


test("cross-media similarity normalizes overlap and resists metadata-volume bias", () => {
  const seed = ["Fantasy", "Drama", "Mystery", "Adventure"];
  const ranked = rankCrossMediaCandidates("Seed", "anime", seed, [
    { title: "Sparse match", category: "book", provider: "Open Library", url: null, genres: ["Fantasy"] },
    { title: "Strong match", category: "book", provider: "Google Books", url: null, genres: ["Fantasy", "Drama", "Mystery"] },
    { title: "Noisy match", category: "movie", provider: "TMDB", url: null, genres: [
      "Fantasy", "Crime", "War", "Family", "Sports", "History", "Documentary", "Animation",
      "Action", "Comedy", "Horror", "Romance", "Thriller", "Adventure", "Western",
    ] },
  ]);
  assert.equal(ranked[0]?.title, "Strong match");
  assert.equal(ranked[0]?.score, 857);
  assert.ok((ranked.find(item => item.title === "Sparse match")?.score ?? 0)
    > (ranked.find(item => item.title === "Noisy match")?.score ?? 0));
});
