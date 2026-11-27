import { fetchProviderResponse } from "./provider-http.js";

export interface CrossrefContributor {
  name: string;
  orcid: string | null;
}

export interface CrossrefBookMatch {
  doi: string;
  title: string;
  type: string | null;
  isbns: string[];
  editors: CrossrefContributor[];
  translators: CrossrefContributor[];
  sourceUrl: string;
}

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as JsonObject
    : null;
}

export function normalizeBibliographicIsbn(value: string): string | null {
  const isbn = value.trim()
    .replace(/^isbn(?:[-\s]?(?:10|13))?\s*[:#]?\s*/i, "")
    .replace(/[\s-]/g, "")
    .toUpperCase();
  if (/^\d{9}[\dX]$/.test(isbn)) {
    const checksum = [...isbn].reduce((sum, digit, index) =>
      sum + (10 - index) * (digit === "X" ? 10 : Number(digit)), 0);
    return checksum % 11 === 0 ? isbn : null;
  }
  if (/^\d{13}$/.test(isbn)) {
    const sum = [...isbn.slice(0, 12)].reduce((total, digit, index) =>
      total + Number(digit) * (index % 2 === 0 ? 1 : 3), 0);
    const checkDigit = (10 - (sum % 10)) % 10;
    return Number(isbn[12]) === checkDigit ? isbn : null;
  }
  return null;
}

function contributors(value: unknown): CrossrefContributor[] {
  return (Array.isArray(value) ? value : []).flatMap((raw): CrossrefContributor[] => {
    const item = object(raw);
    if (!item) return [];
    const name = typeof item.name === "string" && item.name.trim()
      ? item.name.trim()
      : [item.given, item.family]
        .filter((part): part is string => typeof part === "string" && Boolean(part.trim()))
        .join(" ").trim();
    if (!name) return [];
    const orcid = typeof item.ORCID === "string" && /^https:\/\/orcid\.org\/\d{4}-\d{4}-\d{4}-[\dX]{4}$/i.test(item.ORCID)
      ? item.ORCID
      : null;
    return [{ name: name.slice(0, 180), orcid }];
  }).slice(0, 30);
}

export function parseCrossrefBookMatches(value: unknown, requestedIsbn: string): CrossrefBookMatch[] {
  const isbn = normalizeBibliographicIsbn(requestedIsbn);
  if (!isbn) return [];
  const message = object(object(value)?.message);
  const rows = Array.isArray(message?.items) ? message.items : [];
  const matches = new Map<string, CrossrefBookMatch>();
  for (const raw of rows) {
    const item = object(raw);
    if (!item || typeof item.DOI !== "string" || !/^10\.\d{4,9}\/.+$/i.test(item.DOI)) continue;
    const isbns = (Array.isArray(item.ISBN) ? item.ISBN : []).flatMap((entry): string[] => {
      if (typeof entry !== "string") return [];
      const normal = normalizeBibliographicIsbn(entry);
      return normal ? [normal] : [];
    });
    if (!isbns.includes(isbn)) continue;
    const titleValue = Array.isArray(item.title) ? item.title[0] : item.title;
    if (typeof titleValue !== "string" || !titleValue.trim()) continue;
    const doi = item.DOI.trim();
    matches.set(doi.toLowerCase(), {
      doi,
      title: titleValue.trim().slice(0, 240),
      type: typeof item.type === "string" ? item.type.slice(0, 80) : null,
      isbns,
      editors: contributors(item.editor),
      translators: contributors(item.translator),
      sourceUrl: new URL("https://doi.org/" + doi).toString(),
    });
  }
  return [...matches.values()].slice(0, 10);
}

export class CrossrefClient {
  private requestQueue: Promise<void> = Promise.resolve();
  private lastRequestAt = 0;

  constructor(
    private readonly fetcher: typeof fetch = globalThis.fetch,
    private readonly minimumIntervalMs = 1_100,
  ) {}

  async findByIsbn(value: string): Promise<CrossrefBookMatch[]> {
    const isbn = normalizeBibliographicIsbn(value);
    if (!isbn) return [];
    const previous = this.requestQueue;
    let release!: () => void;
    this.requestQueue = new Promise<void>((resolve) => { release = resolve; });
    await previous;
    try {
      const wait = Math.max(0, this.minimumIntervalMs - (Date.now() - this.lastRequestAt));
      if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));
      this.lastRequestAt = Date.now();
      const url = new URL("https://api.crossref.org/works");
      url.searchParams.set("filter", "isbn:" + isbn);
      url.searchParams.set("rows", "20");
      url.searchParams.set("select", "DOI,title,type,ISBN,editor,translator");
      const response = await fetchProviderResponse(this.fetcher, url, {
        headers: {
          Accept: "application/json",
          "User-Agent": "Lemegeton/3.0 (https://github.com/Kyerstorm/Lemegeton)",
        },
        signal: AbortSignal.timeout(10_000),
      });
      if (!response.ok) throw new Error("Crossref returned HTTP " + response.status + ".");
      return parseCrossrefBookMatches(await response.json(), isbn);
    } finally {
      release();
    }
  }
}
