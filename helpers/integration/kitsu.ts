import { fetchProviderResponse } from "./provider-http.js";

export type KitsuMediaType = "anime" | "manga";
export type KitsuAgeRating = "G" | "PG";

export interface KitsuMedia {
  id: string;
  type: KitsuMediaType;
  title: string;
  alternateTitles: string[];
  description: string | null;
  sourceUrl: string;
  image: string | null;
  ageRating: KitsuAgeRating;
  ageRatingGuide: string | null;
  status: string | null;
  format: string | null;
  startDate: string | null;
  endDate: string | null;
  rating: number | null;
  genres: string[];
  categories: string[];
  episodeCount: number | null;
  episodeLength: number | null;
  chapterCount: number | null;
  volumeCount: number | null;
}

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as JsonObject
    : null;
}

function text(value: unknown, maximum = 500): string | null {
  return typeof value === "string" && value.trim() ? value.trim().slice(0, maximum) : null;
}

function count(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
}

function imageUrl(value: unknown): string | null {
  const raw = text(value, 1_000);
  if (!raw) return null;
  try {
    const url = new URL(raw);
    return url.protocol === "https:" && url.hostname === "media.kitsu.io"
      && !url.username && !url.password ? url.toString() : null;
  } catch {
    return null;
  }
}

function includedLabels(
  relationships: JsonObject,
  included: unknown[],
  relationshipName: "genres" | "categories",
): string[] {
  const relation = object(relationships[relationshipName]);
  const links = Array.isArray(relation?.data) ? relation.data : [];
  const ids = new Set(links.flatMap(value => {
    const link = object(value);
    return typeof link?.id === "string" && link.type === relationshipName ? [link.id] : [];
  }));
  if (!ids.size) return [];
  return [...new Set(included.flatMap(value => {
    const record = object(value);
    if (!record || record.type !== relationshipName || typeof record.id !== "string" || !ids.has(record.id)) return [];
    const attributes = object(record.attributes);
    const label = text(attributes?.name) ?? text(attributes?.title);
    return label ? [label] : [];
  }))].slice(0, 24);
}

export function parseKitsuMedia(value: unknown, included: unknown[] = []): KitsuMedia | null {
  const record = object(value);
  const attributes = object(record?.attributes);
  const type = record?.type === "anime" ? "anime" : record?.type === "manga" ? "manga" : null;
  const id = text(record?.id, 40);
  if (!record || !attributes || !type || !id) return null;

  const ageRating = attributes.ageRating;
  if ((ageRating !== "G" && ageRating !== "PG") || attributes.nsfw === true) return null;

  const titles = object(attributes.titles);
  const title = text(attributes.canonicalTitle, 240)
    ?? text(titles?.en, 240)
    ?? text(titles?.en_jp, 240)
    ?? text(titles?.ja_jp, 240);
  if (!title) return null;

  const slug = text(attributes.slug, 180);
  const safeSlug = slug && /^[A-Za-z0-9-]+$/.test(slug) ? slug : id;
  const relationships = object(record.relationships) ?? {};
  const poster = object(attributes.posterImage);
  const score = Number(attributes.averageRating);
  const rating = Number.isFinite(score) && score >= 0 && score <= 100 ? score : null;
  const alternateTitles = [...new Set([
    text(titles?.en, 240),
    text(titles?.en_jp, 240),
    text(titles?.ja_jp, 240),
    ...(Array.isArray(attributes.abbreviatedTitles)
      ? attributes.abbreviatedTitles.flatMap(value => text(value, 180) ?? [])
      : []),
  ].filter((value): value is string => Boolean(value && value.toLocaleLowerCase("en") !== title.toLocaleLowerCase("en"))))].slice(0, 20);

  return {
    id,
    type,
    title,
    alternateTitles,
    description: text(attributes.synopsis) ?? text(attributes.description),
    sourceUrl: `https://kitsu.io/${type}/${encodeURIComponent(safeSlug)}`,
    image: imageUrl(poster?.large) ?? imageUrl(poster?.medium) ?? imageUrl(poster?.small),
    ageRating,
    ageRatingGuide: text(attributes.ageRatingGuide, 160),
    status: text(attributes.status, 60),
    format: text(type === "anime" ? attributes.subtype : attributes.mangaType ?? attributes.subtype, 60),
    startDate: text(attributes.startDate, 10),
    endDate: text(attributes.endDate, 10),
    rating,
    genres: includedLabels(relationships, included, "genres"),
    categories: includedLabels(relationships, included, "categories"),
    episodeCount: count(attributes.episodeCount),
    episodeLength: count(attributes.episodeLength),
    chapterCount: count(attributes.chapterCount),
    volumeCount: count(attributes.volumeCount),
  };
}

export class KitsuClient {
  private readonly searchCache = new Map<string, { storedAt: number; items: KitsuMedia[] }>();

  constructor(private readonly fetcher: typeof fetch = globalThis.fetch) {}

  async search(query: string, type: KitsuMediaType): Promise<KitsuMedia[]> {
    const clean = query.trim().replace(/\s+/g, " ").slice(0, 100);
    if (clean.length < 2) return [];
    return this.cachedSearch(type + ":text:" + clean.toLocaleLowerCase("en"), type, "text", clean);
  }

  async searchByCategory(category: string, type: KitsuMediaType): Promise<KitsuMedia[]> {
    const slug = category.trim().toLocaleLowerCase("en")
      .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 80);
    if (slug.length < 2) return [];
    return this.cachedSearch(type + ":category:" + slug, type, "categories", slug);
  }

  private async cachedSearch(
    key: string,
    type: KitsuMediaType,
    filter: "text" | "categories",
    value: string,
  ): Promise<KitsuMedia[]> {
    const cached = this.searchCache.get(key);
    if (cached && Date.now() - cached.storedAt < 5 * 60_000) return [...cached.items];

    const url = new URL(`https://kitsu.io/api/edge/${type}`);
    url.searchParams.set(`filter[${filter}]`, value);
    url.searchParams.set("page[limit]", "20");
    url.searchParams.set("include", "genres,categories");
    const response = await fetchProviderResponse(this.fetcher, url, {
      headers: {
        Accept: "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
      },
      signal: AbortSignal.timeout(10_000),
    });
    if (!response.ok) throw new Error(`Kitsu ${type} search returned HTTP ${response.status}.`);

    const payload = object(await response.json());
    const rows = Array.isArray(payload?.data) ? payload.data : [];
    const included = Array.isArray(payload?.included) ? payload.included : [];
    const items = rows.flatMap(raw => {
      const media = parseKitsuMedia(raw, included);
      return media ? [media] : [];
    }).slice(0, 20);

    this.searchCache.set(key, { storedAt: Date.now(), items });
    while (this.searchCache.size > 100) {
      const oldest = this.searchCache.keys().next().value;
      if (oldest === undefined) break;
      this.searchCache.delete(oldest);
    }
    return [...items];
  }
}
