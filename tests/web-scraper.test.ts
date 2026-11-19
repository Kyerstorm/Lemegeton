import assert from "node:assert/strict";
import test from "node:test";
import { CookieJar } from "tough-cookie";
import { fetchPublicPage, fetchJson, fetchXml, fetchSitemapUrls, fetchMany, extractStructuredData, crawlPublicSite, ScrapeBlockedError, validatePublicHttpUrl, resolvePublicAddresses } from "../helpers/integration/web-scraper.js";
import { parseNovelFireSearch, buildNovelFireSearchUrl, parseNovelFireChapterData, parseNoveliToSearch, parseNoveliToDetail, parseNovelArchiveSearch, parseWuxiaClickPageData, parseNovelUpdatesSearch } from "../helpers/integration/webnovel-discovery.js";

test("URL validation rejects local hosts, non-public IPv4 ranges and unsupported schemes", () => {
assert.throws(() => validatePublicHttpUrl("http://localhost/admin"));
assert.throws(() => validatePublicHttpUrl("http://127.0.0.1/"));
assert.throws(() => validatePublicHttpUrl("http://10.0.0.1/"));
assert.throws(() => validatePublicHttpUrl("http://100.64.0.1/"));
assert.throws(() => validatePublicHttpUrl("http://192.0.2.1/"));
assert.throws(() => validatePublicHttpUrl("http://198.18.0.1/"));
assert.throws(() => validatePublicHttpUrl("http://[::1]/"));
assert.throws(() => validatePublicHttpUrl("http://[::ffff:7f00:1]/"));
assert.throws(() => validatePublicHttpUrl("http://[::ffff:a00:1]/"));
assert.throws(() => validatePublicHttpUrl("http://[::ffff:a9fe:1]/"));
assert.throws(() => validatePublicHttpUrl("http://[2001:db8::1]/"));
assert.throws(() => validatePublicHttpUrl("http://[2002:0808:0808::1]/"));
assert.throws(() => validatePublicHttpUrl("http://[64:ff9b::7f00:1]/"));
assert.throws(() => validatePublicHttpUrl("file:///etc/passwd"));
assert.equal(validatePublicHttpUrl("https://example.com/page").hostname, "example.com");
assert.equal(validatePublicHttpUrl("https://[2001:4860:4860::8888]/").hostname, "[2001:4860:4860::8888]");
});

