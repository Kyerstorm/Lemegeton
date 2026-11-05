import assert from "node:assert/strict";
import test from "node:test";
import { loadConfig } from "../config.js";

const baseEnvironment: NodeJS.ProcessEnv = {
  DISCORD_TOKEN: "test-token",
  BOT_ID: "123456789012345678",
};

test("loadConfig accepts the existing BOT_ID setting and converts AniList timeout seconds", () => {
  const config = loadConfig({ ...baseEnvironment, ANILIST_API_TIMEOUT: "12" });

  assert.equal(config.applicationId, "123456789012345678");
  assert.equal(config.anilistTimeoutMs, 12_000);
  assert.equal(config.anilistApiUrl, "https://graphql.anilist.co/");
});

test("loadConfig accepts an explicit development guild and client ID", () => {
  const config = loadConfig({
    DISCORD_TOKEN: "test-token",
    DISCORD_CLIENT_ID: "987654321098765432",
    DISCORD_GUILD_ID: "111222333444555666",
  });

  assert.equal(config.applicationId, "987654321098765432");
  assert.equal(config.guildId, "111222333444555666");
});

test("loadConfig rejects missing Discord credentials", () => {
  assert.throws(() => loadConfig({}), /DISCORD_TOKEN/);
  assert.throws(() => loadConfig({ DISCORD_TOKEN: "token" }), /BOT_ID/);
});

test("loadConfig rejects insecure external AniList endpoints", () => {
  assert.throws(
    () => loadConfig({ ...baseEnvironment, ANILIST_API_URL: "http://api.example.com/graphql" }),
    /must use HTTPS/,
  );
});

test("loadConfig rejects invalid AniList timeout values", () => {
  assert.throws(
    () => loadConfig({ ...baseEnvironment, ANILIST_API_TIMEOUT: "0" }),
    /positive integer/,
  );
});

test("loadConfig rejects malformed Discord application and guild IDs", () => {
  assert.throws(() => loadConfig({ ...baseEnvironment, BOT_ID: "not-an-id" }), /valid Discord snowflake/);
  assert.throws(() => loadConfig({ ...baseEnvironment, DISCORD_GUILD_ID: "not-a-guild" }), /valid Discord snowflake/);
});
