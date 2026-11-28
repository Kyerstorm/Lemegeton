import { fetchJson } from "./web-scraper.js";

export interface MediaWikiPage {
  pageId: number;
  title: string;
  url: string;
  excerpt: string | null;
  latestRevisionId: number | null;
}

export type MediaWikiSourceId =
  | "wookieepedia"
  | "memory-alpha"
  | "tardis-wiki"
  | "marvel-database"
  | "dc-database"
  | "tolkien-gateway"
  | "harry-potter-wiki"
  | "a-song-of-ice-and-fire-wiki"
  | "witcher-wiki"
  | "narutopedia"
  | "dragon-ball-wiki"
  | "one-piece-wiki"
  | "jojos-bizarre-encyclopedia"
  | "pokemon-wiki"
  | "transformers-wiki";

const ENDPOINTS: Readonly<Record<MediaWikiSourceId, string>> = {
  "wookieepedia": "https://starwars.fandom.com/api.php",
  "memory-alpha": "https://memory-alpha.fandom.com/api.php",
  "tardis-wiki": "https://tardis.fandom.com/api.php",
  "marvel-database": "https://marvel.fandom.com/api.php",
  "dc-database": "https://dc.fandom.com/api.php",
  "tolkien-gateway": "https://tolkiengateway.net/w/api.php",
  "harry-potter-wiki": "https://harrypotter.fandom.com/api.php",
  "a-song-of-ice-and-fire-wiki": "https://awoiaf.westeros.org/api.php",
  "witcher-wiki": "https://witcher.fandom.com/api.php",
  "narutopedia": "https://naruto.fandom.com/api.php",
  "dragon-ball-wiki": "https://dragonball.fandom.com/api.php",
  "one-piece-wiki": "https://onepiece.fandom.com/api.php",
  "jojos-bizarre-encyclopedia": "https://jojowiki.com/api.php",
  "pokemon-wiki": "https://pokemon.fandom.com/api.php",
  "transformers-wiki": "https://tfwiki.net/api.php",
};

export const MEDIA_WIKI_SOURCE_IDS = Object.freeze(Object.keys(ENDPOINTS) as MediaWikiSourceId[]);

const USER_AGENT = "Lemegeton/3.0 (https://github.com/Kyerstorm/Lemegeton)";
const CACHE_TTL_MS = 15 * 60_000;
const MAX_CACHE_ENTRIES = 100;

type JsonObject = Record<string, unknown>;
const cache = new Map<string, { expiresAt: number; value: unknown }>();

function object(value: unknown): JsonObject | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as JsonObject
    : null;
}

function clean(value: unknown, maximum: number): string | null {
  return typeof value === "string" && value.trim() ? value.trim().slice(0, maximum) : null;
}

function plainText(value: string): string {
  return value
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 1_000);
}

function safeWikiUrl(value: unknown, endpoint: URL): string | null {
  if (typeof value !== "string") return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && url.hostname === endpoint.hostname ? url.toString() : null;
  } catch {
    return null;
  }
}

function pageArray(payload: unknown): JsonObject[] {
  const pages = object(object(payload)?.query);
  return Array.isArray(pages?.pages) ? pages.pages.flatMap(value => {
    const item = object(value);
    return item ? [item] : [];
  }) : [];
}

export function parseMediaWikiPages(payload: unknown, endpoint: string): MediaWikiPage[] {
  const base = new URL(endpoint);
  const unique = new Map<number, MediaWikiPage>();
  for (const item of pageArray(payload)) {
    if (item.missing === true || typeof item.pageid !== "number"
      || !Number.isSafeInteger(item.pageid) || item.pageid < 1) continue;
    const title = clean(item.title, 240);
    const url = safeWikiUrl(item.fullurl, base);
    if (!title || !url) continue;
    const revision = typeof item.lastrevid === "number" && Number.isSafeInteger(item.lastrevid)
      && item.lastrevid > 0 ? item.lastrevid : null;
    const excerpt = clean(item.extract, 1_000);
    unique.set(item.pageid, {
      pageId: item.pageid,
      title,
      url,
      excerpt: excerpt ? plainText(excerpt) : null,
      latestRevisionId: revision,
    });
  }
  return [...unique.values()].slice(0, 10);
}

export function getMediaWikiEndpoint(sourceId: string): string | null {
  return Object.prototype.hasOwnProperty.call(ENDPOINTS, sourceId)
    ? ENDPOINTS[sourceId as MediaWikiSourceId]
    : null;
}

/**
 * Read-only, bounded MediaWiki Action API access.
 *
 * The endpoint list is intentionally explicit. Every request still passes
 * through the shared public-resource SSRF validation gate; an unsupported
 * module, disabled API or access denial is returned as a provider error.
 */
export class MediaWikiClient {
  private readonly endpoint: URL;

  constructor(
    readonly sourceId: MediaWikiSourceId,
    private readonly fetcher: typeof fetch = globalThis.fetch,
  ) {
    this.endpoint = new URL(ENDPOINTS[sourceId]);
  }

  async searchPages(query: string): Promise<MediaWikiPage[]> {
    const term = query.trim().replace(/\s+/g, " ").slice(0, 100);
    if (term.length < 2) return [];
    const key = this.sourceId + ":search:" + term.toLocaleLowerCase("en-US");
    const hit = this.cached<MediaWikiPage[]>(key);
    if (hit) return hit;

    const url = new URL(this.endpoint);
    url.search = new URLSearchParams({
      action: "query",
      generator: "search",
      gsrsearch: term,
      gsrlimit: "8",
      prop: "info",
      inprop: "url",
      format: "json",
      formatversion: "2",
    }).toString();
    return this.remember(key, await this.request(url));
  }

  async page(title: string): Promise<MediaWikiPage | null> {
    const term = title.trim().replace(/\s+/g, " ").slice(0, 200);
    if (term.length < 1) return null;
    const key = this.sourceId + ":page:" + term.toLocaleLowerCase("en-US");
    const hit = this.cached<MediaWikiPage[]>(key);
    if (hit) return hit[0] ?? null;

    const url = new URL(this.endpoint);
    url.search = new URLSearchParams({
      action: "query",
      titles: term,
      prop: "info|extracts",
      inprop: "url",
      exintro: "1",
      explaintext: "1",
      exchars: "900",
      format: "json",
      formatversion: "2",
    }).toString();
    const pages = await this.request(url);
    this.remember(key, pages);
    return pages[0] ?? null;
  }

  private async request(url: URL): Promise<MediaWikiPage[]> {
    const payload = await fetchJson<unknown>(url.toString(), {
      fetchImpl: this.fetcher,
      timeoutMs: 10_000,
      retries: 1,
      maxRetryDelayMs: 2_000,
      maxResponseBytes: 512 * 1024,
      headers: {
        Accept: "application/json",
        "User-Agent": USER_AGENT,
      },
    });
    const error = object(object(payload)?.error);
    if (error) {
      const code = clean(error.code, 80) ?? "unknown";
      throw new Error("MediaWiki API " + code + " error.");
    }
    return parseMediaWikiPages(payload, this.endpoint.toString());
  }

  private cached<T>(key: string): T | null {
    const item = cache.get(key);
    if (!item) return null;
    if (item.expiresAt <= Date.now()) {
      cache.delete(key);
      return null;
    }
    return item.value as T;
  }

  private remember<T>(key: string, value: T): T {
    if (cache.size >= MAX_CACHE_ENTRIES) {
      const oldest = cache.keys().next().value;
      if (oldest) cache.delete(oldest);
    }
    cache.set(key, { value, expiresAt: Date.now() + CACHE_TTL_MS });
    return value;
  }
}
