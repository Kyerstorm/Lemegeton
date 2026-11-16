import { fetchProviderResponse } from "./provider-http.js";

export interface IgdbGame {
  id: number;
  title: string;
  summary: string | null;
  sourceUrl: string;
  image: string | null;
  releaseDate: string | null;
  genres: string[];
  platforms: string[];
  developers: string[];
  publishers: string[];
  rating: number | null;
  ratingCount: number;
  aggregatedRating: number | null;
  aggregatedRatingCount: number;
}

export type IgdbCompanyRole = "Developer" | "Publisher" | "Porting" | "Supporting";

export interface IgdbCompany {
  id: number;
  name: string;
  description: string | null;
  sourceUrl: string;
  logo: string | null;
  websites: string[];
}

export interface IgdbPlatformRelease {
  date: string;
  humanDate: string | null;
  platform: string | null;
  region: string | null;
}

export interface IgdbCompanyCredit {
  gameId: number;
  title: string;
  sourceUrl: string;
  releaseDate: string | null;
  image: string | null;
  roles: IgdbCompanyRole[];
  platforms: string[];
  releases: IgdbPlatformRelease[];
  rating: number | null;
  ratingCount: number;
  aggregatedRating: number | null;
  aggregatedRatingCount: number;
}

export interface IgdbCompanyExplorer {
  company: IgdbCompany;
  credits: IgdbCompanyCredit[];
  truncated: boolean;
}

export interface IgdbUpcomingRelease {
  gameId: number;
  title: string;
  when: Date;
  sourceUrl: string;
  region: string | null;
  platform: string | null;
  image: string | null;
}

export function parseIgdbUpcomingRelease(value: unknown): IgdbUpcomingRelease | null {
  const row = object(value);
  const game = object(row?.game);
  if (!row || !game || !Number.isSafeInteger(game.id) || typeof game.id !== "number"
    || game.id < 1 || typeof game.name !== "string" || !game.name.trim()
    || !Number.isSafeInteger(row.date) || typeof row.date !== "number" || row.date <= 0) return null;
  const when = new Date(row.date * 1000);
  if (!Number.isFinite(when.getTime())) return null;
  const region = object(row.region);
  const platform = object(row.platform);
  const cover = object(game.cover);
  const slug = typeof game.slug === "string" ? game.slug : null;
  return {
    gameId: game.id,
    title: game.name.trim().slice(0, 200),
    when,
    sourceUrl: sourceUrl("games", slug, game.name),
    region: typeof region?.name === "string" ? region.name.slice(0, 80) : null,
    platform: typeof platform?.name === "string" ? platform.name.slice(0, 100) : null,
    image: igdbImageUrl(cover?.url),
  };
}

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as JsonObject
    : null;
}

function safeHttpsUrl(value: unknown): string | null {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const url = new URL(value.trim());
    return url.protocol === "https:" && !url.username && !url.password ? url.toString() : null;
  } catch {
    return null;
  }
}

function igdbImageUrl(value: unknown): string | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const raw = value.startsWith("//") ? "https:" + value : value;
  try {
    const url = new URL(raw);
    return url.protocol === "https:" && url.hostname === "images.igdb.com" && !url.username && !url.password
      ? url.toString()
      : null;
  } catch {
    return null;
  }
}

function sourceUrl(kind: "games" | "companies", slug: unknown, title: string): string {
  if (typeof slug === "string" && /^[A-Za-z0-9-]{1,160}$/.test(slug)) {
    return "https://www.igdb.com/" + kind + "/" + slug;
  }
  return "https://www.igdb.com/search?type=" + (kind === "games" ? "1" : "companies")
    + "&q=" + encodeURIComponent(title);
}

function score(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100
    ? Math.round(value * 10) / 10
    : null;
}

function count(value: unknown): number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : 0;
}

function platformReleases(value: unknown): IgdbPlatformRelease[] {
  const rows = Array.isArray(value) ? value : [];
  const unique = new Map<string, IgdbPlatformRelease>();
  for (const raw of rows) {
    const item = object(raw);
    if (typeof item?.date !== "number" || !Number.isSafeInteger(item.date) || item.date <= 0) continue;
    const date = new Date(item.date * 1000);
    if (!Number.isFinite(date.getTime())) continue;
    const platform = object(item.platform);
    const region = object(item.region);
    const record = {
      date: date.toISOString().slice(0, 10),
      humanDate: typeof item.human === "string" && item.human.trim() ? item.human.trim().slice(0, 80) : null,
      platform: typeof platform?.name === "string" ? platform.name.slice(0, 100) : null,
      region: typeof region?.name === "string" ? region.name.slice(0, 80) : null,
    };
    unique.set([record.date, record.platform, record.region].join("|"), record);
  }
  return [...unique.values()].sort((a, b) => a.date.localeCompare(b.date)).slice(0, 30);
}

