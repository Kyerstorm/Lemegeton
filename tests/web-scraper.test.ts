import assert from "node:assert/strict";
import test from "node:test";
import { fetchPublicPage, fetchJson, validatePublicHttpUrl } from "../helpers/integration/web-scraper.js";
import { parseNovelFireSearch, parseNovelArchiveSearch, parseWuxiaClickPageData, parseNovelUpdatesSearch } from "../helpers/integration/webnovel-discovery.js";

test("URL validation rejects local hosts, private IPs and unsupported schemes", () => {
assert.throws(() => validatePublicHttpUrl("http://localhost/admin"));
assert.throws(() => validatePublicHttpUrl("http://127.0.0.1/"));
assert.throws(() => validatePublicHttpUrl("http://[::1]/"));
assert.throws(() => validatePublicHttpUrl("file:///etc/passwd"));
assert.equal(validatePublicHttpUrl("https://example.com/page").hostname, "example.com");
});

test("HTML scraping extracts metadata, CSS fields and scoped links", async () => {
const html = '<html><head><title>Test page</title><meta name="description" content="Page description"><link rel="canonical" href="/canonical"></head><body><h1>Heading</h1><p>First content</p><a href="/novel/one">Open novel</a></body></html>';
const fetchImpl: typeof fetch = async () => new Response(html, { status: 200, headers: { "content-type": "text/html" } });
const page = await fetchPublicPage("https://example.com/page", { includeHtml: true, includeLinks: true, selectors: { heading: "h1" }, fetchImpl });
assert.equal(page.title, "Test page");
assert.equal(page.description, "Page description");
assert.equal(page.canonicalUrl, "https://example.com/canonical");
assert.equal(page.fields.heading, "Heading");
assert.equal(page.links?.[0]?.url, "https://example.com/novel/one");
assert.equal(page.engine, "fetch");
});

test("redirect destinations are validated before the next request", async () => {
const fetchImpl: typeof fetch = async () => new Response(null, { status: 302, headers: { location: "http://127.0.0.1/private" } });
await assert.rejects(() => fetchPublicPage("https://example.com/", { fetchImpl }), /Private or reserved IP/);
});

test("JSON fetching parses provider responses", async () => {
const fetchImpl: typeof fetch = async () => new Response('{"items":[1,2]}', { status: 200, headers: { "content-type": "application/json" } });
const result = await fetchJson<{ items: number[] }>("https://example.com/api", { fetchImpl });
assert.deepEqual(result.items, [1, 2]);
});

test("NovelFire results normalize story links and reject external hosts", () => {
const html = '<div class="novel-item"><a href="/novel/story-one" title="Story One"><h4>Story One</h4></a><div class="novel-cover"><img src="/covers/one.jpg"></div></div><div class="novel-item"><a href="https://not-novelfire.example/novel/two">Story Two</a></div>';
const results = parseNovelFireSearch(html);
assert.equal(results.length, 1);
assert.equal(results[0]?.title, "Story One");
assert.equal(results[0]?.sourceUrl, "https://novelfire.net/novel/story-one");
});

test("Novel Archive JSON records normalize source metadata", () => {
const results = parseNovelArchiveSearch({ novels: [
{ id: "abc123", title: "A Safe Chronicle", author: "A. Writer", genres: ["Fantasy"], chapter_names: ["One", "Two"] },
{ id: "abc124", title: "Explicit Story", genres: ["Adult"] },
] });
assert.equal(results.length, 1);
assert.equal(results[0]?.provider, "Novel Archive");
assert.equal(results[0]?.chapterCount, 2);
});

test("Wuxia Click embedded records are normalized", () => {
const results = parseWuxiaClickPageData({ result: { items: [
{ name: "The Wandering Sage", slug: "wandering-sage", author: { name: "A. Author" }, genres: [{ name: "Fantasy" }], chapters: 64, coverKey: "covers/sage" },
] } });
assert.equal(results.length, 1);
assert.equal(results[0]?.sourceUrl, "https://wuxia.click/novel/wandering-sage");
assert.equal(results[0]?.author, "A. Author");
assert.equal(results[0]?.chapterCount, 64);
});

test("Novel Updates HTML records retain their source provider", () => {
const html = '<div class="search_main_box_nu"><a href="https://www.novelupdates.com/series/safe-chronicle/">A Safe Chronicle</a><div class="search_body_nu">A fantasy journey.</div><div class="search_genre"><a>Fantasy</a></div></div>';
const results = parseNovelUpdatesSearch(html);
assert.equal(results.length, 1);
assert.equal(results[0]?.provider, "Novel Updates");
assert.equal(results[0]?.genres[0], "Fantasy");
});

test("ScribbleHub series finder results normalize title, link and cover", async () => {
const { parseScribbleHubSearch } = await import("../helpers/integration/webnovel-discovery.js");
const html = '<div class="search_main_box"><div class="search_title"><a href="https://www.scribblehub.com/series/123/story-name/">A Safe Story</a></div><div class="search_img"><img src="/covers/story.jpg"></div></div>';
const results = parseScribbleHubSearch(html);
assert.equal(results.length, 1);
assert.equal(results[0]?.title, "A Safe Story");
assert.equal(results[0]?.sourceUrl, "https://www.scribblehub.com/series/123/story-name/");
});
test("web scraper supports POST form endpoints", async () => {
let method = "";
let body = "";
const fetchImpl: typeof fetch = async (_input, init) => {
method = init?.method ?? "";
body = String(init?.body ?? "");
return new Response("<div class='toc_w'>Chapter item</div>", { status: 200, headers: { "content-type": "text/html" } });
};
const page = await fetchPublicPage("https://example.com/wp-admin/admin-ajax.php", {
method: "POST",
body: new URLSearchParams({ action: "list", post_id: "12" }).toString(),
headers: { "Content-Type": "application/x-www-form-urlencoded" },
includeHtml: true,
includeText: false,
fetchImpl,
});
assert.equal(method, "POST");
assert.match(body, /post_id=12/);
assert.match(page.html ?? "", /Chapter item/);
});
