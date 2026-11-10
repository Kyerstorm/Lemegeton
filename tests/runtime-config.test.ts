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

test("Custom Roles preview switches are development-only", () => {
  const enabled = loadConfig(environment({
    ENVIRONMENT: "development",
    CUSTOM_ROLES_DEBUG_PREVIEW_ENHANCED_COLORS: "true",
    CUSTOM_ROLES_DEBUG_PREVIEW_ROLE_ICONS: "yes",
  }));
  assert.equal(enabled.customRolesDebugPreviewEnhancedColors, true);
  assert.equal(enabled.customRolesDebugPreviewRoleIcons, true);

  const production = loadConfig(environment({
    ENVIRONMENT: "production",
    CUSTOM_ROLES_DEBUG_PREVIEW_ENHANCED_COLORS: "true",
    CUSTOM_ROLES_DEBUG_PREVIEW_ROLE_ICONS: "true",
  }));
  assert.equal(production.customRolesDebugPreviewEnhancedColors, false);
  assert.equal(production.customRolesDebugPreviewRoleIcons, false);

  const nodeProduction = loadConfig(environment({
    NODE_ENV: "production",
    CUSTOM_ROLES_PICKER_ENABLED: "false",
    CUSTOM_ROLES_DEBUG_PREVIEW_ENHANCED_COLORS: "true",
    CUSTOM_ROLES_DEBUG_PREVIEW_ROLE_ICONS: "true",
  }));
  assert.equal(nodeProduction.customRolesDebugPreviewEnhancedColors, false);
  assert.equal(nodeProduction.customRolesDebugPreviewRoleIcons, false);
});

