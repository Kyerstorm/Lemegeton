import test from "node:test";
import assert from "node:assert/strict";
import { parseRoyalRoadFictionId, parseRoyalRoadFeed, RoyalRoadClient } from "../helpers/integration/royal-road.js";

const feed = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>Latest updates of (Knight and Smith)</title>
<link>https://www.royalroad.com/fiction/37155/knight-and-smith</link>
<item><title>Chapter Two</title><link>https://www.royalroad.com/fiction/chapter/200</link><pubDate>Sun, 15 Nov 2026 18:05:33 GMT</pubDate></item>
<item><title><![CDATA[Chapter One &amp; Intro]]></title><link>https://www.royalroad.com/fiction/chapter/100</link><pubDate>Sun, 08 Nov 2026 18:09:15 GMT</pubDate></item>
</channel></rss>`;

test("Royal Road accepts numeric IDs and only its own HTTPS fiction or syndication URLs", () => {
  assert.equal(parseRoyalRoadFictionId("37155"), 37155);
  assert.equal(parseRoyalRoadFictionId("https://www.royalroad.com/fiction/37155/knight-and-smith"), 37155);
  assert.equal(parseRoyalRoadFictionId("https://www.royalroad.com/fiction/syndication/37155"), 37155);
  assert.throws(() => parseRoyalRoadFictionId("https://example.com/fiction/37155"));
  assert.throws(() => parseRoyalRoadFictionId("http://www.royalroad.com/fiction/37155"));
});

test("Royal Road RSS parser extracts story identity and latest chapter dates without chapter bodies", () => {
  const fiction = parseRoyalRoadFeed(feed, 37155);
  assert.equal(fiction?.title, "Knight and Smith");
  assert.equal(fiction?.sourceUrl, "https://www.royalroad.com/fiction/37155/knight-and-smith");
  assert.equal(fiction?.chapters.length, 2);
  assert.equal(fiction?.chapters[0]?.title, "Chapter Two");
  assert.equal(fiction?.latestUpdate, "2026-11-15T18:05:33.000Z");
  assert.equal("description" in (fiction ?? {}), false);
  assert.equal(parseRoyalRoadFeed("<html>not RSS</html>", 37155), null);
});

test("Royal Road client normalizes input to the official feed endpoint and rejects bad feeds", async () => {
  let requested = "";
  const client = new RoyalRoadClient(async (input) => {
    requested = String(input);
    return new Response(feed, { status: 200, headers: { "Content-Type": "application/rss+xml" } });
  });
  const fiction = await client.getFiction("https://www.royalroad.com/fiction/37155/knight-and-smith");
  assert.equal(fiction.id, 37155);
  assert.equal(requested, "https://www.royalroad.com/fiction/syndication/37155");
  const invalid = new RoyalRoadClient(async () => new Response("<html>no feed</html>", { status: 200 }));
  await assert.rejects(() => invalid.getFiction("37155"), /valid public RSS feed/);
});
