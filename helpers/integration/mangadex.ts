import { fetchProviderResponse } from "./provider-http.js";

export interface MangaDexMedia {
  id: string;
  title: string;
  alternateTitles: string[];
  description: string | null;
  authors: string[];
  artists: string[];
  status: string | null;
  publicationDemographic: string | null;
  originalLanguage: string | null;
  year: number | null;
  lastVolume: string | null;
  lastChapter: string | null;
  tags: string[];
  coverUrl: string | null;
  sourceUrl: string;
  contentRating: "safe";
}

type JsonObject = Record<string, unknown>;
type TagRecord = { id: string; name: string };

function object(value: unknown): JsonObject | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : null;
}

function localized(value: unknown): string[] {
  const record = object(value);
  if (!record) return [];
  return Object.values(record).flatMap(item => typeof item === "string" && item.trim() ? [item.trim().slice(0, 200)] : []);
}

function parseManga(value: unknown): MangaDexMedia | null {
  const record = object(value);
  const id = record?.id;
  const attributes = object(record?.attributes);
  if (!record || typeof id !== "string" || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id)
    || !attributes || attributes.contentRating !== "safe") return null;
  const titleRecord = object(attributes.title);
  const title = (typeof titleRecord?.en === "string" && titleRecord.en.trim() ? titleRecord.en.trim() : localized(attributes.title)[0]) ?? "";
  if (!title) return null;
  const alternateTitles = (Array.isArray(attributes.altTitles) ? attributes.altTitles : [])
    .flatMap(item => localized(item)).filter(value => value !== title).slice(0, 12);
  const relationships = Array.isArray(record.relationships) ? record.relationships : [];
  const authors: string[] = [];
  const artists: string[] = [];
  let coverFile: string | null = null;
  for (const raw of relationships) {
    const relation = object(raw);
    const relationAttributes = object(relation?.attributes);
    if (relation?.type === "author" && typeof relationAttributes?.name === "string") authors.push(relationAttributes.name);
    else if (relation?.type === "artist" && typeof relationAttributes?.name === "string") artists.push(relationAttributes.name);
    else if (relation?.type === "cover_art" && typeof relationAttributes?.fileName === "string") coverFile = relationAttributes.fileName;
  }
  const tags = (Array.isArray(attributes.tags) ? attributes.tags : []).flatMap(raw => {
    const tag = object(raw);
    const tagAttributes = object(tag?.attributes);
    return localized(tagAttributes?.name).slice(0, 1);
  }).slice(0, 24);
  const coverUrl = coverFile && /^[a-zA-Z0-9._-]{1,180}$/.test(coverFile)
    ? "https://uploads.mangadex.org/covers/" + encodeURIComponent(id) + "/" + encodeURIComponent(coverFile) + ".256.jpg"
    : null;
  const year = typeof attributes.year === "number" && Number.isInteger(attributes.year) ? attributes.year : null;
  const status = typeof attributes.status === "string" ? attributes.status : null;
  const publicationDemographic = typeof attributes.publicationDemographic === "string" ? attributes.publicationDemographic : null;
  const originalLanguage = typeof attributes.originalLanguage === "string" ? attributes.originalLanguage : null;
  const description = localized(attributes.description)[0] ?? null;
  const lastVolume = typeof attributes.lastVolume === "string" ? attributes.lastVolume : null;
  const lastChapter = typeof attributes.lastChapter === "string" ? attributes.lastChapter : null;
  return {
    id, title: title.slice(0, 240), alternateTitles,
    description: description?.slice(0, 1_200) ?? null,
    authors: [...new Set(authors)].slice(0, 8),
    artists: [...new Set(artists)].slice(0, 8),
    status, publicationDemographic, originalLanguage, year, lastVolume, lastChapter, tags,
    coverUrl, sourceUrl: "https://mangadex.org/title/" + id, contentRating: "safe",
  };
}

function normalizedTag(value: string): string {
  return value.trim().toLocaleLowerCase("en").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, " ").trim();
}

export class MangaDexClient {
  private requestQueue: Promise<void> = Promise.resolve();
  private lastRequestAt = 0;
  private readonly searchCache = new Map<string, { storedAt: number; items: MangaDexMedia[] }>();
  private tagCache: { storedAt: number; tags: TagRecord[] } | null = null;

  constructor(private readonly fetcher: typeof fetch = globalThis.fetch, private readonly minimumIntervalMs = 1_100) {}