export function parseIgdbGame(value: unknown): IgdbGame | null {
  const game = object(value);
  if (!game || typeof game.id !== "number" || !Number.isSafeInteger(game.id) || game.id < 1
    || typeof game.name !== "string" || !game.name.trim()) return null;

  const cover = object(game.cover);
  const companies = (Array.isArray(game.involved_companies) ? game.involved_companies : [])
    .flatMap((raw) => {
      const involved = object(raw);
      const company = object(involved?.company);
      return company && typeof company.name === "string"
        ? [{ name: company.name, developer: involved?.developer === true, publisher: involved?.publisher === true }]
        : [];
    });
  const names = (input: unknown): string[] => Array.isArray(input)
    ? input.flatMap((entry) => {
      const item = object(entry);
      return typeof item?.name === "string" ? [item.name] : [];
    })
    : [];
  const releaseDate = typeof game.first_release_date === "number" && Number.isFinite(game.first_release_date)
    ? new Date(game.first_release_date * 1000).toISOString().slice(0, 10)
    : null;

  return {
    id: game.id,
    title: game.name.trim().slice(0, 200),
    summary: typeof game.summary === "string" ? game.summary : null,
    sourceUrl: sourceUrl("games", game.slug, game.name),
    image: igdbImageUrl(cover?.url),
    releaseDate,
    genres: names(game.genres),
    platforms: names(game.platforms),
    developers: companies.filter((item) => item.developer).map((item) => item.name),
    publishers: companies.filter((item) => item.publisher).map((item) => item.name),
    rating: score(game.rating),
    ratingCount: count(game.rating_count),
    aggregatedRating: score(game.aggregated_rating),
    aggregatedRatingCount: count(game.aggregated_rating_count),
  };
}

export function parseIgdbCompany(value: unknown): IgdbCompany | null {
  const row = object(value);
  if (!row || typeof row.id !== "number" || !Number.isSafeInteger(row.id) || row.id < 1
    || typeof row.name !== "string" || !row.name.trim()) return null;
  const logo = object(row.logo);
  const websites = Array.isArray(row.websites)
    ? row.websites.flatMap((raw) => {
      const website = object(raw);
      const url = safeHttpsUrl(website?.url);
      return url ? [url] : [];
    }).slice(0, 5)
    : [];
  return {
    id: row.id,
    name: row.name.trim().slice(0, 180),
    description: typeof row.description === "string" && row.description.trim()
      ? row.description.trim().slice(0, 1_200)
      : null,
    sourceUrl: sourceUrl("companies", row.slug, row.name),
    logo: igdbImageUrl(logo?.url),
    websites,
  };
}

