import assert from "node:assert/strict";
import test from "node:test";
import { configureBotasaurusBridgeForTests } from "../helpers/integration/botasaurus-bridge.js";
import {
  parseNovelUpdatesDetails,
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


test("Novel Updates parses factual search-card metadata without synopsis or artwork", () => {
  const results = parseNovelUpdatesSearch(`
    <article class="search_main_box_nu">
      <div class="search_body_nu">
        <div class="search_title"><a href="/series/123/">Community Submitted Story</a></div>
        <div class="search_stats">
          <span><i title="Chapter Count"></i>24 Chapters</span>
          <span><i title="Last Updated"></i>11-28-2026</span>
        </div>
        <div class="search_genre"><a>Fantasy</a></div>
        <div class="search_ratings">(4.5)</div>
        <p>Synopsis text must never be copied into discovery results.</p>
      </div>
    </article>
  `, "https://www.novelupdates.com/series-finder/");

  assert.equal(results.length, 1);
  assert.equal(results[0]?.provider, "Novel Updates");
  assert.equal(results[0]?.title, "Community Submitted Story");
  assert.equal(results[0]?.chapterCount, 24);
  assert.equal(results[0]?.rating, 4.5);
  assert.equal(results[0]?.latestUpdate, "11-28-2026");
  assert.deepEqual(results[0]?.genres, ["Fantasy"]);
  assert.equal(results[0]?.description, null);
  assert.equal(results[0]?.image, null);
  assert.equal(results[0]?.latestChapters.length, 0);
});

test("Novel Updates series details add factual catalogue fields without synopsis or artwork", () => {
  const result = parseNovelUpdatesDetails(`
    <div class="seriestitlenu">Example Web Novel</div>
    <div id="showtype"><a>Web Novel</a> <span>(KR)</span></div>
    <div id="seriesgenre"><a class="genre">Fantasy</a><a class="genre">Adventure</a></div>
    <div id="showauthors"><a>Example Author</a></div>
    <div id="edityear">2015</div>
    <div id="editstatus">Completed</div>
    <div id="showopublisher"><a>Original Press</a></div>
    <div id="showepublisher"><a>English Press</a></div>
    <meta property="ratingValue" content="4.25">
    <div id="editdescription">This synopsis must not be copied.</div>
  `, "https://www.novelupdates.com/series/example-web-novel/");

  assert.equal(result?.title, "Example Web Novel");
  assert.equal(result?.format, "Web Novel");
  assert.equal(result?.language, "KR");
  assert.equal(result?.publicationYear, 2015);
  assert.equal(result?.author, "Example Author");
  assert.equal(result?.status, "Completed");
  assert.equal(result?.rating, 4.25);
  assert.equal(result?.originalPublisher, "Original Press");
  assert.equal(result?.englishPublisher, "English Press");
  assert.deepEqual(result?.genres, ["Fantasy", "Adventure"]);
  assert.equal(result?.description, null);
  assert.equal(result?.image, null);
});

test("Novel Updates filters the live Reincarnator result because its catalogue marks it Mature", () => {
  const results = parseNovelUpdatesSearch(`
    <div class="search_main_box_nu">
      <div class="search_title"><a href="https://www.novelupdates.com/series/reincarnator/">Reincarnator</a></div>
      <div class="search_stats"><span><i title="Chapter Count"></i>107 Chapters</span></div>
      <div class="search_genre"><a>Action</a><a>Adventure</a><a>Fantasy</a><a>Mature</a><a>Sci-fi</a><a>Seinen</a><a>Supernatural</a></div>
    </div>
  `, "https://www.novelupdates.com/series-finder/?sf=1&sh=reincarnator&sort=sdate&order=desc");

  assert.deepEqual(results, []);
});

test("Novel Updates search enriches results with series metadata", async () => {
  const requests: URL[] = [];
  const searchHtml = `
    <div class="search_main_box_nu">
      <div class="search_body_nu">
        <div class="search_title"><a href="https://www.novelupdates.com/series/example-story/">Example Story</a></div>
        <div class="search_stats">
          <span><i title="Chapter Count"></i>24 Chapters</span>
          <span><i title="Last Updated"></i>11-28-2026</span>
        </div>
        <div class="search_genre"><a>Fantasy</a></div>
        <div class="search_ratings">(4.5)</div>
      </div>
    </div>
  `;
  const detailHtml = `
    <div class="seriestitlenu">Example Story</div>
    <div id="showtype"><a>Web Novel</a> <span>(KR)</span></div>
    <div id="seriesgenre"><a class="genre">Fantasy</a></div>
    <div id="showauthors"><a>Example Author</a></div>
    <div id="edityear">2015</div>
    <div id="editstatus">Completed</div>
    <div id="showopublisher"><a>Original Press</a></div>
    <div id="showepublisher"><a>English Press</a></div>
    <meta property="ratingValue" content="4.5">
    <div id="editdescription">Do not return synopsis text.</div>
  `;
  const fetchImpl: typeof fetch = async input => {
    const url = new URL(String(input));
    requests.push(url);
    const html = url.pathname === "/series-finder/" ? searchHtml : detailHtml;
    return new Response(html, { status: 200, headers: { "content-type": "text/html; charset=utf-8" } });
  };

  const results = await searchNovelUpdates("Example Story", { fetchImpl });
  assert.equal(results.length, 1);
  assert.deepEqual(requests.map(url => url.pathname), ["/series-finder/", "/series/example-story/"]);
  assert.equal(requests[0]?.searchParams.get("sh"), "Example Story");
  assert.equal(results[0]?.title, "Example Story");
  assert.equal(results[0]?.author, "Example Author");
  assert.equal(results[0]?.format, "Web Novel");
  assert.equal(results[0]?.language, "KR");
  assert.equal(results[0]?.publicationYear, 2015);
  assert.equal(results[0]?.originalPublisher, "Original Press");
  assert.equal(results[0]?.englishPublisher, "English Press");
  assert.equal(results[0]?.chapterCount, 24);
  assert.equal(results[0]?.description, null);
  assert.equal(results[0]?.image, null);
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

test("Novel Updates is always searched without the source allowlist while other providers remain gated", async () => {
  const calls: string[] = [];
  const providers: WebNovelSearchProvider[] = [
    {
      name: "Novel Updates",
      sourceId: "novel-updates",
      search: async () => {
        calls.push("novel-updates");
        return [record("Novel Updates", "https://www.novelupdates.com/series/example/", "metadata")];
      },
    },
    {
      name: "NovelFire",
      sourceId: "novelfire",
      search: async () => {
        calls.push("novelfire");
        return [record("NovelFire", "https://novelfire.net/novel/example", "metadata")];
      },
    },
  ];

  const result = await new WebNovelDiscoveryClient(providers).searchDetailed("Example Story");
  assert.deepEqual(calls, ["novel-updates"]);
  assert.deepEqual(result.results.map(item => item.provider), ["Novel Updates"]);
  assert.deepEqual(result.disabledProviders, ["NovelFire"]);
  assert.deepEqual(result.unavailableProviders, []);
});


test("Novel Updates does not send unrelated CAPTCHA challenges to Botasaurus", async () => {
  let workerRequests = 0;
  const workerFetch: typeof fetch = async () => {
    workerRequests += 1;
    return new Response(JSON.stringify({ error: "Unexpected worker request." }), {
      status: 404,
      headers: { "content-type": "application/json" },
    });
  };
  const fetchImpl: typeof fetch = async () => new Response("<html>verify you are human</html>", {
    status: 403,
    headers: { "content-type": "text/html" },
  });

  configureBotasaurusBridgeForTests({
    mode: "remote",
    workerUrl: "https://scraper.example.test",
    token: "u".repeat(32),
    fetchImpl: workerFetch,
  });
  try {
    await assert.rejects(
      () => searchNovelUpdates("Example Story", { fetchImpl }),
      /access challenge/i,
    );
    assert.equal(workerRequests, 0);
  } finally {
    configureBotasaurusBridgeForTests(null);
  }
});
