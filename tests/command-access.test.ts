import test from "node:test";
import assert from "node:assert/strict";
import { commandAccessMatches, type CommandAccessPolicy } from "../helpers/runtime/command-access.js";

const policy = (overrides: Partial<Omit<CommandAccessPolicy, "revision">> = {}) => ({
  role_mode: "everyone" as const,
  role_ids: [] as string[],
  channel_mode: "all" as const,
  channel_ids: [] as string[],
  ...overrides,
});

test("default command policy allows every member in every channel", () => {
  assert.equal(commandAccessMatches(policy(), "channel-a", ["role-a"]), true);
  assert.equal(commandAccessMatches(policy(), null, []), true);
});

test("role include rules require at least one selected role", () => {
  assert.equal(commandAccessMatches(policy({ role_mode: "include", role_ids: ["role-a"] }), "channel-a", ["role-a"]), true);
  assert.equal(commandAccessMatches(policy({ role_mode: "include", role_ids: ["role-a"] }), "channel-a", ["role-b"]), false);
  assert.equal(commandAccessMatches(policy({ role_mode: "include" }), "channel-a", ["role-a"]), false);
});

test("role exclude rules deny matching roles and allow everyone else", () => {
  const rules = policy({ role_mode: "exclude", role_ids: ["role-blocked"] });
  assert.equal(commandAccessMatches(rules, "channel-a", ["role-blocked", "role-other"]), false);
  assert.equal(commandAccessMatches(rules, "channel-a", ["role-other"]), true);
  assert.equal(commandAccessMatches(policy({ role_mode: "exclude" }), "channel-a", []), true);
});

test("channel include and exclude rules handle missing channels safely", () => {
  const include = policy({ channel_mode: "include", channel_ids: ["channel-a"] });
  assert.equal(commandAccessMatches(include, "channel-a", []), true);
  assert.equal(commandAccessMatches(include, "channel-b", []), false);
  assert.equal(commandAccessMatches(include, null, []), false);
  assert.equal(commandAccessMatches(policy({ channel_mode: "include" }), "channel-a", []), false);

  const exclude = policy({ channel_mode: "exclude", channel_ids: ["channel-a"] });
  assert.equal(commandAccessMatches(exclude, "channel-a", []), false);
  assert.equal(commandAccessMatches(exclude, "channel-b", []), true);
  assert.equal(commandAccessMatches(policy({ channel_mode: "exclude" }), null, []), true);
});

test("role and channel rules must both pass", () => {
  const rules = policy({
    role_mode: "include",
    role_ids: ["trusted"],
    channel_mode: "include",
    channel_ids: ["staff-chat"],
  });
  assert.equal(commandAccessMatches(rules, "staff-chat", ["trusted"]), true);
  assert.equal(commandAccessMatches(rules, "staff-chat", ["member"]), false);
  assert.equal(commandAccessMatches(rules, "general", ["trusted"]), false);
});
