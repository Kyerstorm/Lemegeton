import test from "node:test";
import assert from "node:assert/strict";
import { formatMediaComparisonSide, parseMediaComparisonEntries } from "../helpers/media/media-comparison.js";

test("comparison input accepts two to four mixed media entries", () => {
  assert.deepEqual(parseMediaComparisonEntries("anime | Your Name\nbook | Dune"), [
    { category: "anime", title: "Your Name" },
    { category: "book", title: "Dune" },
  ]);
  assert.deepEqual(parseMediaComparisonEntries("light novels | Spice and Wolf\nfilm | Arrival\ntv | Dark\ngames | Hades"), [
    { category: "light_novel", title: "Spice and Wolf" },
    { category: "movie", title: "Arrival" },
    { category: "tv", title: "Dark" },
    { category: "game", title: "Hades" },
  ]);
});

test("comparison input rejects too few or too many entries", () => {
  assert.throws(() => parseMediaComparisonEntries("anime | One title"), /two and four/);
  assert.throws(() => parseMediaComparisonEntries("anime | A\nanime | B\nanime | C\nanime | D\nanime | E"), /two and four/);
});

test("comparison input rejects missing separators, unsupported categories and invalid titles", () => {
  assert.throws(() => parseMediaComparisonEntries("anime One Name\nbook | Dune"), /category \| title/);
  assert.throws(() => parseMediaComparisonEntries("webnovel | Example\nbook | Dune"), /unsupported category/);
  assert.throws(() => parseMediaComparisonEntries("anime | A\nbook | Dune"), /2–100/);
  assert.throws(() => parseMediaComparisonEntries("anime | " + "x".repeat(101) + "\nbook | Dune"), /2–100/);
});

test("comparison formatting preserves provider scales and leaves missing or incompatible fields absent", () => {
  const anime = formatMediaComparisonSide({
    category: "anime",
    title: "Example Series",
    provider: "AniList",
    sourceUrl: "https://anilist.co/anime/1",
    fields: [
      { name: "Provider", value: "AniList" },
      { name: "Score", value: "82/100" },
      { name: "Episodes", value: "12" },
    ],
  });
  const film = formatMediaComparisonSide({
    category: "movie",
    title: "Example Film",
    provider: "TMDB",
    sourceUrl: "https://www.themoviedb.org/movie/2",
    fields: [
      { name: "Rating", value: "7.8/10" },
      { name: "Runtime", value: "104 minutes" },
    ],
  });
  assert.match(anime.value, /Score: 82\/100/);
  assert.match(film.value, /Rating: 7\.8\/10/);
  assert.match(anime.value, /Episodes: 12/);
  assert.match(film.value, /Runtime: 104 minutes/);
  assert.doesNotMatch(anime.value, /Runtime:/);
  assert.doesNotMatch(film.value, /Episodes:/);
  assert.doesNotMatch(anime.value, /Provider: AniList\nProvider:/);
});

test("mixed comparisons preserve each category without media-type coercion", () => {
  const entries = parseMediaComparisonEntries(
    "anime | Example Series\nbook | Example Edition\nfilm | Example Film\ngame | Example Game",
  );
  assert.deepEqual(entries.map(entry => entry.category), ["anime", "book", "movie", "game"]);
});
