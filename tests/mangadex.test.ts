import assert from "node:assert/strict";
import test from "node:test";
import { MangaDexClient } from "../helpers/integration/mangadex.js";

const id = "b7e5a8c2-3f66-4e9c-9355-c9d5df5c4a90";

function manga(contentRating: string, title: string) {
  return {
    id,
    type: "manga",
    attributes: {
      title: { en: title },
      altTitles: [{ ja: "Japanese title" }],
      description: { en: "A story." },
      status: "ongoing",
      year: 2022,
      originalLanguage: "ja",
      publicationDemographic: "shounen",
      contentRating,
      tags: [{ attributes: { name: { en: "Fantasy" } } }],
    },
    relationships: [
      { id: "author-id", type: "author", attributes: { name: "A. Author" } },
      { id: "artist-id", type: "artist", attributes: { name: "A. Artist" } },
      { id: "cover-id", type: "cover_art", attributes: { fileName: "cover.jpg" } },
    ],
  };
}

test("MangaDex title search requests safe content and normalizes metadata", async () => {
  let requestUrl = "";
  let userAgent = "";
  const client = new MangaDexClient(async (input, init) => {
    requestUrl = String(input);
    userAgent = new Headers(init?.headers).get("User-Agent") ?? "";
    return new Response(JSON.stringify({ data: [manga("safe", "A Safe Manga"), manga("suggestive", "Filtered title")] }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }, 0);
  const results = await client.search("A Safe Manga");
  const url = new URL(requestUrl);
  assert.equal(url.searchParams.get("title"), "A Safe Manga");
  assert.equal(url.searchParams.get("contentRating[]"), "safe");
  assert.match(userAgent, /Lemegeton/);
  assert.equal(results.length, 1);
  assert.equal(results[0]?.title, "A Safe Manga");
  assert.deepEqual(results[0]?.authors, ["A. Author"]);
  assert.deepEqual(results[0]?.artists, ["A. Artist"]);
  assert.deepEqual(results[0]?.tags, ["Fantasy"]);
  assert.equal(results[0]?.coverUrl, "https://uploads.mangadex.org/covers/" + id + "/cover.jpg.256.jpg");
  assert.equal(results[0]?.contentRating, "safe");
});

test("MangaDex tag search resolves tag IDs and requests Safe-rated works", async () => {
  const requests: string[] = [];
  const client = new MangaDexClient(async input => {
    const url = String(input);
    requests.push(url);
    if (url.endsWith("/manga/tag")) {
      return new Response(JSON.stringify({ data: [{ id: "tag-id", attributes: { name: { en: "Fantasy" } } }] }), { status: 200 });
    }
    return new Response(JSON.stringify({ data: [manga("safe", "Fantasy manga")] }), { status: 200 });
  }, 0);
  const results = await client.searchByTags(["Fantasy"]);
  const url = new URL(requests[1]!);
  assert.equal(url.searchParams.get("contentRating[]"), "safe");
  assert.equal(url.searchParams.get("includedTags[]"), "tag-id");
  assert.equal(url.searchParams.get("includedTagsMode"), "OR");
  assert.equal(results[0]?.title, "Fantasy manga");
});

test("MangaDex never returns malformed IDs or non-safe results when a provider ignores filters", async () => {
  const client = new MangaDexClient(async () => new Response(JSON.stringify({
    data: [manga("pornographic", "Filtered out"), { id: "invalid", attributes: { title: { en: "Bad ID" }, contentRating: "safe" } }],
  }), { status: 200 }), 0);
  assert.deepEqual(await client.search("title"), []);
});
