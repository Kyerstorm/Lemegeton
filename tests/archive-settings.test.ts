import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizeArchiveDashboardSettings,
  type ArchiveSettings,
} from "../helpers/archive/archive.js";

import {
  isValidArchiveChannelId,
  isValidArchiveModeratorRoleId,
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

test("Archive moderator role setting accepts valid roles and clearing but rejects @everyone", () => {
  assert.equal(isValidArchiveModeratorRoleId("123456789012345678"), true);
  assert.equal(isValidArchiveModeratorRoleId("12345678901234567890"), true);
  assert.equal(isValidArchiveModeratorRoleId(null), true);
  assert.equal(isValidArchiveModeratorRoleId("123"), false);
  assert.equal(isValidArchiveModeratorRoleId("123456789012345678901"), false);
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

test("Dashboard Archive settings normalize valid selections and reject empty categories", () => {
  const settings: ArchiveSettings = {
    enabledCategories: ["panels", "quotes", "panels"],
    uploadTypes: ["image", "video", "image"],
    uploadChannelId: "123456789012345678",
    legacyStorageChannelId: null,
    moderationChannelId: "223456789012345678",
    moderatorRoleId: "323456789012345678",
  };
  assert.deepEqual(normalizeArchiveDashboardSettings("423456789012345678", settings), {
    ...settings,
    enabledCategories: ["panels", "quotes"],
    uploadTypes: ["image", "video"],
  });
  assert.throws(() => normalizeArchiveDashboardSettings("423456789012345678", {
    ...settings,
    enabledCategories: [],
  }), /at least one valid Archive category/i);
  assert.throws(() => normalizeArchiveDashboardSettings("423456789012345678", {
    ...settings,
    uploadTypes: ["image", "executable"],
  }), /supported Archive upload types/i);
  assert.throws(() => normalizeArchiveDashboardSettings("423456789012345678", {
    ...settings,
    uploadChannelId: "not-a-channel",
  }), /valid channels/i);
  assert.throws(() => normalizeArchiveDashboardSettings("423456789012345678", {
    ...settings,
    moderatorRoleId: "423456789012345678",
  }), /valid Archive moderator role/i);
});
