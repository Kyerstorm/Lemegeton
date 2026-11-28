import type { BotConfig } from "../runtime/config.js";
import {
  fetchJson,
  fetchXml,
} from "./web-scraper.js";
import { MEDIA_SOURCES, getMediaSource } from "../media/media-source-registry.js";
import { MediaWikiClient, MEDIA_WIKI_SOURCE_IDS } from "./mediawiki.js";
import { getMusicRuntime } from "./music.js";
import { GoogleBooksClient } from "./google-books.js";

export type MediaSourceSearchCategory = "anime" | "manga" | "screen" | "book" | "music" | "community";

export interface MediaSourceSearchRecord {
  sourceId: string;
  sourceName: string;
  providerId: string;
  title: string;
  url: string;
  category: MediaSourceSearchCategory | "chronology" | "organization";
  summary: string | null;
  date: string | null;
  attribution: string | null;
  ageRating: string | null;
  organizationType?: string;
}

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as JsonObject
    : null;
}

function text(value: unknown, maximum = 1_000): string | null {
  if (typeof value !== "string" || !value.trim()) return null;
  return value.replace(/<[^>]*>/g, " ").replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&").replace(/&quot;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'").replace(/\s+/g, " ").trim().slice(0, maximum);
}

function safeProviderUrl(value: unknown, hosts: string[]): string | null {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    return url.protocol === "https:" && !url.username && !url.password
      && hosts.some(allowed => host === allowed || host.endsWith("." + allowed))
      ? url.toString()
      : null;
  } catch {
    return null;
  }
}

function queryText(value: string): string {
  const clean = value.trim().replace(/\s+/g, " ").slice(0, 100);
  if (clean.length < 2) throw new Error("Search requires at least two characters.");
  return clean;
}

function record(
  sourceId: string,
  providerId: string,
  title: string,
  url: string | null,
  category: MediaSourceSearchRecord["category"],
  values: { summary?: string | null; date?: string | null; attribution?: string | null; ageRating?: string | null; organizationType?: string } = {},
): MediaSourceSearchRecord | null {
  const source = getMediaSource(sourceId);
  if (!source || !title.trim() || !url) return null;
  return {
    sourceId,
    sourceName: source.name,
    providerId: providerId.slice(0, 120),
    title: title.trim().slice(0, 240),
    url,
    category,
    summary: text(values.summary, 1_000),
    date: text(values.date, 40),
    attribution: text(values.attribution, 180),
    ageRating: text(values.ageRating, 40),
    ...(values.organizationType ? { organizationType: values.organizationType } : {}),
  };
}

export function parseMalResults(payload: unknown, category: "anime" | "manga"): MediaSourceSearchRecord[] {
  const rows = object(payload)?.data;
  if (!Array.isArray(rows)) return [];
  return rows.flatMap(entry => {
    const item = object(object(entry)?.node);
    const id = item?.id;
    const title = text(item?.title, 240);
    const ageRating = safeAgeRating(item?.rating);
    if (!Number.isSafeInteger(id) || !title || !ageRating) return [];

    const result = record(
      "myanimelist",
      String(id),
      title,
      "https://myanimelist.net/" + category + "/" + id,
      category,
      { date: text(item.start_date, 40), ageRating },
    );
    const people = category === "manga" && Array.isArray(item.authors) ? item.authors : [];
    const studios = category === "anime" && Array.isArray(item.studios) ? item.studios : [];
    const organizations = [...studios, ...people].flatMap(value => {
      const row = object(value);
      const node = object(row?.node) ?? row;
      const entityId = node?.id;
      const name = text(node?.name, 160)
        ?? [text(node?.first_name, 80), text(node?.last_name, 80)].filter(Boolean).join(" ");
      if ((typeof entityId !== "number" && typeof entityId !== "string") || !name) return [];
      const organization = record(
        "myanimelist",
        String(entityId),
        name,
        "https://myanimelist.net/" + (category === "anime" ? "people/" : "people/") + entityId,
        "organization",
        { organizationType: category === "anime" ? "Animation studio" : "Author" },
      );
      return organization ? [organization] : [];
    });

    return [...(result ? [result] : []), ...organizations];
  }).slice(0, 20);
}

