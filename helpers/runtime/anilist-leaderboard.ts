import type { AniListUserStatistics } from "../integration/anilist.js";

export type AniListLeaderboardMode =
  | "anime"
  | "manga"
  | "combined"
  | "chapters"
  | "episodes"
  | "manga_completed"
  | "anime_completed";

export interface AniListLeaderboardProfile {
  userId: string;
  aniListName: string;
  aniListUrl: string;
  anime: AniListUserStatistics;
  manga: AniListUserStatistics;
}

export interface AniListLeaderboardEntry {
  userId: string;
  aniListName: string;
  aniListUrl: string;
  totalAnime: number;
  totalEpisodes: number;
  animeMeanScore: number;
  animeCompleted: number;
  totalManga: number;
  totalChapters: number;
  mangaMeanScore: number;
  mangaCompleted: number;
  animeAverage: number;
  mangaAverage: number;
  activityScore: number;
}

const ORIGIN_MULTIPLIERS: Record<
  "manga" | "manhwa" | "manhua" | "japaneseAnime" | "koreanAnime" | "chineseAnime",
  { chapter: number; episode: number; variety: number; efficiency: number }
> = {
  manga: { chapter: 1, episode: 0, variety: 1, efficiency: 1 },
  manhwa: { chapter: 1.1, episode: 0, variety: 1.05, efficiency: 1.1 },
  manhua: { chapter: 0.95, episode: 0, variety: 0.98, efficiency: 0.95 },
  japaneseAnime: { chapter: 0, episode: 1, variety: 1, efficiency: 1 },
  koreanAnime: { chapter: 0, episode: 1.15, variety: 1.1, efficiency: 1.15 },
  chineseAnime: { chapter: 0, episode: 1.05, variety: 1.02, efficiency: 1.05 },
};

const ANIME_FORMAT_WEIGHTS = {
  TV: { episode: 1, variety: 1, efficiency: 1 },
  ONA: { episode: 1.05, variety: 1.03, efficiency: 1.05 },
  OVA: { episode: 1.15, variety: 1.1, efficiency: 1.15 },
  TV_SHORT: { episode: 0.75, variety: 0.9, efficiency: 0.85 },
  MOVIE: { episode: 2, variety: 1.25, efficiency: 1.3 },
  SPECIAL: { episode: 1.08, variety: 1.05, efficiency: 1.08 },
} as const;

const MANGA_FORMAT_WEIGHTS = {
  MANGA: { chapter: 1, variety: 1, efficiency: 1 },
  LIGHT_NOVEL: { chapter: 1.35, variety: 1.2, efficiency: 1.25 },
  ONE_SHOT: { chapter: 1.15, variety: 1.1, efficiency: 0.9 },
  DOUJINSHI: { chapter: 0.85, variety: 0.95, efficiency: 0.8 },
  NOVEL: { chapter: 1.5, variety: 1.3, efficiency: 1.4 },
} as const;

type Distribution<K extends string> = Record<K, number>;
type MangaOrigin = "manga" | "manhwa" | "manhua";
type AnimeOrigin = "japaneseAnime" | "koreanAnime" | "chineseAnime";
type AnimeFormat = keyof typeof ANIME_FORMAT_WEIGHTS;
type MangaFormat = keyof typeof MANGA_FORMAT_WEIGHTS;

function normalize<K extends string>(values: Distribution<K>): Distribution<K> {
  const total = Object.values(values).reduce((sum, value) => sum + value, 0);
  if (total <= 0) {
    const keys = Object.keys(values) as K[];
    return Object.fromEntries(keys.map((key) => [key, 1 / keys.length])) as Distribution<K>;
  }
  return Object.fromEntries(
    Object.entries(values).map(([key, value]) => [key, Number(value) / total]),
  ) as Distribution<K>;
}

