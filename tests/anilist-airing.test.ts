import test from "node:test";
import assert from "node:assert/strict";
import { AniListClient } from "../helpers/providers/anilist.js";

const now = new Date("2026-11-10T00:00:00.000Z");
const start = Math.floor(now.getTime() / 1000);
function airing(airingAt: number, overrides: Record<string, unknown> = {}) {
  return {
    airingAt,
    episode: 4,
    media: {
      id: 42,
      title: { english: "Example Anime", romaji: "Example" },
      siteUrl: "https://anilist.co/anime/42",
      coverImage: { large: "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/b42.jpg" },
      format: "TV",
      status: "RELEASING",
      season: "WINTER",
      seasonYear: 2027,
      isAdult: false,
      ...overrides,
    },
  };
}
function clientFor(payload: unknown, requests: Array<{ query: string; variables: Record<string, unknown> }>) {
  return new AniListClient("https://anilist.example/graphql", 1_000, async (_input, init) => {
    const request = JSON.parse(String(init?.body)) as { query: string; variables: Record<string, unknown> };
    requests.push(request);
    return new Response(JSON.stringify({ data: payload }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  });
}

test("general airing results are future-only, UTC-filtered, sorted and bounded", async () => {
  const requests: Array<{ query: string; variables: Record<string, unknown> }> = [];
  const rows = [
    airing(start + 86_400),
    airing(start + 3_600),
    airing(start + 8 * 86_400),
    airing(start + 90_000, { isAdult: true }),
    airing(start + 91_000, { siteUrl: "https://example.com/anime/42" }),
  ];
  const client = clientFor({ Page: { airingSchedules: rows } }, requests);

  const entries = await client.searchUpcomingAirings({ day: "wednesday", days: 2 }, now);

  assert.equal(requests.length, 1);
  assert.equal(requests[0]?.variables.from, start);
  assert.equal(requests[0]?.variables.to, start + 2 * 86_400);
  assert.match(requests[0]?.query ?? "", /airingAt_greater/);
  assert.equal(entries.length, 1);
  assert.equal(entries[0]?.airingAt, start + 86_400);
  assert.equal(entries[0]?.format, "TV");
  assert.equal(entries[0]?.season, "WINTER");
  assert.equal(entries[0]?.seasonYear, 2027);
});

test("title airings use AniList title search and retain the selected media metadata", async () => {
  const requests: Array<{ query: string; variables: Record<string, unknown> }> = [];
  const media = {
    id: 88,
    title: { english: "Selected Anime" },
    siteUrl: "https://anilist.co/anime/88",
    coverImage: { large: "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/b88.jpg" },
    format: "TV",
    status: "RELEASING",
    season: "FALL",
    seasonYear: 2026,
    isAdult: false,
    airingSchedule: { nodes: [{ airingAt: start + 1_000, episode: 9 }] },
  };
  const client = clientFor({ Page: { media: [media] } }, requests);

  const entries = await client.searchUpcomingAirings({ title: "Selected Anime", days: 1 }, now);

  assert.equal(requests[0]?.variables.search, "Selected Anime");
  assert.match(requests[0]?.query ?? "", /airingSchedule\(notYetAired:true/);
  assert.equal(entries.length, 1);
  assert.equal(entries[0]?.mediaId, 88);
  assert.equal(entries[0]?.title, "Selected Anime");
  assert.equal(entries[0]?.episode, 9);
  assert.equal(entries[0]?.seasonYear, 2026);
});

test("season and year filters use the dedicated AniList season query", async () => {
  const requests: Array<{ query: string; variables: Record<string, unknown> }> = [];
  const client = clientFor({
    Page: { media: [
      { ...airing(start + 1_000).media, airingSchedule: { nodes: [{ airingAt: start + 1_000, episode: 4 }] } },
      { ...airing(start + 2_000).media, seasonYear: 2026, airingSchedule: { nodes: [{ airingAt: start + 2_000, episode: 5 }] } },
    ] },
  }, requests);

  const entries = await client.searchUpcomingAirings({ season: "winter", year: 2027, days: 1 }, now);

  assert.equal(requests.length, 1);
  assert.match(requests[0]?.query ?? "", /season:\$season,seasonYear:\$year/);
  assert.equal(requests[0]?.variables.season, "WINTER");
  assert.equal(requests[0]?.variables.year, 2027);
  assert.equal(entries.length, 1);
  assert.equal(entries[0]?.episode, 4);
});

test("airing filters reject invalid windows, seasons, years and weekdays", async () => {
  const client = clientFor({ Page: { airingSchedules: [] } }, []);

  await assert.rejects(client.searchUpcomingAirings({ days: 0 }, now), /1 and 14 days/);
  await assert.rejects(client.searchUpcomingAirings({ season: "AUTUMN" }, now), /valid AniList season/);
  await assert.rejects(client.searchUpcomingAirings({ year: 2101 }, now), /1970 and 2100/);
  await assert.rejects(client.searchUpcomingAirings({ day: "Funday" }, now), /valid UTC weekday/);
});