function safeAgeRating(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim().toUpperCase().replace(/_/g, "-");
  const direct = /^(G|PG|PG-13)(?:\s|$)/.exec(normalized);
  if (direct) return direct[1]!;
  if (normalized === "PG13") return "PG-13";
  return null;
}

export function parseShikimoriResults(payload: unknown, category: "anime" | "manga"): MediaSourceSearchRecord[] {
  if (!Array.isArray(payload)) return [];
  return payload.flatMap(value => {
    const item = object(value);
    const id = item?.id;
    const title = text(item?.name, 240) ?? text(item?.russian, 240);
    const ageRating = safeAgeRating(item?.rating);
    if (!Number.isSafeInteger(id) || !title || !ageRating) return [];

    const result = record(
      "shikimori",
      String(id),
      title,
      "https://shikimori.one/" + (category === "anime" ? "animes/" : "mangas/") + id,
      category,
      {
        date: text(item.aired_on ?? item.released_on, 40),
        ageRating,
      },
    );
    const studios = category === "anime" && Array.isArray(item.studios) ? item.studios : [];
    const organizations = studios.flatMap(studioValue => {
      const studio = object(studioValue);
      const studioId = studio?.id;
      const name = text(studio?.name, 160);
      if (!Number.isSafeInteger(studioId) || !name) return [];
      const value = record("shikimori", String(studioId), name,
        "https://shikimori.one/studios/" + studioId, "organization", { organizationType: "Animation studio" });
      return value ? [value] : [];
    });
    return [...(result ? [result] : []), ...organizations];
  }).slice(0, 20);
}

export function parseTvMazeResults(payload: unknown): MediaSourceSearchRecord[] {
  if (!Array.isArray(payload)) return [];
  return payload.flatMap(value => {
    const show = object(object(value)?.show);
    const id = show?.id;
    const name = text(show?.name, 240);
    const url = safeProviderUrl(show?.url, ["tvmaze.com"]);
    if (!Number.isSafeInteger(id) || !name || !url) return [];
    const summary = text(show.summary, 600);
    const result = record("tvmaze", String(id), name, url, "screen", {
      summary,
      date: text(show.premiered, 40),
      attribution: "TVmaze data — CC BY-SA; retain attribution and ShareAlike terms.",
    });
    const network = object(show.network) ?? object(show.webChannel);
    const networkId = network?.id;
    const networkName = text(network?.name, 180);
    const organization = Number.isSafeInteger(networkId) && networkName
      ? record("tvmaze", String(networkId), networkName, "https://www.tvmaze.com/networks/" + networkId, "organization", {
        organizationType: "Television network",
        attribution: "TVmaze data — CC BY-SA; retain attribution and ShareAlike terms.",
      })
      : null;
    return [...(result ? [result] : []), ...(organization ? [organization] : [])];
  }).slice(0, 20);
}

export function parseTraktResults(payload: unknown): MediaSourceSearchRecord[] {
  if (!Array.isArray(payload)) return [];
  return payload.flatMap(value => {
    const entry = object(value);
    const kind = entry?.type;
    const media = object(entry?.[kind === "show" ? "show" : kind === "movie" ? "movie" : ""]);
    const title = text(media?.title, 240);
    const ids = object(media?.ids);
    const id = ids?.trakt ?? ids?.slug;
    const slug = text(ids?.slug, 160);
    if ((kind !== "show" && kind !== "movie") || !title || (typeof id !== "number" && typeof id !== "string")) return [];
    const url = slug ? "https://trakt.tv/" + (kind === "show" ? "shows/" : "movies/") + encodeURIComponent(slug) : null;
    const result = record("trakt", String(id), title, url, "screen", { date: media?.year ? String(media.year) : null });
    return result ? [result] : [];
  }).slice(0, 20);
}

export function parseTvdbSearch(payload: unknown): MediaSourceSearchRecord[] {
  const rows = object(payload)?.data;
  if (!Array.isArray(rows)) return [];
  return rows.flatMap(value => {
    const item = object(value);
    const id = item?.tvdb_id ?? item?.id;
    const title = text(item?.name ?? item?.seriesName ?? item?.movieName, 240);
    if ((typeof id !== "number" && typeof id !== "string") || !title) return [];
    const url = "https://thetvdb.com/" + (item?.type === "movie" ? "movies/" : "series/") + encodeURIComponent(String(id));
    const result = record("thetvdb", String(id), title, url, "screen", {
      summary: text(item?.overview, 600),
      date: text(item?.year ?? item?.firstAired, 40),
      attribution: "Metadata provided by TheTVDB.com",
    });
    return result ? [result] : [];
  }).slice(0, 20);
}