function estimateMangaOrigins(total: number, chapters: number, anime: number, episodes: number): Distribution<MangaOrigin> {
  const values: Distribution<MangaOrigin> = { manga: 0.75, manhwa: 0.2, manhua: 0.05 };
  const average = chapters / Math.max(total, 1);
  const intensityRatio = (total + chapters / 100) / Math.max(anime + episodes / 50, 1);
  if (average > 80) {
    values.manhwa = Math.min(0.45, values.manhwa * 2.2);
    values.manga = Math.max(0.5, 1 - values.manhwa - values.manhua);
    values.manhua = 1 - values.manga - values.manhwa;
  } else if (average > 40) {
    values.manhwa = Math.min(0.35, values.manhwa * 1.6);
    values.manga = Math.max(0.6, 1 - values.manhwa - values.manhua);
    values.manhua = 1 - values.manga - values.manhwa;
  }
  if (chapters > 8000) {
    values.manhua = Math.min(0.08, values.manhua * 1.6);
    values.manhwa = Math.min(0.3, values.manhwa * 1.3);
    values.manga = Math.max(0.62, 1 - values.manhwa - values.manhua);
  } else if (chapters > 5000) {
    values.manhwa = Math.min(0.25, values.manhwa * 1.2);
    values.manga = Math.max(0.7, 1 - values.manhwa - values.manhua);
  }
  if (total > 150) {
    values.manhwa = Math.min(0.3, values.manhwa * 1.4);
    values.manhua = Math.min(0.07, values.manhua * 1.4);
    values.manga = Math.max(0.63, 1 - values.manhwa - values.manhua);
  } else if (total > 80) {
    values.manhwa = Math.min(0.25, values.manhwa * 1.2);
    values.manga = Math.max(0.7, 1 - values.manhwa - values.manhua);
  }
  if (intensityRatio > 3) {
    values.manhwa = Math.min(0.35, values.manhwa * 1.3);
    values.manga = Math.max(0.6, 1 - values.manhwa - values.manhua);
  }
  return normalize(values);
}

function estimateAnimeOrigins(total: number, episodes: number, manga: number, chapters: number): Distribution<AnimeOrigin> {
  const values: Distribution<AnimeOrigin> = { japaneseAnime: 0.85, koreanAnime: 0.05, chineseAnime: 0.1 };
  const average = episodes / Math.max(total, 1);
  const intensityRatio = (manga + chapters / 100) / Math.max(total + episodes / 50, 1);
  if (average > 30) {
    values.chineseAnime = Math.min(0.18, values.chineseAnime * 1.6);
    values.japaneseAnime = Math.max(0.77, 1 - values.chineseAnime - values.koreanAnime);
  }
  if (total > 300) {
    values.chineseAnime = Math.min(0.15, values.chineseAnime * 1.4);
    values.koreanAnime = Math.min(0.08, values.koreanAnime * 1.3);
    values.japaneseAnime = Math.max(0.77, 1 - values.chineseAnime - values.koreanAnime);
  } else if (total > 150) {
    values.chineseAnime = Math.min(0.12, values.chineseAnime * 1.2);
    values.japaneseAnime = Math.max(0.83, 1 - values.chineseAnime - values.koreanAnime);
  }
  if (intensityRatio < 0.5) {
    values.chineseAnime = Math.min(0.15, values.chineseAnime * 1.3);
    values.japaneseAnime = Math.max(0.8, 1 - values.chineseAnime - values.koreanAnime);
  }
  return normalize(values);
}

function estimateAnimeFormats(total: number, episodes: number, average: number): Distribution<AnimeFormat> {
  const values: Distribution<AnimeFormat> = {
    TV: 0.65, ONA: 0.12, OVA: 0.08, TV_SHORT: 0.06, MOVIE: 0.07, SPECIAL: 0.02,
  };
  if (average > 25) {
    values.TV = Math.min(0.8, values.TV * 1.2);
    values.ONA = Math.max(0.08, values.ONA * 0.8);
    values.MOVIE = Math.max(0.05, values.MOVIE * 0.7);
  } else if (average > 15) {
    values.TV = Math.min(0.75, values.TV * 1.1);
  } else if (average < 8) {
    values.TV_SHORT = Math.min(0.12, values.TV_SHORT * 1.8);
    values.OVA = Math.min(0.15, values.OVA * 1.5);
    values.MOVIE = Math.min(0.12, values.MOVIE * 1.4);
    values.TV = Math.max(0.5, values.TV * 0.8);
  }
  if (total > 500) {
    values.ONA = Math.min(0.18, values.ONA * 1.4);
    values.OVA = Math.min(0.12, values.OVA * 1.3);
    values.SPECIAL = Math.min(0.04, values.SPECIAL * 1.5);
  } else if (total > 200) {
    values.ONA = Math.min(0.15, values.ONA * 1.2);
    values.OVA = Math.min(0.1, values.OVA * 1.1);
  }
  if (total < 100 && episodes > 1500) {
    values.MOVIE = Math.min(0.15, values.MOVIE * 1.8);
    values.TV = Math.max(0.55, values.TV * 0.9);
  }
  return normalize(values);
}

