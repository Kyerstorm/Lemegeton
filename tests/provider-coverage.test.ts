import test from "node:test";
import assert from "node:assert/strict";
import {
  TmdbClient,
  normalizeTmdbContentRatings,
  normalizeTmdbMedia,
  normalizeTmdbMovieReleaseDates,
} from "../helpers/integration/tmdb.js";
import { parseIgdbGame, parseIgdbCompanyCredits } from "../helpers/integration/igdb.js";

test("IGDB game metadata keeps user and critic ratings on their separate scales", () => {
  const game = parseIgdbGame({
    id: 5, name: "Example", slug: "example", rating: 82.5, rating_count: 120,
    aggregated_rating: 91.2, aggregated_rating_count: 9,
    platforms: [{ name: "PC" }],
  });
  assert.equal(game?.rating, 82.5);
  assert.equal(game?.ratingCount, 120);
  assert.equal(game?.aggregatedRating, 91.2);
  assert.equal(game?.aggregatedRatingCount, 9);
  assert.deepEqual(game?.platforms, ["PC"]);
});

test("IGDB company credits retain platform and region-specific release dates", () => {
  const rows = parseIgdbCompanyCredits([{
    developer: true,
    game: {
      id: 20, name: "Example Game", slug: "example-game", first_release_date: 1798761600,
      rating: 80, rating_count: 100, aggregated_rating: 88, aggregated_rating_count: 12,
      platforms: [{ name: "PC" }, { name: "PlayStation 5" }],
      release_dates: [
        { date: 1798761600, human: "Dec 31, 2026", region: { name: "Worldwide" }, platform: { name: "PC" } },
      ],
    },
  }]);
  assert.equal(rows[0]?.rating, 80);
  assert.equal(rows[0]?.aggregatedRating, 88);
  assert.deepEqual(rows[0]?.platforms, ["PC", "PlayStation 5"]);
  assert.deepEqual(rows[0]?.releases[0], {
    date: "2026-12-31", humanDate: "Dec 31, 2026", platform: "PC", region: "Worldwide",
  });
});

test("TMDB normalizers preserve runtime and country-labelled certifications and ratings", () => {
  const movie = normalizeTmdbMedia({ id: 10, title: "Film", runtime: 121 }, "movie");
  assert.equal(movie?.runtime, 121);
  const tv = normalizeTmdbMedia({ id: 11, name: "Series", episode_run_time: [42, 44] }, "tv");
  assert.deepEqual(tv?.episodeRuntimes, [42, 44]);
  assert.deepEqual(normalizeTmdbMovieReleaseDates({
    results: [{ iso_3166_1: "US", release_dates: [
      { certification: "PG-13", release_date: "2026-12-01T00:00:00.000Z", type: 3, descriptors: ["violence"] },
    ] }],
  }), [{
    region: "US", certification: "PG-13", releaseDate: "2026-12-01T00:00:00.000Z",
    releaseType: 3, descriptors: ["violence"],
  }]);
  assert.deepEqual(normalizeTmdbContentRatings({
    results: [{ iso_3166_1: "IE", rating: "16", descriptors: [] }, { iso_3166_1: "XX", rating: "" }],
  }), [{ region: "IE", rating: "16", descriptors: [] }]);
});

test("TMDB detail lookup enriches movie release certificates and TV content ratings", async () => {
  const requests: string[] = [];
  const client = new TmdbClient("token", async (input) => {
    const path = new URL(String(input)).pathname;
    requests.push(path);
    const body = path.endsWith("/release_dates")
      ? { results: [{ iso_3166_1: "US", release_dates: [{ certification: "PG-13", type: 3 }] }] }
      : path.endsWith("/content_ratings")
        ? { results: [{ iso_3166_1: "GB", rating: "15" }] }
        : path.endsWith("/movie/1") ? { id: 1, title: "Film", runtime: 100 }
        : { id: 2, name: "Series", episode_run_time: [45] };
    return new Response(JSON.stringify(body), { status: 200 });
  });
  const movie = await client.details(1, "movie");
  const tv = await client.details(2, "tv");
  assert.equal(movie?.runtime, 100);
  assert.equal(movie?.certifications[0]?.certification, "PG-13");
  assert.equal(tv?.contentRatings[0]?.rating, "15");
  assert.deepEqual(requests, [
    "/3/movie/1", "/3/movie/1/release_dates", "/3/tv/2", "/3/tv/2/content_ratings",
  ]);
});
