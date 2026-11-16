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
    isbn10: strings(item?.isbn_10),
    isbn13: strings(item?.isbn_13),
    publishDate: typeof item?.publish_date === "string" ? item.publish_date.slice(0, 80) : null,
    editionName: typeof item?.edition_name === "string" && item.edition_name.trim()
      ? item.edition_name.trim().slice(0, 120)
      : null,
  };
}

export class OpenLibraryClient {
  private requestQueue: Promise<void> = Promise.resolve();
  private lastRequestAt = 0;

  constructor(
    private readonly fetcher: typeof fetch = globalThis.fetch,
    private readonly minimumIntervalMs = 1_100,
  ) {}

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
