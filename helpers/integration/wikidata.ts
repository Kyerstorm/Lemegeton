import { fetchProviderResponse } from "./provider-http.js";

const ENTITY_API = "https://www.wikidata.org/w/api.php";
const QUERY_API = "https://query-next.wikidata.org/sparql";
const USER_AGENT = "Lemegeton/3.0 (https://github.com/Kyerstorm/Lemegeton)";
const CACHE_TTL_MS = 15 * 60_000;
const MAX_CACHE_ENTRIES = 200;

export interface WikidataEntity {
  id: string;
  label: string;
  description: string | null;
  url: string;
}

export type WikidataRelationKind = "sequence" | "organization";

export interface WikidataRelation {
  subjectId: string;
  objectId: string;
  subjectLabel: string | null;
  objectLabel: string | null;
  propertyId: string;
  kind: WikidataRelationKind;
}

type JsonObject = Record<string, unknown>;

const cache = new Map<string, { expiresAt: number; value: unknown }>();
let requestQueue: Promise<void> = Promise.resolve();
let nextRequestAt = 0;

function object(value: unknown): JsonObject | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as JsonObject
    : null;
}

function cleanString(value: unknown, limit = 500): string | null {
  return typeof value === "string" && value.trim() ? value.trim().slice(0, limit) : null;
}

function validQid(value: string): string | null {
  const match = /^Q[1-9]\d{0,11}$/i.exec(value.trim());
  return match ? match[0].toUpperCase() : null;
}

function cached<T>(key: string): T | null {
  const value = cache.get(key);
  if (!value) return null;
  if (value.expiresAt <= Date.now()) {
    cache.delete(key);
    return null;
  }
  return value.value as T;
}

function remember<T>(key: string, value: T): T {
  if (cache.size >= MAX_CACHE_ENTRIES) {
    const oldest = cache.keys().next().value;
    if (oldest) cache.delete(oldest);
  }
  cache.set(key, { value, expiresAt: Date.now() + CACHE_TTL_MS });
  return value;
}

function entityUrl(id: string): string {
  return "https://www.wikidata.org/wiki/" + id;
}

export function parseWikidataEntitySearch(payload: unknown): WikidataEntity[] {
  const rows = object(payload)?.search;
  if (!Array.isArray(rows)) return [];
  const seen = new Set<string>();
  return rows.flatMap((value): WikidataEntity[] => {
    const row = object(value);
    const id = typeof row?.id === "string" ? validQid(row.id) : null;
    const label = cleanString(row?.label, 200);
    if (!id || !label || seen.has(id)) return [];
    seen.add(id);
    return [{
      id,
      label,
      description: cleanString(row?.description, 500),
      url: entityUrl(id),
    }];
  }).slice(0, 20);
}

function entityIdFromUri(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const match = /^http:\/\/www\.wikidata\.org\/entity\/(Q[1-9]\d{0,11})$/i.exec(value);
  return match?.[1]?.toUpperCase() ?? null;
}

function propertyIdFromUri(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const match = /^http:\/\/www\.wikidata\.org\/prop\/direct\/(P[1-9]\d{0,8})$/i.exec(value);
  return match?.[1]?.toUpperCase() ?? null;
}

export function parseWikidataRelations(payload: unknown, kind: WikidataRelationKind): WikidataRelation[] {
  const bindings = object(object(payload)?.results)?.bindings;
  if (!Array.isArray(bindings)) return [];
  const unique = new Map<string, WikidataRelation>();
  for (const raw of bindings) {
    const row = object(raw);
    const subject = object(row?.subject);
    const property = object(row?.property);
    const target = object(row?.object);
    const subjectId = entityIdFromUri(subject?.value);
    const objectId = entityIdFromUri(target?.value);
    const propertyId = propertyIdFromUri(property?.value);
    if (!subjectId || !objectId || !propertyId) continue;
    const relation = {
      subjectId,
      objectId,
      subjectLabel: cleanString(object(row?.subjectLabel)?.value, 200),
      objectLabel: cleanString(object(row?.objectLabel)?.value, 200),
      propertyId,
      kind,
    };
    unique.set([subjectId, propertyId, objectId].join(":"), relation);
  }
  return [...unique.values()].slice(0, 40);
}

