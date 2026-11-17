import { isIP } from "node:net";
import { load } from "cheerio";
import { chromium } from "playwright-core";
import robotsParser from "robots-parser";
import { XMLParser, XMLValidator } from "fast-xml-parser";

export const DEFAULT_MAX_TEXT_CHARS = 12_000;
export const MAX_TEXT_CHARS = 40_000;
export const MAX_SELECTOR_RESULTS = 50;
export const MAX_LINK_RESULTS = 50;
export const MAX_RESPONSE_BYTES = 5 * 1024 * 1024;
export const MAX_CRAWL_PAGES = 500;
export const DEFAULT_TIMEOUT_MS = 20_000;
export const DEFAULT_USER_AGENT = "Lemegeton/3.1 (media discovery scraper)";

export class ScrapeError extends Error {
constructor(message: string) {
super(message);
this.name = "ScrapeError";
}
}

export class ScrapeBlockedError extends ScrapeError {
constructor(message: string) {
super(message);
this.name = "ScrapeBlockedError";
}
}

export class ScrapeRequestError extends ScrapeError {
constructor(message: string) {
super(message);
this.name = "ScrapeRequestError";
}
}

export type ScrapeEngine = "http" | "browser";

export interface ScrapeOptions {
engine?: ScrapeEngine;
selectors?: Record<string, string>;
includeText?: boolean;
maxTextChars?: number;
includeStructuredData?: boolean;
maxResponseBytes?: number;
includeLinks?: boolean;
linkSelector?: string;
includeHtml?: boolean;
timeoutMs?: number;
retries?: number;
headers?: Record<string, string>;
method?: "GET" | "POST";
body?: BodyInit | null;
fetchImpl?: typeof fetch;
}

export interface ScrapeResult {
url: string;
canonicalUrl: string;
title: string;
description: string;
fields: Record<string, string | string[]>;
engine: "fetch" | "playwright";
statusCode: number;
text?: string;
structuredData?: Record<string, unknown>[];
links?: Array<{ text: string; url: string }>;
html?: string;
}

export type ScrapeManyResult =
| { url: string; result: ScrapeResult }
| { url: string; error: string; blocked: boolean };

function isPrivateIp(hostname: string): boolean {
const ipVersion = isIP(hostname);
if (ipVersion === 4) {
const octets = hostname.split(".").map(Number);
return octets[0] === 0
|| octets[0] === 10
|| octets[0] === 127
|| (octets[0] === 169 && octets[1] === 254)
|| (octets[0] === 172 && octets[1]! >= 16 && octets[1]! <= 31)
|| (octets[0] === 192 && octets[1] === 168)
|| octets[0]! >= 224;
}
if (ipVersion === 6) {
const value = hostname.toLowerCase();
return value === "::"
|| value === "::1"
|| value.startsWith("fc")
|| value.startsWith("fd")
|| value.startsWith("fe8")
|| value.startsWith("fe9")
|| value.startsWith("fea")
|| value.startsWith("feb")
|| value.startsWith("ff");
}
return false;
}

export function validatePublicHttpUrl(value: string): URL {
let url: URL;
try {
url = new URL(value);
} catch {
throw new TypeError("A complete HTTP(S) URL is required.");
}
if (url.protocol !== "http:" && url.protocol !== "https:") {
throw new TypeError("Only HTTP(S) URLs can be scraped.");
}
if (url.username || url.password) {
throw new TypeError("URLs containing embedded credentials are not supported.");
}
if (url.port && url.port !== "80" && url.port !== "443") {
throw new TypeError("Only standard HTTP(S) ports are supported.");
}
const hostname = url.hostname.toLowerCase().replace(/^\[/, "").replace(/\]$/, "").replace(/\.$/, "");
if (!hostname || hostname === "localhost" || hostname.endsWith(".localhost") || hostname.endsWith(".local") || hostname.endsWith(".internal")) {
throw new TypeError("Local and internal hosts are not supported.");
}
if (isPrivateIp(hostname)) {
throw new TypeError("Private or reserved IP addresses are not supported.");
}
return url;
}

