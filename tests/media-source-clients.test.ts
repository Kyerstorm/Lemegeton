import test from "node:test";
import assert from "node:assert/strict";
import { loadConfig } from "../helpers/runtime/config.js";
import {
  MediaSourceClients,
  parseBookBrainzSearch,
  parseMalResults,
  parseRedditSearch,
  parseShikimoriResults,
} from "../helpers/integration/media-source-clients.js";
import { getMediaSourceResearchLinks } from "../helpers/media/media-source-adapters.js";

test("MyAnimeList parsing keeps only general-audience and teen ratings", () => {
  const results = parseMalResults({
    data: [
      { node: { id: 1, title: "General title", rating: "G - All Ages", start_date: "2020" } },
      { node: { id: 2, title: "Teen title", rating: "PG-13 - Teens 13 or older", start_date: "2021" } },
      { node: { id: 3, title: "Restricted title", rating: "R - 17+", start_date: "2022" } },
      { node: { id: 4, title: "Unrated title", start_date: "2023" } },
    ],
  }, "anime");
  assert.deepEqual(results.map(item => item.title), ["General title", "Teen title"]);
  assert.deepEqual(results.map(item => item.ageRating), ["G", "PG-13"]);
  assert.ok(results.every(item => item.url.includes("/anime/")));
});

test("Shikimori parsing keeps only G, PG and PG-13 records", () => {
  const results = parseShikimoriResults([
    { id: 10, name: "General", rating: "g", aired_on: "2020-01-01" },
    { id: 11, name: "Teen", rating: "pg_13", aired_on: "2021-01-01" },
    { id: 12, name: "Restricted", rating: "r_plus", aired_on: "2022-01-01" },
    { id: 13, name: "Unrated", aired_on: "2023-01-01" },
  ], "manga");
  assert.deepEqual(results.map(item => item.title), ["General", "Teen"]);
  assert.deepEqual(results.map(item => item.ageRating), ["G", "PG-13"]);
  assert.ok(results.every(item => item.url.includes("/mangas/")));
});

test("Reddit parsing rejects adult posts and never returns post bodies", () => {
  const results = parseRedditSearch({
    data: { children: [
      { data: { id: "1", title: "Discussion", permalink: "/r/example/1", selftext: "body", over_18: false, created_utc: 1 } },
      { data: { id: "2", title: "Adult", permalink: "/r/example/2", over_18: true, selftext: "not for discovery" } },
      { data: { id: "3", title: "Missing flag", permalink: "/r/example/3", selftext: "body" } },
    ] },
  });
  assert.deepEqual(results.map(item => item.title), ["Discussion"]);
  assert.ok(results.every(item => item.summary === null));
});

