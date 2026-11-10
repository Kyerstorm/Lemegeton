import test from "node:test";
import assert from "node:assert/strict";
import {
  archiveMediaTypesForCategory, createAtlasDiscordUrl,
  normalizeAtlasCategory, normalizeAtlasTitle, safeAtlasUrl,
} from "../helpers/integration/atlas.js";

test("Atlas accepts typed community nodes without conflating them with media categories", () => {
  assert.equal(normalizeAtlasCategory("anime"), "ANIME");
  assert.equal(normalizeAtlasCategory("light novel"), "LIGHT_NOVEL");
  assert.equal(normalizeAtlasCategory("archive_entry"), "ARCHIVE_ENTRY");
  assert.equal(normalizeAtlasCategory("archive-collection"), "ARCHIVE_COLLECTION");
  assert.equal(normalizeAtlasCategory("discussion"), "DISCUSSION");
  assert.equal(normalizeAtlasCategory("activity"), "ACTIVITY");
  assert.equal(normalizeAtlasCategory("creator"), "CREATOR");
  assert.equal(normalizeAtlasCategory("franchise"), "FRANCHISE");
  assert.equal(normalizeAtlasCategory("not-a-node"), null);
});

test("Atlas archive media matching remains category-aware", () => {
  assert.deepEqual(archiveMediaTypesForCategory("MANGA"), ["manga", "manhwa", "manhua", "webtoon"]);
  assert.deepEqual(archiveMediaTypesForCategory("LIGHT_NOVEL"), ["light novel", "light_novel"]);
  assert.deepEqual(archiveMediaTypesForCategory("GAME"), ["game", "video game"]);
  assert.deepEqual(archiveMediaTypesForCategory("CREATOR"), []);
});

test("Atlas title, HTTPS URL and Discord deep-link normalization are bounded", () => {
  assert.equal(normalizeAtlasTitle("  FRIEREN: Beyond Journey's End  "), "frieren beyond journey s end");
  assert.equal(safeAtlasUrl("https://anilist.co/manga/1"), "https://anilist.co/manga/1");
  assert.equal(safeAtlasUrl("http://example.com"), null);
  assert.equal(safeAtlasUrl("https://user:pass@example.com"), null);
  assert.equal(createAtlasDiscordUrl("12345678901234567", "22345678901234567"),
    "https://discord.com/channels/12345678901234567/22345678901234567");
  assert.equal(createAtlasDiscordUrl("guild", "channel"), null);
});
