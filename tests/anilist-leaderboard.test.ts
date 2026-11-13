import test from "node:test";
import assert from "node:assert/strict";
import {
  buildAniListLeaderboardEntry,
  calculateOriginWeightedActivityScore,
  sortAniListLeaderboardEntries,
  type AniListLeaderboardEntry,
  type AniListLeaderboardProfile,
} from "../helpers/runtime/anilist-leaderboard.js";
import type { AniListUserStatistics } from "../helpers/integration/anilist.js";

function stats(overrides: Partial<AniListUserStatistics> = {}): AniListUserStatistics {
  return {
    count: 0,
    meanScore: 0,
    episodesWatched: 0,
    minutesWatched: null,
    chaptersRead: 0,
    volumesRead: null,
    genres: [],
    statuses: [],
    formats: [],
    ...overrides,
  };
}

function profile(
  userId: string,
  anime: Partial<AniListUserStatistics> = {},
  manga: Partial<AniListUserStatistics> = {},
): AniListLeaderboardProfile {
  return {
    userId,
    aniListName: userId,
    aniListUrl: `https://anilist.co/user/${userId}`,
    anime: stats(anime),
    manga: stats(manga),
  };
}

function entry(
  userId: string,
  anime: Partial<AniListUserStatistics> = {},
  manga: Partial<AniListUserStatistics> = {},
): AniListLeaderboardEntry {
  return buildAniListLeaderboardEntry(profile(userId, anime, manga));
}

test("AniList leaderboard maps provider totals, averages, and completed statuses", () => {
  const result = buildAniListLeaderboardEntry(profile(
    "reader",
    { count: 12, episodesWatched: 240, meanScore: 81, statuses: [{ status: "COMPLETED", count: 8 }] },
    { count: 6, chaptersRead: 360, meanScore: 75, statuses: [{ status: "completed", count: 4 }] },
  ));
  assert.equal(result.animeAverage, 20);
  assert.equal(result.mangaAverage, 60);
  assert.equal(result.animeCompleted, 8);
  assert.equal(result.mangaCompleted, 4);
  assert.equal(result.totalEpisodes, 240);
  assert.equal(result.totalChapters, 360);
  assert.ok(result.activityScore > 0);
});

test("missing AniList episode and chapter totals safely become zero", () => {
  const result = buildAniListLeaderboardEntry(profile(
    "empty",
    { count: 5, episodesWatched: null },
    { count: 2, chaptersRead: null },
  ));
  assert.equal(result.animeAverage, 0);
  assert.equal(result.mangaAverage, 0);
  assert.equal(result.totalEpisodes, 0);
  assert.equal(result.totalChapters, 0);
  assert.equal(result.animeCompleted, 0);
  assert.equal(result.mangaCompleted, 0);
  assert.equal(result.activityScore, 0);
});

test("all seven leaderboard modes sort by their documented measure", () => {
  const low = entry("low", { count: 10, episodesWatched: 100, statuses: [{ status: "COMPLETED", count: 2 }] },
    { count: 10, chaptersRead: 100, statuses: [{ status: "COMPLETED", count: 1 }] });
  const high = entry("high", { count: 5, episodesWatched: 200, statuses: [{ status: "COMPLETED", count: 5 }] },
    { count: 5, chaptersRead: 250, statuses: [{ status: "COMPLETED", count: 4 }] });
  const modes = ["anime", "manga", "combined", "chapters", "episodes", "manga_completed", "anime_completed"] as const;
  for (const mode of modes) {
    assert.equal(sortAniListLeaderboardEntries([low, high], mode)[0]?.userId, "high", mode);
  }
});

test("Golden Ratio rankings use per-entry averages, then mean score as a tie-breaker", () => {
  const lowerScore = entry("alpha", { count: 10, episodesWatched: 200, meanScore: 70 });
  const higherScore = entry("beta", { count: 5, episodesWatched: 100, meanScore: 90 });
  assert.deepEqual(
    sortAniListLeaderboardEntries([lowerScore, higherScore], "anime").map((item) => item.userId),
    ["beta", "alpha"],
  );
});

test("legacy weighted activity score is deterministic, finite, and zero for empty profiles", () => {
  assert.equal(calculateOriginWeightedActivityScore(0, 0, 0, 0), 0);
  const first = calculateOriginWeightedActivityScore(120, 80, 6_400, 1_600);
  const second = calculateOriginWeightedActivityScore(120, 80, 6_400, 1_600);
  assert.ok(Number.isFinite(first));
  assert.ok(first > 0);
  assert.equal(first, second);
});