function estimateMangaFormats(total: number, chapters: number, average: number): Distribution<MangaFormat> {
  const values: Distribution<MangaFormat> = {
    MANGA: 0.75, LIGHT_NOVEL: 0.15, ONE_SHOT: 0.05, DOUJINSHI: 0.03, NOVEL: 0.02,
  };
  if (average < 5) {
    values.ONE_SHOT = Math.min(0.25, values.ONE_SHOT * 4);
    values.MANGA = Math.max(0.6, values.MANGA * 0.8);
    values.LIGHT_NOVEL = Math.max(0.1, values.LIGHT_NOVEL * 0.7);
  } else if (average < 15) {
    values.ONE_SHOT = Math.min(0.12, values.ONE_SHOT * 2);
    values.MANGA = Math.max(0.7, values.MANGA * 0.9);
  }
  if (average > 200 && total < 100) {
    values.LIGHT_NOVEL = Math.min(0.4, values.LIGHT_NOVEL * 2.5);
    values.NOVEL = Math.min(0.08, values.NOVEL * 3);
    values.MANGA = Math.max(0.45, values.MANGA * 0.6);
  } else if (average > 100) {
    values.LIGHT_NOVEL = Math.min(0.3, values.LIGHT_NOVEL * 1.8);
    values.NOVEL = Math.min(0.05, values.NOVEL * 2);
    values.MANGA = Math.max(0.6, values.MANGA * 0.8);
  } else if (average > 50) {
    values.LIGHT_NOVEL = Math.min(0.25, values.LIGHT_NOVEL * 1.4);
    values.MANGA = Math.max(0.65, values.MANGA * 0.9);
  }
  if (total > 500) {
    values.DOUJINSHI = Math.min(0.08, values.DOUJINSHI * 2);
    values.ONE_SHOT = Math.min(0.08, values.ONE_SHOT * 1.5);
    values.LIGHT_NOVEL = Math.min(0.2, values.LIGHT_NOVEL * 1.2);
  } else if (total > 200) {
    values.DOUJINSHI = Math.min(0.05, values.DOUJINSHI * 1.5);
    values.LIGHT_NOVEL = Math.min(0.18, values.LIGHT_NOVEL * 1.1);
  }
  if (chapters > 10000) {
    values.NOVEL = Math.min(0.05, values.NOVEL * 2.5);
    values.LIGHT_NOVEL = Math.min(0.2, values.LIGHT_NOVEL * 1.1);
  }
  return normalize(values);
}

function allocate<T extends string>(total: number, weights: Distribution<T>): Record<T, number> {
  const normalized = normalize(weights);
  return Object.fromEntries(
    Object.entries(normalized).map(([key, value]) => [key, Math.trunc(total * Number(value))]),
  ) as Record<T, number>;
}

function distributeByEstimatedCounts<T extends string>(total: number, counts: Record<T, number>): Record<T, number> {
  const sum = Object.values(counts).reduce((value, item) => value + item, 0);
  return Object.fromEntries(
    Object.entries(counts).map(([key, value]) => [key, Math.trunc(total * Number(value) / Math.max(sum, 1))]),
  ) as Record<T, number>;
}

