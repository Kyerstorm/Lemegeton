import assert from "node:assert/strict";
import test from "node:test";
import { normalizeTitleSearchValue, scoreTitleSearchMatch, rankTitleSearchResults } from "../helpers/media/title-matching.js";

test("title normalization handles punctuation, accents and Unicode composition", () => {
  assert.equal(normalizeTitleSearchValue("Björk: Dancer in the Dark!"), "bjork dancer in the dark");
  assert.equal(normalizeTitleSearchValue("  Full—Metal   Alchemist "), "full metal alchemist");
});

test("exact, prefix and token matches rank in relevance order", () => {
  const records = [
    { title: "Legend of Galactic Heroes" },
    { title: "Legend of Zelda" },
    { title: "The Legend of the Galactic Heroes" },
    { title: "Heroes of the Galaxy" },
  ];
  const ranked = rankTitleSearchResults("Legend of the Galactic Heroes", records, record => [record.title]);
  assert.equal(ranked[0]?.title, "The Legend of the Galactic Heroes");
  assert.ok(scoreTitleSearchMatch("Legend Galactic", ["The Legend of the Galactic Heroes"]) >
    scoreTitleSearchMatch("Legend Galactic", ["Legend of Zelda"]));
});

test("title matching ignores common filler words and prefers the original token order", () => {
  const exactMeaning = scoreTitleSearchMatch("The Legend of the Galactic Heroes", ["Legend of Galactic Heroes"]);
  const ordered = scoreTitleSearchMatch("Legend Galactic", ["Legend of Galactic Heroes"]);
  const reversed = scoreTitleSearchMatch("Galactic Legend", ["Legend of Galactic Heroes"]);
  assert.ok(exactMeaning > 0);
  assert.ok(ordered > reversed);
  assert.ok(ordered > scoreTitleSearchMatch("Legend Galactic", ["Legend of Zelda"]));
});

test("alternate language titles match while provider display title stays unchanged", () => {
  const records = [
    { title: "My Hero Academia", aliases: ["Boku no Hero Academia"] },
    { title: "My Hero Academia: Vigilantes", aliases: [] },
  ];
  const ranked = rankTitleSearchResults("Boku no Hero Academia", records, item => [item.title, ...item.aliases]);
  assert.equal(ranked[0]?.title, "My Hero Academia");
});

test("equal scores preserve provider order and empty queries preserve all records", () => {
  const records = [{ title: "Dune A" }, { title: "Dune B" }, { title: "Other" }];
  const ranked = rankTitleSearchResults("Dune", records, item => [item.title]);
  assert.deepEqual(ranked.slice(0, 2).map(item => item.title), ["Dune A", "Dune B"]);
  assert.deepEqual(rankTitleSearchResults("", records, item => [item.title]), records);
});
