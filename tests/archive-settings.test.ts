import test from "node:test";
import assert from "node:assert/strict";
import {
  isValidArchiveChannelId,
  parseAniListMangaReference,
  parsePanelChapterCaption,
} from "../helpers/archive/archive.js";

test("Archive channel setting accepts normal Discord text-channel snowflakes and clearing", () => {
  assert.equal(isValidArchiveChannelId("123456789012345678"), true);
  assert.equal(isValidArchiveChannelId("12345678901234567890"), true);
  assert.equal(isValidArchiveChannelId(null), true);
  assert.equal(isValidArchiveChannelId("123"), false);
  assert.equal(isValidArchiveChannelId("123456789012345678901"), false);
  assert.equal(isValidArchiveChannelId("12345678901234567x"), false);
  assert.equal(isValidArchiveChannelId(""), false);
});

test("Archive quick Manga Panels form parses chapter and AniList references", () => {
  assert.deepEqual(parsePanelChapterCaption("Chapter 12 — Final battle"), {
    chapterNumber: "12",
    caption: "Final battle",
  });
  assert.deepEqual(parsePanelChapterCaption("N/A"), {
    chapterNumber: "N/A",
    caption: "",
  });
  assert.deepEqual(parseAniListMangaReference("456"), {
    id: "456",
    url: "https://anilist.co/manga/456",
  });
  assert.deepEqual(parseAniListMangaReference("https://anilist.co/manga/456/example"), {
    id: "456",
    url: "https://anilist.co/manga/456",
  });
});
