import test from "node:test";
import assert from "node:assert/strict";
import { normalizeQuizDifficulty } from "../helpers/runtime/games.js";

test("quiz question difficulty accepts all supported levels", () => {
  assert.equal(normalizeQuizDifficulty("easy"), "easy");
  assert.equal(normalizeQuizDifficulty("STANDARD"), "standard");
  assert.equal(normalizeQuizDifficulty("Hard"), "hard");
  assert.equal(normalizeQuizDifficulty("expert"), "expert");
});

test("quiz question difficulty rejects unsupported levels", () => {
  assert.throws(() => normalizeQuizDifficulty("impossible"), /easy, standard, hard or expert/);
  assert.throws(() => normalizeQuizDifficulty(""), /easy, standard, hard or expert/);
});
