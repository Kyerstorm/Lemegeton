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

test("accepts the legacy CLIENT_ID application setting and prefers DISCORD_CLIENT_ID", () => {
  assert.equal(loadConfig(environment({ CLIENT_ID: "123456789012345679" })).applicationId, "123456789012345679");
  assert.equal(
    loadConfig(environment({ CLIENT_ID: "123456789012345679", DISCORD_CLIENT_ID: "123456789012345680" })).applicationId,
    "123456789012345680",
  );
});

test("loads independent community feature secrets and validates minimum key length", () => {
  const defaults = loadConfig(environment());
  assert.equal(defaults.expeditionAnswerSecret, null);
  assert.equal(defaults.casebookSolutionSecret, null);

  const configured = loadConfig(environment({
    EXPEDITION_ANSWER_SECRET: "e".repeat(32),
    CASEBOOK_SOLUTION_SECRET: "c".repeat(32),
  }));
  assert.equal(configured.expeditionAnswerSecret, "e".repeat(32));
  assert.equal(configured.casebookSolutionSecret, "c".repeat(32));

  assert.throws(
    () => loadConfig(environment({ EXPEDITION_ANSWER_SECRET: "too-short" })),
    /EXPEDITION_ANSWER_SECRET must contain at least 32 UTF-8 bytes/,
  );
  assert.throws(
    () => loadConfig(environment({ CASEBOOK_SOLUTION_SECRET: "too-short" })),
    /CASEBOOK_SOLUTION_SECRET must contain at least 32 UTF-8 bytes/,
  );
});

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
  const soundcloud = loadConfig(environment({ SOUNDCLOUD_CLIENT_ID: "client-id", SOUNDCLOUD_CLIENT_SECRET: "client-secret" }));
  assert.equal(soundcloud.soundcloudClientId, "client-id");
  assert.equal(soundcloud.soundcloudClientSecret, "client-secret");
  assert.throws(() => loadConfig(environment({ DASHBOARD_PICKER_HOST: "0.0.0.0" })), /loopback/);
});



test("loads the unified libSQL, RocksDB and local backup paths", () => {
  const defaults = loadConfig(environment());
  assert.equal(defaults.database.path, "./data/bot/lemegeton.db");
  assert.equal(defaults.database.primaryGuildId, null);
  assert.equal(defaults.rocksDbPath, "./data/objects");
  assert.equal(defaults.backupDirectory, "./data/backups");

  const configured = loadConfig(environment({
    LIBSQL_PATH: "./data/test.db",
    ROCKSDB_PATH: "./data/test-objects",
    BACKUP_DIRECTORY: "./data/snapshots",
    PRIMARY_GUILD_ID: "987654321098765432",
  }));
  assert.equal(configured.database.path, "./data/test.db");
  assert.equal(configured.database.primaryGuildId, "987654321098765432");
  assert.equal(configured.rocksDbPath, "./data/test-objects");
  assert.equal(configured.backupDirectory, "./data/snapshots");

  assert.throws(() => loadConfig(environment({ LIBSQL_PATH: "libsql://remote.example" })), /local file path/);
  assert.throws(() => loadConfig(environment({ PRIMARY_GUILD_ID: "invalid" })), /GUILD_ID \/ PRIMARY_GUILD_ID/);
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
});

test("loads configured translation providers and keys", () => {
  const config = loadConfig(environment({
    NLLB_TRANSLATION_URL: "https://nllb.example.test/translate",
    NLLB_NONCOMMERCIAL_USE_CONFIRMED: "true",
    LIBRETRANSLATE_URL: "https://translate.example.test/translate",
    LIBRETRANSLATE_API_KEY: "libre-key",
    GOOGLE_TRANSLATE_API_KEY: "google-key",
    TRANSLATION_TIMEOUT_MS: "9000",
  }));
  assert.equal(config.translation.nllbUrl, "https://nllb.example.test/translate");
  assert.equal(config.translation.nllbNonCommercialUseConfirmed, true);
  assert.equal(config.translation.libreTranslateUrl, "https://translate.example.test/translate");
  assert.equal(config.translation.libreTranslateApiKey, "libre-key");
  assert.equal(config.translation.googleTranslateApiKey, "google-key");
  assert.equal(config.translation.timeoutMs, 9000);
});

