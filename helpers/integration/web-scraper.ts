import { isIP } from "node:net";
import { load } from "cheerio";
import { chromium } from "playwright-core";

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
includeLinks?: boolean;
linkSelector?: string;
includeHtml?: boolean;
timeoutMs?: number;
retries?: number;
headers?: Record<string, string>;
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
if (status === 429) return "HTTP 429 rate limit";
if (status === 401 || status === 403) return "HTTP " + status + " access response";
const lower = body.toLowerCase();
const server = (headers.get("server") ?? "").toLowerCase();
if (lower.includes("cf-chl-") || lower.includes("challenge-platform") || lower.includes("just a moment...") || lower.includes("verify you are human") || lower.includes("captcha-container") || lower.includes("g-recaptcha") || lower.includes("h-captcha")) {
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
options: { timeoutMs?: number; retries?: number; headers?: Record<string, string>; fetchImpl?: typeof fetch; maxBytes?: number } = {},
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
method: "GET",
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
try {
const page = await browser.newPage({ userAgent: DEFAULT_USER_AGENT });
await page.route("**/*", async route => {
const requestUrl = route.request().url();
if (!requestUrl.startsWith("http://") && !requestUrl.startsWith("https://")) {
await route.continue();
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
await browser.close();
}
}

export async function fetchPublicPage(url: string, options: ScrapeOptions = {}): Promise<ScrapeResult> {
const validated = validatePublicHttpUrl(url);
if (options.engine === "browser") return fetchBrowserPage(validated.toString(), options);
const response = await fetchResource(validated.toString(), options);
const contentType = (response.headers.get("content-type") ?? "").toLowerCase();
if (contentType && !contentType.includes("text/html") && !contentType.includes("application/xhtml+xml")) {
throw new ScrapeRequestError("Expected HTML from " + response.url + ", received " + contentType + ".");
}
return extractPageData(response.url, response.text, response.status, "fetch", options);
}

export async function fetchJson<T = unknown>(url: string, options: Omit<ScrapeOptions, "engine" | "selectors" | "includeLinks" | "includeText" | "includeHtml"> = {}): Promise<T> {
const response = await fetchResource(url, options);
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

async function robotsAllows(url: URL, cache: Map<string, string[]>): Promise<boolean> {
const origin = url.origin;
let rules = cache.get(origin);
if (!rules) {
try {
const response = await fetchResource(origin + "/robots.txt", { retries: 0, timeoutMs: 5_000, maxBytes: 256 * 1024 });
const lines = response.text.split(/\r?\n/);
let applies = false;
rules = [];
for (const raw of lines) {
const line = raw.split("#", 1)[0]!.trim();
if (!line) continue;
const separator = line.indexOf(":");
if (separator < 0) continue;
const key = line.slice(0, separator).trim().toLowerCase();
const value = line.slice(separator + 1).trim();
if (key === "user-agent") applies = value === "*" || value.toLowerCase() === "lemegeton";
else if (applies && key === "disallow" && value) rules.push(value);
}
} catch {
rules = [];
}
cache.set(origin, rules);
}
return !rules.some(path => url.pathname.startsWith(path));
}

export async function crawlPublicSite(
startUrls: string[],
options: {
maxPages?: number;
allowedDomains?: string[];
selectors?: Record<string, string>;
includeText?: boolean;
maxTextChars?: number;
includeLinks?: boolean;
respectRobots?: boolean;
concurrency?: number;
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
const robotsCache = new Map<string, string[]>();
while (queue.length && results.length < maxPages) {
const batch = queue.splice(0, concurrency);
const settled = await Promise.all(batch.map(async url => {
const parsed = new URL(url);
if (options.respectRobots !== false && !(await robotsAllows(parsed, robotsCache))) return null;
try {
return await fetchPublicPage(url, {
selectors: options.selectors,
includeText: options.includeText,
maxTextChars: options.maxTextChars,
includeLinks: true,
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
if (queue.length && results.length < maxPages && (options.delayMs ?? 1_000) > 0) {
await new Promise(resolve => setTimeout(resolve, Math.max(0, Math.min(options.delayMs ?? 1_000, 30_000))));
}
}
return results.slice(0, maxPages);
}
