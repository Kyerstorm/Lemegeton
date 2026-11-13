import test from "node:test";
import assert from "node:assert/strict";
import { AniListClient } from "../helpers/integration/anilist.js";
import { GoogleBooksClient } from "../helpers/integration/google-books.js";
import { IgdbClient } from "../helpers/integration/igdb.js";
import { SteamClient } from "../helpers/integration/steam.js";
import { TmdbClient } from "../helpers/integration/tmdb.js";

const liveEnabled = process.env.LEMEGETON_LIVE_PROVIDER_TESTS === "1";
const steamKey = process.env.STEAM_API_KEY?.trim() ?? "";
const steamProfile = process.env.STEAM_TEST_PROFILE_ID?.trim() ?? "";
const igdbClientId = process.env.IGDB_CLIENT_ID?.trim() ?? "";
const igdbClientSecret = process.env.IGDB_CLIENT_SECRET?.trim() ?? "";
const tmdbToken = process.env.TMDB_BEARER_TOKEN?.trim() ?? "";

test("live AniList search returns normalized anime metadata", {
  skip: !liveEnabled,
}, async () => {
  const results = await new AniListClient().search("Frieren", "ANIME");
  assert.ok(results.length > 0, "AniList must return at least one matching anime.");
  assert.ok(results.every(item => Number.isSafeInteger(item.id) && item.id > 0 && item.title));
});

test("live Google Books search returns normalized book metadata", {
  skip: !liveEnabled,
}, async () => {
  const results = await new GoogleBooksClient(process.env.GOOGLE_BOOKS_API_KEY).search("Dune Frank Herbert");
  assert.ok(results.length > 0, "Google Books must return at least one matching book.");
  assert.ok(results.every(item => item.id.length > 0 && item.title.length > 0));
});

test("live Steam profile lookup resolves the configured public test profile", {
  skip: !liveEnabled || !steamKey || !steamProfile,
}, async () => {
  const profile = await new SteamClient(steamKey).getProfile(steamProfile);
  assert.equal(profile.steamId, steamProfile);
  assert.ok(profile.personaName.length > 0);
  assert.ok(["public", "private", "unknown"].includes(profile.visibility));
});

test("live IGDB search authenticates and returns game metadata", {
  skip: !liveEnabled || !igdbClientId || !igdbClientSecret,
}, async () => {
  const results = await new IgdbClient(igdbClientId, igdbClientSecret).search("The Witcher 3 Wild Hunt");
  assert.ok(results.length > 0, "IGDB must return at least one matching game.");
  assert.ok(results.every(item => Number.isSafeInteger(item.id) && item.id > 0 && item.title.length > 0));
});

test("live TMDB search returns movie metadata", {
  skip: !liveEnabled || !tmdbToken,
}, async () => {
  const results = await new TmdbClient(tmdbToken).search("Dune", "movie");
  assert.ok(results.length > 0, "TMDB must return at least one matching movie.");
  assert.ok(results.every(item => Number.isSafeInteger(item.id) && item.id > 0 && item.category === "movie"));
});
