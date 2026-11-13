import test from "node:test";
import assert from "node:assert/strict";
import { upcomingProviderReleases } from "../helpers/community/community-sessions.js";
import type { AniListClient } from "../helpers/integration/anilist.js";
import type { TmdbClient } from "../helpers/integration/tmdb.js";
import {
  nextReleaseOccurrence,
  normalizeReleaseCategories,
} from "../helpers/community/community-releases.js";

test("daily release digest uses the selected timezone and next local time", () => {
  const next = nextReleaseOccurrence("Europe/Dublin", "18:30", "daily", 1, new Date("2026-11-09T17:00:00.000Z"));
  assert.equal(next.toISOString(), "2026-11-09T18:30:00.000Z");
});

test("weekly release digest advances to the selected local weekday", () => {
  const next = nextReleaseOccurrence("Europe/Dublin", "09:15", "weekly", 4, new Date("2026-11-09T10:00:00.000Z"));
  assert.equal(next.toISOString(), "2026-11-12T09:15:00.000Z");
});

test("release digest schedule rejects invalid timezones, local times and weekdays", () => {
  assert.throws(() => nextReleaseOccurrence("Mars/Olympus", "09:15", "daily", 1), /timezone/i);
  assert.throws(() => nextReleaseOccurrence("Europe/Dublin", "25:00", "daily", 1), /HH:MM/);
  assert.throws(() => nextReleaseOccurrence("Europe/Dublin", "09:15", "weekly", 7), /weekday/i);
});

test("release digest categories are deduplicated and restricted to provider-backed types", () => {
  assert.deepEqual(normalizeReleaseCategories(["anime", "tv", "anime"]), ["anime", "tv"]);
  assert.throws(() => normalizeReleaseCategories([]), /supported categories/i);
  assert.throws(() => normalizeReleaseCategories(["anime", "unknown"]), /supported categories/i);
});

test("release calendar includes date-only movie and TV releases scheduled today", async () => {
  const from = new Date("2026-11-09T18:00:00.000Z");
  const to = new Date("2026-11-11T18:00:00.000Z");
  const anilist = {
    upcomingAirings: async () => [{
      id: 1, title: "Current Anime", episode: 3, airingAt: Math.floor(new Date("2026-11-09T19:00:00.000Z").getTime() / 1000),
      url: "https://anilist.co/anime/1",
    }],
  } as unknown as AniListClient;
  const tmdb = {
    upcomingMovies: async (region: string) => [{
      id: 2, category: "movie", title: "Release Today", overview: null, sourceUrl: "https://www.themoviedb.org/movie/2",
      image: null, releaseDate: "2026-11-09", rating: null,
    }],
    upcomingTvEpisodes: async () => [{
      showId: 3, showTitle: "Returning Series",
      episode: {
        episodeNumber: 4, seasonNumber: 2, name: "Next Episode", airDate: "2026-11-10",
        runtime: 42, overview: null, sourceUrl: "https://www.themoviedb.org/tv/3/episode/4",
      },
    }],
  } as unknown as TmdbClient;
  const calendar = await upcomingProviderReleases(anilist, tmdb, from, to, "IE", ["anime", "tv", "movies"]);
  const results = calendar.results;
  assert.deepEqual(calendar.unavailableProviders, []);
  assert.deepEqual(results.map((item) => item.provider), ["TMDB Movies · IE", "AniList", "TMDB TV"]);
  assert.equal(results[0]?.title, "Release Today");
  assert.equal(results[2]?.title, "Returning Series · S2 E4 · Next Episode");
});

test("release calendar only requests selected provider categories", async () => {
  let movieCalls = 0;
  let tvCalls = 0;
  const anilist = { upcomingAirings: async () => [] } as unknown as AniListClient;
  const tmdb = {
    upcomingMovies: async () => { movieCalls += 1; return []; },
    upcomingTvEpisodes: async () => { tvCalls += 1; return []; },
  } as unknown as TmdbClient;
  const calendar = await upcomingProviderReleases(anilist, tmdb, new Date("2026-11-09T00:00:00Z"), new Date("2026-11-15T00:00:00Z"), "IE", ["anime"]);
  assert.deepEqual(calendar.unavailableProviders, []);
  assert.equal(movieCalls, 0);
  assert.equal(tvCalls, 0);
});


test("release calendar preserves successful provider results when another provider fails", async () => {
  const from = new Date("2026-11-09T00:00:00.000Z");
  const to = new Date("2026-11-15T00:00:00.000Z");
  const anilist = {
    upcomingAirings: async () => [{
      id: 1, title: "Available Anime", episode: 2,
      airingAt: Math.floor(new Date("2026-11-10T12:00:00.000Z").getTime() / 1000),
      url: "https://anilist.co/anime/1",
    }],
  } as unknown as AniListClient;
  const tmdb = {
    upcomingMovies: async () => { throw new Error("provider unavailable"); },
    upcomingTvEpisodes: async () => [{
      showId: 3, showTitle: "Available Series",
      episode: {
        episodeNumber: 4, seasonNumber: 1, name: "Next Episode", airDate: "2026-11-11",
        runtime: 42, overview: null, sourceUrl: "https://www.themoviedb.org/tv/3/episode/4",
      },
    }],
  } as unknown as TmdbClient;

  const calendar = await upcomingProviderReleases(anilist, tmdb, from, to, "IE", ["anime", "tv", "movies"]);
  assert.deepEqual(calendar.unavailableProviders, ["TMDB Movies"]);
  assert.deepEqual(calendar.results.map(item => item.provider), ["AniList", "TMDB TV"]);
});

test("release calendar reports all selected providers unavailable without inventing empty results", async () => {
  const anilist = { upcomingAirings: async () => { throw new Error("AniList down"); } } as unknown as AniListClient;
  const tmdb = {
    upcomingMovies: async () => { throw new Error("TMDB down"); },
    upcomingTvEpisodes: async () => { throw new Error("TMDB down"); },
  } as unknown as TmdbClient;
  const calendar = await upcomingProviderReleases(
    anilist, tmdb, new Date("2026-11-09T00:00:00Z"), new Date("2026-11-15T00:00:00Z"),
    "IE", ["anime", "tv", "movies"],
  );
  assert.deepEqual(calendar.results, []);
  assert.deepEqual(calendar.unavailableProviders, ["AniList", "TMDB Movies", "TMDB TV"]);
});
