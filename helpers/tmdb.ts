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

export interface TmdbTvEpisode {
  episodeNumber: number;
  seasonNumber: number | null;
  name: string;
  airDate: string | null;
  runtime: number | null;
  overview: string | null;
  sourceUrl: string;
}

export interface TmdbTvSeasonSummary {
  id: number;
  seasonNumber: number;
  name: string;
  episodeCount: number;
  airDate: string | null;
}

export interface TmdbTvShowDetails {
  id: number;
  name: string;
  overview: string | null;
  sourceUrl: string;
  image: string | null;
  status: string | null;
  numberOfSeasons: number;
  numberOfEpisodes: number;
  episodeRuntimes: number[];
  creators: string[];
  networks: string[];
  nextEpisode: TmdbTvEpisode | null;
  seasons: TmdbTvSeasonSummary[];
}

export interface TmdbTvSeason {
  showId: number;
  seasonNumber: number;
  name: string;
  sourceUrl: string;
  episodes: TmdbTvEpisode[];
}

export interface TmdbUpcomingTvEpisode {
  showId: number;
  showTitle: string;
  episode: TmdbTvEpisode;
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

function normalizeTmdbEpisode(value: unknown, showId: number): TmdbTvEpisode | null {
  const item = object(value);
  if (!item || typeof item.episode_number !== "number" || !Number.isSafeInteger(item.episode_number)
    || item.episode_number < 0) return null;
  const id = typeof item.id === "number" && Number.isSafeInteger(item.id) && item.id > 0 ? item.id : null;
  const name = typeof item.name === "string" && item.name.trim() ? item.name.trim() : `Episode ${item.episode_number}`;
  return {
    episodeNumber:item.episode_number,
    seasonNumber:typeof item.season_number === "number" && Number.isSafeInteger(item.season_number) && item.season_number >= 0 ? item.season_number : null,
    name:name.slice(0,200),
    airDate:typeof item.air_date === "string" && item.air_date ? item.air_date : null,
    runtime:typeof item.runtime === "number" && Number.isFinite(item.runtime) && item.runtime > 0 ? item.runtime : null,
    overview:typeof item.overview === "string" && item.overview.trim() ? item.overview.trim().slice(0,1_000) : null,
    sourceUrl:id ? `https://www.themoviedb.org/tv/${showId}/episode/${id}` : `https://www.themoviedb.org/tv/${showId}`,
  };
}

export function normalizeTmdbTvDetails(value: unknown): TmdbTvShowDetails | null {
  const item = object(value);
  if (!item || typeof item.id !== "number" || !Number.isSafeInteger(item.id) || item.id < 1
    || typeof item.name !== "string" || !item.name.trim()) return null;
  const poster = typeof item.poster_path === "string" && item.poster_path.startsWith("/") ? item.poster_path : null;
  const seasons = (Array.isArray(item.seasons) ? item.seasons : []).flatMap((entry): TmdbTvSeasonSummary[] => {
    const season = object(entry);
    if (!season || typeof season.season_number !== "number" || !Number.isSafeInteger(season.season_number)
      || season.season_number < 0) return [];
    const id = typeof season.id === "number" && Number.isSafeInteger(season.id) && season.id > 0
      ? season.id : 0;
    const episodeCount = typeof season.episode_count === "number" && Number.isFinite(season.episode_count)
      ? Math.max(0,Math.floor(season.episode_count)) : 0;
    return [{
      id,
      seasonNumber:season.season_number,
      name:typeof season.name === "string" && season.name.trim() ? season.name.trim().slice(0,120) : `Season ${season.season_number}`,
      episodeCount,
      airDate:typeof season.air_date === "string" && season.air_date ? season.air_date : null,
    }];
  }).sort((left,right)=>left.seasonNumber-right.seasonNumber).slice(0,25);
  const nextEpisode = normalizeTmdbEpisode(item.next_episode_to_air,item.id);
  const runtimeValues = Array.isArray(item.episode_run_time) ? item.episode_run_time : [];
  const episodeRuntimes = runtimeValues.flatMap((value):number[] =>
    typeof value === "number" && Number.isFinite(value) && value > 0 ? [Math.floor(value)] : [],
  ).slice(0,10);
  const creators = (Array.isArray(item.created_by) ? item.created_by : []).flatMap((entry):string[] => {
    const name = object(entry)?.name;
    return typeof name === "string" && name.trim() ? [name.trim().slice(0,100)] : [];
  }).slice(0,10);
  const networks = (Array.isArray(item.networks) ? item.networks : []).flatMap((entry):string[] => {
    const name = object(entry)?.name;
    return typeof name === "string" && name.trim() ? [name.trim().slice(0,100)] : [];
  }).slice(0,10);
  return {
    id:item.id,
    name:item.name.trim().slice(0,200),
    overview:typeof item.overview === "string" && item.overview.trim() ? item.overview.trim().slice(0,1_000) : null,
    sourceUrl:`https://www.themoviedb.org/tv/${item.id}`,
    image:poster ? `https://image.tmdb.org/t/p/w500${poster}` : null,
    status:typeof item.status === "string" && item.status.trim() ? item.status.trim() : null,
    numberOfSeasons:typeof item.number_of_seasons === "number" && Number.isFinite(item.number_of_seasons) ? Math.max(0,Math.floor(item.number_of_seasons)) : seasons.length,
    numberOfEpisodes:typeof item.number_of_episodes === "number" && Number.isFinite(item.number_of_episodes) ? Math.max(0,Math.floor(item.number_of_episodes)) : 0,
    episodeRuntimes,creators,networks,nextEpisode,seasons,
  };
}

export function normalizeTmdbTvSeason(value: unknown, showId: number): TmdbTvSeason | null {
  const item = object(value);
  if (!item || typeof item.season_number !== "number" || !Number.isSafeInteger(item.season_number)
    || item.season_number < 0 || !Number.isSafeInteger(showId) || showId < 1) return null;
  const rawEpisodes = Array.isArray(item.episodes) ? item.episodes : [];
  const episodes = rawEpisodes.flatMap((entry):TmdbTvEpisode[] => {
    const episode = normalizeTmdbEpisode(entry,showId);
    return episode ? [episode] : [];
  }).sort((left,right)=>left.episodeNumber-right.episodeNumber).slice(0,100);
  return {
    showId,
    seasonNumber:item.season_number,
    name:typeof item.name === "string" && item.name.trim() ? item.name.trim().slice(0,120) : `Season ${item.season_number}`,
    sourceUrl:`https://www.themoviedb.org/tv/${showId}/season/${item.season_number}`,
    episodes,
  };
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

  async upcomingTvEpisodes(from: Date, to: Date): Promise<TmdbUpcomingTvEpisode[]> {
    const shows = await this.searchPath("/tv/on_the_air", "tv", {});
    const details = await Promise.allSettled(
      shows.slice(0, 8).map((show) => this.tvDetails(show.id)),
    );
    if (details.length > 0 && details.every((result) => result.status === "rejected")) {
      throw new Error("TMDB could not load details for the currently airing TV series.");
    }
    const fromDay = from.toISOString().slice(0, 10);
    const toDay = to.toISOString().slice(0, 10);
    const releases = details.flatMap((result): TmdbUpcomingTvEpisode[] => {
      if (result.status !== "fulfilled" || !result.value?.nextEpisode) return [];
      const detail = result.value;
      const episode = detail.nextEpisode;
      if (!episode.airDate || !/^\\d{4}-\\d{2}-\\d{2}$/.test(episode.airDate)) return [];
      const when = new Date(`${episode.airDate}T00:00:00.000Z`);
      if (!Number.isFinite(when.getTime()) || episode.airDate < fromDay || episode.airDate > toDay) return [];
      return [{ showId: detail.id, showTitle: detail.name, episode }];
    });
    return releases.sort((a, b) =>
      (a.episode.airDate ?? "").localeCompare(b.episode.airDate ?? "") || a.showTitle.localeCompare(b.showTitle),
    );
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

  async tvDetails(id: number): Promise<TmdbTvShowDetails | null> {
    this.validateMediaId(id);
    return normalizeTmdbTvDetails(await this.request(`/tv/${id}`));
  }

  async tvSeason(showId: number, seasonNumber: number): Promise<TmdbTvSeason | null> {
    this.validateMediaId(showId);
    if (!Number.isSafeInteger(seasonNumber) || seasonNumber < 0 || seasonNumber > 100) {
      throw new RangeError("TMDB season number must be between 0 and 100.");
    }
    return normalizeTmdbTvSeason(await this.request(`/tv/${showId}/season/${seasonNumber}`),showId);
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