test("BookBrainz parser follows the public search response and keeps work/publisher identities distinct", () => {
  const payload = {
    resultCount: 2,
    totalCount: 2,
    searchResult: [
      {
        bbid: "ba446064-90a5-447b-abe5-139be547da2e",
        defaultAlias: { name: "Example Work" },
        entityType: "Work",
      },
      {
        bbid: "e418874e-5684-4fe9-9d2d-1b7e5d43fd59",
        defaultAlias: { name: "Example Press" },
        entityType: "Publisher",
      },
    ],
  };
  const works = parseBookBrainzSearch(payload, "work");
  const publishers = parseBookBrainzSearch(payload, "publisher");

  assert.deepEqual(works.map(item => item.title), ["Example Work"]);
  assert.deepEqual(publishers.map(item => item.title), ["Example Press"]);
  assert.equal(publishers[0]?.organizationType, "Publisher");
  assert.match(publishers[0]?.url ?? "", /bookbrainz\.org\/publisher\//);
  assert.deepEqual(parseBookBrainzSearch({ results: [{ id: "fake", title: "Wrong shape" }] }), []);
});

test("BookBrainz client sends its documented search parameters", async () => {
  const requests: URL[] = [];
  const fetcher: typeof fetch = async input => {
    requests.push(new URL(String(input)));
    return new Response(JSON.stringify({
      resultCount: 1,
      totalCount: 1,
      searchResult: [{
        bbid: "ba446064-90a5-447b-abe5-139be547da2e",
        defaultAlias: { name: "Example Work" },
        entityType: "Work",
      }],
    }), { status: 200 });
  };
  const clients = new MediaSourceClients(loadConfig({
    DISCORD_TOKEN: "test-token",
    BOT_ID: "123456789012345678",
  }), fetcher);

  const results = await clients.searchBookBrainz("Example Work");
  assert.equal(results[0]?.title, "Example Work");
  assert.equal(requests[0]?.pathname, "/1/search");
  assert.equal(requests[0]?.searchParams.get("q"), "Example Work");
  assert.equal(requests[0]?.searchParams.get("type"), "work");
  assert.equal(requests[0]?.searchParams.get("size"), "10");
  assert.equal(requests[0]?.searchParams.get("from"), "0");
});

test("Google Books publisher discovery uses the injected provider transport", async () => {
  const requests: URL[] = [];
  const fetcher: typeof fetch = async input => {
    requests.push(new URL(String(input)));
    return new Response(JSON.stringify({
      items: [
        { id: "volume-0001", volumeInfo: { title: "Example Book", publisher: "Example Press" } },
        { id: "volume-0002", volumeInfo: { title: "Another Book", publisher: "Example Press" } },
      ],
    }), { status: 200 });
  };
  const clients = new MediaSourceClients(loadConfig({
    DISCORD_TOKEN: "test-token",
    BOT_ID: "123456789012345678",
  }), fetcher);

  const results = await clients.searchGoogleBooksPublishers("Example Press");
  assert.equal(results.length, 1);
  assert.equal(results[0]?.title, "Example Press");
  assert.equal(results[0]?.sourceId, "google-books");
  assert.equal(results[0]?.organizationType, "Publisher");
  assert.equal(requests[0]?.searchParams.get("q"), "inpublisher:Example Press");
});

test("organization search returns only source-backed publisher entities", async () => {
  const requests: URL[] = [];
  const fetcher: typeof fetch = async input => {
    const url = new URL(String(input));
    requests.push(url);
    if (url.hostname === "www.googleapis.com") {
      return new Response(JSON.stringify({
        items: [{ id: "volume-0001", volumeInfo: { title: "Example Book", publisher: "Example Press" } }],
      }), { status: 200 });
    }
    if (url.hostname === "api.bookbrainz.org") {
      return new Response(JSON.stringify({
        resultCount: 1,
        totalCount: 1,
        searchResult: [{
          bbid: "ba446064-90a5-447b-abe5-139be547da2e",
          defaultAlias: { name: "Example Press" },
          entityType: "Publisher",
        }],
      }), { status: 200 });
    }
    throw new Error("Unexpected provider request: " + url.hostname);
  };
  const clients = new MediaSourceClients(loadConfig({
    DISCORD_TOKEN: "test-token",
    BOT_ID: "123456789012345678",
  }), fetcher);

  const results = await clients.searchOrganizations("Example Press");
  assert.deepEqual(results.map(item => item.sourceId).sort(), ["bookbrainz", "google-books"]);
  assert.ok(results.every(item => item.category === "organization" && item.organizationType === "Publisher"));
  assert.ok(requests.some(url => url.searchParams.get("type") === "publisher"));
});

test("screen and community search do not expose providers without reliable suitability metadata", async () => {
  const requests: string[] = [];
  const fetcher: typeof fetch = async input => {
    requests.push(String(input));
    return new Response("{}", { status: 200 });
  };
  const clients = new MediaSourceClients(loadConfig({
    DISCORD_TOKEN: "test-token",
    BOT_ID: "123456789012345678",
    MAL_CLIENT_ID: "mal-client",
    TVMAZE_SHAREALIKE_CONFIRMED: "true",
    TRAKT_CLIENT_ID: "trakt-client",
    TVDB_API_KEY: "tvdb-key",
    TVDB_ACCESS_ENABLED: "true",
    REDDIT_CLIENT_ID: "reddit-id",
    REDDIT_CLIENT_SECRET: "reddit-secret",
    REDDIT_API_ACCESS_CONFIRMED: "true",
    COMIC_VINE_API_KEY: "comic-key",
    COMIC_VINE_NONCOMMERCIAL_CONFIRMED: "true",
  }), fetcher);

  assert.deepEqual(await clients.search("Example", "screen"), []);
  assert.deepEqual(await clients.search("Example", "community"), []);
  assert.equal(requests.length, 0);
});

test("wiki and public-page access are disabled until explicit source allowlists are set", async () => {
  const requests: string[] = [];
  const fetcher: typeof fetch = async input => {
    requests.push(String(input));
    return new Response("{}", { status: 200 });
  };
  const clients = new MediaSourceClients(loadConfig({
    DISCORD_TOKEN: "test-token",
    BOT_ID: "123456789012345678",
  }), fetcher);

  assert.deepEqual(await clients.searchEnabledMediaWikis("Example"), []);
  assert.deepEqual(await clients.searchChronologyReferences("Example"), []);
  assert.equal(requests.length, 0);
});

test("Comic Book Herald uses only its unmodified RSS feed after non-commercial opt-in", async () => {
  const requests: string[] = [];
  const xml = `<?xml version="1.0"?><rss><channel><item><title>Example Reading Guide</title><link>https://www.comicbookherald.com/example-reading-guide/</link></item></channel></rss>`;
  const fetcher: typeof fetch = async input => {
    requests.push(String(input));
    return new Response(xml, {
      status: 200,
      headers: { "content-type": "application/rss+xml; charset=utf-8" },
    });
  };
  const clients = new MediaSourceClients(loadConfig({
    DISCORD_TOKEN: "test-token",
    BOT_ID: "123456789012345678",
    MEDIA_SOURCE_SCRAPE_ALLOWLIST: "comic-book-herald",
    COMIC_BOOK_HERALD_RSS_NONCOMMERCIAL_CONFIRMED: "true",
  }), fetcher);

  const items = await clients.searchChronologyReferences("Example");
  assert.equal(items.length, 1);
  assert.equal(items[0]?.title, "Example Reading Guide");
  assert.equal(items[0]?.url, "https://www.comicbookherald.com/example-reading-guide/");
  assert.deepEqual(requests, ["https://www.comicbookherald.com/feed/"]);
});

test("Comic Book Herald feed is not fetched without explicit non-commercial confirmation", async () => {
  const requests: string[] = [];
  const fetcher: typeof fetch = async input => {
    requests.push(String(input));
    return new Response("{}", { status: 200, headers: { "content-type": "application/rss+xml" } });
  };
  const clients = new MediaSourceClients(loadConfig({
    DISCORD_TOKEN: "test-token",
    BOT_ID: "123456789012345678",
    MEDIA_SOURCE_SCRAPE_ALLOWLIST: "comic-book-herald",
  }), fetcher);

  assert.deepEqual(await clients.searchChronologyReferences("Example"), []);
  assert.equal(requests.length, 0);
});

test("source reference directory includes Novel Updates and supported search links", () => {
  const links = getMediaSourceResearchLinks("Example title");
  assert.ok(links.some(link => link.id === "novel-updates"
    && link.url === "https://www.novelupdates.com/series-finder/?sf=1&sh=Example%20title"));
  assert.ok(links.some(link => link.id === "wookieepedia" && link.url?.includes("Special:Search")));
  assert.ok(links.some(link => link.id === "anilist" && link.url?.includes("Example%20title")));
});

