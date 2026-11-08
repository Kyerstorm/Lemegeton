export type TmdbCategory = "movie" | "tv";

export interface TmdbMedia {
  id: number;
  category: TmdbCategory;
  title: string;
  overview: string | null;
  sourceUrl: string;
  image: string | null;
  releaseDate: string | null;
  rating: number | null;
  genres: string[];
  status: string | null;
}

export interface TmdbWatchProviderGroup {
  type: "streaming" | "rent" | "buy" | "free" | "ads";
  label: string;
  providers: string[];
}

export interface TmdbWatchAvailability {
  region: string;
  link: string | null;
  groups: TmdbWatchProviderGroup[];
}

export interface TmdbVideo {
  name: string;
  site: "YouTube" | "Vimeo";
  key: string;
  type: string;
  official: boolean;
  url: string;
}

export interface TmdbPerson {
  id: number;
  name: string;
  sourceUrl: string;
  image: string | null;
}

export interface TmdbPersonCredit {
  id: number;
  category: TmdbCategory;
  title: string;
  releaseDate: string | null;
  role: string | null;
  sourceUrl: string;
  popularity: number;
}

export interface TmdbCollectionItem {
  id: number;
  title: string;
  releaseDate: string | null;
  sourceUrl: string;
}

export interface TmdbCollection {
  id: number;
  name: string;
  sourceUrl: string;
  image: string | null;
  items: TmdbCollectionItem[];
}

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as JsonObject
    : null;
}

function safeProviderLink(value: unknown): string | null {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password ? url.toString() : null;
  } catch {
    return null;
  }
}

export function normalizeTmdbMedia(value: unknown, category: TmdbCategory): TmdbMedia | null {
  const item = object(value);
  if (!item || typeof item.id !== "number" || !Number.isSafeInteger(item.id) || item.id < 1) return null;
  const name = item[category === "movie" ? "title" : "name"];
  if (typeof name !== "string" || !name.trim()) return null;
  const poster = typeof item.poster_path === "string" ? item.poster_path : null;
  const date = item[category === "movie" ? "release_date" : "first_air_date"];
  return {
    id: item.id,
    category,
    title: name.trim(),
    overview: typeof item.overview === "string" ? item.overview : null,
    sourceUrl: `https://www.themoviedb.org/${category}/${item.id}`,
    image: poster && poster.startsWith("/") ? `https://image.tmdb.org/t/p/w500${poster}` : null,
    releaseDate: typeof date === "string" && date ? date : null,
    rating: typeof item.vote_average === "number" && Number.isFinite(item.vote_average) ? item.vote_average : null,
    genres: [],
    status: typeof item.status === "string" ? item.status : null,
  };
}

const PROVIDER_GROUPS = [
  { key: "flatrate", type: "streaming", label: "Streaming" },
  { key: "rent", type: "rent", label: "Rent" },
  { key: "buy", type: "buy", label: "Buy" },
  { key: "free", type: "free", label: "Free" },
  { key: "ads", type: "ads", label: "Ad-supported" },
] as const;

export function normalizeTmdbWatchAvailability(value: unknown, region: string): TmdbWatchAvailability | null {
  const record = object(value);
  if (!record) return null;
  const groups = PROVIDER_GROUPS.flatMap((group): TmdbWatchProviderGroup[] => {
    const rawProviders = record[group.key];
    const values: unknown[] = Array.isArray(rawProviders) ? rawProviders : [];
    const providers = [...new Set<string>(values.flatMap((entry: unknown): string[] => {
      const name = object(entry)?.provider_name;
      return typeof name === "string" && name.trim() ? [name.trim()] : [];
    }))].slice(0, 20);
    return providers.length ? [{ type: group.type, label: group.label, providers }] : [];
  });
  return {
    region,
    link: safeProviderLink(record.link),
    groups,
  };
}