function challengeReason(status: number, body: string, headers: Headers): string | null {
if (headers.get("cf-mitigated")?.toLowerCase() === "challenge") return "Cloudflare challenge response";
if (status === 429) return "HTTP 429 rate limit";
if (status === 401 || status === 403) return "HTTP " + status + " access response";
const lower = body.toLowerCase();
const server = (headers.get("server") ?? "").toLowerCase();
if (lower.includes("cf-chl-") || lower.includes("challenge-platform") || lower.includes("cdn-cgi/challenge-platform") || lower.includes("just a moment...") || lower.includes("verify you are human") || lower.includes("captcha-container") || lower.includes("g-recaptcha") || lower.includes("h-captcha") || lower.includes("cf-turnstile")) {
return "access challenge";
}
if ((status === 503 || status === 522 || status === 524) && server.includes("cloudflare")) {
return "Cloudflare unavailable or challenged";
}
return null;
}

async function readBoundedBody(response: Response, maxBytes: number): Promise<string> {
if (!response.body) return "";
const reader = response.body.getReader();
const chunks: Uint8Array[] = [];
let total = 0;
try {
while (true) {
const part = await reader.read();
if (part.done) break;
total += part.value.byteLength;
if (total > maxBytes) {
await reader.cancel();
throw new ScrapeRequestError("The response exceeded the " + maxBytes + "-byte limit.");
}
chunks.push(part.value);
}
} finally {
reader.releaseLock();
}
const result = new Uint8Array(total);
let offset = 0;
for (const chunk of chunks) {
result.set(chunk, offset);
offset += chunk.byteLength;
}
return new TextDecoder("utf-8", { fatal: false }).decode(result);
}

interface ResourceResponse {
url: string;
status: number;
headers: Headers;
text: string;
}

async function fetchResource(
input: string,
options: { timeoutMs?: number; retries?: number; headers?: Record<string, string>; method?: "GET" | "POST"; body?: BodyInit | null; fetchImpl?: typeof fetch; maxBytes?: number } = {},
): Promise<ResourceResponse> {
let current = validatePublicHttpUrl(input);
const timeoutMs = Math.max(1_000, Math.min(options.timeoutMs ?? DEFAULT_TIMEOUT_MS, 60_000));
const retries = Math.max(0, Math.min(options.retries ?? 1, 4));
const fetchImpl = options.fetchImpl ?? fetch;
for (let redirects = 0; redirects <= 5; redirects++) {
let lastError: unknown;
for (let attempt = 0; attempt <= retries; attempt++) {
try {
const response = await fetchImpl(current, {
method: options.method ?? "GET",
...(options.body !== undefined ? { body: options.body } : {}),
redirect: "manual",
headers: {
"User-Agent": DEFAULT_USER_AGENT,
"Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
...options.headers,
},
signal: AbortSignal.timeout(timeoutMs),
});
if ([301, 302, 303, 307, 308].includes(response.status)) {
const location = response.headers.get("location");
if (!location) throw new ScrapeRequestError("A redirect did not include a Location header.");
if (redirects === 5) throw new ScrapeRequestError("The page exceeded the five-redirect limit.");
current = validatePublicHttpUrl(new URL(location, current).toString());
lastError = null;
break;
}
const contentType = (response.headers.get("content-type") ?? "").toLowerCase();
const text = await readBoundedBody(response, options.maxBytes ?? MAX_RESPONSE_BYTES);
const reason = challengeReason(response.status, text, response.headers);
if (reason) throw new ScrapeBlockedError("Scraping stopped after " + reason + ".");
if (!response.ok) {
if (response.status >= 500 && attempt < retries) {
await new Promise(resolve => setTimeout(resolve, Math.min(500 * 2 ** attempt, 4_000)));
continue;
}
throw new ScrapeRequestError("HTTP " + response.status + " returned for " + current.toString() + ".");
}
return { url: current.toString(), status: response.status, headers: response.headers, text };
} catch (error) {
if (error instanceof ScrapeError || error instanceof TypeError) throw error;
lastError = error;
if (attempt < retries) {
await new Promise(resolve => setTimeout(resolve, Math.min(500 * 2 ** attempt, 4_000)));
}
}
}
if (lastError) {
throw new ScrapeRequestError("Request failed for " + current.toString() + ": " + (lastError instanceof Error ? lastError.message : String(lastError)));
}
}
throw new ScrapeRequestError("Redirect handling failed for " + input + ".");
}