export function calculateOriginWeightedActivityScore(
  totalManga: number,
  totalAnime: number,
  totalChapters: number,
  totalEpisodes: number,
): number {
  const mangaAverage = totalChapters / Math.max(totalManga, 1);
  const animeAverage = totalEpisodes / Math.max(totalAnime, 1);
  const mangaOrigins = estimateMangaOrigins(totalManga, totalChapters, totalAnime, totalEpisodes);
  const animeOrigins = estimateAnimeOrigins(totalAnime, totalEpisodes, totalManga, totalChapters);
  const mangaTitles = allocate(totalManga, mangaOrigins);
  const mangaUnits = allocate(totalChapters, mangaOrigins);
  const animeTitles = allocate(totalAnime, animeOrigins);
  const animeUnits = allocate(totalEpisodes, animeOrigins);

  // The Python model estimates format counts and unit counts independently from the same average.
  const mangaFormatTitles = allocate(totalManga, estimateMangaFormats(totalManga, 0, mangaAverage));
  const mangaFormatUnits = allocate(totalChapters, estimateMangaFormats(0, totalChapters, mangaAverage));
  const animeFormatTitles = allocate(totalAnime, estimateAnimeFormats(totalAnime, 0, animeAverage));
  const animeFormatUnits = allocate(totalEpisodes, estimateAnimeFormats(0, totalEpisodes, animeAverage));
  let score = 0;

  for (const origin of Object.keys(mangaOrigins) as MangaOrigin[]) {
    const originWeight = ORIGIN_MULTIPLIERS[origin];
    const originTitleCounts = distributeByEstimatedCounts(mangaTitles[origin], mangaFormatTitles);
    const originUnitCounts = distributeByEstimatedCounts(mangaUnits[origin], mangaFormatUnits);
    for (const format of Object.keys(mangaFormatTitles) as MangaFormat[]) {
      const formatWeight = MANGA_FORMAT_WEIGHTS[format];
      const titleCount = originTitleCounts[format];
      const unitCount = originUnitCounts[format];
      if (unitCount > 0) {
        score += unitCount * 2.5 * originWeight.chapter * formatWeight.chapter;
        score += titleCount * 25 * originWeight.variety * formatWeight.variety;
        if (titleCount > 0) {
          score += Math.min((unitCount / titleCount) * 5, 500) * originWeight.efficiency * formatWeight.efficiency;
        }
      }
    }
  }

  for (const origin of Object.keys(animeOrigins) as AnimeOrigin[]) {
    const originWeight = ORIGIN_MULTIPLIERS[origin];
    const originTitleCounts = distributeByEstimatedCounts(animeTitles[origin], animeFormatTitles);
    const originUnitCounts = distributeByEstimatedCounts(animeUnits[origin], animeFormatUnits);
    for (const format of Object.keys(animeFormatTitles) as AnimeFormat[]) {
      const formatWeight = ANIME_FORMAT_WEIGHTS[format];
      const titleCount = originTitleCounts[format];
      const unitCount = originUnitCounts[format];
      if (unitCount > 0) {
        score += unitCount * 1.8 * originWeight.episode * formatWeight.episode;
        score += titleCount * 20 * originWeight.variety * formatWeight.variety;
        if (titleCount > 0) {
          score += Math.min((unitCount / titleCount) * 8, 400) * originWeight.efficiency * formatWeight.efficiency;
        }
      }
    }
  }
  return score;
}

function completedCount(stats: AniListUserStatistics): number {
  return stats.statuses.find((item) => item.status.toUpperCase() === "COMPLETED")?.count ?? 0;
}

export function buildAniListLeaderboardEntry(profile: AniListLeaderboardProfile): AniListLeaderboardEntry {
  const totalAnime = profile.anime.count;
  const totalManga = profile.manga.count;
  const totalEpisodes = profile.anime.episodesWatched ?? 0;
  const totalChapters = profile.manga.chaptersRead ?? 0;
  return {
    userId: profile.userId,
    aniListName: profile.aniListName,
    aniListUrl: profile.aniListUrl,
    totalAnime,
    totalEpisodes,
    animeMeanScore: profile.anime.meanScore,
    animeCompleted: completedCount(profile.anime),
    totalManga,
    totalChapters,
    mangaMeanScore: profile.manga.meanScore,
    mangaCompleted: completedCount(profile.manga),
    animeAverage: totalAnime > 0 ? totalEpisodes / totalAnime : 0,
    mangaAverage: totalManga > 0 ? totalChapters / totalManga : 0,
    activityScore: calculateOriginWeightedActivityScore(totalManga, totalAnime, totalChapters, totalEpisodes),
  };
}

export function sortAniListLeaderboardEntries(
  entries: AniListLeaderboardEntry[],
  mode: AniListLeaderboardMode,
): AniListLeaderboardEntry[] {
  const metric = (entry: AniListLeaderboardEntry): number => {
    switch (mode) {
      case "anime": return entry.animeAverage;
      case "manga": return entry.mangaAverage;
      case "chapters": return entry.totalChapters;
      case "episodes": return entry.totalEpisodes;
      case "manga_completed": return entry.mangaCompleted;
      case "anime_completed": return entry.animeCompleted;
      case "combined": return entry.activityScore;
    }
  };
  const score = (entry: AniListLeaderboardEntry): number =>
    mode === "manga" || mode === "manga_completed" ? entry.mangaMeanScore : entry.animeMeanScore;
  return [...entries].sort((left, right) =>
    metric(right) - metric(left) || score(right) - score(left) || left.aniListName.localeCompare(right.aniListName),
  );
}
