export type RecommendationCategory = "anime" | "manga" | "light_novel" | "book" | "movie" | "tv" | "game";

export interface CrossMediaLabels {
  genres?: readonly string[];
  tags?: readonly string[];
  subjects?: readonly string[];
  categories?: readonly string[];
}

export interface CrossMediaCandidate {
  title: string;
  category: RecommendationCategory;
  provider: string;
  url: string | null;
  genres: readonly string[];
  tags?: readonly string[];
  subjects?: readonly string[];
  categories?: readonly string[];
}

export interface SharedCrossMediaLabelGroup {
  kind: "genres" | "tags" | "subjects" | "categories";
  values: string[];
}

export interface RankedCrossMediaCandidate extends CrossMediaCandidate {
  score: number;
  sharedGenres: string[];
  sharedTags: string[];
  sharedSubjects: string[];
  sharedCategories: string[];
  sharedLabels: string[];
  sharedLabelGroups: SharedCrossMediaLabelGroup[];
}

const GENERIC_LABELS = new Set([
  "fiction", "nonfiction", "non fiction", "literature", "book", "books",
  "novel", "novels", "manga", "manhwa", "manhua", "comics", "graphic novel",
  "media", "other", "miscellaneous",
]);

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
    let recognized = false;
    for (const [alias, canonical] of Object.entries(GENRE_ALIASES)) {
      if (padded.includes(` ${alias} `)) {
        result.add(canonical);
        recognized = true;
      }
    }
    if (!recognized && !GENERIC_LABELS.has(normalized) && normalized.length <= 80) result.add(normalized);
  }
  return result;
}

function sharedTokens(seed: readonly string[], candidate: readonly string[]): string[] {
  const seedTokens = normalizeGenreTokens(seed);
  return [...normalizeGenreTokens(candidate)].filter(value => seedTokens.has(value)).sort();
}

function matchingLabels(seedTokens: Set<string>, candidateValues: readonly string[]): string[] {
  return candidateValues.filter(value =>
    [...normalizeGenreTokens([value])].some(token => seedTokens.has(token)));
}

function allLabels(value: CrossMediaLabels): string[] {
  return [
    ...(value.genres ?? []),
    ...(value.tags ?? []),
    ...(value.subjects ?? []),
    ...(value.categories ?? []),
  ];
}

export function rankCrossMediaCandidates(
  seedTitle: string,
  seedCategory: RecommendationCategory,
  seedMetadata: readonly string[] | CrossMediaLabels,
  candidates: readonly CrossMediaCandidate[],
  limit = 10,
): RankedCrossMediaCandidate[] {
  const seedLabels: CrossMediaLabels = Array.isArray(seedMetadata)
    ? { genres: seedMetadata }
    : seedMetadata as CrossMediaLabels;
  const seedGenres = seedLabels.genres ?? [];
  const seedTags = seedLabels.tags ?? [];
  const seedSubjects = seedLabels.subjects ?? [];
  const seedCategories = seedLabels.categories ?? [];
  const seedTokens = normalizeGenreTokens(allLabels(seedLabels));
  const normalizedSeedTitle = normalizeGenreLabel(seedTitle);
  if (!seedTokens.size || !Number.isSafeInteger(limit) || limit < 1) return [];
  const best = new Map<string, RankedCrossMediaCandidate>();
  for (const candidate of candidates) {
    const title = candidate.title.trim().slice(0, 200);
    const provider = candidate.provider.trim();
    if (!title || !provider) continue;
    const keyTitle = normalizeGenreLabel(title);
    if (candidate.category === seedCategory && keyTitle === normalizedSeedTitle) continue;
    const candidateTokens = normalizeGenreTokens(allLabels(candidate));
    const matched = [...candidateTokens].filter(value => seedTokens.has(value)).sort();
    if (!matched.length) continue;
    const sharedLabelGroups: SharedCrossMediaLabelGroup[] = [
      { kind: "genres", values: matchingLabels(seedTokens, candidate.genres) },
      { kind: "tags", values: matchingLabels(seedTokens, candidate.tags ?? []) },
      { kind: "subjects", values: matchingLabels(seedTokens, candidate.subjects ?? []) },
      { kind: "categories", values: matchingLabels(seedTokens, candidate.categories ?? []) },
    ].filter((group): group is SharedCrossMediaLabelGroup => group.values.length > 0);
    const ranked: RankedCrossMediaCandidate = {
      ...candidate,
      title,
      provider,
      score: matched.length,
      sharedGenres: sharedTokens(seedGenres, candidate.genres),
      sharedTags: sharedTokens(seedTags, candidate.tags ?? []),
      sharedSubjects: sharedTokens(seedSubjects, candidate.subjects ?? []),
      sharedCategories: sharedTokens(seedCategories, candidate.categories ?? []),
      sharedLabels: matched,
      sharedLabelGroups,
    };
    const key = `${candidate.category}|${keyTitle}`;
    const existing = best.get(key);
    if (!existing || ranked.score > existing.score) best.set(key, ranked);
  }
  const counts = new Map<RecommendationCategory, number>();
  const result: RankedCrossMediaCandidate[] = [];
  const ordered = [...best.values()].sort((left, right) =>
    right.score - left.score || left.category.localeCompare(right.category) || left.title.localeCompare(right.title));
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
  return [...new Set([...normalizeGenreTokens(values)].map(value => labels[value]).filter((value): value is string => Boolean(value)))].slice(0, 3);
}