const xmlParser = new XMLParser({
ignoreAttributes: false,
attributeNamePrefix: "@",
cdataPropName: "__cdata",
parseTagValue: false,
parseAttributeValue: false,
processEntities: false,
htmlEntities: false,
allowBooleanAttributes: false,
trimValues: true,
removeNSPrefix: false,
});

export function parseXmlDocument(xml: string): unknown {
if (Buffer.byteLength(xml, "utf8") > MAX_RESPONSE_BYTES) {
throw new ScrapeRequestError("The XML document exceeded the " + MAX_RESPONSE_BYTES + "-byte limit.");
}
if (/<!DOCTYPE|<!ENTITY/i.test(xml)) {
throw new ScrapeRequestError("XML documents containing DTD or entity declarations are not supported.");
}
const validation = XMLValidator.validate(xml);
if (validation !== true) throw new ScrapeRequestError("The provider returned invalid XML.");
try {
return xmlParser.parse(xml);
} catch {
throw new ScrapeRequestError("The provider returned XML that could not be parsed.");
}
}

export async function fetchXml<T = unknown>(
url: string,
options: Omit<ScrapeOptions, "engine" | "selectors" | "includeLinks" | "includeText" | "includeHtml" | "includeStructuredData"> = {},
): Promise<T> {
const response = await fetchResource(url, {
timeoutMs: options.timeoutMs,
retries: options.retries,
headers: options.headers,
method: options.method,
body: options.body,
fetchImpl: options.fetchImpl,
maxBytes: options.maxResponseBytes ?? MAX_RESPONSE_BYTES,
});
const contentType = (response.headers.get("content-type") ?? "").toLowerCase();
if (contentType && !/(?:xml|rss|atom)/i.test(contentType)) {
throw new ScrapeRequestError("Expected XML from " + response.url + ", received " + contentType + ".");
}
return parseXmlDocument(response.text) as T;
}

export function extractStructuredData(html: string): Record<string, unknown>[] {
const $ = load(html);
const records: Record<string, unknown>[] = [];
$("script[type='application/ld+json']").each((_, node) => {
if (records.length >= 30) return;
const raw = $(node).text().trim();
if (!raw || Buffer.byteLength(raw, "utf8") > 256 * 1024) return;
try {
const parsed: unknown = JSON.parse(raw);
const append = (value: unknown): void => {
if (records.length >= 30 || !value || typeof value !== "object" || Array.isArray(value)) return;
const record = value as Record<string, unknown>;
records.push(record);
if (Array.isArray(record["@graph"])) for (const item of record["@graph"] as unknown[]) append(item);
};
if (Array.isArray(parsed)) for (const value of parsed) append(value);
else append(parsed);
} catch {
// Malformed third-party JSON-LD is ignored while ordinary extraction continues.
}
});
return records;
}

