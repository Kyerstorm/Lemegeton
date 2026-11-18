import assert from "node:assert/strict";
import test from "node:test";
import { emoji, providerEmoji, providerFooter } from "../helpers/emoji.js";

test("provider emoji mapping resolves the central Steam, AniList and media provider icons", () => {
  assert.equal(providerEmoji("Steam Store"), emoji.steam);
  assert.equal(providerEmoji("AniList"), emoji.anilist);
  assert.equal(providerEmoji("Google Books"), emoji.GoogleBooks);
  assert.equal(providerEmoji("YouTube Music"), emoji.Youtube);
  assert.equal(providerEmoji("TMDB"), emoji.TMDB);
});

test("provider emoji mapping normalizes punctuation and has a safe fallback", () => {
  assert.equal(providerEmoji("Noveli.to"), emoji.NoveliTo);
  assert.equal(providerEmoji("Novel Archive"), emoji.NovelArchive);
  assert.equal(providerEmoji("Not A Provider"), emoji.link);
});

test("provider footers include the provider icon, source and context", () => {
  const footer = providerFooter("Steam", "Ireland store metadata");
  assert.equal(footer, emoji.steam + " Steam · Ireland store metadata");
  assert.ok(footer.length <= 2_048);
});