export function parseBookBrainzSearch(payload: unknown, requestedType: "work" | "publisher" = "work"): MediaSourceSearchRecord[] {
  const rows = object(payload)?.searchResult;
  if (!Array.isArray(rows)) return [];
  const paths: Readonly<Record<string, string>> = {
    author: "author",
    edition: "edition",
    "editiongroup": "edition-group",
    publisher: "publisher",
    series: "series",
    work: "work",
  };
  return rows.flatMap(value => {
    const item = object(value);
    const id = text(item?.bbid, 80);
    const alias = object(item?.defaultAlias);
    const title = text(alias?.name, 240);
    const entityType = text(item?.entityType, 40)?.toLowerCase().replace(/[^a-z]/g, "") ?? "";
    const path = paths[entityType];
    if (!id || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id)
      || !title || !path) return [];
    if (requestedType === "publisher" && entityType !== "publisher") return [];
    if (requestedType === "work" && entityType !== "work" && entityType !== "edition") return [];
    const publisher = entityType === "publisher";
    const result = record(
      "bookbrainz",
      id,
      title,
      "https://bookbrainz.org/" + path + "/" + id,
      publisher ? "organization" : "book",
      publisher ? { organizationType: "Publisher" } : {},
    );
    return result ? [result] : [];
  }).slice(0, 20);
}
export function parseHardcoverSearch(payload: unknown): MediaSourceSearchRecord[] {
  const data = object(object(payload)?.data);
  const search = object(data?.search);
  const values = Array.isArray(search?.results) ? search.results
    : Array.isArray(search?.results_json) ? search.results_json : [];
  return values.flatMap(value => {
    const outer = object(value);
    const item = object(outer?.document) ?? outer;
    const id = item?.id;
    const title = text(item?.title ?? item?.name, 240);
    if ((typeof id !== "number" && typeof id !== "string") || !title) return [];
    const slug = text(item?.slug, 180);
    const url = slug ? "https://hardcover.app/books/" + encodeURIComponent(slug) : "https://hardcover.app/search?q=" + encodeURIComponent(title);
    const result = record("hardcover", String(id), title, url, "book", {
      summary: text(item?.description, 600),
      date: text(item?.release_date ?? item?.release_year, 40),
    });
    return result ? [result] : [];
  }).slice(0, 10);
}

export function parseComicVineSearch(payload: unknown): MediaSourceSearchRecord[] {
  const rows = object(payload)?.results;
  if (!Array.isArray(rows)) return [];
  return rows.flatMap(value => {
    const item = object(value);
    const id = item?.id;
    const title = text(item?.name, 240);
    const url = safeProviderUrl(item?.site_detail_url, ["comicvine.gamespot.com"]);
    if (!Number.isSafeInteger(id) || !title || !url) return [];
    const result = record("comic-vine", String(id), title, url, "book", { summary: text(item?.deck, 500) });
    return result ? [result] : [];
  }).slice(0, 10);
}

export function parseLastFmArtists(payload: unknown): MediaSourceSearchRecord[] {
  const rows = object(object(object(payload)?.results)?.artistmatches)?.artist;
  if (!Array.isArray(rows)) return [];
  return rows.flatMap(value => {
    const item = object(value);
    const name = text(item?.name, 180);
    const url = safeProviderUrl(item?.url, ["last.fm"]);
    const id = text(item?.mbid, 80) ?? name;
    if (!name || !url || !id) return [];
    const result = record("last-fm", id, name, url, "music", {
      summary: text(item?.listeners, 100) ? "Listeners: " + text(item?.listeners, 100) : null,
    });
    return result ? [result] : [];
  }).slice(0, 10);
}

export function parseSetlistArtists(payload: unknown): MediaSourceSearchRecord[] {
  const rows = object(payload)?.artist;
  if (!Array.isArray(rows)) return [];
  return rows.flatMap(value => {
    const item = object(value);
    const name = text(item?.name, 180);
    const id = text(item?.mbid, 80);
    const url = safeProviderUrl(item?.url, ["setlist.fm"]);
    if (!name || !url || !id) return [];
    const result = record("setlist-fm", id, name, url, "music");
    return result ? [result] : [];
  }).slice(0, 10);
}

