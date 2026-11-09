import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizeTmdbCollection,
  normalizeTmdbMedia,
  normalizeTmdbPeople,
  normalizeTmdbPersonCredits,
  normalizeTmdbTvDetails,
  normalizeTmdbTvSeason,
  normalizeTmdbVideos,
  normalizeTmdbWatchAvailability,
} from "../helpers/tmdb.js";
import { normalizeMediaRegion } from "../helpers/media-region.js";

test("TMDB media normalization accepts valid movie and TV records", () => {
  const movie = normalizeTmdbMedia({
    id: 12,
    title: "Example Film",
    overview: "A film.",
    poster_path: "/poster.jpg",
    release_date: "2026-01-02",
    vote_average: 7.5,
  }, "movie");
  assert.equal(movie?.title, "Example Film");
  assert.equal(movie?.sourceUrl, "https://www.themoviedb.org/movie/12");
  assert.equal(movie?.image, "https://image.tmdb.org/t/p/w500/poster.jpg");
  assert.equal(movie?.releaseDate, "2026-01-02");

  const series = normalizeTmdbMedia({ id: 13, name: "Example Series" }, "tv");
  assert.equal(series?.title, "Example Series");
  assert.equal(series?.sourceUrl, "https://www.themoviedb.org/tv/13");
});

test("TMDB media normalization rejects invalid identifiers and missing titles", () => {
  assert.equal(normalizeTmdbMedia({ id: -1, title: "Bad" }, "movie"), null);
  assert.equal(normalizeTmdbMedia({ id: 3, name: "TV name" }, "movie"), null);
  assert.equal(normalizeTmdbMedia({ id: 3, title: " " }, "movie"), null);
});

test("TMDB watch availability deduplicates provider names and validates the provider link", () => {
  const result = normalizeTmdbWatchAvailability({
    flatrate: [
      { provider_name: "Stream A" },
      { provider_name: "Stream A" },
      { provider_name: "Stream B" },
      { provider_name: "" },
    ],
    rent: [{ provider_name: "Rent Store" }],
    link: "https://www.themoviedb.org/movie/12/watch",
  }, "IE");

  assert.equal(result?.region, "IE");
  assert.equal(result?.link, "https://www.themoviedb.org/movie/12/watch");
  assert.deepEqual(result?.groups.map((group) => [group.type, group.providers]), [
    ["streaming", ["Stream A", "Stream B"]],
    ["rent", ["Rent Store"]],
  ]);

  const unsafe = normalizeTmdbWatchAvailability({ link: "javascript:alert(1)" }, "US");
  assert.equal(unsafe?.link, null);
  assert.deepEqual(unsafe?.groups, []);
});

test("TMDB availability distinguishes a missing regional record", () => {
  assert.equal(normalizeTmdbWatchAvailability(undefined, "IE"), null);
});

test("TMDB videos only exposes safe YouTube and Vimeo links", () => {
  const videos = normalizeTmdbVideos({
    results: [
      { id: "yt-1", name: "Official Trailer", site: "YouTube", key: "abc123", type: "Trailer", official: true },
      { id: "vm-1", name: "Teaser", site: "Vimeo", key: "clip-7", type: "Teaser", official: false },
      { id: "bad", name: "Unsupported", site: "Other", key: "untrusted", type: "Trailer" },
      { id: "empty", name: "Missing key", site: "YouTube", key: "" },
    ],
  });

  assert.equal(videos.length, 2);
  assert.equal(videos[0]?.url, "https://www.youtube.com/watch?v=abc123");
  assert.equal(videos[0]?.official, true);
  assert.equal(videos[1]?.url, "https://vimeo.com/clip-7");
});

test("TMDB video normalization limits results and removes duplicate records", () => {
  const results = Array.from({ length: 15 }, (_, index) => ({
    id: "video-" + index,
    name: "Video " + index,
    site: "YouTube",
    key: "key-" + index,
    type: "Trailer",
  }));
  results.push(results[0]!);
  const videos = normalizeTmdbVideos({ results });
  assert.equal(videos.length, 12);
});

test("server media regions normalize valid ISO-style country codes", () => {
  assert.equal(normalizeMediaRegion("ie"), "IE");
  assert.equal(normalizeMediaRegion("US"), "US");
  assert.equal(normalizeMediaRegion(" I "), null);
  assert.equal(normalizeMediaRegion("USA"), null);
  assert.equal(normalizeMediaRegion("1E"), null);
});

test("TMDB people normalization validates IDs and safe profile paths", () => {
  const people = normalizeTmdbPeople({
    results: [
      { id: 4, name: "Example Creator", profile_path: "/creator.jpg" },
      { id: -1, name: "Invalid" },
      { id: 5, name: "   " },
    ],
  });
  assert.equal(people.length, 1);
  assert.equal(people[0]?.name, "Example Creator");
  assert.equal(people[0]?.sourceUrl, "https://www.themoviedb.org/person/4");
  assert.equal(people[0]?.image, "https://image.tmdb.org/t/p/w500/creator.jpg");
});