export function normalizeTmdbPeople(value: unknown): TmdbPerson[] {
  const results = object(value)?.results;
  if (!Array.isArray(results)) return [];
  return results.flatMap((entry): TmdbPerson[] => {
    const item = object(entry);
    if (!item || typeof item.id !== "number" || !Number.isSafeInteger(item.id) || item.id < 1
      || typeof item.name !== "string" || !item.name.trim()) return [];
    const profile = typeof item.profile_path === "string" && item.profile_path.startsWith("/")
      ? `https://image.tmdb.org/t/p/w500${item.profile_path}`
      : null;
    return [{
      id: item.id,
      name: item.name.trim().slice(0, 200),
      sourceUrl: `https://www.themoviedb.org/person/${item.id}`,
      image: profile,
    }];
  }).slice(0, 10);
}

export function normalizeTmdbPersonCredits(value: unknown): TmdbPersonCredit[] {
  const payload = object(value);
  if (!payload) return [];
  const credits = [
    ...(Array.isArray(payload.cast) ? payload.cast : []),
    ...(Array.isArray(payload.crew) ? payload.crew : []),
  ];
  const unique = new Map<string, TmdbPersonCredit>();
  for (const entry of credits) {
    const item = object(entry);
    if (!item || !Number.isSafeInteger(item.id) || typeof item.id !== "number" || item.id < 1) continue;
    if (item.media_type !== "movie" && item.media_type !== "tv") continue;
    const category = item.media_type;
    const rawTitle = category === "movie" ? item.title : item.name;
    if (typeof rawTitle !== "string" || !rawTitle.trim()) continue;
    const roleValue = item.character ?? item.job ?? item.department;
    const role = typeof roleValue === "string" && roleValue.trim() ? roleValue.trim().slice(0, 120) : null;
    const dateValue = category === "movie" ? item.release_date : item.first_air_date;
    const popularity = typeof item.popularity === "number" && Number.isFinite(item.popularity) ? item.popularity : 0;
    const credit: TmdbPersonCredit = {
      id: item.id,
      category,
      title: rawTitle.trim().slice(0, 200),
      releaseDate: typeof dateValue === "string" && dateValue ? dateValue : null,
      role,
      sourceUrl: `https://www.themoviedb.org/${category}/${item.id}`,
      popularity,
    };
    const key = `${category}:${item.id}`;
    const existing = unique.get(key);
    if (!existing || (!existing.role && credit.role)) unique.set(key, credit);
  }
  return [...unique.values()]
    .sort((left, right) => right.popularity - left.popularity || left.title.localeCompare(right.title))
    .slice(0, 12);
}

export function normalizeTmdbCollection(value: unknown): TmdbCollection | null {
  const item = object(value);
  if (!item || typeof item.id !== "number" || !Number.isSafeInteger(item.id) || item.id < 1
    || typeof item.name !== "string" || !item.name.trim()) return null;
  const parts = Array.isArray(item.parts) ? item.parts : [];
  const items = parts.flatMap((entry): TmdbCollectionItem[] => {
    const part = object(entry);
    if (!part || typeof part.id !== "number" || !Number.isSafeInteger(part.id) || part.id < 1
      || typeof part.title !== "string" || !part.title.trim()) return [];
    return [{
      id: part.id,
      title: part.title.trim().slice(0, 200),
      releaseDate: typeof part.release_date === "string" && part.release_date ? part.release_date : null,
      sourceUrl: `https://www.themoviedb.org/movie/${part.id}`,
    }];
  });
  items.sort((left, right) =>
    (left.releaseDate ?? "9999-99-99").localeCompare(right.releaseDate ?? "9999-99-99")
    || left.title.localeCompare(right.title),
  );
  const poster = typeof item.poster_path === "string" && item.poster_path.startsWith("/") ? item.poster_path : null;
  return {
    id: item.id,
    name: item.name.trim().slice(0, 200),
    sourceUrl: `https://www.themoviedb.org/collection/${item.id}`,
    image: poster ? `https://image.tmdb.org/t/p/w500${poster}` : null,
    items: items.slice(0, 20),
  };
}

