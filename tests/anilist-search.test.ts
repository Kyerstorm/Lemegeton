import assert from "node:assert/strict";
import test from "node:test";
import { AniListClient } from "../helpers/integration/anilist.js";

function makeClient(queries: Array<{ query: string; variables: Record<string, unknown> }>): AniListClient {
  return new AniListClient("https://anilist.example/graphql", 1_000, async (_input, init) => {
    const body = JSON.parse(String(init?.body)) as { query: string; variables: Record<string, unknown> };
    queries.push(body);
    return new Response(JSON.stringify({ data: { Page: { media: [] } } }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  });
}

test("AniList manga results use MANGA format and light novels use NOVEL format", async () => {
  const queries: Array<{ query: string; variables: Record<string, unknown> }> = [];
  const client = makeClient(queries);
  await client.search("Dandadan", "MANGA");
  await client.search("Ascendance of a Bookworm", "MANGA", true);
  assert.equal(queries[0]?.variables.type, "MANGA");
  assert.equal(queries[0]?.variables.format, "MANGA");
  assert.equal(queries[1]?.variables.type, "MANGA");
  assert.equal(queries[1]?.variables.format, "NOVEL");
});

test("AniList random, trending, genre and Media Night manga pools exclude novel format", async () => {
  const queries: Array<{ query: string; variables: Record<string, unknown> }> = [];
  const client = makeClient(queries);
  await client.random("MANGA");
  await client.trending("MANGA");
  await client.searchByGenres("MANGA", ["Fantasy"]);
  await client.mediaNightCandidates("MANGA");
  assert.deepEqual(queries.map(item => item.variables.format), ["MANGA", "MANGA", "MANGA", "MANGA"]);
});

test("AniList rejects a format filter that crosses the manga/light-novel boundary", async () => {
  const client = makeClient([]);
  await assert.rejects(() => client.search("Bookworm", "MANGA", false, { format: "NOVEL" }), /separate MANGA records from light novels/);
  await assert.rejects(() => client.search("Manga", "MANGA", true, { format: "MANGA" }), /separate MANGA records from light novels/);
});