export function parseRedditSearch(payload: unknown): MediaSourceSearchRecord[] {
  const children = object(object(payload)?.data)?.children;
  if (!Array.isArray(children)) return [];
  return children.flatMap(value => {
    const item = object(object(value)?.data);
    const id = text(item?.id, 100);
    const title = text(item?.title, 240);
    const permalink = text(item?.permalink, 400);
    if (item?.over_18 !== false || !id || !title || !permalink || !permalink.startsWith("/")) return [];
    const result = record("reddit", id, title, "https://www.reddit.com" + permalink, "community", {
      summary: null,
      date: typeof item?.created_utc === "number" ? new Date(item.created_utc * 1000).toISOString() : null,
    });
    return result ? [result] : [];
  }).slice(0, 10);
}

function stripQueryForSearch(value: string): string {
  return value.trim().replace(/\s+/g, " ").slice(0, 100);
}

const PUBLIC_FEEDS: Readonly<Record<string, string>> = {
  "comic-book-herald": "https://www.comicbookherald.com/feed/",
};

function xmlObject(value: unknown): JsonObject | null {
  return object(value);
}

function rssEntries(payload: unknown): JsonObject[] {
  const root = xmlObject(payload);
  const channel = object(object(root?.rss)?.channel);
  const atom = object(root?.feed);
  const rows = channel?.item ?? atom?.entry;
  return Array.isArray(rows) ? rows.flatMap(value => object(value) ? [object(value)!] : [])
    : rows && typeof rows === "object" ? [object(rows)!] : [];
}

function rssValue(item: JsonObject, key: string): string | null {
  const value = item[key];
  if (typeof value === "string") return text(value, 500);
  const entry = object(value);
  return text(entry?.["#text"] ?? entry?.["@_href"] ?? entry?.["__cdata"], 500);
}

export class MediaSourceClients {
  private tvdbToken: { value: string; expiresAt: number } | null = null;
  private tvdbLogin: Promise<string> | null = null;
  private redditToken: { value: string; expiresAt: number } | null = null;
  private redditLogin: Promise<string> | null = null;
  private readonly musicRuntime: ReturnType<typeof getMusicRuntime>;
  private readonly googleBooks: GoogleBooksClient;

  constructor(
    private readonly config: BotConfig,
    private readonly fetcher: typeof fetch = globalThis.fetch,
  ) {
    this.musicRuntime = getMusicRuntime(config);
    this.googleBooks = new GoogleBooksClient(config.googleBooksApiKey, fetcher);
  }

  async search(query: string, category: MediaSourceSearchCategory): Promise<MediaSourceSearchRecord[]> {
    const term = queryText(query);
    const tasks: Array<Promise<MediaSourceSearchRecord[]>> = [];
    if (category === "anime" || category === "manga") {
      tasks.push(this.searchShikimori(term, category));
      if (this.config.myAnimeListClientId) tasks.push(this.searchMyAnimeList(term, category));
    } else if (category === "screen") {
      // Member-facing screen discovery uses TMDB, which already excludes adult results.
      // Other APIs remain available only through their individually gated adapters.
    } else if (category === "book") {
      tasks.push(this.searchBookBrainz(term));
      if (this.config.hardcoverApiToken) tasks.push(this.searchHardcover(term));
    } else if (category === "music") {
      tasks.push(this.searchMusicPlatforms(term));
      if (this.config.lastFmApiKey) tasks.push(this.searchLastFm(term));
      if (this.config.setlistFmApiKey && this.config.setlistFmNonCommercialConfirmed) tasks.push(this.searchSetlistFm(term));
    } else if (category === "community") {
      // Community search remains citation-only until reliable content classification is available.
    }

    const settled = await Promise.allSettled(tasks);
    return uniqueRecords(settled.flatMap(result => result.status === "fulfilled" ? result.value : []));
  }

  async searchOrganizations(query: string): Promise<MediaSourceSearchRecord[]> {
    const term = queryText(query);
    const [googleBooks, bookBrainz] = await Promise.all([
      this.searchGoogleBooksPublishers(term).catch(() => []),
      this.searchBookBrainz(term, "publisher").catch(() => []),
    ]);
    return uniqueRecords([...googleBooks, ...bookBrainz])
      .filter(item => item.category === "organization");
  }