export function normalizeTmdbVideos(value: unknown): TmdbVideo[] {
  const record = object(value);
  const results = Array.isArray(record?.results) ? record.results : [];
  const videos = new Map<string, TmdbVideo>();
  for (const entry of results) {
    const item = object(entry);
    if (!item || typeof item.key !== "string" || !item.key.trim()) continue;
    const site = item.site;
    if (site !== "YouTube" && site !== "Vimeo") continue;
    const key = item.key.trim();
    const url = site === "YouTube"
      ? `https://www.youtube.com/watch?v=${encodeURIComponent(key)}`
      : `https://vimeo.com/${encodeURIComponent(key)}`;
    const name = typeof item.name === "string" && item.name.trim() ? item.name.trim() : "Untitled video";
    const id = typeof item.id === "string" ? item.id : `${site}:${key}`;
    videos.set(id, {
      name: name.slice(0, 200),
      site,
      key,
      type: typeof item.type === "string" && item.type.trim() ? item.type.trim().slice(0, 60) : "Video",
      official: item.official === true,
      url,
    });
  }
  return [...videos.values()].slice(0, 12);
}

export class TmdbClient {
  constructor(private readonly token?: string) {}

  async search(query: string, category: TmdbCategory): Promise<TmdbMedia[]> {
    return this.searchPath(`/search/${category}`, category, { query: query.trim(), include_adult: "false" });
  }

  async trending(category: TmdbCategory): Promise<TmdbMedia[]> {
    return this.searchPath(`/trending/${category}/week`, category, {});
  }

  async upcomingMovies(region = "US"): Promise<TmdbMedia[]> {
    return this.searchPath("/movie/upcoming", "movie", { region });
  }

  async searchPeople(query: string): Promise<TmdbPerson[]> {
    if (query.trim().length < 2) return [];
    return normalizeTmdbPeople(await this.request("/search/person", {
      query: query.trim(),
      include_adult: "false",
      page: "1",
    }));
  }

  async personCredits(id: number): Promise<TmdbPersonCredit[]> {
    this.validateMediaId(id);
    return normalizeTmdbPersonCredits(await this.request(`/person/${id}/combined_credits`));
  }

  async collectionForMovie(id: number): Promise<TmdbCollection | null> {
    this.validateMediaId(id);
    const detail = await this.request(`/movie/${id}`);
    const collectionRef = object(detail.belongs_to_collection);
    const collectionId = collectionRef?.id;
    if (typeof collectionId !== "number" || !Number.isSafeInteger(collectionId) || collectionId < 1) return null;
    const collection = await this.request(`/collection/${collectionId}`);
    return normalizeTmdbCollection(collection);
  }

  async watchAvailability(id: number, category: TmdbCategory, region: string): Promise<TmdbWatchAvailability | null> {
    this.validateMediaId(id);
    const code = region.trim().toUpperCase();
    if (!/^[A-Z]{2}$/.test(code)) throw new Error("Region must be a two-letter country code.");
    const payload = await this.request(`/${category}/${id}/watch/providers`);
    const regions = object(payload.results);
    return normalizeTmdbWatchAvailability(regions?.[code], code);
  }

  async videos(id: number, category: TmdbCategory): Promise<TmdbVideo[]> {
    this.validateMediaId(id);
    return normalizeTmdbVideos(await this.request(`/${category}/${id}/videos`));
  }

  private validateMediaId(id: number): void {
    if (!Number.isSafeInteger(id) || id < 1) throw new RangeError("TMDB media ID must be a positive integer.");
  }

  private async searchPath(path: string, category: TmdbCategory, params: Record<string, string>): Promise<TmdbMedia[]> {
    const payload = await this.request(path, params);
    const results = Array.isArray(payload.results) ? payload.results : [];
    return results.flatMap((entry) => {
      const media = normalizeTmdbMedia(entry, category);
      return media ? [media] : [];
    });
  }

  private async request(path: string, params: Record<string, string> = {}): Promise<JsonObject> {
    if (!this.token) throw new Error("TMDB is not configured. Set TMDB_BEARER_TOKEN to enable film and television discovery.");
    const url = new URL(`https://api.themoviedb.org/3${path}`);
    url.searchParams.set("language", "en-US");
    for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
    const response = await fetch(url, {
      headers: { Authorization: `Bearer ${this.token}`, Accept: "application/json" },
      signal: AbortSignal.timeout(12_000),
    });
    if (!response.ok) throw new Error(`TMDB returned HTTP ${response.status}.`);
    const payload = object(await response.json());
    if (!payload) throw new Error("TMDB returned an invalid response.");
    return payload;
  }
}
