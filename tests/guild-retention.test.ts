import test from "node:test";
import assert from "node:assert/strict";
import {
  canConfigureGuildLeaveAction,
  isGuildLeaveAction,
} from "../helpers/runtime/guild-retention.js";

test("the recorded inviter can configure the guild leave policy without Manage Server", () => {
  assert.equal(
    canConfigureGuildLeaveAction("111111111111111111", "111111111111111111", false),
    true,
  );
});

test("a member with Manage Server can configure the guild leave policy", () => {
  assert.equal(
    canConfigureGuildLeaveAction("111111111111111111", "222222222222222222", true),
    true,
  );
});

test("other members cannot configure the guild leave policy", () => {
  assert.equal(
    canConfigureGuildLeaveAction("111111111111111111", "222222222222222222", false),
    false,
  );
  assert.equal(canConfigureGuildLeaveAction(null, "222222222222222222", false), false);
});

test("only explicit retain and delete choices count as configured policies", () => {
  assert.equal(isGuildLeaveAction("retain"), true);
  assert.equal(isGuildLeaveAction("delete"), true);
  assert.equal(isGuildLeaveAction(null), false);
  assert.equal(isGuildLeaveAction(undefined), false);
  assert.equal(isGuildLeaveAction("unset"), false);
  assert.equal(isGuildLeaveAction("RETAIN"), false);
});

test("Manage Server remains a valid fallback when the bot inviter cannot be resolved", () => {
  assert.equal(
    canConfigureGuildLeaveAction(null, "222222222222222222", true),
    true,
  );
});