  async searchEnabledMediaWikis(query: string): Promise<MediaSourceSearchRecord[]> {
    const enabled = this.config.mediaWikiEnabledSources;
    if (!enabled.length) return [];
    const ids = MEDIA_WIKI_SOURCE_IDS.filter(id => enabled.includes(id));
    const settled = await Promise.allSettled(ids.map(async sourceId => {
      const client = new MediaWikiClient(sourceId, this.fetcher);
      const pages = await client.searchPages(query);
      return pages.flatMap(page => {
        const item = record(sourceId, String(page.pageId), page.title, page.url, "chronology", {
          summary: null,
          attribution: "Community-maintained reference; verify continuity and cited primary sources.",
        });
        return item ? [item] : [];
      });
    }));
    return uniqueRecords(settled.flatMap(result => result.status === "fulfilled" ? result.value : []));
  }

  async searchChronologyReferences(query: string): Promise<MediaSourceSearchRecord[]> {
    const term = stripQueryForSearch(query);
    if (term.length < 2) return [];
    const allowed = this.config.mediaSourceScrapeAllowlist;
    const ids = Object.keys(PUBLIC_FEEDS).filter(id => allowed.includes(id));
    const settled = await Promise.allSettled(ids.map(id => this.searchPublicReference(id, term)));
    return uniqueRecords(settled.flatMap(result => result.status === "fulfilled" ? result.value : []));
  }

  async searchMyAnimeList(query: string, category: "anime" | "manga"): Promise<MediaSourceSearchRecord[]> {
    const url = new URL("https://api.myanimelist.net/v2/" + category);
    url.search = new URLSearchParams({
      q: query,
      limit: "8",
      fields: category === "anime" ? "start_date,studios,rating" : "start_date,authors,rating",
    }).toString();
    const payload = await fetchJson<unknown>(url.toString(), {
      fetchImpl: this.fetcher,
      timeoutMs: 10_000,
      retries: 1,
      maxResponseBytes: 512 * 1024,
      headers: { "X-MAL-CLIENT-ID": this.config.myAnimeListClientId!, Accept: "application/json" },
    });
    return parseMalResults(payload, category);
  }

  async searchShikimori(query: string, category: "anime" | "manga"): Promise<MediaSourceSearchRecord[]> {
    const url = new URL("https://shikimori.one/api/" + (category === "anime" ? "animes" : "mangas"));
    url.search = new URLSearchParams({ search: query, limit: "8" }).toString();
    const payload = await fetchJson<unknown>(url.toString(), {
      fetchImpl: this.fetcher,
      timeoutMs: 10_000,
      retries: 1,
      maxResponseBytes: 512 * 1024,
      headers: { Accept: "application/json", "User-Agent": "Lemegeton/3.0 (media discovery)" },
    });
    return parseShikimoriResults(payload, category);
  }

  async searchTvMaze(query: string): Promise<MediaSourceSearchRecord[]> {
    const url = new URL("https://api.tvmaze.com/search/shows");
    url.searchParams.set("q", query);
    const payload = await fetchJson<unknown>(url.toString(), { fetchImpl: this.fetcher, timeoutMs: 10_000, retries: 1 });
    return parseTvMazeResults(payload);
  }

  async searchTrakt(query: string): Promise<MediaSourceSearchRecord[]> {
    const url = new URL("https://api.trakt.tv/search/show,movie");
    url.searchParams.set("query", query);
    url.searchParams.set("limit", "8");
    const payload = await fetchJson<unknown>(url.toString(), {
      fetchImpl: this.fetcher,
      timeoutMs: 10_000,
      retries: 1,
      headers: {
        "trakt-api-version": "2",
        "trakt-api-key": this.config.traktClientId!,
        Accept: "application/json",
      },
    });
    return parseTraktResults(payload);
  }

  async searchTvdb(query: string): Promise<MediaSourceSearchRecord[]> {
    const token = await this.getTvdbToken();
    const url = new URL("https://api4.thetvdb.com/v4/search");
    url.searchParams.set("query", query);
    url.searchParams.set("type", "series");
    const payload = await fetchJson<unknown>(url.toString(), {
      fetchImpl: this.fetcher,
      timeoutMs: 10_000,
      retries: 1,
      headers: { Authorization: "Bearer " + token, Accept: "application/json" },
    });
    return parseTvdbSearch(payload);
  }