export async function fetchSitemapUrls(
sitemapUrl: string,
options: { maxUrls?: number; allowedDomains?: string[]; timeoutMs?: number; fetchImpl?: typeof fetch } = {},
): Promise<string[]> {
const start = validatePublicHttpUrl(sitemapUrl);
const maxUrls = Math.max(1, Math.min(Math.floor(options.maxUrls ?? 500), MAX_CRAWL_PAGES));
const allowed = new Set((options.allowedDomains?.length ? options.allowedDomains : [start.hostname])
.map(value => value.toLowerCase().replace(/^www\\./, "")));
const payload = await fetchXml<Record<string, unknown>>(start.toString(), {
timeoutMs: options.timeoutMs ?? 10_000,
retries: 0,
fetchImpl: options.fetchImpl,
maxResponseBytes: MAX_RESPONSE_BYTES,
});
const isIndex = Boolean(payload.sitemapindex);
const root = isIndex ? payload.sitemapindex : payload.urlset;
if (!root || typeof root !== "object" || Array.isArray(root)) return [];
const rootObject = root as Record<string, unknown>;
const key = isIndex ? "sitemap" : "url";
const entries = Array.isArray(rootObject[key]) ? rootObject[key] as unknown[] : rootObject[key] ? [rootObject[key]] : [];
const urls: string[] = [];
for (const entry of entries) {
if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
const loc = (entry as Record<string, unknown>).loc;
if (typeof loc !== "string") continue;
try {
const target = validatePublicHttpUrl(new URL(loc, start).toString());
const host = target.hostname.toLowerCase().replace(/^www\\./, "");
if (![...allowed].some(domain => host === domain || host.endsWith("." + domain))) continue;
urls.push(target.toString());
if (urls.length >= maxUrls) break;
} catch {
// Invalid and out-of-scope sitemap locations are ignored.
}
}
return [...new Set(urls)];
}

function extractPageData(url: string, html: string, statusCode: number, engine: "fetch" | "playwright", options: ScrapeOptions): ScrapeResult {
if (Buffer.byteLength(html, "utf8") > MAX_RESPONSE_BYTES) {
throw new ScrapeRequestError("The page exceeded the " + MAX_RESPONSE_BYTES + "-byte limit.");
}
const $ = load(html);
const readMeta = (...selectors: string[]): string => {
for (const selector of selectors) {
const value = $(selector).first().attr("content")?.trim();
if (value) return value;
}
return "";
};
const title = $("title").first().text().trim() || readMeta('meta[property="og:title"]');
const description = readMeta('meta[name="description"]', 'meta[property="og:description"]', 'meta[name="twitter:description"]');
const canonical = $('link[rel="canonical"][href]').first().attr("href");
const canonicalUrl = canonical ? new URL(canonical, url).toString() : url;
const fields: Record<string, string | string[]> = {};
for (const [name, selector] of Object.entries(options.selectors ?? {})) {
try {
const values = $(selector).slice(0, MAX_SELECTOR_RESULTS).toArray()
.map(node => $(node).text().replace(/\s+/g, " ").trim())
.filter(Boolean)
.map(value => value.slice(0, MAX_TEXT_CHARS));
if (values.length === 1) fields[name.slice(0, 100)] = values[0]!;
else if (values.length > 1) fields[name.slice(0, 100)] = values;
} catch {
// An invalid optional selector does not prevent the other fields from being extracted.
}
}
const result: ScrapeResult = {
url,
canonicalUrl,
title,
description,
fields,
engine,
statusCode,
};
if (options.includeStructuredData) result.structuredData = extractStructuredData(html);
if (options.includeText !== false) {
const textPage = load(html);
textPage("script,style,noscript,svg,template").remove();
const max = Math.max(1, Math.min(options.maxTextChars ?? DEFAULT_MAX_TEXT_CHARS, MAX_TEXT_CHARS));
result.text = textPage("body").text().replace(/\s+/g, " ").trim().slice(0, max);
}
if (options.includeLinks) {
const selector = options.linkSelector?.trim() || "a[href]";
const links: Array<{ text: string; url: string }> = [];
try {
for (const node of $(selector).toArray()) {
if (links.length >= MAX_LINK_RESULTS) break;
const link = $(node).is("a[href]") ? $(node) : $(node).find("a[href]").first();
const href = link.attr("href")?.trim();
if (!href) continue;
let target: URL;
try {
target = validatePublicHttpUrl(new URL(href, url).toString());
} catch {
continue;
}
const text = (link.text().trim() || link.attr("title") || link.attr("aria-label") || "").replace(/\s+/g, " ").slice(0, 200);
links.push({ text, url: target.toString() });
}
} catch {
// Return any fields already extracted if an optional link selector is invalid.
}
result.links = links;
}
if (options.includeHtml) result.html = html;
return result;
}

