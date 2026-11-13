import test from "node:test";
import assert from "node:assert/strict";
import { parseMediaComparisonEntries } from "../helpers/media/media-comparison.js";

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
