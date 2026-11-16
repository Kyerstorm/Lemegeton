import test from "node:test";
import assert from "node:assert/strict";
import {
  filterCommunityCalendarEntries,
  formatCommunityCalendarTime,
  mergeCommunityCalendarEntries,
  normalizeCommunityCalendarSelection,
  type UpcomingCommunitySession,
} from "../helpers/community/community-sessions.js";

const sessions: UpcomingCommunitySession[] = [{
  id: "10",
  title: "Friday watch session",
  channel_id: "12345678901234567",
  activity_type: "watch",
  scheduled_at: new Date("2026-11-16T19:00:00Z"),
  media_url: "https://example.com/media",
}];

const releases = [
  { title: "New episode", when: new Date("2026-11-15T18:00:00Z"), provider: "AniList", url: "https://anilist.co/anime/1", category: "anime" as const },
  { title: "New film", when: new Date("2026-11-17T00:00:00Z"), provider: "TMDB Movies", url: "https://www.themoviedb.org/movie/1", category: "movies" as const },
  { title: "New game", when: new Date("2026-11-18T12:00:00Z"), provider: "IGDB", url: "https://www.igdb.com/games/1", category: "games" as const },
];

test("calendar merges provider releases and guild sessions in chronological order", () => {
  const items = mergeCommunityCalendarEntries(releases, sessions);
  assert.deepEqual(items.map(item => item.title), ["New episode", "Friday watch session", "New film", "New game"]);
  assert.equal(items[1]?.source, "Community · Watch");
  assert.equal(items[1]?.kind, "community");
  assert.equal(items[1]?.category, "community");
  assert.equal(items[1]?.channelId, "12345678901234567");
  assert.equal(items[1]?.sourceUrl, "https://example.com/media");
  assert.equal(items[0]?.kind, "release");
  assert.equal(items[0]?.category, "anime");
});

test("calendar filters releases, community events and individual provider categories", () => {
  const items = mergeCommunityCalendarEntries(releases, sessions);
  assert.deepEqual(filterCommunityCalendarEntries(items, "community").map(item => item.title), ["Friday watch session"]);
  assert.deepEqual(filterCommunityCalendarEntries(items, "releases").map(item => item.title), ["New episode", "New film", "New game"]);
  assert.deepEqual(filterCommunityCalendarEntries(items, "anime").map(item => item.title), ["New episode"]);
  assert.deepEqual(filterCommunityCalendarEntries(items, "games").map(item => item.title), ["New game"]);
  assert.deepEqual(filterCommunityCalendarEntries(items, "all"), items);
});

test("calendar filter state accepts supported windows and falls back for invalid values", () => {
  assert.deepEqual(normalizeCommunityCalendarSelection("7|community"), { days: 7, scope: "community" });
  assert.deepEqual(normalizeCommunityCalendarSelection("30|games"), { days: 30, scope: "games" });
  assert.deepEqual(normalizeCommunityCalendarSelection("90|unknown"), { days: 14, scope: "all" });
  assert.deepEqual(normalizeCommunityCalendarSelection("14"), { days: 14, scope: "all" });
});

test("calendar formats event times using the configured IANA timezone", () => {
  const local = formatCommunityCalendarTime(new Date("2026-01-15T12:00:00.000Z"), "Europe/Dublin");
  assert.match(local, /15 Jan 2026/);
  assert.match(local, /12:00/);
  assert.match(local, /GMT/);
  assert.throws(() => formatCommunityCalendarTime(new Date(), "Mars/Olympus"), /valid IANA timezone/);
});

test("calendar bounds combined output and drops invalid dates", () => {
  const manySessions = Array.from({ length: 110 }, (_, index) => ({
    id: String(index),
    title: "Session " + index,
    channel_id: "12345678901234567",
    activity_type: "discuss" as const,
    scheduled_at: new Date(Date.UTC(2026, 10, 1, 0, index)),
    media_url: null,
  }));
  const invalid = { ...manySessions[0]!, id: "invalid", scheduled_at: new Date(Number.NaN) };
  const items = mergeCommunityCalendarEntries([], [...manySessions, invalid]);
  assert.equal(items.length, 100);
  assert.ok(items.every(item => Number.isFinite(item.when.getTime())));
});
