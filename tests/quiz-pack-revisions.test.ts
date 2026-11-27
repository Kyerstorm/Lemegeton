import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizeMediaClues,
  normalizeMultipleChoiceOptions,
  normalizeQuizDifficulty,
  resolveQuizAnswer,
  validateQuizQuestionClues,
} from "../helpers/runtime/games.js";

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


test("trivia multiple-choice options are normalized and require the correct choice", () => {
  assert.deepEqual(normalizeMultipleChoiceOptions("Correct", [" Correct ", "Wrong", "Other"]), ["Correct", "Wrong", "Other"]);
  assert.deepEqual(normalizeMultipleChoiceOptions("Answer", []), []);
  assert.throws(() => normalizeMultipleChoiceOptions("A", ["A"]), /two to four/i);
  assert.throws(() => normalizeMultipleChoiceOptions("A", ["A", " A "]), /distinct/i);
  assert.throws(() => normalizeMultipleChoiceOptions("A", ["B", "C"]), /correct answer must be included/i);
});

test("trivia scoring accepts answer aliases and numbered multiple-choice selections", () => {
  assert.equal(resolveQuizAnswer("2", "Correct", [], ["Wrong", "Correct", "Other"]), true);
  assert.equal(resolveQuizAnswer("correct!", "Correct", ["correct!"]), true);
  assert.equal(resolveQuizAnswer("1", "Correct", [], ["Wrong", "Correct"]), false);
});

test("guessing packs accept identification clues and require at least one", () => {
  const clues = normalizeMediaClues(["creator: credited creator", "game: target franchise"]);
  assert.doesNotThrow(() => validateQuizQuestionClues("guessing", clues));
  assert.throws(() => validateQuizQuestionClues("guessing", []), /at least one/i);
});

test("mystery packs require clue layers from different media categories", () => {
  assert.doesNotThrow(() => validateQuizQuestionClues("mystery", normalizeMediaClues(["title: unknown work", "release: release period"])));
  assert.throws(() => validateQuizQuestionClues("mystery", normalizeMediaClues(["title: only clue"])), /at least two clues/i);
  assert.throws(() => validateQuizQuestionClues("mystery", normalizeMediaClues(["title: clue one", "title: clue two"])), /different categories/i);
});

test("trivia rejects layered clues while puzzle packs require a relation-style clue", () => {
  assert.throws(() => validateQuizQuestionClues("trivia", normalizeMediaClues(["title: hidden work"])), /not layered media clues/i);
  assert.doesNotThrow(() => validateQuizQuestionClues("puzzle", normalizeMediaClues(["connection: connect the works"])));
  assert.throws(() => validateQuizQuestionClues("puzzle", normalizeMediaClues(["title: name the work"])), /need at least one word/i);
});
