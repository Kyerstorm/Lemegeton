import assert from "node:assert/strict";
import test from "node:test";
import { configureBotasaurusBridgeForTests } from "../helpers/integration/botasaurus-bridge.js";
import {
  parseNovelUpdatesSearch,
  searchNovelUpdates,
  WebNovelDiscoveryClient,
  type WebNovelMedia,
  type WebNovelSearchProvider,
} from "../helpers/integration/webnovel-discovery.js";

function record(provider: WebNovelMedia["provider"], sourceUrl: string, description: string): WebNovelMedia {
  return {
    provider,
    title: "Shared Story",
    sourceUrl,
    description,
    image: null,
    author: null,
    status: null,
    genres: [],
    rating: null,
    chapterCount: null,
    latestUpdate: null,
    latestChapters: [],
  };
}

test("webnovel discovery keeps same-title provider records separately and deduplicates identical source records", async () => {
  const providers: WebNovelSearchProvider[] = [
    {
      name: "NovelFire",
      sourceId: "novelfire",
      search: async query => {
        assert.equal(query, "Shared Story");
        return [
        record("NovelFire", "https://novelfire.net/novel/shared-story", "NovelFire description"),
        record("NovelFire", "https://novelfire.net/novel/shared-story", "Duplicate response"),
        ];
      },
    },
    {
      name: "Noveli.to",
      sourceId: "noveli-to",
      search: async () => [
        record("Noveli.to", "https://noveli.to/novel/42", "Noveli.to description"),
      ],
    },
  ];
  const result = await new WebNovelDiscoveryClient(providers, ["novelfire", "noveli-to"]).searchDetailed("  Shared   Story  ");
  assert.deepEqual(result.unavailableProviders, []);
  assert.deepEqual(result.disabledProviders, []);
  assert.equal(result.results.length, 2);
  assert.deepEqual(result.results.map(item => item.provider), ["NovelFire", "Noveli.to"]);
  assert.deepEqual(result.results.map(item => item.description), ["NovelFire description", "Noveli.to description"]);
});

test("webnovel discovery reports failed providers without discarding successful records", async () => {
  const providers: WebNovelSearchProvider[] = [
    {
      name: "NovelFire",
      sourceId: "novelfire",
      search: async () => { throw new Error("temporary provider outage"); },
    },
    {
      name: "Wuxia Click",
      sourceId: "wuxia-click",
      search: async () => [record("Wuxia Click", "https://www.wuxia.click/novel/two", "Still available")],
    },
  ];
  const result = await new WebNovelDiscoveryClient(providers, ["novelfire", "wuxia-click"]).searchDetailed("Story");
  assert.deepEqual(result.unavailableProviders, ["NovelFire"]);
  assert.deepEqual(result.disabledProviders, []);
  assert.deepEqual(result.results.map(item => item.provider), ["Wuxia Click"]);
});

test("webnovel allowlist skips sources that have not been approved", async () => {
  const calls: string[] = [];
  const providers: WebNovelSearchProvider[] = [
    {
      name: "NovelFire",
      sourceId: "novelfire",
      search: async () => {
        calls.push("novelfire");
        return [record("NovelFire", "https://novelfire.net/novel/one", "Approved")];
      },
    },
    {
      name: "Novel Archive",
      sourceId: "novel-archive",
      search: async () => {
        calls.push("novel-archive");
        return [record("Novel Archive", "https://novelarchive.cc/novel?id=2", "Not approved")];
      },
    },
    {
      name: "Wuxia Click",
      sourceId: "wuxia-click",
      search: async () => {
        calls.push("wuxia-click");
        return [];
      },
    },
  ];

  const result = await new WebNovelDiscoveryClient(providers, ["novelfire"]).searchDetailed("Shared Story");
  assert.deepEqual(calls, ["novelfire"]);
  assert.deepEqual(result.results.map(item => item.provider), ["NovelFire"]);
  assert.deepEqual(result.unavailableProviders, []);
  assert.deepEqual(result.disabledProviders, ["Novel Archive", "Wuxia Click"]);
});

test("webnovel discovery defaults to no enabled sources", async () => {
  let calls = 0;
  const client = new WebNovelDiscoveryClient([{
    name: "NovelFire",
    sourceId: "novelfire",
    search: async () => {
      calls += 1;
      return [record("NovelFire", "https://novelfire.net/novel/one", "Should not be fetched")];
    },
  }]);

  const result = await client.searchDetailed("Shared Story");
  assert.equal(calls, 0);
  assert.deepEqual(result.results, []);
  assert.deepEqual(result.unavailableProviders, []);
  assert.deepEqual(result.disabledProviders, ["NovelFire"]);
});

