import test from "node:test";
import assert from "node:assert/strict";
import {
  missingChannelPermissions,
  providerConfigurationChecks,
  jobQueueChecks,
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
    ["RocksDB private asset storage", false],
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

test("scheduled delivery diagnostics distinguish healthy, due and failed queues", () => {
  assert.deepEqual(jobQueueChecks([
    { name: "Daily Drop", due_count: 0, failed_count: 0, stale_count: 0 },
    { name: "Release digest", due_count: 3, failed_count: 0, stale_count: 0 },
    { name: "Media follow", due_count: 0, failed_count: 1, stale_count: 0 },
    { name: "Automation", due_count: 0, failed_count: 0, stale_count: 2 },
  ]), [
    { name: "Daily Drop", status: "Healthy", detail: "0 due · 0 failed · 0 expired claims." },
    { name: "Release digest", status: "Backlog", detail: "3 due · 0 failed · 0 expired claims." },
    { name: "Media follow", status: "Needs attention", detail: "0 due · 1 failed · 0 expired claims." },
    { name: "Automation", status: "Needs attention", detail: "0 due · 0 failed · 2 expired claims." },
  ]);
});
