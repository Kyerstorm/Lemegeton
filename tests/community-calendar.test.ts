import test from "node:test";
import assert from "node:assert/strict";
import { mergeCommunityCalendarEntries, type UpcomingCommunitySession } from "../helpers/community/community-sessions.js";

test("community calendar merges provider releases and server sessions in chronological order", () => {
  const sessions: UpcomingCommunitySession[] = [{
    id: "10",
    title: "Friday watch session",
    channel_id: "12345678901234567",
    activity_type: "watch",
    scheduled_at: new Date("2026-11-16T19:00:00Z"),
    media_url: "https://example.com/media",
  }];
  const items = mergeCommunityCalendarEntries([
    { title: "New episode", when: new Date("2026-11-15T18:00:00Z"), provider: "AniList", url: "https://anilist.co/anime/1" },
    { title: "New film", when: new Date("2026-11-17T00:00:00Z"), provider: "TMDB Movies", url: "https://www.themoviedb.org/movie/1" },
  ], sessions);
  assert.deepEqual(items.map(item => item.title), ["New episode", "Friday watch session", "New film"]);
  assert.equal(items[1]?.source, "Community · Watch");
  assert.equal(items[1]?.channelId, "12345678901234567");
  assert.equal(items[1]?.sourceUrl, "https://example.com/media");
});

test("community calendar bounds combined output and drops invalid dates", () => {
  const sessions = Array.from({ length: 35 }, (_, index) => ({
    id: String(index),
    title: "Session " + index,
    channel_id: "12345678901234567",
    activity_type: "discuss" as const,
    scheduled_at: new Date(Date.UTC(2026, 10, 1, 0, index)),
    media_url: null,
  }));
  const invalid = { ...sessions[0]!, id: "invalid", scheduled_at: new Date(Number.NaN) };
  const items = mergeCommunityCalendarEntries([], [...sessions, invalid]);
  assert.equal(items.length, 30);
  assert.ok(items.every(item => Number.isFinite(item.when.getTime())));
});
