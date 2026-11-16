import test from "node:test";
import assert from "node:assert/strict";
import { normalizeMediaClues, normalizeQuizPackMode } from "../helpers/runtime/games.js";

test("media clues preserve supported categories and clue text", () => {
  assert.deepEqual(normalizeMediaClues(["title: A hidden work", "creator: An acclaimed writer"]), [
    { category: "title", text: "A hidden work" },
    { category: "creator", text: "An acclaimed writer" },
  ]);
});

test("media clues support release, franchise, adaptation, game and puzzle categories", () => {
  assert.deepEqual(normalizeMediaClues(["release: 2010s", "franchise: Long-running series", "adaptation: Based on a novel", "game: Console RPG", "word: Five letters", "connection: Shared creator", "relationship: Sequel", "chronology: Before the original"]).map(item => item.category),
    ["release", "franchise", "adaptation", "game", "word", "connection", "relationship", "chronology"]);
});

test("media clues reject invalid categories, missing text and excess entries", () => {
  assert.throws(() => normalizeMediaClues(["unknown: unsupported"]), /supported category/);
  assert.throws(() => normalizeMediaClues(["title: "]), /supported category|text after its category/);
  assert.throws(() => normalizeMediaClues(Array.from({ length: 9 }, (_, index) => "genre: clue " + index)), /up to eight/);
});


test("quiz pack modes include the Challenge Centre and Media Puzzle Room", () => {
  assert.deepEqual(["trivia", "guessing", "mystery", "challenge", "puzzle"].map(normalizeQuizPackMode),
    ["trivia", "guessing", "mystery", "challenge", "puzzle"]);
  assert.throws(() => normalizeQuizPackMode("unsupported"), /Choose trivia, guessing, mystery, challenge or puzzle/);
});