function relationQuery(id: string, properties: readonly string[]): string {
  const values = properties.map(property => "wdt:" + property).join(" ");
  return [
    "PREFIX wd: <http://www.wikidata.org/entity/>",
    "PREFIX wdt: <http://www.wikidata.org/prop/direct/>",
    "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>",
    "SELECT ?subject ?property ?object ?subjectLabel ?objectLabel WHERE {",
    "  VALUES ?property { " + values + " }",
    "  { BIND(wd:" + id + " AS ?subject) ?subject ?property ?object . }",
    "  UNION",
    "  { ?subject ?property wd:" + id + " . BIND(wd:" + id + " AS ?object) }",
    '  OPTIONAL { ?subject rdfs:label ?subjectLabel . FILTER(LANG(?subjectLabel) = "en") }',
    '  OPTIONAL { ?object rdfs:label ?objectLabel . FILTER(LANG(?objectLabel) = "en") }',
    "}",
    "LIMIT 40",
  ].join("\n");
}

/**
 * Read-only Wikidata access. Queries use the current Query Service v2 host,
 * fixed property allowlists, bounded results and a process-wide request queue.
 */
export class WikidataClient {
  constructor(
    private readonly fetcher: typeof fetch = globalThis.fetch,
    private readonly minimumIntervalMs = 1_000,
  ) {}

  async searchEntities(query: string): Promise<WikidataEntity[]> {
    const term = query.trim().replace(/\s+/g, " ").slice(0, 100);
    if (term.length < 2) return [];
    const key = "search:" + term.toLocaleLowerCase("en-US");
    const hit = cached<WikidataEntity[]>(key);
    if (hit) return hit;

    const url = new URL(ENTITY_API);
    url.search = new URLSearchParams({
      action: "wbsearchentities",
      search: term,
      language: "en",
      uselang: "en",
      type: "item",
      limit: "10",
      format: "json",
    }).toString();
    return remember(key, await this.request(url, parseWikidataEntitySearch));
  }

  async sequenceRelations(value: string): Promise<WikidataRelation[]> {
    return this.fetchRelations(value, "sequence", ["P155", "P156", "P179"]);
  }

  async organizationRelations(value: string): Promise<WikidataRelation[]> {
    return this.fetchRelations(value, "organization", ["P749", "P355"]);
  }

  private async fetchRelations(
    value: string,
    kind: WikidataRelationKind,
    properties: readonly string[],
  ): Promise<WikidataRelation[]> {
    const id = validQid(value);
    if (!id) throw new TypeError("Wikidata identifiers must use a valid QID such as Q42.");
    const key = kind + ":" + id;
    const hit = cached<WikidataRelation[]>(key);
    if (hit) return hit;

    const url = new URL(QUERY_API);
    url.searchParams.set("query", relationQuery(id, properties));
    url.searchParams.set("format", "json");
    return remember(key, await this.request(url, payload => parseWikidataRelations(payload, kind)));
  }

  private async request<T>(url: URL, parse: (payload: unknown) => T): Promise<T> {
    const previous = requestQueue;
    let release!: () => void;
    requestQueue = new Promise<void>(resolve => { release = resolve; });
    await previous;
    try {
      const wait = Math.max(0, this.minimumIntervalMs - (Date.now() - nextRequestAt));
      if (wait > 0) await new Promise(resolve => setTimeout(resolve, wait));
      nextRequestAt = Date.now();
      const response = await fetchProviderResponse(this.fetcher, url, {
        headers: {
          Accept: "application/sparql-results+json, application/json;q=0.9",
          "User-Agent": USER_AGENT,
        },
        signal: AbortSignal.timeout(12_000),
      }, { maxAttempts: 2, maxRetryDelayMs: 2_000 });
      if (!response.ok) throw new Error("Wikidata returned HTTP " + response.status + ".");
      return parse(await response.json());
    } finally {
      release();
    }
  }
}
