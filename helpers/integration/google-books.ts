export interface GoogleBook {
  id: string;
  title: string;
  subtitle: string | null;
  authors: string[];
  publisher: string | null;
  publishedDate: string | null;
  description: string | null;
  pageCount: number | null;
  categories: string[];
  mainCategory: string | null;
  language: string | null;
  printType: string | null;
  isbn: string | null;
  isbn10: string | null;
  isbn13: string | null;
  seriesBookTitle: string | null;
  seriesDisplayNumber: string | null;
  seriesOrder: number | null;
  seriesId: string | null;
  seriesBookType: string | null;
  sourceUrl: string;
  previewUrl: string | null;
  infoUrl: string | null;
  image: string | null;
}

type RecordValue = Record<string, unknown>;

function object(value: unknown): RecordValue | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as RecordValue
    : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function positiveNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0
    ? value
    : null;
}

function googleBooksUrl(value: unknown): string | null {
  const raw = stringValue(value);
  if (!raw) return null;
  try {
    const url = new URL(raw);
    const hostname = url.hostname.toLowerCase();
    const trustedHost = hostname === "google.com" || hostname.endsWith(".google.com")
      || hostname === "googleusercontent.com" || hostname.endsWith(".googleusercontent.com");
    return url.protocol === "https:" && trustedHost && !url.username && !url.password
      ? url.toString()
      : null;
  } catch {
    return null;
  }
}

function normalizeVolume(value: unknown): GoogleBook | null {
  const item = object(value);
  const volume = object(item?.volumeInfo);
  const id = stringValue(item?.id);
  const title = stringValue(volume?.title);
  if (!id || !title || !volume) return null;

  const identifiers = Array.isArray(volume.industryIdentifiers) ? volume.industryIdentifiers : [];
  let isbn10: string | null = null;
  let isbn13: string | null = null;
  for (const rawIdentifier of identifiers) {
    const identifier = object(rawIdentifier);
    const value = stringValue(identifier?.identifier);
    if (!value) continue;
    if (identifier?.type === "ISBN_13" && !isbn13) isbn13 = value;
    if (identifier?.type === "ISBN_10" && !isbn10) isbn10 = value;
  }

  const series = object(volume.seriesInfo);
  const volumeSeries = Array.isArray(series?.volumeSeries) ? series.volumeSeries : [];
  const firstSeries = volumeSeries.map(object).find((entry) => entry !== null) ?? null;
  const imageLinks = object(volume.imageLinks);

  return {
    id,
    title,
    subtitle: stringValue(volume.subtitle),
    authors: Array.isArray(volume.authors)
      ? volume.authors.flatMap((author) => stringValue(author) ?? [])
      : [],
    publisher: stringValue(volume.publisher),
    publishedDate: stringValue(volume.publishedDate),
    description: stringValue(volume.description),
    pageCount: typeof volume.pageCount === "number" && Number.isSafeInteger(volume.pageCount)
      && volume.pageCount >= 0 ? volume.pageCount : null,
    categories: Array.isArray(volume.categories)
      ? volume.categories.flatMap((category) => stringValue(category) ?? [])
      : [],
    mainCategory: stringValue(volume.mainCategory),
    language: stringValue(volume.language),
    printType: stringValue(volume.printType),
    isbn10,
    isbn13,
    isbn: isbn13 ?? isbn10,
    seriesBookTitle: stringValue(series?.shortSeriesBookTitle),
    seriesDisplayNumber: stringValue(series?.bookDisplayNumber),
    seriesOrder: positiveNumber(firstSeries?.orderNumber),
    seriesId: stringValue(firstSeries?.seriesId),
    seriesBookType: stringValue(firstSeries?.seriesBookType),
    sourceUrl: "https://books.google.com/books?id=" + encodeURIComponent(id),
    previewUrl: googleBooksUrl(volume.previewLink),
    infoUrl: googleBooksUrl(volume.infoLink),
    image: googleBooksUrl(imageLinks?.thumbnail),
  };
}

export class GoogleBooksClient {
  constructor(private readonly apiKey?: string) {}

  async searchBySubject(subject: string): Promise<GoogleBook[]> {
    const clean = subject.trim().replace(/\s+/g, " ").slice(0, 80);
    if (!clean || !/[a-z0-9]/i.test(clean) || /["<>]/.test(clean)) {
      throw new Error("Google Books subject must be a valid non-empty category.");
    }
    return this.search("subject:" + clean);
  }

  async search(query: string): Promise<GoogleBook[]> {
    const cleanQuery = query.trim().replace(/\s+/g, " ").slice(0, 200);
    if (!cleanQuery) return [];

    const url = new URL("https://www.googleapis.com/books/v1/volumes");
    url.searchParams.set("q", cleanQuery);
    url.searchParams.set("maxResults", "10");
    url.searchParams.set("printType", "books");
    url.searchParams.set("projection", "full");
    if (this.apiKey) url.searchParams.set("key", this.apiKey);

    const response = await fetch(url, { signal: AbortSignal.timeout(10_000) });
    if (!response.ok) throw new Error("Google Books returned HTTP " + response.status + ".");
    const payload = object(await response.json());
    const items = Array.isArray(payload?.items) ? payload.items : [];
    return items.flatMap((item) => {
      const normalized = normalizeVolume(item);
      return normalized ? [normalized] : [];
    });
  }
}