test("loads and validates the configured Custom Roles reconciliation interval", () => {
  const config = loadConfig(environment({ CUSTOM_ROLES_RECONCILE_MINUTES: "7" }));
  assert.equal(config.customRolesReconcileMinutes, 7);
  assert.throws(
    () => loadConfig(environment({ CUSTOM_ROLES_RECONCILE_MINUTES: "0" })),
    /CUSTOM_ROLES_RECONCILE_MINUTES must be a positive integer/,
  );
});
test("loads the Custom Roles mass-archive threshold from typed configuration", () => {
  assert.equal(loadConfig(environment()).customRolesMassArchiveThreshold, 10);
  assert.equal(loadConfig(environment({ CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD: "4" })).customRolesMassArchiveThreshold, 4);
  assert.equal(loadConfig(environment({ CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD: "0" })).customRolesMassArchiveThreshold, 0);
  assert.equal(loadConfig(environment({ CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD: "-3" })).customRolesMassArchiveThreshold, 0);
  assert.equal(loadConfig(environment({ CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD: "invalid" })).customRolesMassArchiveThreshold, 10);
  assert.equal(loadConfig(environment({ CUSTOM_ROLES_MASS_ARCHIVE_THRESHOLD: "" })).customRolesMassArchiveThreshold, 10);
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


test("loads PostgreSQL settings into the typed database configuration", () => {
  const config = loadConfig(environment());
  assert.equal(config.database.host, "127.0.0.1");
  assert.equal(config.database.port, 5432);
  assert.equal(config.database.poolSize, 5);
  assert.equal(config.database.ssl, false);
  assert.equal(config.database.primaryGuildId, null);
});

test("parses remote PostgreSQL URLs and requires TLS outside loopback", () => {
  const config = loadConfig(environment({
    DATABASE_URL: "postgres://user:pass@db.example.com:6432/lemegeton",
    POSTGRES_POOL_SIZE: "12",
  }));
  assert.equal(config.database.connectionString, "postgresql://user:pass@db.example.com:6432/lemegeton");
  assert.equal(config.database.host, "db.example.com");
  assert.equal(config.database.port, 6432);
  assert.equal(config.database.ssl, true);
  assert.equal(config.database.poolSize, 12);
  assert.throws(
    () => loadConfig(environment({ DATABASE_URL: "postgresql://user:pass@db.example.com/db", POSTGRES_SSL: "false" })),
    /TLS may only be disabled for loopback/,
  );
  assert.throws(
    () => loadConfig(environment({ ENVIRONMENT: "production", POSTGRES_SSL: "false" })),
    /TLS cannot be disabled in production/,
  );
});

test("validates database ports, TLS flags and the optional Steam backfill guild", () => {
  assert.throws(() => loadConfig(environment({ POSTGRES_PORT: "70000" })), /POSTGRES_PORT must be between/);
  assert.throws(() => loadConfig(environment({ POSTGRES_SSL: "sometimes" })), /POSTGRES_SSL must be a boolean/);
  assert.throws(() => loadConfig(environment({ PRIMARY_GUILD_ID: "invalid" })), /GUILD_ID \/ PRIMARY_GUILD_ID/);
  const config = loadConfig(environment({ PRIMARY_GUILD_ID: "987654321098765432" }));
  assert.equal(config.database.primaryGuildId, "987654321098765432");
});


test("loads and validates private S3 settings and loopback dashboard binding", () => {
  const defaults = loadConfig(environment());
  assert.equal(defaults.dashboardBridgeHost, "127.0.0.1");
  assert.equal(defaults.dashboardBridgePort, 8091);
  assert.equal(defaults.s3Region, "us-east-1");
  assert.equal(defaults.s3Bucket, null);
  assert.equal(defaults.s3SignedUrlTtlSeconds, 900);

  const configured = loadConfig(environment({
    DASHBOARD_BRIDGE_HOST: "localhost",
    S3_ENDPOINT_URL: "https://storage.example.test",
    S3_REGION: "auto",
    S3_ACCESS_KEY_ID: "test-access",
    S3_SECRET_ACCESS_KEY: "test-secret",
    S3_BUCKET: "private-archive",
    S3_SIGNED_URL_TTL_SECONDS: "7200",
  }));
  assert.equal(configured.dashboardBridgeHost, "localhost");
  assert.equal(configured.s3EndpointUrl, "https://storage.example.test");
  assert.equal(configured.s3Region, "auto");
  assert.equal(configured.s3AccessKeyId, "test-access");
  assert.equal(configured.s3SecretAccessKey, "test-secret");
  assert.equal(configured.s3Bucket, "private-archive");
  assert.equal(configured.s3SignedUrlTtlSeconds, 3600);

  assert.throws(() => loadConfig(environment({ DASHBOARD_BRIDGE_HOST: "0.0.0.0" })), /loopback/);
  assert.throws(() => loadConfig(environment({ DASHBOARD_BRIDGE_PORT: "70000" })), /DASHBOARD_BRIDGE_PORT/);
  assert.throws(() => loadConfig(environment({ S3_ACCESS_KEY_ID: "test-access" })), /configured together/);
  assert.throws(() => loadConfig(environment({ S3_SIGNED_URL_TTL_SECONDS: "invalid" })), /positive integer/);
});

test("loads operator and Atlas bridge settings into typed configuration", () => {
  const config = loadConfig(environment({
    ADMIN_DISCORD_ID: "123456789012345679",
    DASHBOARD_BRIDGE_SECRET: "a".repeat(40),
    DASHBOARD_BRIDGE_HOST: "127.0.0.2",
    DASHBOARD_BRIDGE_PORT: "8094",
    DASHBOARD_ATLAS_BRIDGE_PORT: "9000",
  }));
  assert.equal(config.adminDiscordId, "123456789012345679");
  assert.equal(config.dashboardBridgeSecret, "a".repeat(40));
  assert.equal(config.dashboardBridgeHost, "127.0.0.2");
  assert.equal(config.dashboardBridgePort, 8094);
  assert.equal(config.dashboardAtlasBridgePort, 9000);
  assert.throws(() => loadConfig(environment({ ADMIN_DISCORD_ID: "bad" })), /ADMIN_DISCORD_ID/);
  assert.equal(loadConfig(environment({ ADMIN_DISCORD_ID: "123456789012345679" })).adminDiscordId, "123456789012345679");
  assert.equal(loadConfig(environment({ BOT_FEEDBACK_CHANNEL_ID: "123456789012345680" })).botFeedbackChannelId, "123456789012345680");
  assert.throws(() => loadConfig(environment({ BOT_FEEDBACK_CHANNEL_ID: "invalid" })), /BOT_FEEDBACK_CHANNEL_ID/);
  assert.deepEqual(loadConfig(environment({ ARCHIVE_GLOBAL_MODERATOR_IDS: "123456789012345681,invalid,123456789012345682,123456789012345681" })).archiveGlobalModeratorIds,
    ["123456789012345681", "123456789012345682"]);
});
