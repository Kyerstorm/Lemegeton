import assert from "node:assert/strict";
import test from "node:test";
import {
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
