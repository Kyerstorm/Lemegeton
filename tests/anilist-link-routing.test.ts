import assert from "node:assert/strict";
import test from "node:test";
import { aniListLinkFeature, parseAniListUrl } from "../src/integrations/anilist-embed.js";

test("AniList user and profile routes use the Profile feature", () => {
  for (const url of [
    "https://anilist.co/user/example",
    "https://anilist.co/user/example/stats",
    "https://anilist.co/user/example/favorites",
    "https://anilist.co/user/example/activity",
  ]) {
    const target = parseAniListUrl(url);
    assert.ok(target, url);
    assert.equal(aniListLinkFeature(target), "profile", url);
  }
});

test("AniList media and public entity routes use the Discover feature", () => {
  for (const url of [
    "https://anilist.co/anime/1",
    "https://anilist.co/manga/2",
    "https://anilist.co/character/3",
    "https://anilist.co/staff/4",
    "https://anilist.co/studio/5",
    "https://anilist.co/review/6",
    "https://anilist.co/activity/7",
  ]) {
    const target = parseAniListUrl(url);
    assert.ok(target, url);
    assert.equal(aniListLinkFeature(target), "discover", url);
  }
});

test("personal list routes remain excluded rather than bypassing feature boundaries", () => {
  for (const url of [
    "https://anilist.co/user/example/animelist",
    "https://anilist.co/user/example/mangalist",
    "https://anilist.co/user/example/anime",
  ]) {
    assert.equal(parseAniListUrl(url), null, url);
  }
});