  async searchGoogleBooksPublishers(query: string): Promise<MediaSourceSearchRecord[]> {
    const books = await this.googleBooks.search("inpublisher:" + query);
    const publishers = new Map<string, MediaSourceSearchRecord>();
    for (const book of books) {
      const name = text(book.publisher, 180);
      if (!name) continue;
      const key = name.toLocaleLowerCase("en-US");
      if (publishers.has(key)) continue;
      const item = record(
        "google-books",
        "publisher:" + key,
        name,
        book.sourceUrl,
        "organization",
        { organizationType: "Publisher", summary: "Publisher name returned by Google Books for " + book.title },
      );
      if (item) publishers.set(key, item);
    }
    return [...publishers.values()].slice(0, 10);
  }

  async searchBookBrainz(query: string, type: "work" | "publisher" = "work"): Promise<MediaSourceSearchRecord[]> {
    const url = new URL("https://api.bookbrainz.org/1/search");
    url.search = new URLSearchParams({ q: query, type, size: "10", from: "0" }).toString();
    const payload = await fetchJson<unknown>(url.toString(), {
      fetchImpl: this.fetcher,
      timeoutMs: 10_000,
      retries: 1,
      maxResponseBytes: 512 * 1024,
      headers: { Accept: "application/json", "User-Agent": "Lemegeton/3.0 (https://github.com/Kyerstorm/Lemegeton)" },
    });
    return parseBookBrainzSearch(payload, type);
  }

  async searchHardcover(query: string): Promise<MediaSourceSearchRecord[]> {
    const body = JSON.stringify({
      query: "query SearchBooks($query: String!) { search(query: $query, query_type: \"Book\") { results } }",
      variables: { query },
    });
    const payload = await fetchJson<unknown>("https://api.hardcover.app/v1/graphql", {
      fetchImpl: this.fetcher,
      method: "POST",
      body,
      timeoutMs: 10_000,
      retries: 0,
      maxResponseBytes: 512 * 1024,
      headers: { Authorization: "Bearer " + this.config.hardcoverApiToken!, "Content-Type": "application/json", Accept: "application/json" },
    });
    if (object(payload)?.errors) throw new Error("Hardcover API returned a GraphQL error.");
    return parseHardcoverSearch(payload);
  }

  async searchComicVine(query: string): Promise<MediaSourceSearchRecord[]> {
    const url = new URL("https://comicvine.gamespot.com/api/search/");
    url.search = new URLSearchParams({
      api_key: this.config.comicVineApiKey!,
      format: "json",
      resources: "volume,issue",
      limit: "8",
      query,
    }).toString();
    const payload = await fetchJson<unknown>(url.toString(), {
      fetchImpl: this.fetcher,
      timeoutMs: 10_000,
      retries: 0,
      maxResponseBytes: 512 * 1024,
      headers: { Accept: "application/json", "User-Agent": "Lemegeton/3.0 (media discovery)" },
    });
    return parseComicVineSearch(payload);
  }

  async searchMusicPlatforms(query: string): Promise<MediaSourceSearchRecord[]> {
    const artists = await this.musicRuntime.searchCatalogueArtists(query);
    return artists.flatMap(item => {
      const sourceId = item.provider === "spotify" ? "spotify"
        : item.provider === "youtube" ? "youtube-data-api" : "soundcloud";
      const result = record(sourceId, item.providerId, item.name, item.url, "music", {
        summary: item.summary,
      });
      return result ? [result] : [];
    });
  }

  async searchLastFm(query: string): Promise<MediaSourceSearchRecord[]> {
    const url = new URL("https://ws.audioscrobbler.com/2.0/");
    url.search = new URLSearchParams({
      method: "artist.search",
      artist: query,
      api_key: this.config.lastFmApiKey!,
      format: "json",
      limit: "8",
    }).toString();
    const payload = await fetchJson<unknown>(url.toString(), {
      fetchImpl: this.fetcher,
      timeoutMs: 10_000,
      retries: 1,
      maxResponseBytes: 512 * 1024,
    });
    return parseLastFmArtists(payload);
  }

