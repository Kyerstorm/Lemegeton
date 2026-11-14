import test from "node:test";
import assert from "node:assert/strict";
import {
  missingChannelPermissions,
  providerConfigurationChecks,
} from "../helpers/runtime/server-diagnostics.js";

test("channel diagnostics reports missing permissions in stable order", () => {
  assert.deepEqual(missingChannelPermissions({
    viewChannel: false,
    sendMessages: true,
    embedLinks: false,
  }), ["View Channel", "Embed Links"]);
});

test("provider diagnostics distinguishes configured integrations from missing optional setup", () => {
  const checks = providerConfigurationChecks({
    aniListEndpointConfigured: true,
    tmdbCredentialsConfigured: true,
    googleBooksKeyConfigured: false,
    igdbCredentialsConfigured: false,
    steamKeyConfigured: true,
    objectStorageConfigured: false,
  });

  assert.deepEqual(checks.map(item => [item.name, item.configured]), [
    ["AniList", true],
    ["TMDB", true],
    ["Google Books", false],
    ["IGDB", false],
    ["Steam", true],
    ["S3-compatible asset storage", false],
  ]);
});

test("provider diagnostic output never includes supplied credentials", () => {
  const checks = providerConfigurationChecks({
    aniListEndpointConfigured: true,
    tmdbCredentialsConfigured: true,
    googleBooksKeyConfigured: true,
    igdbCredentialsConfigured: true,
    steamKeyConfigured: true,
    objectStorageConfigured: true,
  });
  assert.ok(checks.every(check => !/[A-Za-z0-9_-]{24,}/.test(check.detail)));
});
