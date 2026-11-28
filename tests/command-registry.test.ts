import test from "node:test";
import assert from "node:assert/strict";
import { createCommandRegistry } from "../src/registry.js";
import { loadConfig } from "../helpers/runtime/config.js";
import { isFeatureName } from "../helpers/runtime/settings.js";

test("registers the expanded community command entry points", () => {
  const config = loadConfig({
    ...process.env,
    DISCORD_TOKEN: "test-discord-token",
    BOT_ID: "123456789012345678",
    EXPEDITION_ANSWER_SECRET: "e".repeat(32),
    CASEBOOK_SOLUTION_SECRET: "c".repeat(32),
  });
  const commands = createCommandRegistry(config);
  const names = commands.map(command => command.data.name);

  assert.ok(names.includes("expedition"));
  assert.ok(names.includes("casebook"));
  assert.equal(new Set(names).size, names.length);
  assert.equal(isFeatureName("expedition"), true);
  assert.equal(isFeatureName("casebook"), true);
});
