import { fetchProviderResponse } from "./provider-http.js";
import { normalizeBibliographicIsbn } from "./crossref.js";

export interface OpenLibraryEdition {
  id: string;
  title: string;
  sourceUrl: string;
  isbn10: string[];
  isbn13: string[];
  publishDate: string | null;
  editionName: string | null;
}

export interface OpenLibraryWork {
  workId: string;
  title: string;
  authors: string[];
  firstPublishYear: number | null;
  editionCount: number | null;
  subjects: string[];
  publishers: string[];
  languages: string[];
  isbn10: string[];
  isbn13: string[];
  coverUrl: string | null;
  sourceUrl: string;
}

export interface OpenLibraryEditionFamily {
  workId: string;
  workUrl: string;
  editionCount: number;
  editions: OpenLibraryEdition[];
  truncated: boolean;
}

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as JsonObject
    : null;
}

function strings(value: unknown, maximum = 20): string[] {
  return (Array.isArray(value) ? value : []).flatMap((entry): string[] =>
    typeof entry === "string" && entry.trim() ? [entry.trim().slice(0, 100)] : [],
  ).slice(0, maximum);
}

function bibliographicIsbns(value: unknown, length: 10 | 13): string[] {
  return [...new Set(strings(value, 100).flatMap(entry => {
    const isbn = normalizeBibliographicIsbn(entry);
    return isbn && isbn.length === length ? [isbn] : [];
  }))].slice(0, 5);
}

function parseWork(value: unknown): OpenLibraryWork | null {
  const item = object(value);
  const key = item?.key;
  if (typeof key !== "string" || !/^\/works\/OL\d+W$/.test(key)) return null;
  const title = typeof item?.title === "string" && item.title.trim() ? item.title.trim().slice(0, 240) : null;
  if (!title) return null;
  const isbnValues = strings(item?.isbn, 100).flatMap(value => {
    const isbn = normalizeBibliographicIsbn(value);
    return isbn ? [isbn] : [];
  });
  const coverId = typeof item?.cover_i === "number" && Number.isSafeInteger(item.cover_i) && item.cover_i > 0 ? item.cover_i : null;
  const firstPublishYear = typeof item?.first_publish_year === "number" && Number.isInteger(item.first_publish_year) ? item.first_publish_year : null;
  const editionCount = typeof item?.edition_count === "number" && Number.isInteger(item.edition_count) ? Math.max(0, item.edition_count) : null;
  return {
    workId: key.slice("/works/".length),
    title,
    authors: strings(item?.author_name, 12).length
      ? strings(item?.author_name, 12)
      : (Array.isArray(item?.authors) ? item.authors.flatMap(value => {
          const author = object(value);
          return typeof author?.name === "string" && author.name.trim() ? [author.name.trim().slice(0, 100)] : [];
        }).slice(0, 12) : []),
    firstPublishYear,
    editionCount,
    subjects: strings(item?.subject, 16),
    publishers: strings(item?.publisher, 8),
    languages: strings(item?.language, 8).map(value => value.split("/").filter(Boolean).at(-1) ?? value),
    isbn10: isbnValues.filter(value => value.length === 10).slice(0, 5),
    isbn13: isbnValues.filter(value => value.length === 13).slice(0, 5),
    coverUrl: coverId ? "https://covers.openlibrary.org/b/id/" + coverId + "-M.jpg" : null,
    sourceUrl: "https://openlibrary.org" + key,
  };
}

function parseEdition(value: unknown): OpenLibraryEdition | null {
  const item = object(value);
  const key = item?.key;
  if (typeof key !== "string" || !/^\/books\/OL\d+M$/.test(key)) return null;
  const title = typeof item?.title === "string" && item.title.trim() ? item.title.trim() : "Untitled edition";
  const id = key.slice("/books/".length);
  return {
    id,
    title: title.slice(0, 240),
    sourceUrl: "https://openlibrary.org" + key,
    isbn10: bibliographicIsbns(item?.isbn_10, 10),
    isbn13: bibliographicIsbns(item?.isbn_13, 13),
    publishDate: typeof item?.publish_date === "string" ? item.publish_date.slice(0, 80) : null,
    editionName: typeof item?.edition_name === "string" && item.edition_name.trim()
      ? item.edition_name.trim().slice(0, 120)
      : null,
  };
}

export class OpenLibraryClient {
  private requestQueue: Promise<void> = Promise.resolve();
  private lastRequestAt = 0;
  private readonly searchCache = new Map<string, { storedAt: number; items: OpenLibraryWork[] }>();