export function parseIgdbCompanyCredits(value: unknown): IgdbCompanyCredit[] {
  const rows = Array.isArray(value) ? value : [];
  const credits = new Map<number, IgdbCompanyCredit>();
  for (const raw of rows) {
    const row = object(raw);
    const game = object(row?.game);
    if (!game || typeof game.id !== "number" || !Number.isSafeInteger(game.id) || game.id < 1
      || typeof game.name !== "string" || !game.name.trim()) continue;
    const roles: IgdbCompanyRole[] = [];
    if (row?.developer === true) roles.push("Developer");
    if (row?.publisher === true) roles.push("Publisher");
    if (row?.porting === true) roles.push("Porting");
    if (row?.supporting === true) roles.push("Supporting");
    if (!roles.length) continue;

    const existing = credits.get(game.id);
    if (existing) {
      existing.roles = [...new Set([...existing.roles, ...roles])];
      existing.platforms = [...new Set([...existing.platforms, ...(Array.isArray(game.platforms)
        ? game.platforms.flatMap((raw): string[] => {
          const name = object(raw)?.name;
          return typeof name === "string" && name.trim() ? [name.trim().slice(0, 100)] : [];
        }) : [])])].slice(0, 20);
      existing.releases = platformReleases([...existing.releases.map(item => ({
        date: Math.floor(new Date(item.date + "T00:00:00Z").getTime() / 1000),
        human: item.humanDate,
        platform: item.platform ? { name: item.platform } : null,
        region: item.region ? { name: item.region } : null,
      })), ...(Array.isArray(game.release_dates) ? game.release_dates : [])]);
      continue;
    }
    const cover = object(game.cover);
    const releaseDate = typeof game.first_release_date === "number" && Number.isFinite(game.first_release_date)
      ? new Date(game.first_release_date * 1000).toISOString().slice(0, 10)
      : null;
    credits.set(game.id, {
      gameId: game.id,
      title: game.name.trim().slice(0, 180),
      sourceUrl: sourceUrl("games", game.slug, game.name),
      releaseDate,
      image: igdbImageUrl(cover?.url),
      roles,
      platforms: [...new Set((Array.isArray(game.platforms) ? game.platforms : []).flatMap((raw): string[] => {
        const name = object(raw)?.name;
        return typeof name === "string" && name.trim() ? [name.trim().slice(0, 100)] : [];
      }))].slice(0, 20),
      releases: platformReleases(game.release_dates),
      rating: score(game.rating),
      ratingCount: count(game.rating_count),
      aggregatedRating: score(game.aggregated_rating),
      aggregatedRatingCount: count(game.aggregated_rating_count),
    });
  }
  return [...credits.values()];
}

export class IgdbClient {
  private token: string | null = null;
  private expires = 0;
  private tokenRequest: Promise<string> | null = null;
  private requestQueue: Promise<void> = Promise.resolve();
  private lastRequestAt = 0;

  constructor(
    private readonly clientId?: string,
    private readonly secret?: string,
    private readonly fetcher: typeof fetch = globalThis.fetch,
  ) {}