async function fetchBrowserPage(url: string, options: ScrapeOptions): Promise<ScrapeResult> {
const browser = process.env.BROWSER_WS_ENDPOINT
? await chromium.connectOverCDP(process.env.BROWSER_WS_ENDPOINT)
: await chromium.launch({
headless: true,
...(process.env.CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.CHROMIUM_EXECUTABLE_PATH } : {}),
args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const context = await browser.newContext({ userAgent: DEFAULT_USER_AGENT, serviceWorkers: "block" });
try {
const page = await context.newPage();
await page.route("**/*", async route => {
const request = route.request();
const requestUrl = request.url();
if (!requestUrl.startsWith("http://") && !requestUrl.startsWith("https://")) {
await route.continue();
return;
}
if (["image", "font", "media"].includes(request.resourceType())) {
await route.abort();
return;
}
try {
validatePublicHttpUrl(requestUrl);
await route.continue();
} catch {
await route.abort();
}
});
const response = await page.goto(url, { waitUntil: "domcontentloaded", timeout: Math.max(1_000, Math.min(options.timeoutMs ?? DEFAULT_TIMEOUT_MS, 60_000)) });
if (!response) throw new ScrapeRequestError("The browser did not receive a page response.");
const html = await page.content();
const reason = challengeReason(response.status(), html, new Headers(response.headers()));
if (reason) throw new ScrapeBlockedError("Scraping stopped after " + reason + ".");
if (response.status() < 200 || response.status() >= 300) {
throw new ScrapeRequestError("Browser navigation returned HTTP " + response.status() + ".");
}
const finalUrl = validatePublicHttpUrl(page.url()).toString();
return extractPageData(finalUrl, html, response.status(), "playwright", options);
} finally {
await context.close();
await browser.close();
}
}
export async function fetchPublicPage(url: string, options: ScrapeOptions = {}): Promise<ScrapeResult> {
const validated = validatePublicHttpUrl(url);
if (options.engine === "browser") return fetchBrowserPage(validated.toString(), options);
const response = await fetchResource(validated.toString(), { ...options, maxBytes: options.maxResponseBytes ?? MAX_RESPONSE_BYTES });
const contentType = (response.headers.get("content-type") ?? "").toLowerCase();
if (contentType && !contentType.includes("text/html") && !contentType.includes("application/xhtml+xml")) {
throw new ScrapeRequestError("Expected HTML from " + response.url + ", received " + contentType + ".");
}
return extractPageData(response.url, response.text, response.status, "fetch", options);
}

export async function fetchJson<T = unknown>(url: string, options: Omit<ScrapeOptions, "engine" | "selectors" | "includeLinks" | "includeText" | "includeHtml"> = {}): Promise<T> {
const response = await fetchResource(url, { ...options, maxBytes: options.maxResponseBytes ?? MAX_RESPONSE_BYTES });
try {
return JSON.parse(response.text) as T;
} catch {
throw new ScrapeRequestError("The provider returned invalid JSON for " + response.url + ".");
}
}

export async function fetchMany(urls: string[], options: ScrapeOptions & { concurrency?: number } = {}): Promise<ScrapeManyResult[]> {
const concurrency = Math.max(1, Math.min(options.concurrency ?? 4, 8));
const results: ScrapeManyResult[] = [];
for (let index = 0; index < urls.length; index += concurrency) {
const batch = urls.slice(index, index + concurrency);
const settled = await Promise.all(batch.map(async url => {
try {
return { url, result: await fetchPublicPage(url, options) } as const;
} catch (error) {
return {
url,
error: error instanceof Error ? error.message : String(error),
blocked: error instanceof ScrapeBlockedError,
} as const;
}
}));
results.push(...settled);
}
return results;
}

function hostAllowed(url: URL, domains: Set<string>): boolean {
const host = url.hostname.toLowerCase().replace(/^www\./, "");
return [...domains].some(domain => host === domain || host.endsWith("." + domain));
}

type RobotsRules = ReturnType<typeof robotsParser>;

async function loadRobotsRules(
url: URL,
cache: Map<string, RobotsRules | null>,
fetchImpl: typeof fetch = fetch,
): Promise<RobotsRules | null> {
const origin = url.origin;
if (cache.has(origin)) return cache.get(origin) ?? null;
let rules: RobotsRules | null = null;
try {
const response = await fetchResource(origin + "/robots.txt", {
retries: 0,
timeoutMs: 5_000,
maxBytes: 256 * 1024,
fetchImpl,
});
rules = robotsParser(origin + "/robots.txt", response.text);
} catch (error) {
const message = error instanceof Error ? error.message : String(error);
if (/HTTP (?:404|410) returned/i.test(message)) {
rules = robotsParser(origin + "/robots.txt", "");
}
// Network errors, challenges, access denials and server failures fail closed.
}
cache.set(origin, rules);
return rules;
}


export async function crawlPublicSite(
startUrls: string[],
options: {
maxPages?: number;
allowedDomains?: string[];
selectors?: Record<string, string>;
includeText?: boolean;
maxTextChars?: number;
includeStructuredData?: boolean;
includeLinks?: boolean;
respectRobots?: boolean;
concurrency?: number;
fetchImpl?: typeof fetch;
delayMs?: number;
} = {},
): Promise<ScrapeResult[]> {
const maxPages = Math.max(1, Math.min(options.maxPages ?? 50, MAX_CRAWL_PAGES));
const concurrency = Math.max(1, Math.min(options.concurrency ?? 2, 8));
const seeds = [...new Set(startUrls.map(url => validatePublicHttpUrl(url).toString()))].slice(0, maxPages);
if (!seeds.length) return [];
const domains = new Set((options.allowedDomains?.length ? options.allowedDomains : seeds.map(url => new URL(url).hostname.replace(/^www\./, ""))).map(value => value.toLowerCase().replace(/^www\./, "")));
if (seeds.some(url => !hostAllowed(new URL(url), domains))) {
throw new TypeError("Every start URL must be inside allowedDomains.");
}
const queue = [...seeds];
const seen = new Set(seeds);
const results: ScrapeResult[] = [];
const robotsCache = new Map<string, RobotsRules | null>();
const robotsDelays = new Map<string, number>();
while (queue.length && results.length < maxPages) {
const batch = queue.splice(0, concurrency);
const settled = await Promise.all(batch.map(async url => {
const parsed = new URL(url);
if (options.respectRobots !== false) {
const rules = await loadRobotsRules(parsed, robotsCache, options.fetchImpl);
if (!rules || rules.isAllowed(url, "Lemegeton") === false) return null;
const crawlDelay = rules.getCrawlDelay("Lemegeton");
if (typeof crawlDelay === "number" && Number.isFinite(crawlDelay) && crawlDelay > 0) {
robotsDelays.set(parsed.origin, Math.min(crawlDelay * 1_000, 30_000));
}
}
try {
return await fetchPublicPage(url, {
selectors: options.selectors,
includeText: options.includeText,
maxTextChars: options.maxTextChars,
includeStructuredData: options.includeStructuredData,
includeLinks: true,
fetchImpl: options.fetchImpl,
});
} catch {
return null;
}
}));
for (const result of settled) {
if (!result) continue;
results.push(result);
for (const link of result.links ?? []) {
if (seen.size >= maxPages) break;
const next = validatePublicHttpUrl(link.url);
if (!hostAllowed(next, domains)) continue;
const normalized = next.toString();
if (!seen.has(normalized)) {
seen.add(normalized);
queue.push(normalized);
}
}
}
if (queue.length && results.length < maxPages) {
const policyDelay = Math.max(0, ...batch.map(url => robotsDelays.get(new URL(url).origin) ?? 0));
const delayMs = Math.max(options.delayMs ?? 1_000, policyDelay);
if (delayMs > 0) await new Promise(resolve => setTimeout(resolve, Math.min(delayMs, 30_000)));
}
}
return results.slice(0, maxPages);
}