test("keeps the dashboard bridge on loopback with RocksDB storage paths", () => {
  const defaults = loadConfig(environment());
  assert.equal(defaults.dashboardBridgeHost, "127.0.0.1");
  assert.equal(defaults.dashboardBridgePort, 8091);
  assert.equal(defaults.rocksDbPath, "./data/objects");

  const configured = loadConfig(environment({
    DASHBOARD_BRIDGE_HOST: "localhost",
    ROCKSDB_PATH: "./data/private-objects",
  }));
  assert.equal(configured.dashboardBridgeHost, "localhost");
  assert.equal(configured.rocksDbPath, "./data/private-objects");

  assert.throws(() => loadConfig(environment({ DASHBOARD_BRIDGE_HOST: "0.0.0.0" })), /loopback/);
  assert.throws(() => loadConfig(environment({ DASHBOARD_BRIDGE_PORT: "70000" })), /DASHBOARD_BRIDGE_PORT/);
});


test("keeps NLLB disabled unless non-commercial use is explicitly confirmed", () => {
  assert.equal(loadConfig(environment({ NLLB_TRANSLATION_URL: "https://nllb.example.test/translate" })).translation.nllbNonCommercialUseConfirmed, false);
  assert.throws(
    () => loadConfig(environment({ NLLB_NONCOMMERCIAL_USE_CONFIRMED: "maybe" })),
    /NLLB_NONCOMMERCIAL_USE_CONFIRMED must be a boolean/,
  );
});

test("rejects insecure remote translation endpoints and malformed URLs", () => {
  assert.throws(
    () => loadConfig(environment({ MADLAD_TRANSLATION_URL: "http://madlad.example.test/translate" })),
    /MADLAD_TRANSLATION_URL must use HTTPS/,
  );
  assert.throws(
    () => loadConfig(environment({ LIBRETRANSLATE_URL: "not-a-url" })),
    /LIBRETRANSLATE_URL must be a valid URL/,
  );
  assert.throws(
    () => loadConfig(environment({ NLLB_TRANSLATION_URL: "https://user:pass@nllb.example.test/translate" })),
    /NLLB_TRANSLATION_URL must not contain credentials/,
  );
  assert.throws(
    () => loadConfig(environment({ DEEPL_TRANSLATION_URL: "http://api-free.deepl.com/v2/translate" })),
    /DEEPL_TRANSLATION_URL must use HTTPS/,
  );
});

test("allows loopback translation endpoints for local development", () => {
  const config = loadConfig(environment({
    MADLAD_TRANSLATION_URL: "http://127.0.0.1:8001/translate",
    LIBRETRANSLATE_URL: "http://localhost:5000/translate",
  }));
  assert.equal(config.translation.madladUrl, "http://127.0.0.1:8001/translate");
  assert.equal(config.translation.libreTranslateUrl, "http://localhost:5000/translate");
});


test("keeps NLLB disabled in production even when non-commercial use is confirmed", () => {
  const config = loadConfig(environment({
    ENVIRONMENT: "production",
    CUSTOM_ROLES_PUBLIC_URL: "https://roles.example.test",
    NLLB_TRANSLATION_URL: "https://nllb.example.test/translate",
    NLLB_NONCOMMERCIAL_USE_CONFIRMED: "true",
  }));
  assert.equal(config.translation.nllbNonCommercialUseConfirmed, false);

  const nodeProduction = loadConfig(environment({
    NODE_ENV: "production",
    CUSTOM_ROLES_PUBLIC_URL: "https://roles.example.test",
    NLLB_TRANSLATION_URL: "https://nllb.example.test/translate",
    NLLB_NONCOMMERCIAL_USE_CONFIRMED: "true",
  }));
  assert.equal(nodeProduction.translation.nllbNonCommercialUseConfirmed, false);
});


