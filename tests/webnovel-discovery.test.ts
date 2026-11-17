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
      search: async () => [
        record("Noveli.to", "https://noveli.to/novel/42", "Noveli.to description"),
      ],
    },
  ];
  const result = await new WebNovelDiscoveryClient(providers).searchDetailed("  Shared   Story  ");
  assert.deepEqual(result.unavailableProviders, []);
  assert.equal(result.results.length, 2);
  assert.deepEqual(result.results.map(item => item.provider), ["NovelFire", "Noveli.to"]);
  assert.deepEqual(result.results.map(item => item.description), ["NovelFire description", "Noveli.to description"]);
});

test("webnovel discovery reports failed providers without discarding successful records", async () => {
  const providers: WebNovelSearchProvider[] = [
    {
      name: "NovelFire",
      search: async () => [record("NovelFire", "https://novelfire.net/novel/one", "Available")],
    },
    {
      name: "ScribbleHub",
      search: async () => { throw new Error("temporary provider outage"); },
    },
    {
      name: "Wuxia Click",
      search: async () => [record("Wuxia Click", "https://www.wuxia.click/novel/two", "Still available")],
    },
  ];
  const result = await new WebNovelDiscoveryClient(providers).searchDetailed("Story");
  assert.deepEqual(result.unavailableProviders, ["ScribbleHub"]);
  assert.deepEqual(result.results.map(item => item.provider), ["NovelFire", "Wuxia Click"]);
});

test("webnovel discovery skips short queries without calling providers", async () => {
  let calls = 0;
  const client = new WebNovelDiscoveryClient([{
    name: "NovelFire",
    search: async () => { calls += 1; return []; },
  }]);
  assert.deepEqual(await client.searchDetailed(" x "), { results: [], unavailableProviders: [] });
  assert.equal(calls, 0);
});