test("webnovel discovery skips short queries without calling providers", async () => {
  let calls = 0;
  const client = new WebNovelDiscoveryClient([{
    name: "NovelFire",
    sourceId: "novelfire",
    search: async () => { calls += 1; return []; },
  }], ["novelfire"]);
  assert.deepEqual(await client.searchDetailed(" x "), { results: [], unavailableProviders: [], disabledProviders: [] });
  assert.equal(calls, 0);
});


test("Novel Updates parses submitted series metadata without chapter content", () => {
  const results = parseNovelUpdatesSearch(`
    <article class="search_main_box_nu">
      <a href="/series/123/">Community Submitted Story</a>
      <div class="search_body">A synopsis submitted by a community member.</div>
      <div class="search_author">Example Author</div>
      <div class="search_genres"><a>Fantasy</a></div>
      <span>24 chapters</span>
    </article>
  `, "https://www.novelupdates.com/series-finder/");

  assert.equal(results.length, 1);
  assert.equal(results[0]?.provider, "Novel Updates");
  assert.equal(results[0]?.title, "Community Submitted Story");
  assert.equal(results[0]?.author, "Example Author");
  assert.equal(results[0]?.chapterCount, 24);
  assert.deepEqual(results[0]?.genres, ["Fantasy"]);
  assert.equal(results[0]?.latestChapters.length, 0);
});

test("Novel Updates retries only Cloudflare challenges through Botasaurus", async () => {
  const submitted: Array<{ url: string; options: Record<string, unknown> }> = [];
  let requestedUrl = "";
  const resultHtml = `
    <div class="search_main_box_nu">
      <a href="/series/123/">Cloudflare Retry Story</a>
      <div class="search_body">Community-submitted catalogue summary.</div>
    </div>
  `;
  const workerFetch: typeof fetch = async (input, init) => {
    const target = new URL(String(input));
    if (target.pathname === "/v1/jobs") {
      const body = JSON.parse(String(init?.body)) as {
        url: string;
        options: Record<string, unknown>;
      };
      requestedUrl = body.url;
      submitted.push(body);
      return new Response(JSON.stringify({ jobId: "novel-updates-job", status: "queued" }), {
        status: 202,
        headers: { "content-type": "application/json" },
      });
    }
    if (target.pathname === "/v1/jobs/novel-updates-job") {
      return new Response(JSON.stringify({
        jobId: "novel-updates-job",
        status: "succeeded",
        result: {
          url: requestedUrl,
          canonicalUrl: requestedUrl,
          title: "Series Finder",
          description: "",
          fields: {},
          statusCode: 200,
          engine: "obscura",
          html: resultHtml,
        },
      }), { headers: { "content-type": "application/json" } });
    }
    return new Response(JSON.stringify({ error: "Unexpected worker request." }), {
      status: 404,
      headers: { "content-type": "application/json" },
    });
  };
  const fetchImpl: typeof fetch = async () => new Response("<html>challenge</html>", {
    status: 403,
    headers: {
      "content-type": "text/html",
      "cf-mitigated": "challenge",
    },
  });

  configureBotasaurusBridgeForTests({
    mode: "remote",
    workerUrl: "https://scraper.example.test",
    token: "n".repeat(32),
    fetchImpl: workerFetch,
  });
  try {
    const results = await searchNovelUpdates("Cloudflare Retry Story", { fetchImpl });
    assert.equal(results[0]?.title, "Cloudflare Retry Story");
    assert.equal(submitted.length, 1);
    assert.equal(submitted[0]?.options.cfBypass, true);
    assert.match(submitted[0]?.url ?? "", /^https:\/\/www\.novelupdates\.com\//);
  } finally {
    configureBotasaurusBridgeForTests(null);
  }
});

test("Novel Updates is registered but remains disabled without the source allowlist", async () => {
  const result = await new WebNovelDiscoveryClient().searchDetailed("Example Story");
  assert.ok(result.disabledProviders.includes("Novel Updates"));
  assert.ok(!result.unavailableProviders.includes("Novel Updates"));
  assert.deepEqual(result.results, []);
});
