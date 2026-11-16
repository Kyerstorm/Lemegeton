import test from "node:test";
import assert from "node:assert/strict";
import { aniListReleaseOrder, tmdbCollectionReleaseOrder } from "../helpers/media/franchise-order.js";

test("AniList franchise release order requires complete dates and sorts provider relationships", () => {
  const order = aniListReleaseOrder(
    { title: "Middle", url: "https://anilist.co/anime/2", startDate: { year: 2020, month: 2, day: 1 } },
    [
      { title: "Later", url: "https://anilist.co/anime/3", startDate: { year: 2021, month: 1, day: 1 } },
      { title: "Earlier", url: "https://anilist.co/anime/1", startDate: { year: 2019, month: 12, day: 31 } },
    ],
  );
  assert.deepEqual(order?.map(item => [item.title, item.date]), [
    ["Earlier", "2019-12-31"],
    ["Middle", "2020-02-01"],
    ["Later", "2021-01-01"],
  ]);
  assert.equal(aniListReleaseOrder(
    { title: "Seed", url: null, startDate: { year: 2020, month: 1, day: null } },
    [{ title: "Related", url: "https://anilist.co/anime/4", startDate: { year: 2021, month: 1, day: 1 } }],
  ), null);
});

test("TMDB collection release order requires every member to have a valid full date", () => {
  const order = tmdbCollectionReleaseOrder([
    { title: "Later", sourceUrl: "https://www.themoviedb.org/movie/2", releaseDate: "2021-05-02" },
    { title: "Earlier", sourceUrl: "https://www.themoviedb.org/movie/1", releaseDate: "2019-12-31" },
  ]);
  assert.deepEqual(order?.map(item => [item.title, item.date]), [
    ["Earlier", "2019-12-31"],
    ["Later", "2021-05-02"],
  ]);
  assert.equal(tmdbCollectionReleaseOrder([
    { title: "First", sourceUrl: "https://www.themoviedb.org/movie/1", releaseDate: "2020-01-01" },
    { title: "Unknown", sourceUrl: "https://www.themoviedb.org/movie/2", releaseDate: null },
  ]), null);
  assert.equal(tmdbCollectionReleaseOrder([
    { title: "Invalid", sourceUrl: "https://www.themoviedb.org/movie/1", releaseDate: "2020-02-31" },
    { title: "Valid", sourceUrl: "https://www.themoviedb.org/movie/2", releaseDate: "2020-03-01" },
  ]), null);
});