  async search(query: string): Promise<IgdbGame[]> {
    const clean = query.replace(/[";\\]/g, " ").replace(/\s+/g, " ").trim().slice(0, 100);
    if (clean.length < 2) return [];
    const rows = await this.request("games",
      'search "' + clean + '"; fields id,name,slug,summary,first_release_date,rating,rating_count,aggregated_rating,aggregated_rating_count,cover.url,genres.name,platforms.name,involved_companies.developer,involved_companies.publisher,involved_companies.company.name; limit 10;'
    );
    return (Array.isArray(rows) ? rows : []).flatMap((raw) => {
      const game = parseIgdbGame(raw);
      return game ? [game] : [];
    });
  }

  async searchCompanies(query: string): Promise<IgdbCompany[]> {
    const clean = query.replace(/[";\\]/g, " ").replace(/\s+/g, " ").trim().slice(0, 100);
    if (clean.length < 2) return [];
    const rows = await this.request("companies",
      'search "' + clean + '"; fields id,name,slug,description,country,logo.url,websites.url; limit 10;'
    );
    return (Array.isArray(rows) ? rows : []).flatMap((raw) => {
      const company = parseIgdbCompany(raw);
      return company ? [company] : [];
    });
  }

  async getCompanyExplorer(companyId: number): Promise<IgdbCompanyExplorer | null> {
    if (!Number.isSafeInteger(companyId) || companyId < 1) {
      throw new RangeError("IGDB company ID must be a positive safe integer.");
    }
    const companyRows = await this.request("companies",
      "where id = " + companyId + "; fields id,name,slug,description,country,logo.url,websites.url; limit 1;"
    );
    const company = Array.isArray(companyRows) ? parseIgdbCompany(companyRows[0]) : null;
    if (!company) return null;
    const creditRows = await this.request("involved_companies",
      "where company = " + companyId + "; fields developer,publisher,porting,supporting,game.id,game.name,game.slug,game.first_release_date,game.rating,game.rating_count,game.aggregated_rating,game.aggregated_rating_count,game.platforms.name,game.release_dates.date,game.release_dates.human,game.release_dates.region.name,game.release_dates.platform.name,game.cover.url; limit 21;"
    );
    const rawCredits = Array.isArray(creditRows) ? creditRows : [];
    return {
      company,
      credits: parseIgdbCompanyCredits(rawCredits.slice(0, 20)),
      truncated: rawCredits.length > 20,
    };
  }

  async upcomingReleaseDates(from: Date, to: Date): Promise<IgdbUpcomingRelease[]> {
    if (!Number.isFinite(from.getTime()) || !Number.isFinite(to.getTime()) || from.getTime() > to.getTime()) {
      throw new Error("IGDB release window must contain valid dates in ascending order.");
    }
    const start = Math.floor(from.getTime() / 1000);
    const end = Math.floor(to.getTime() / 1000);
    const rows = await this.request("release_dates",
      "fields date,region.name,platform.name,game.id,game.name,game.slug,game.cover.url; " +
      "where date >= " + start + " & date <= " + end + " & game != null; " +
      "sort date asc; limit 100;"
    );
    return (Array.isArray(rows) ? rows : []).flatMap(row => {
      const release = parseIgdbUpcomingRelease(row);
      return release && release.when >= from && release.when <= to ? [release] : [];
    }).slice(0, 50);
  }

  async similarGames(gameId: number): Promise<IgdbGame[]> {
    if (!Number.isSafeInteger(gameId) || gameId < 1) {
      throw new RangeError("IGDB game ID must be a positive safe integer.");
    }
    const baseRows = await this.request("games",
      "fields similar_games; where id = " + gameId + "; limit 1;"
    );
    const baseGame = Array.isArray(baseRows) ? object(baseRows[0]) : null;
    const ids = Array.isArray(baseGame?.similar_games)
      ? baseGame.similar_games.filter((id): id is number => typeof id === "number"
        && Number.isSafeInteger(id) && id > 0).slice(0, 10)
      : [];
    if (!ids.length) return [];
    const rows = await this.request("games",
      "where id = (" + ids.join(",") + "); fields id,name,slug,summary,first_release_date,rating,rating_count,aggregated_rating,aggregated_rating_count,cover.url,genres.name,platforms.name,involved_companies.developer,involved_companies.publisher,involved_companies.company.name; limit 10;"
    );
    return (Array.isArray(rows) ? rows : []).flatMap((raw) => {
      const game = parseIgdbGame(raw);
      return game ? [game] : [];
    });
  }

  private async request(endpoint: "games" | "companies" | "involved_companies" | "release_dates", body: string): Promise<unknown> {
    if (!this.clientId || !this.secret) {
      throw new Error("IGDB is not configured. Set IGDB_CLIENT_ID and IGDB_CLIENT_SECRET.");
    }
    const token = await this.getToken();
    const previous = this.requestQueue;
    let release!: () => void;
    this.requestQueue = new Promise<void>((resolve) => { release = resolve; });
    await previous;
    try {
      const wait = Math.max(0, 250 - (Date.now() - this.lastRequestAt));
      if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));
      this.lastRequestAt = Date.now();
      const response = await fetchProviderResponse(this.fetcher,
        "https://api.igdb.com/v4/" + endpoint,
        {
          method: "POST",
          headers: { "Client-ID": this.clientId, Authorization: "Bearer " + token, "Content-Type": "text/plain" },
          body,
          signal: AbortSignal.timeout(12_000),
        },
        { retryPost: true },
      );
      if (!response.ok) throw new Error("IGDB returned HTTP " + response.status + ".");
      return await response.json();
    } finally {
      release();
    }
  }

  private async getToken(): Promise<string> {
    if (this.token && Date.now() < this.expires) return this.token;
    if (this.tokenRequest) return this.tokenRequest;
    if (!this.clientId || !this.secret) {
      throw new Error("IGDB is not configured. Set IGDB_CLIENT_ID and IGDB_CLIENT_SECRET.");
    }
    this.tokenRequest = (async () => {
      const url = new URL("https://id.twitch.tv/oauth2/token");
      url.searchParams.set("client_id", this.clientId!);
      url.searchParams.set("client_secret", this.secret!);
      url.searchParams.set("grant_type", "client_credentials");
      const response = await this.fetcher(url, { method: "POST", signal: AbortSignal.timeout(10_000) });
      if (!response.ok) throw new Error("IGDB authentication returned HTTP " + response.status + ".");
      const payload = object(await response.json());
      if (typeof payload?.access_token !== "string" || typeof payload.expires_in !== "number") {
        throw new Error("IGDB authentication response was invalid.");
      }
      const token = payload.access_token;
      this.token = token;
      this.expires = Date.now() + Math.max(60, payload.expires_in - 120) * 1000;
      return token;
    })();
    try {
      return await this.tokenRequest;
    } finally {
      this.tokenRequest = null;
    }
  }
}