  async searchSetlistFm(query: string): Promise<MediaSourceSearchRecord[]> {
    const url = new URL("https://api.setlist.fm/rest/1.0/search/artists");
    url.searchParams.set("artistName", query);
    url.searchParams.set("p", "1");
    const payload = await fetchJson<unknown>(url.toString(), {
      fetchImpl: this.fetcher,
      timeoutMs: 10_000,
      retries: 1,
      maxResponseBytes: 512 * 1024,
      headers: { "x-api-key": this.config.setlistFmApiKey!, Accept: "application/json" },
    });
    return parseSetlistArtists(payload);
  }

  async searchReddit(query: string): Promise<MediaSourceSearchRecord[]> {
    const token = await this.getRedditToken();
    const url = new URL("https://oauth.reddit.com/search");
    url.search = new URLSearchParams({ q: query, limit: "8", sort: "relevance", restrict_sr: "false", include_over_18: "false" }).toString();
    const payload = await fetchJson<unknown>(url.toString(), {
      fetchImpl: this.fetcher,
      timeoutMs: 10_000,
      retries: 0,
      maxResponseBytes: 512 * 1024,
      headers: {
        Authorization: "Bearer " + token,
        "User-Agent": "Lemegeton/3.0 (+https://github.com/Kyerstorm/Lemegeton)",
        Accept: "application/json",
      },
    });
    return parseRedditSearch(payload);
  }

  async searchPublicReference(sourceId: string, query: string): Promise<MediaSourceSearchRecord[]> {
    const feedUrl = PUBLIC_FEEDS[sourceId];
    const source = getMediaSource(sourceId);
    if (!feedUrl || !source || source.status !== "manual-reference"
      || sourceId !== "comic-book-herald"
      || !this.config.mediaSourceScrapeAllowlist.includes(sourceId)
      || !this.config.comicBookHeraldRssNonCommercialConfirmed) return [];

    const document = await fetchXml<unknown>(feedUrl, {
      fetchImpl: this.fetcher,
      timeoutMs: 10_000,
      retries: 0,
      maxResponseBytes: 512 * 1024,
      headers: { Accept: "application/rss+xml, application/atom+xml, application/xml" },
    });
    const term = query.toLocaleLowerCase("en-US");
    const rows = rssEntries(document);
    return rows.flatMap(item => {
      const title = rssValue(item, "title");
      const link = rssValue(item, "link");
      if (!title || title !== title.trim() || title.length > 240
        || !title.toLocaleLowerCase("en-US").includes(term) || !link) return [];
      const safe = safeProviderUrl(link, ["comicbookherald.com", "www.comicbookherald.com"]);
      if (!safe) return [];
      const value = record(sourceId, safe, title, safe, "chronology", {
        attribution: "Comic Book Herald RSS item. Reproduced without modification under the source's RSS permission.",
      });
      return value ? [value] : [];
    }).slice(0, 8);
  }

  private async getTvdbToken(): Promise<string> {
    if (this.tvdbToken && this.tvdbToken.expiresAt > Date.now()) return this.tvdbToken.value;
    if (this.tvdbLogin) return this.tvdbLogin;
    this.tvdbLogin = (async () => {
      const payload = await fetchJson<unknown>("https://api4.thetvdb.com/v4/login", {
        fetchImpl: this.fetcher,
        method: "POST",
        body: JSON.stringify({
          apikey: this.config.tvdbApiKey,
          ...(this.config.tvdbSubscriberPin ? { pin: this.config.tvdbSubscriberPin } : {}),
        }),
        timeoutMs: 10_000,
        retries: 0,
        headers: { "Content-Type": "application/json", Accept: "application/json" },
      });
      const token = text(object(object(payload)?.data)?.token, 4_000);
      if (!token) throw new Error("TheTVDB did not issue an access token.");
      this.tvdbToken = { value: token, expiresAt: Date.now() + 27 * 24 * 60 * 60_000 };
      return token;
    })();
    try {
      return await this.tvdbLogin;
    } finally {
      this.tvdbLogin = null;
    }
  }

