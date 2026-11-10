import test from "node:test";
import assert from "node:assert/strict";
import { loadConfig } from "../helpers/runtime/config.js";

function environment(overrides: NodeJS.ProcessEnv = {}): NodeJS.ProcessEnv {
  return {
    DISCORD_TOKEN: "test-discord-token",
    BOT_ID: "123456789012345678",
    ...overrides,
  };
}

test("loads safe defaults for a local TypeScript bot", () => {
  const config = loadConfig(environment());

  assert.equal(config.applicationId, "123456789012345678");
  assert.equal(config.anilistApiUrl, "https://graphql.anilist.co/");
  assert.equal(config.anilistTimeoutMs, 10_000);
  assert.equal(config.customRolesReconcileMinutes, 30);
  assert.equal(config.archiveUploadMaxBytes, 20 * 1024 * 1024);
  assert.equal(config.customRolePickerEnabled, true);
  assert.equal(config.customRolesTrustProxy, false);
  assert.equal(config.botModeratorGuildId, null);
});

test("loads and validates the configured Custom Roles reconciliation interval", () => {
  const config = loadConfig(environment({ CUSTOM_ROLES_RECONCILE_MINUTES: "7" }));
  assert.equal(config.customRolesReconcileMinutes, 7);
  assert.throws(
    () => loadConfig(environment({ CUSTOM_ROLES_RECONCILE_MINUTES: "0" })),
    /CUSTOM_ROLES_RECONCILE_MINUTES must be a positive integer/,
  );
});

test("loads and bounds the Custom Roles original icon size", () => {
  assert.equal(loadConfig(environment()).customRoleIconSourceMaxBytes, 8 * 1024 * 1024);
  assert.equal(
    loadConfig(environment({ CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES: String(4 * 1024 * 1024) })).customRoleIconSourceMaxBytes,
    4 * 1024 * 1024,
  );
  assert.equal(
    loadConfig(environment({ CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES: "1024" })).customRoleIconSourceMaxBytes,
    256 * 1024,
  );
  assert.throws(
    () => loadConfig(environment({ CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES: "invalid" })),
    /CUSTOM_ROLES_ICON_SOURCE_MAX_BYTES must be a positive integer/,
  );
});

test("accepts a valid dedicated bot-moderator guild and paired IGDB credentials", () => {
  const config = loadConfig(environment({
    BOT_MODERATOR_GUILD_ID: "987654321098765432",
    IGDB_CLIENT_ID: "client-id",
    IGDB_CLIENT_SECRET: "client-secret",
  }));

  assert.equal(config.botModeratorGuildId, "987654321098765432");
  assert.equal(config.igdbClientId, "client-id");
  assert.equal(config.igdbClientSecret, "client-secret");
});

test("rejects an invalid Discord application or moderator-guild ID", () => {
  assert.throws(() => loadConfig(environment({ BOT_ID: "not-an-id" })), /application ID/);
  assert.throws(() => loadConfig(environment({ BOT_MODERATOR_GUILD_ID: "1234" })), /server ID/);
});

test("rejects non-HTTPS provider and public picker origins", () => {
  assert.throws(() => loadConfig(environment({ ANILIST_API_URL: "http://anilist.example/graphql" })), /ANILIST_API_URL must use HTTPS/);
  assert.throws(() => loadConfig(environment({ CUSTOM_ROLES_PUBLIC_URL: "http://roles.example" })), /CUSTOM_ROLES_PUBLIC_URL must use HTTPS/);
});

test("rejects partial provider credentials and unsafe picker binding", () => {
  assert.throws(() => loadConfig(environment({ IGDB_CLIENT_ID: "client-id" })), /configured together/);
  assert.throws(() => loadConfig(environment({ DASHBOARD_PICKER_HOST: "0.0.0.0" })), /loopback/);
});