test("loads and validates GitHub tracker configuration", () => {
  const configured = loadConfig(environment({
    GITHUB_REPO: "example/project",
    GITHUB_BRANCH: "release/v3",
    GITHUB_TOKEN: "github-token",
    GITHUB_POLL_MINUTES: "5",
    GITHUB_UPDATE_CHANNEL_ID: "123456789012345678",
  }));
  assert.equal(configured.githubRepository, "example/project");
  assert.equal(configured.githubBranch, "release/v3");
  assert.equal(configured.githubToken, "github-token");
  assert.equal(configured.githubPollIntervalMinutes, 5);
  assert.equal(configured.githubUpdateChannelId, "123456789012345678");

  assert.throws(() => loadConfig(environment({ GITHUB_REPO: "../project" })), /GITHUB_REPO/);
  assert.throws(() => loadConfig(environment({ GITHUB_BRANCH: "bad branch" })), /GITHUB_BRANCH/);
  assert.throws(() => loadConfig(environment({ GITHUB_POLL_MINUTES: "0" })), /GITHUB_POLL_MINUTES/);
  assert.throws(() => loadConfig(environment({ GITHUB_UPDATE_CHANNEL_ID: "not-a-channel" })), /GITHUB_UPDATE_CHANNEL_ID/);
});

test("defaults media source access to explicit opt-in and validates source IDs", () => {
  const defaults = loadConfig(environment());
  assert.deepEqual(defaults.mediaWikiEnabledSources, []);
  assert.deepEqual(defaults.mediaSourceScrapeAllowlist, []);
  assert.equal(defaults.tvdbAccessEnabled, false);
  assert.equal(defaults.tvMazeAttributionConfirmed, false);
  assert.equal(defaults.comicVineNonCommercialConfirmed, false);
  assert.equal(defaults.redditApiAccessConfirmed, false);
  assert.equal(defaults.setlistFmNonCommercialConfirmed, false);
  assert.equal(defaults.comicBookHeraldRssNonCommercialConfirmed, false);

  const configured = loadConfig(environment({
    MEDIAWIKI_ENABLED_SOURCES: "wookieepedia,tolkien-gateway",
    MEDIA_SOURCE_SCRAPE_ALLOWLIST: "comic-book-herald",
    COMIC_BOOK_HERALD_RSS_NONCOMMERCIAL_CONFIRMED: "true",
    TVMAZE_SHAREALIKE_CONFIRMED: "true",
    SETLISTFM_NONCOMMERCIAL_CONFIRMED: "true",
  }));
  assert.deepEqual(configured.mediaWikiEnabledSources, ["wookieepedia", "tolkien-gateway"]);
  assert.deepEqual(configured.mediaSourceScrapeAllowlist, ["comic-book-herald"]);
  assert.equal(configured.comicBookHeraldRssNonCommercialConfirmed, true);
  assert.equal(configured.tvMazeAttributionConfirmed, true);
  assert.equal(configured.setlistFmNonCommercialConfirmed, true);

  assert.throws(() => loadConfig(environment({ MEDIAWIKI_ENABLED_SOURCES: "unknown-wiki" })), /unsupported source ID/);
  assert.throws(() => loadConfig(environment({ MEDIA_SOURCE_SCRAPE_ALLOWLIST: "unknown-source" })), /unsupported source ID/);
  assert.throws(() => loadConfig(environment({ MEDIA_SOURCE_SCRAPE_ALLOWLIST: "the-canonicle" })), /unsupported source ID/);
});

test("requires explicit access prerequisites for restricted media providers", () => {
  assert.throws(
    () => loadConfig(environment({ TVDB_ACCESS_ENABLED: "true" })),
    /TVDB_ACCESS_ENABLED requires TVDB_API_KEY/,
  );
  assert.throws(
    () => loadConfig(environment({ COMIC_VINE_NONCOMMERCIAL_CONFIRMED: "true" })),
    /COMIC_VINE_NONCOMMERCIAL_CONFIRMED requires COMIC_VINE_API_KEY/,
  );
  assert.throws(
    () => loadConfig(environment({ REDDIT_API_ACCESS_CONFIRMED: "true" })),
    /REDDIT_API_ACCESS_CONFIRMED requires Reddit app credentials/,
  );
  assert.throws(
    () => loadConfig(environment({ REDDIT_CLIENT_ID: "one-sided" })),
    /REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be configured together/,
  );
});

