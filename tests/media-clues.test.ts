import test from "node:test";
import assert from "node:assert/strict";
import { normalizeMediaClues } from "../helpers/runtime/games.js";

test("media clues preserve supported categories and clue text", () => {
  assert.deepEqual(normalizeMediaClues(["title: A hidden work", "creator: An acclaimed writer"]), [
    { category: "title", text: "A hidden work" },
    { category: "creator", text: "An acclaimed writer" },
  ]);
});

test("media clues support release, franchise, adaptation and game categories", () => {
  assert.deepEqual(normalizeMediaClues(["release: 2010s", "franchise: Long-running series", "adaptation: Based on a novel", "game: Console RPG"]).map(item => item.category),
    ["release", "franchise", "adaptation", "game"]);
});

test("media clues reject invalid categories, missing text and excess entries", () => {
  assert.throws(() => normalizeMediaClues(["unknown: unsupported"]), /supported category/);
  assert.throws(() => normalizeMediaClues(["title: "]), /supported category|text after its category/);
  assert.throws(() => normalizeMediaClues(Array.from({ length: 9 }, (_, index) => "genre: clue " + index)), /up to eight/);
});
