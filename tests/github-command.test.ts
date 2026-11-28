import test from "node:test";
import assert from "node:assert/strict";
import { GitHubCommand } from "../src/standalone/github.js";
import type { BotConfig } from "../helpers/runtime/config.js";

test("registers one /github command with the three tracker actions", () => {
  const command = new GitHubCommand({
    botModeratorGuildId: "123456789012345678",
    adminDiscordId: null,
  } as BotConfig);
  const definition = command.data.toJSON();
  const action = definition.options?.find(option => option.name === "action") as
    | { choices?: Array<{ value: string }> }
    | undefined;

  assert.equal(definition.name, "github");
  assert.deepEqual(action?.choices?.map(choice => choice.value), ["recent", "status", "check"]);
  assert.ok(definition.options?.some(option => option.name === "count"));
});