test("DNS resolution rejects mixed public/private answers and accepts public-only records", async () => {
const publicAddress = async () => [{ address: "8.8.8.8", family: 4 as const }];
assert.deepEqual(await resolvePublicAddresses("example.com", publicAddress), [
{ address: "8.8.8.8", family: 4 },
]);
await assert.rejects(
() => resolvePublicAddresses("example.com", async () => [
{ address: "8.8.8.8", family: 4 },
{ address: "127.0.0.1", family: 4 },
]),
/private or reserved address/,
);
await assert.rejects(
() => resolvePublicAddresses("example.com", async () => [{ address: "::ffff:7f00:1", family: 6 }]),
/private or reserved address/,
);
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

test("NovelFire title search URL uses the title-search endpoint", () => {
const url = new URL(buildNovelFireSearchUrl("The King's Avatar"));
assert.equal(url.origin, "https://novelfire.net");
assert.equal(url.pathname, "/search");
assert.equal(url.searchParams.get("keyword"), "The King's Avatar");
assert.equal(url.searchParams.get("type"), "title");
assert.equal(url.searchParams.get("page"), "1");
});

test("NovelFire results normalize story links and reject external hosts", () => {
const html = '<div class="novel-item"><a href="/novel/story-one" title="Story One"><h4>Story One</h4></a><div class="novel-cover"><img src="/covers/one.jpg"></div></div><div class="novel-item"><a href="https://not-novelfire.example/novel/two">Story Two</a></div>';
const results = parseNovelFireSearch(html);
assert.equal(results.length, 1);
assert.equal(results[0]?.title, "Story One");
assert.equal(results[0]?.sourceUrl, "https://novelfire.net/novel/story-one");
});

test("NovelFire chapter JSON returns the newest chapter titles and chapter count", () => {
const metadata = parseNovelFireChapterData({
recordsFiltered: 42,
recordsTotal: 42,
data: [
{ n_sort: "2", title: "Chapter 2" },
{ n_sort: "11", title: "Chapter 11" },
{ n_sort: "9", title: "Chapter 9" },
{ n_sort: "10", title: "Chapter 10" },
{ n_sort: "7", title: "Chapter 7" },
{ n_sort: "8", title: "Chapter 8" },
{ n_sort: "invalid", title: "Broken row" },
],
});
assert.equal(metadata.chapterCount, 42);
assert.deepEqual(metadata.latestChapters, ["Chapter 11", "Chapter 10", "Chapter 9", "Chapter 8", "Chapter 7"]);
});

test("NovelFire chapter JSON falls back to total count and ignores malformed payloads", () => {
assert.deepEqual(parseNovelFireChapterData({ recordsTotal: "12", data: [{ n_sort: 1, slug: "Chapter One" }] }), {
chapterCount: 12,
latestChapters: ["Chapter One"],
});
assert.deepEqual(parseNovelFireChapterData(null), { chapterCount: null, latestChapters: [] });
});

test("Noveli.to JSON search filters invalid and mature records", () => {
const items = parseNoveliToSearch({
success: true,
data: [
{ id: 123, title: "A Safe Chronicle", cover_image: "/covers/one.jpg", genres: ["Fantasy"] },
{ id: 124, title: "Mature Story", genres: ["Adult"] },
{ id: 125, title: "Flagged Story", is_adult: true },
{ id: "bad-id", title: "Invalid ID" },
],
});
assert.equal(items.length, 1);
assert.equal(items[0]?.record.provider, "Noveli.to");
assert.equal(items[0]?.record.sourceUrl, "https://noveli.to/novel/123");
assert.equal(items[0]?.record.image, "https://noveli.to/covers/one.jpg");
});

test("Noveli.to detail JSON adds metadata and rejects flagged records", () => {
const item = parseNoveliToSearch({ success: true, data: [{ id: 77, title: "A Safe Chronicle", cover_image: "/cover.jpg" }] })[0]!;
const detail = parseNoveliToDetail({
success: true,
data: {
title: "A Safe Chronicle",
author: "A. Writer",
description: "A fantasy journey.",
genres: ["Fantasy", "Adventure"],
status: "Ongoing",
rating: 4.5,
total_chapters: 82,
updated_at: "2026-11-15",
cover_image: "/covers/chronicle.jpg",
},
}, item);
assert.equal(detail?.author, "A. Writer");
assert.equal(detail?.chapterCount, 82);
assert.equal(detail?.rating, 4.5);
assert.equal(detail?.latestUpdate, "2026-11-15");
assert.equal(parseNoveliToDetail({ data: { title: "Flagged", is_adult: true } }, item), null);
assert.equal(parseNoveliToDetail({ data: { title: "Flagged", content_rating: "18+" } }, item), null);
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

test("JSON-LD extraction reads top-level and graph records", () => {
  const html = '<script type="application/ld+json">{"@type":"Book","name":"Dune","@graph":[{"@type":"Person","name":"Frank Herbert"}]}</script>';
  const data = extractStructuredData(html);
  assert.equal(data.length, 2);
  assert.equal(data[0]?.name, "Dune");
  assert.equal(data[1]?.name, "Frank Herbert");
});

test("XML fetching validates and parses bounded RSS documents", async () => {
  const fetchImpl: typeof fetch = async () => new Response(
    '<rss version="2.0"><channel><title>Example feed</title><item><title>Latest</title></item></channel></rss>',
    { status: 200, headers: { "content-type": "application/rss+xml" } },
  );
  const payload = await fetchXml<Record<string, unknown>>("https://example.com/feed.xml", { fetchImpl });
  const rss = payload.rss as Record<string, unknown>;
  const channel = rss.channel as Record<string, unknown>;
  assert.equal(channel.title, "Example feed");
});

test("XML fetching rejects DTD/entity declarations and malformed documents", async () => {
  const dtd: typeof fetch = async () => new Response(
    '<!DOCTYPE rss [<!ENTITY local SYSTEM "file:///etc/passwd">]><rss>&local;</rss>',
    { status: 200, headers: { "content-type": "application/xml" } },
  );
  await assert.rejects(() => fetchXml("https://example.com/feed.xml", { fetchImpl: dtd }), /DTD or entity declarations/);
  const malformed: typeof fetch = async () => new Response("<rss><channel>", { status: 200, headers: { "content-type": "application/xml" } });
  await assert.rejects(() => fetchXml("https://example.com/feed.xml", { fetchImpl: malformed }), /invalid XML/);
});

test("Cloudflare challenge headers stop scraping", async () => {
  const fetchImpl: typeof fetch = async () => new Response("<html>challenge</html>", {
    status: 503,
    headers: { "content-type": "text/html", "cf-mitigated": "challenge" },
  });
  await assert.rejects(
    () => fetchPublicPage("https://example.com/page", { fetchImpl }),
    (error: unknown) => error instanceof ScrapeBlockedError && /Cloudflare challenge/.test(error.message),
  );
});

test("Sitemap discovery is bounded and remains on its allowed host", async () => {
  const fetchImpl: typeof fetch = async () => new Response(
    '<urlset><url><loc>https://example.com/one</loc></url><url><loc>https://other.example/two</loc></url><url><loc>https://example.com/three</loc></url></urlset>',
    { status: 200, headers: { "content-type": "application/xml" } },
  );
  const urls = await fetchSitemapUrls("https://example.com/sitemap.xml", { maxUrls: 1, fetchImpl });
  assert.deepEqual(urls, ["https://example.com/one"]);
});

test("crawler follows robots Allow overrides and disallows restricted paths", async () => {
  const fetchImpl: typeof fetch = async input => {
    const url = String(input);
    if (url.endsWith("/robots.txt")) {
      return new Response("User-agent: *\nDisallow: /private\nAllow: /private/open\n", { status: 200 });
    }
    return new Response("<html><head><title>Allowed path</title></head><body>Open</body></html>", {
      status: 200,
      headers: { "content-type": "text/html" },
    });
  };
  const denied = await crawlPublicSite(["https://example.com/private/blocked"], { fetchImpl, delayMs: 0 });
  const allowed = await crawlPublicSite(["https://example.com/private/open"], { fetchImpl, delayMs: 0 });
  assert.equal(denied.length, 0);
  assert.equal(allowed.length, 1);
  assert.equal(allowed[0]?.title, "Allowed path");
});

test("scraper extracts Open Graph metadata and discovers RSS alternate feeds", async () => {
  const html = '<html><head><title>Feed page</title><meta property="og:image" content="/cover.jpg"><meta name="author" content="A. Author"><meta property="article:published_time" content="2026-11-17"><link rel="alternate" type="application/rss+xml" title="Updates" href="/feed.xml"></head><body><p>Content</p></body></html>';
  const fetchImpl: typeof fetch = async () => new Response(html, { status: 200, headers: { "content-type": "text/html" } });
  const page = await fetchPublicPage("https://example.com/article", { includeText: false, fetchImpl });
  assert.equal(page.image, "https://example.com/cover.jpg");
  assert.equal(page.author, "A. Author");
  assert.equal(page.publishedAt, "2026-11-17");
  assert.deepEqual(page.feeds, [{ title: "Updates", type: "application/rss+xml", url: "https://example.com/feed.xml" }]);
});

test("article extraction returns bounded readable text and metadata", async () => {
  const paragraphs = Array.from({ length: 8 }, (_, index) => '<p>Paragraph ' + index + ' — ' + "A useful sentence about the subject. ".repeat(12) + '</p>').join("");
  const html = '<html><head><title>Readable article</title><meta name="author" content="A. Writer"></head><body><nav>Navigation only</nav><article><h1>Readable article</h1>' + paragraphs + '</article></body></html>';
  const fetchImpl: typeof fetch = async () => new Response(html, { status: 200, headers: { "content-type": "text/html" } });
  const page = await fetchPublicPage("https://example.com/story", { includeArticle: true, includeHtml: false, fetchImpl });
  assert.equal(page.article?.title, "Readable article");
  assert.match(page.article?.content ?? "", /Paragraph 0/);
  assert.doesNotMatch(page.article?.content ?? "", /Navigation only/);
});

test("429 responses honour a bounded Retry-After before retrying", async () => {
  let calls = 0;
  const fetchImpl: typeof fetch = async () => {
    calls += 1;
    return calls === 1
      ? new Response("rate limited", { status: 429, headers: { "Retry-After": "0" } })
      : new Response('{"ok":true}', { status: 200, headers: { "content-type": "application/json" } });
  };
  const result = await fetchJson<{ ok: boolean }>("https://example.com/api", { fetchImpl, retries: 1 });
  assert.equal(result.ok, true);
  assert.equal(calls, 2);
});

test("sitemap indexes recursively collect scoped URLs and deduplicate children", async () => {
  const fetchImpl: typeof fetch = async input => {
    const url = String(input);
    if (url.endsWith("/index.xml")) return new Response(
      '<sitemapindex><sitemap><loc>https://example.com/one.xml</loc></sitemap><sitemap><loc>https://example.com/two.xml</loc></sitemap></sitemapindex>',
      { status: 200, headers: { "content-type": "application/xml" } },
    );
    if (url.endsWith("/one.xml")) return new Response(
      '<urlset><url><loc>https://example.com/a</loc></url><url><loc>https://example.com/shared</loc></url></urlset>',
      { status: 200, headers: { "content-type": "application/xml" } },
    );
    return new Response(
      '<urlset><url><loc>https://example.com/shared</loc></url><url><loc>https://other.example/out</loc></url><url><loc>https://example.com/b</loc></url></urlset>',
      { status: 200, headers: { "content-type": "application/xml" } },
    );
  };
  const urls = await fetchSitemapUrls("https://example.com/index.xml", { fetchImpl, maxUrls: 10 });
  assert.deepEqual(urls, ["https://example.com/a", "https://example.com/shared", "https://example.com/b"]);
});

test("detailed crawling reports failures and continues with reachable pages", async () => {
  const { crawlPublicSiteDetailed } = await import("../helpers/integration/web-scraper.js");
  const fetchImpl: typeof fetch = async input => {
    const url = String(input);
    if (url.endsWith("/robots.txt")) return new Response("User-agent: *\nAllow: /", { status: 200 });
    if (url.endsWith("/blocked")) return new Response("<html>challenge</html>", {
      status: 503, headers: { "content-type": "text/html", "cf-mitigated": "challenge" },
    });
    if (url.endsWith("/broken")) return new Response("bad", { status: 500 });
    return new Response("<html><head><title>Good page</title></head><body>Ok</body></html>", {
      status: 200, headers: { "content-type": "text/html" },
    });
  };
  const report = await crawlPublicSiteDetailed(
    ["https://example.com/blocked", "https://example.com/broken", "https://example.com/good"],
    { fetchImpl, concurrency: 1, delayMs: 0, maxPages: 5 },
  );
  assert.equal(report.pages.length, 1);
  assert.equal(report.pages[0]?.title, "Good page");
  assert.deepEqual(report.failures.map(value => value.kind), ["blocked", "request"]);
});


test("HTTP transport retries transient network errors and preserves cookie-jar state", async () => {
  const jar = new CookieJar();
  await jar.setCookie("session=ready; Path=/", "https://example.com");
  let calls = 0;
  let sentCookie = "";
  const fetchImpl: typeof fetch = async (_input, init) => {
    calls += 1;
    sentCookie = new Headers(init?.headers).get("cookie") ?? "";
    if (calls === 1) throw new Error("temporary socket failure");
    return new Response("<html><head><title>Cookie page</title></head><body>Public content</body></html>", {
      status: 200,
      headers: { "content-type": "text/html", "set-cookie": "preference=compact; Path=/" },
    });
  };
  const page = await fetchPublicPage("https://example.com/page", {
    cookieJar: jar,
    fetchImpl,
    retries: 1,
    includeText: false,
  });
  assert.equal(page.title, "Cookie page");
  assert.equal(calls, 2);
  assert.match(sentCookie, /session=ready/);
  assert.match(await jar.getCookieString("https://example.com/page"), /preference=compact/);
});

test("fast and DOM text parsers remove non-content elements", async () => {
  const html = "<html><body><main><p>Readable content</p></main><script>secret script text</script><style>hidden style text</style></body></html>";
  const fetchImpl: typeof fetch = async () => new Response(html, {
    status: 200,
    headers: { "content-type": "text/html" },
  });
  for (const textParser of ["fast", "jsdom"] as const) {
    const page = await fetchPublicPage("https://example.com/page", {
      fetchImpl,
      textParser,
    });
    assert.match(page.text ?? "", /Readable content/);
    assert.doesNotMatch(page.text ?? "", /secret script text|hidden style text/);
  }
});

test("fetchMany enforces concurrency and preserves input ordering", async () => {
  const urls = [
    "https://example.com/first",
    "https://example.com/second",
    "https://example.com/third",
    "https://example.com/fourth",
  ];
  let active = 0;
  let maximumActive = 0;
  const fetchImpl: typeof fetch = async input => {
    active += 1;
    maximumActive = Math.max(maximumActive, active);
    await new Promise(resolve => setTimeout(resolve, 5));
    active -= 1;
    const path = new URL(String(input)).pathname.slice(1);
    return new Response("<html><head><title>" + path + "</title></head><body>Page</body></html>", {
      status: 200,
      headers: { "content-type": "text/html" },
    });
  };
  const results = await fetchMany(urls, { fetchImpl, concurrency: 2, includeText: false });
  assert.equal(maximumActive, 2);
  assert.deepEqual(results.map(result => result.url), urls);
  assert.deepEqual(results.map(result => "result" in result ? result.result.title : ""), [
    "first",
    "second",
    "third",
    "fourth",
  ]);
});