  constructor(
    private readonly fetcher: typeof fetch = globalThis.fetch,
    private readonly minimumIntervalMs = 1_100,
  ) {}

  async searchTitle(value: string): Promise<OpenLibraryWork[]> {
    const title = value.trim().replace(/\s+/g, " ").slice(0, 120);
    if (title.length < 2) return [];
    return this.cachedSearch("title:" + title.toLocaleLowerCase("en"), async () => {
      const url = new URL("https://openlibrary.org/search.json");
      url.searchParams.set("title", title);
      url.searchParams.set("limit", "10");
      url.searchParams.set("fields", "key,title,author_name,first_publish_year,edition_count,subject,publisher,language,isbn,cover_i");
      const payload = object(await this.requestJson(url.toString()));
      const rows = Array.isArray(payload?.docs) ? payload.docs : [];
      return rows.flatMap((row): OpenLibraryWork[] => {
        const work = parseWork(row);
        return work ? [work] : [];
      });
    });
  }

  async searchBySubject(value: string): Promise<OpenLibraryWork[]> {
    const subject = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 80);
    if (subject.length < 2) return [];
    return this.cachedSearch("subject:" + subject, async () => {
      const url = "https://openlibrary.org/subjects/" + encodeURIComponent(subject) + ".json?limit=10";
      const payload = object(await this.requestJson(url));
      const rows = Array.isArray(payload?.works) ? payload.works : [];
      return rows.flatMap((row): OpenLibraryWork[] => {
        const work = parseWork(row);
        return work ? [work] : [];
      });
    });
  }

  private async cachedSearch(key: string, load: () => Promise<OpenLibraryWork[]>): Promise<OpenLibraryWork[]> {
    const existing = this.searchCache.get(key);
    if (existing && Date.now() - existing.storedAt < 10 * 60_000) return [...existing.items];
    const items = await load();
    this.searchCache.set(key, { storedAt: Date.now(), items });
    while (this.searchCache.size > 100) {
      const oldest = this.searchCache.keys().next().value;
      if (oldest === undefined) break;
      this.searchCache.delete(oldest);
    }
    return [...items];
  }

  async findEditionFamily(value: string): Promise<OpenLibraryEditionFamily | null> {
    const isbn = normalizeBibliographicIsbn(value);
    if (!isbn) return null;
    const edition = object(await this.requestJson("https://openlibrary.org/isbn/" + encodeURIComponent(isbn) + ".json"));
    const rawWorks = Array.isArray(edition?.works) ? edition.works : [];
    const workIds = [...new Set(rawWorks.flatMap((raw): string[] => {
      const key = object(raw)?.key;
      return typeof key === "string" && /^\/works\/OL\d+W$/.test(key) ? [key.slice("/works/".length)] : [];
    }))];
    if (workIds.length !== 1) return null;
    const workId = workIds[0]!;
    const workUrl = "https://openlibrary.org/works/" + workId;
    const payload = object(await this.requestJson(workUrl + "/editions.json?limit=50"));
    const rows = Array.isArray(payload?.entries) ? payload.entries : [];
    const editions = rows.flatMap((raw): OpenLibraryEdition[] => {
      const item = parseEdition(raw);
      return item ? [item] : [];
    });
    const size = typeof payload?.size === "number" && Number.isSafeInteger(payload.size)
      ? Math.max(0, payload.size)
      : editions.length;
    return {
      workId,
      workUrl,
      editionCount: size,
      editions: editions.slice(0, 50),
      truncated: size > editions.length,
    };
  }

  private async requestJson(url: string): Promise<unknown> {
    const previous = this.requestQueue;
    let release!: () => void;
    this.requestQueue = new Promise<void>((resolve) => { release = resolve; });
    await previous;
    try {
      const wait = Math.max(0, this.minimumIntervalMs - (Date.now() - this.lastRequestAt));
      if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));
      this.lastRequestAt = Date.now();
      const response = await fetchProviderResponse(this.fetcher, url, {
        headers: {
          Accept: "application/json",
          "User-Agent": "Lemegeton/3.0 (https://github.com/Kyerstorm/Lemegeton/issues)",
        },
        signal: AbortSignal.timeout(10_000),
      });
      if (!response.ok) throw new Error("Open Library returned HTTP " + response.status + ".");
      return await response.json();
    } finally {
      release();
    }
  }
}
