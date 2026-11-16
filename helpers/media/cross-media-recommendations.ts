export type RecommendationCategory = "anime" | "manga" | "light_novel" | "book" | "movie" | "tv" | "game";

export interface CrossMediaCandidate {
  title: string;
  category: RecommendationCategory;
  provider: string;
  url: string | null;
  genres: readonly string[];
}

export interface RankedCrossMediaCandidate extends CrossMediaCandidate {
  score: number;
  sharedGenres: string[];
}

const GENRE_ALIASES: Record<string, string> = {
  "science fiction": "sci-fi",
  "sci-fi": "sci-fi",
  "sci fi": "sci-fi",
  "slice of life": "slice of life",
  psychological: "psychological",
  supernatural: "supernatural",
  historical: "historical",
  history: "historical",
  documentary: "documentary",
  animation: "animation",
  adventure: "adventure",
  fantasy: "fantasy",
  action: "action",
  comedy: "comedy",
  drama: "drama",
  horror: "horror",
  mystery: "mystery",
  romance: "romance",
  thriller: "thriller",
  crime: "crime",
  family: "family",
  sports: "sports",
  war: "war",
};

function normalizeGenreLabel(value: string): string {
  return value.normalize("NFKC").toLocaleLowerCase("en-US")
    .replace(/[^\p{L}\p{N}]+/gu, " ").trim();
}

export function normalizeGenreTokens(values: readonly string[] | null | undefined): Set<string> {
  const result = new Set<string>();
  for (const value of values ?? []) {
    const normalized = normalizeGenreLabel(String(value ?? ""));
    if (!normalized) continue;
    const padded = ` ${normalized} `;
    for (const [alias, canonical] of Object.entries(GENRE_ALIASES)) {
      if (padded.includes(` ${alias} `)) result.add(canonical);
    }
  }
  return result;
}

export function rankCrossMediaCandidates(
  seedTitle: string,
  seedCategory: RecommendationCategory,
  seedGenres: readonly string[],
  candidates: readonly CrossMediaCandidate[],
  limit = 10,
): RankedCrossMediaCandidate[] {
  const seedTokens = normalizeGenreTokens(seedGenres);
  const normalizedSeedTitle = normalizeGenreLabel(seedTitle);
  if (!seedTokens.size || !Number.isSafeInteger(limit) || limit < 1) return [];
  const best = new Map<string, RankedCrossMediaCandidate>();
  for (const candidate of candidates) {
    const title = candidate.title.trim().slice(0, 200);
    const provider = candidate.provider.trim();
    if (!title || !provider) continue;
    const keyTitle = normalizeGenreLabel(title);
    if (candidate.category === seedCategory && keyTitle === normalizedSeedTitle) continue;
    const sharedGenres = [...normalizeGenreTokens(candidate.genres)]
      .filter(token => seedTokens.has(token)).sort();
    if (!sharedGenres.length) continue;
    const key = `${candidate.category}|${keyTitle}`;
    const ranked: RankedCrossMediaCandidate = { ...candidate, title, provider, score: sharedGenres.length, sharedGenres };
    const existing = best.get(key);
    if (!existing || ranked.score > existing.score) best.set(key, ranked);
  }
  const counts = new Map<RecommendationCategory, number>();
  const result: RankedCrossMediaCandidate[] = [];
  const ordered = [...best.values()].sort((a, b) =>
    b.score - a.score || a.category.localeCompare(b.category) || a.title.localeCompare(b.title));
  for (const candidate of ordered) {
    if ((counts.get(candidate.category) ?? 0) >= 3) continue;
    counts.set(candidate.category, (counts.get(candidate.category) ?? 0) + 1);
    result.push(candidate);
    if (result.length >= limit) break;
  }
  return result;
}

export function recommendationGenreLabels(values: readonly string[]): string[] {
  const labels: Record<string, string> = {
    "sci-fi": "Science Fiction",
    "slice of life": "Slice of Life",
    psychological: "Psychological",
    supernatural: "Supernatural",
    historical: "History",
    documentary: "Documentary",
    animation: "Animation",
    adventure: "Adventure",
    fantasy: "Fantasy",
    action: "Action",
    comedy: "Comedy",
    drama: "Drama",
    horror: "Horror",
    mystery: "Mystery",
    romance: "Romance",
    thriller: "Thriller",
    crime: "Crime",
    family: "Family",
    sports: "Sports",
    war: "War",
  };
  return [...new Set(values.map(value => labels[value]).filter((value): value is string => Boolean(value)))].slice(0, 3);
}