test("TMDB person credits combine cast and crew, deduplicate and retain role/date", () => {
  const credits = normalizeTmdbPersonCredits({
    cast: [
      { id: 12, media_type: "movie", title: "Film A", release_date: "2024-01-01", character: "Lead", popularity: 8 },
      { id: 14, media_type: "tv", name: "Series B", first_air_date: "2023-01-01", character: "Guest", popularity: 7 },
    ],
    crew: [
      { id: 12, media_type: "movie", title: "Film A", job: "Director", popularity: 8 },
      { id: 15, media_type: "unknown", title: "Unsupported" },
      { id: 16, media_type: "movie", title: "", popularity: 1 },
    ],
  });
  assert.equal(credits.length, 2);
  assert.equal(credits[0]?.title, "Film A");
  assert.equal(credits[0]?.role, "Lead");
  assert.equal(credits[0]?.releaseDate, "2024-01-01");
  assert.equal(credits[1]?.category, "tv");
});

test("TMDB collection normalization sorts dates, filters invalid members and limits output", () => {
  const collection = normalizeTmdbCollection({
    id: 30,
    name: "Example Collection",
    poster_path: "/collection.jpg",
    parts: [
      { id: 3, title: "Later", release_date: "2025-01-01" },
      { id: 2, title: "Earlier", release_date: "2020-01-01" },
      { id: 4, title: "Date unknown" },
      { id: -2, title: "Invalid id" },
      { id: 5, title: "" },
    ],
  });
  assert.equal(collection?.sourceUrl, "https://www.themoviedb.org/collection/30");
  assert.deepEqual(collection?.items.map((item) => item.title), ["Earlier", "Later", "Date unknown"]);
  assert.equal(collection?.image, "https://image.tmdb.org/t/p/w500/collection.jpg");
  assert.equal(normalizeTmdbCollection({ id: 2, name: " " }), null);
});

test("TMDB TV detail normalization includes creators, networks, runtimes and season summaries", () => {
  const details = normalizeTmdbTvDetails({
    id: 99,
    name: "Example Series",
    overview: "A show.",
    status: "Returning Series",
    number_of_seasons: 2,
    number_of_episodes: 16,
    episode_run_time: [42, 43, "invalid", -1],
    created_by: [{ name: "Creator One" }, { name: "" }],
    networks: [{ name: "Network A" }],
    poster_path: "/show.jpg",
    seasons: [
      { id: 2, season_number: 2, name: "Second", episode_count: 8, air_date: "2024-01-01" },
      { id: 1, season_number: 1, name: "First", episode_count: 8, air_date: "2023-01-01" },
      { id: 3, season_number: -1, name: "Invalid" },
    ],
    next_episode_to_air: { id: 990, episode_number: 1, season_number: 2, name: "Next", air_date: "2026-01-01", runtime: 45 },
  });
  assert.equal(details?.name, "Example Series");
  assert.equal(details?.numberOfEpisodes, 16);
  assert.deepEqual(details?.episodeRuntimes, [42, 43]);
  assert.deepEqual(details?.creators, ["Creator One"]);
  assert.deepEqual(details?.networks, ["Network A"]);
  assert.deepEqual(details?.seasons.map((season) => season.seasonNumber), [1, 2]);
  assert.equal(details?.nextEpisode?.sourceUrl, "https://www.themoviedb.org/tv/99/episode/990");
  assert.equal(details?.nextEpisode?.seasonNumber, 2);
  assert.equal(normalizeTmdbTvDetails({ id: 0, name: "Bad" }), null);
});

test("TMDB TV season normalization validates episode data and sorts episode numbers", () => {
  const season = normalizeTmdbTvSeason({
    season_number: 1,
    name: "Season One",
    episodes: [
      { id: 22, episode_number: 2, season_number: 1, name: "Second", air_date: "2025-02-01", runtime: 45, overview: "Second." },
      { id: 21, episode_number: 1, season_number: 1, name: "First", air_date: "2025-01-01", runtime: 43, overview: "First." },
      { id: -1, episode_number: -5, name: "Bad" },
    ],
  }, 99);
  assert.deepEqual(season?.episodes.map((episode) => episode.episodeNumber), [1, 2]);
  assert.equal(season?.episodes[0]?.sourceUrl, "https://www.themoviedb.org/tv/99/episode/21");
  assert.equal(season?.episodes[0]?.seasonNumber, 1);
  assert.equal(season?.sourceUrl, "https://www.themoviedb.org/tv/99/season/1");
  assert.equal(normalizeTmdbTvSeason({ season_number: -1 }, 99), null);
});