  private async getRedditToken(): Promise<string> {
    if (this.redditToken && this.redditToken.expiresAt > Date.now()) return this.redditToken.value;
    if (this.redditLogin) return this.redditLogin;
    this.redditLogin = (async () => {
      const authorization = Buffer.from(this.config.redditClientId + ":" + this.config.redditClientSecret).toString("base64");
      const body = new URLSearchParams({ grant_type: "client_credentials" });
      const payload = await fetchJson<unknown>("https://www.reddit.com/api/v1/access_token", {
        fetchImpl: this.fetcher,
        method: "POST",
        body,
        timeoutMs: 10_000,
        retries: 0,
        headers: {
          Authorization: "Basic " + authorization,
          "User-Agent": "web:lemegeton:v3 (by /u/lemegeton)",
          "Content-Type": "application/x-www-form-urlencoded",
          Accept: "application/json",
        },
      });
      const token = text(object(payload)?.access_token, 4_000);
      const expires = object(payload)?.expires_in;
      if (!token) throw new Error("Reddit did not issue an application access token.");
      this.redditToken = {
        value: token,
        expiresAt: Date.now() + (typeof expires === "number" ? Math.max(60, expires - 60) : 3_540) * 1_000,
      };
      return token;
    })();
    try {
      return await this.redditLogin;
    } finally {
      this.redditLogin = null;
    }
  }
}

function uniqueRecords(records: MediaSourceSearchRecord[]): MediaSourceSearchRecord[] {
  const seen = new Set<string>();
  return records.filter(item => {
    const key = item.sourceId + ":" + item.providerId;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 40);
}

/** Complete source access plan for every entry in the command-expansion inventory. */
export type MediaSourceIntegrationMode = "api" | "credentialed-api" | "licensed-api" | "restricted-api" | "mediawiki" | "scrape" | "feed" | "manual" | "retired";

export const MEDIA_SOURCE_INTEGRATION_MODES: Readonly<Record<string, MediaSourceIntegrationMode>> = {
  "the-canonicle": "manual", "chronocanon": "manual", "chronelines": "manual", "chronologeek": "manual",
  "order-of-book-series": "manual", "comic-book-herald": "feed", "official-franchise-timelines": "manual",
  "official-episode-guides": "manual", "official-novel-series-guides": "manual",
  "wookieepedia": "mediawiki", "memory-alpha": "mediawiki", "tardis-wiki": "mediawiki",
  "marvel-database": "mediawiki", "dc-database": "mediawiki", "tolkien-gateway": "mediawiki",
  "harry-potter-wiki": "mediawiki", "a-song-of-ice-and-fire-wiki": "mediawiki", "witcher-wiki": "mediawiki",
  "narutopedia": "mediawiki", "dragon-ball-wiki": "mediawiki", "one-piece-wiki": "mediawiki",
  "jojos-bizarre-encyclopedia": "mediawiki", "pokemon-wiki": "mediawiki", "transformers-wiki": "mediawiki",
  "fandom-wikis": "manual",
  "myanimelist": "credentialed-api", "anime-planet": "manual", "mangaupdates": "manual", "novel-updates": "scrape",
  "mangadex": "api", "anilist": "api", "anidb": "manual", "jikan": "retired", "kitsu": "api",
  "shikimori": "api", "anime-news-network-encyclopedia": "manual",
  "tmdb": "api", "thetvdb": "licensed-api", "tvmaze": "licensed-api", "trakt": "credentialed-api", "imdb": "manual",
  "goodreads": "manual", "storygraph": "manual", "hardcover": "credentialed-api", "comic-vine": "restricted-api",
  "novelfire": "scrape", "novel-archive": "scrape", "wuxia-click": "scrape", "noveli-to": "scrape",
  "publisher-websites": "manual", "google-books": "api", "open-library": "api", "bookbrainz": "api",
  "isfdb": "manual", "worldcat": "licensed-api", "wikidata": "api", "tv-tropes": "manual",
  "reddit": "credentialed-api", "musicbrainz": "api", "last-fm": "credentialed-api", "setlist-fm": "restricted-api",
  "spotify": "credentialed-api", "youtube-data-api": "credentialed-api", "soundcloud": "credentialed-api",
};

export function getMediaSourceIntegrationMode(sourceId: string): MediaSourceIntegrationMode | null {
  return MEDIA_SOURCE_INTEGRATION_MODES[sourceId.trim().toLowerCase()] ?? null;
}

export function getMediaSourceIntegrationCoverage(): Array<{ id: string; mode: MediaSourceIntegrationMode }> {
  return MEDIA_SOURCES.flatMap(source => {
    const mode = getMediaSourceIntegrationMode(source.id);
    return mode ? [{ id: source.id, mode }] : [];
  });
}
