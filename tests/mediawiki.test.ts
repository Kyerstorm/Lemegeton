import test from "node:test";
import assert from "node:assert/strict";
import {
  getMediaWikiEndpoint,
  MediaWikiClient,
  parseMediaWikiPages,
} from "../helpers/integration/mediawiki.js";

test("MediaWiki pages accept only source-host HTTPS canonical URLs", () => {
  const pages = parseMediaWikiPages({ query: { pages: [
    { pageid: 42, title: "Example", fullurl: "https://starwars.fandom.com/wiki/Example", extract: "<p>Example summary</p>", lastrevid: 900 },
    { pageid: 43, title: "External", fullurl: "https://evil.example/wiki/External" },
    { pageid: 44, title: "Insecure", fullurl: "http://starwars.fandom.com/wiki/Insecure" },
    { pageid: 45, title: "Missing", fullurl: "https://starwars.fandom.com/wiki/Missing", missing: true },
  ] } }, "https://starwars.fandom.com/api.php");
  assert.deepEqual(pages, [{
    pageId: 42,
    title: "Example",
    url: "https://starwars.fandom.com/wiki/Example",
    excerpt: "Example summary",
    latestRevisionId: 900,
  }]);
});

test("MediaWiki endpoint lookup is restricted to the reviewed source map", () => {
  assert.equal(getMediaWikiEndpoint("wookieepedia"), "https://starwars.fandom.com/api.php");
  assert.equal(getMediaWikiEndpoint("unlisted-wiki"), null);
});

test("MediaWiki client sends bounded Action API requests directly", async () => {
  const requested: URL[] = [];
  const fetcher: typeof fetch = async input => {
    const url = new URL(String(input));
    requested.push(url);
    return new Response(JSON.stringify({ query: { pages: [{
      pageid: 12,
      title: "The Example",
      fullurl: "https://starwars.fandom.com/wiki/The_Example",
      lastrevid: 77,
    }] } }), { status: 200, headers: { "content-type": "application/json" } });
  };
  const client = new MediaWikiClient("wookieepedia", fetcher);
  const pages = await client.searchPages("The Example");
  assert.equal(pages[0]?.pageId, 12);
  const apiRequest = requested.find(url => url.pathname === "/api.php");
  assert.equal(apiRequest?.searchParams.get("action"), "query");
  assert.equal(apiRequest?.searchParams.get("generator"), "search");
  assert.equal(apiRequest?.searchParams.get("gsrlimit"), "8");
  assert.equal(apiRequest?.searchParams.get("formatversion"), "2");
  assert.equal(requested[0]?.pathname, "/api.php");
});