  async search(title: string): Promise<MangaDexMedia[]> {
    const query = title.trim().replace(/\s+/g, " ").slice(0, 120);
    if (query.length < 2) return [];
    return this.cachedSearch("title:" + query.toLocaleLowerCase("en"), () => {
      const url = new URL("https://api.mangadex.org/manga");
      url.searchParams.set("title", query);
      url.searchParams.set("limit", "10");
      url.searchParams.set("contentRating[]", "safe");
      url.searchParams.set("includes[]", "author");
      url.searchParams.set("includes[]", "artist");
      url.searchParams.set("includes[]", "cover_art");
      url.searchParams.set("order[relevance]", "desc");
      return this.requestManga(url);
    });
  }

  async searchByTags(values: readonly string[], limit = 10): Promise<MangaDexMedia[]> {
    const requested = [...new Set(values.map(normalizedTag).filter(Boolean))].slice(0, 3);
    if (!requested.length) return [];
    const tags = await this.getTags();
    const ids = requested.flatMap(name => {
      const exact = tags.find(tag => normalizedTag(tag.name) === name);
      return exact ? [exact.id] : [];
    });
    if (!ids.length) return [];
    const key = "tags:" + [...ids].sort().join(",");
    return this.cachedSearch(key, () => {
      const url = new URL("https://api.mangadex.org/manga");
      url.searchParams.set("limit", String(Math.max(1, Math.min(20, Math.floor(limit)))));
      url.searchParams.set("contentRating[]", "safe");
      url.searchParams.set("includedTagsMode", "OR");
      for (const id of ids) url.searchParams.append("includedTags[]", id);
      url.searchParams.set("includes[]", "author");
      url.searchParams.set("includes[]", "artist");
      url.searchParams.set("includes[]", "cover_art");
      url.searchParams.set("order[followedCount]", "desc");
      return this.requestManga(url);
    });
  }

  private async cachedSearch(key: string, load: () => Promise<MangaDexMedia[]>): Promise<MangaDexMedia[]> {
    const cached = this.searchCache.get(key);
    if (cached && Date.now() - cached.storedAt < 5 * 60_000) return [...cached.items];
    const items = await load();
    this.searchCache.set(key, { storedAt: Date.now(), items });
    while (this.searchCache.size > 100) {
      const oldest = this.searchCache.keys().next().value;
      if (oldest === undefined) break;
      this.searchCache.delete(oldest);
    }
    return [...items];
  }

  private async requestManga(url: URL): Promise<MangaDexMedia[]> {
    const payload = object(await this.requestJson(url.toString()));
    const rows = Array.isArray(payload?.data) ? payload.data : [];
    return rows.flatMap(value => {
      const media = parseManga(value);
      return media ? [media] : [];
    }).slice(0, 20);
  }

  private async getTags(): Promise<TagRecord[]> {
    if (this.tagCache && Date.now() - this.tagCache.storedAt < 24 * 60 * 60_000) return this.tagCache.tags;
    const payload = object(await this.requestJson("https://api.mangadex.org/manga/tag"));
    const rows = Array.isArray(payload?.data) ? payload.data : [];
    const tags = rows.flatMap(raw => {
      const record = object(raw);
      const attributes = object(record?.attributes);
      const names = object(attributes?.name);
      const name = typeof names?.en === "string" ? names.en : null;
      return typeof record?.id === "string" && name ? [{ id: record.id, name }] : [];
    });
    this.tagCache = { storedAt: Date.now(), tags };
    return tags;
  }

  private async requestJson(url: string): Promise<unknown> {
    const previous = this.requestQueue;
    let release!: () => void;
    this.requestQueue = new Promise<void>(resolve => { release = resolve; });
    await previous;
    try {
      const wait = Math.max(0, this.minimumIntervalMs - (Date.now() - this.lastRequestAt));
      if (wait > 0) await new Promise(resolve => setTimeout(resolve, wait));
      this.lastRequestAt = Date.now();
      const response = await fetchProviderResponse(this.fetcher, url, {
        headers: { Accept: "application/json", "User-Agent": "Lemegeton/3.2 (https://github.com/Kyerstorm/Lemegeton)" },
        signal: AbortSignal.timeout(10_000),
      });
      if (!response.ok) throw new Error("MangaDex returned HTTP " + response.status + ".");
      return await response.json();
    } finally {
      release();
    }
  }
}
