import assert from "node:assert/strict";
import test from "node:test";
import { KitsuClient, parseKitsuMedia } from "../helpers/integration/kitsu.js";
import { rankTitleSearchResults } from "../helpers/media/title-matching.js";

const anime = {
  id: "1",
  type: "anime",
  attributes: {
    slug: "example-anime",
    synopsis: "A source-backed anime summary.",
    titles: { en: "Example Anime", en_jp: "Example Anime", ja_jp: "例アニメ" },
    canonicalTitle: "Example Anime",
    abbreviatedTitles: ["EA"],
    ageRating: "PG",
    ageRatingGuide: "Teens 13 or older",
    status: "finished",
    subtype: "TV",
    startDate: "2024-01-02",
    endDate: "2024-04-02",
    averageRating: "84.25",
    episodeCount: 12,
    episodeLength: 24,
    posterImage: { large: "https://media.kitsu.io/anime/poster_images/1/large.jpg" },
  },
  relationships: {
    genres: { data: [{ id: "2", type: "genres" }] },
    categories: { data: [{ id: "3", type: "categories" }] },
  },
};
const included = [
  { id: "2", type: "genres", attributes: { name: "Adventure" } },
  { id: "3", type: "categories", attributes: { title: "Coming of Age" } },
];

test("Kitsu media normalization retains metadata, titles and linked genre/category labels", () => {
  const result = parseKitsuMedia(anime, included);
  assert.ok(result);
  assert.equal(result.title, "Example Anime");
  assert.deepEqual(result.alternateTitles, ["例アニメ", "EA"]);
  assert.equal(result.sourceUrl, "https://kitsu.io/anime/example-anime");
  assert.equal(result.ageRating, "PG");
  assert.equal(result.rating, 84.25);
  assert.equal(result.episodeCount, 12);
  assert.equal(result.episodeLength, 24);
  assert.deepEqual(result.genres, ["Adventure"]);
  assert.deepEqual(result.categories, ["Coming of Age"]);
  assert.equal(parseKitsuMedia({ ...anime, attributes: { ...anime.attributes, nsfw: true } }, included), null);
});

test("Kitsu rejects adult, unknown-rated and incomplete media records", () => {
  for (const rating of ["R", "R18", "PG-13", null, undefined]) {
    assert.equal(parseKitsuMedia({ ...anime, attributes: { ...anime.attributes, ageRating: rating } }, included), null);
  }
  assert.equal(parseKitsuMedia({ ...anime, attributes: { ...anime.attributes, canonicalTitle: "", titles: {} } }, included), null);
  assert.equal(parseKitsuMedia({ ...anime, relationships: {} }, included)?.genres.length, 0);
});

test("Kitsu title search uses the public JSON:API filter and returns only G/PG titles", async () => {
  let requestUrl = "";
  let accept = "";
  const fetcher: typeof fetch = async (input, init) => {
    requestUrl = String(input);
    accept = new Headers(init?.headers).get("accept") ?? "";
    return new Response(JSON.stringify({
      data: [
        anime,
        { ...anime, id: "2", attributes: { ...anime.attributes, slug: "adult-anime", canonicalTitle: "Adult Anime", ageRating: "R18" } },
        { ...anime, id: "3", attributes: { ...anime.attributes, slug: "unrated-anime", canonicalTitle: "Unrated Anime", ageRating: null } },
      ],
      included,
    }), { status: 200, headers: { "content-type": "application/vnd.api+json" } });
  };
  const client = new KitsuClient(fetcher);
  const results = await client.search("Example Anime", "anime");
  const url = new URL(requestUrl);
  assert.equal(url.origin + url.pathname, "https://kitsu.io/api/edge/anime");
  assert.equal(url.searchParams.get("filter[text]"), "Example Anime");
  assert.equal(url.searchParams.get("filter[ageRating]"), "G,PG");
  assert.equal(url.searchParams.get("page[limit]"), "20");
  assert.equal(url.searchParams.get("include"), "genres,categories");
  assert.equal(accept, "application/vnd.api+json");
  assert.equal(results.length, 1);
  assert.equal(results[0]?.title, "Example Anime");
});

test("Kitsu category search normalizes its filter slug and caches repeated queries", async () => {
  let calls = 0;
  const client = new KitsuClient(async input => {
    calls += 1;
    const url = new URL(String(input));
    assert.equal(url.pathname, "/api/edge/manga");
    assert.equal(url.searchParams.get("filter[categories]"), "science-fiction");
    return new Response(JSON.stringify({ data: [], included: [] }), {
      status: 200,
      headers: { "content-type": "application/vnd.api+json" },
    });
  });
  assert.deepEqual(await client.searchByCategory("Science Fiction", "manga"), []);
  assert.deepEqual(await client.searchByCategory("Science Fiction", "manga"), []);
  assert.equal(calls, 1);
});

test("Kitsu alternate title variants participate in shared title relevance ranking", () => {
  const records = [
    { title: "Other Title", alternateTitles: [] },
    { title: "Example Anime", alternateTitles: ["例アニメ", "EA"] },
  ];
  const ranked = rankTitleSearchResults("EA", records, item => [item.title, ...item.alternateTitles]);
  assert.equal(ranked[0]?.title, "Example Anime");
});
