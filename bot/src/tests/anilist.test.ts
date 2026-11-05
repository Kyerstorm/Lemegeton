import assert from "node:assert/strict";
import test from "node:test";
import { AniListClient, AniListError } from "../providers/anilist.js";

const sampleMedia = {
  id: 1,
  type: "ANIME",
  title: { romaji: "Sample", english: "Sample", native: null },
  description: "A sample title.",
  averageScore: 82,
  siteUrl: "https://anilist.co/anime/1",
  status: "FINISHED",
  format: "TV",
  episodes: 12,
  chapters: null,
  volumes: null,
  startDate: { year: 2024, month: 1, day: 1 },
  genres: ["Drama"],
  coverImage: { large: "https://example.com/cover.jpg" },
};

test("searchMedia sends AniList search variables and returns validated media", async () => {
  let sentVariables: Record<string, unknown> | undefined;
  const fetcher: typeof fetch = async (_input, init) => {
    const body = JSON.parse(String(init?.body)) as { variables?: Record<string, unknown> };
    sentVariables = body.variables;
    return new Response(JSON.stringify({ data: { Page: { media: [sampleMedia] } } }), { status: 200 });
  };
  const client = new AniListClient("https://graphql.anilist.co", 1_000, fetcher);
  const result = await client.searchMedia("  Sample  ", "ANIME");

  assert.equal(sentVariables?.search, "Sample");
  assert.equal(sentVariables?.type, "ANIME");
  assert.equal(sentVariables?.sort, "SEARCH_MATCH");
  assert.equal(result[0]?.id, 1);
});

test("getTrending requests AniList trending sort without a search term", async () => {
  let sentVariables: Record<string, unknown> | undefined;
  const fetcher: typeof fetch = async (_input, init) => {
    sentVariables = (JSON.parse(String(init?.body)) as { variables: Record<string, unknown> }).variables;
    return new Response(JSON.stringify({ data: { Page: { media: [] } } }), { status: 200 });
  };
  const client = new AniListClient("https://graphql.anilist.co", 1_000, fetcher);
  await client.getTrending("MANGA");

  assert.deepEqual(sentVariables, { type: "MANGA", sort: "TRENDING_DESC" });
});

test("AniList GraphQL errors become a safe provider error", async () => {
  const fetcher: typeof fetch = async () =>
    new Response(JSON.stringify({ errors: [{ message: "Provider details" }] }), { status: 200 });
  const client = new AniListClient("https://graphql.anilist.co", 1_000, fetcher);

  await assert.rejects(
    () => client.searchMedia("Sample", "ANIME"),
    (error: unknown) => error instanceof AniListError && error.message === "AniList could not complete this search.",
  );
});

test("AniList HTTP errors preserve their status code", async () => {
  const fetcher: typeof fetch = async () => new Response("", { status: 429 });
  const client = new AniListClient("https://graphql.anilist.co", 1_000, fetcher);

  await assert.rejects(
    () => client.searchMedia("Sample", "ANIME"),
    (error: unknown) => error instanceof AniListError && error.statusCode === 429,
  );
});

test("malformed provider records are ignored", async () => {
  const fetcher: typeof fetch = async () =>
    new Response(JSON.stringify({
      data: { Page: { media: [sampleMedia, { id: "not-an-id", type: "ANIME", siteUrl: "https://anilist.co" }] } },
    }), { status: 200 });
  const client = new AniListClient("https://graphql.anilist.co", 1_000, fetcher);
  const result = await client.searchMedia("Sample", "ANIME");

  assert.equal(result.length, 1);
  assert.equal(result[0]?.id, 1);
});

test("AniList timeout failures return a provider-specific timeout error", async () => {
  const fetcher: typeof fetch = async () => {
    throw new DOMException("The request timed out", "TimeoutError");
  };
  const client = new AniListClient("https://graphql.anilist.co", 1_000, fetcher);

  await assert.rejects(
    () => client.searchMedia("Sample", "ANIME"),
    (error: unknown) => error instanceof AniListError && error.message === "AniList request timed out.",
  );
});
