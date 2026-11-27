import test from "node:test";
import assert from "node:assert/strict";
import type { BotConfig } from "../helpers/runtime/config.js";
import {
  allowPickerCall,
  clearPickerLinksForTests,
  createPickerLink,
  lookupPickerLink,
  pickerLinkExpiry,
  pickerTokenCountForTests,
  revokePickerLink,
} from "../helpers/custom-roles/custom-role-picker-tokens.js";

const config = {
  customRolePickerIdleTtl: 600,
  customRolePickerMaxTtl: 3_600,
} as BotConfig;

test.afterEach(() => clearPickerLinksForTests());

test("picker links use unique opaque tokens and are scoped to a guild member", () => {
  const first = createPickerLink("guild-a", "member-1", config);
  const second = createPickerLink("guild-b", "member-1", config);
  assert.equal(first.token.length, 43);
  assert.match(first.token, /^[A-Za-z0-9_-]+$/);
  assert.notEqual(first.token, second.token);
  assert.deepEqual(
    [lookupPickerLink(first.token)?.guildId, lookupPickerLink(first.token)?.userId],
    ["guild-a", "member-1"],
  );
  assert.deepEqual(
    [lookupPickerLink(second.token)?.guildId, lookupPickerLink(second.token)?.userId],
    ["guild-b", "member-1"],
  );
});

test("creating a new link revokes only that member's previous link", () => {
  const oldLink = createPickerLink("guild-a", "member-1", config);
  const otherMember = createPickerLink("guild-a", "member-2", config);
  const replacement = createPickerLink("guild-a", "member-1", config);

  assert.equal(lookupPickerLink(oldLink.token), null);
  assert.equal(lookupPickerLink(replacement.token)?.userId, "member-1");
  assert.equal(lookupPickerLink(otherMember.token)?.userId, "member-2");
  assert.equal(pickerTokenCountForTests(), 2);
});

test("idle and absolute expiry are both enforced", () => {
  const idle = createPickerLink("guild-a", "member-1", config);
  const idleRecord = lookupPickerLink(idle.token);
  assert.ok(idleRecord);
  idleRecord.lastUsed = Date.now() - idleRecord.idleTtlMs;
  assert.equal(lookupPickerLink(idle.token), null);

  const absolute = createPickerLink("guild-a", "member-2", {
    ...config,
    customRolePickerIdleTtl: 3_600,
    customRolePickerMaxTtl: 60,
  } as BotConfig);
  const absoluteRecord = lookupPickerLink(absolute.token);
  assert.ok(absoluteRecord);
  const expiry = pickerLinkExpiry(absoluteRecord);
  assert.equal(expiry.max_expires_at, Math.floor(absolute.maxExpiresAt / 1000));
  assert.equal(expiry.expires_at, expiry.max_expires_at);
});

test("picker read and write limits use separate rolling windows", () => {
  const created = createPickerLink("guild-a", "member-1", config);
  const link = lookupPickerLink(created.token);
  assert.ok(link);
  const now = Date.now();

  for (let index = 0; index < 60; index += 1) {
    assert.equal(allowPickerCall(link, false, now + index), true);
  }
  assert.equal(allowPickerCall(link, false, now + 60), false);
  assert.equal(allowPickerCall(link, false, now + 60_001), true);

  for (let index = 0; index < 20; index += 1) {
    assert.equal(allowPickerCall(link, true, now + index), true);
  }
  assert.equal(allowPickerCall(link, true, now + 20), false);
  assert.equal(allowPickerCall(link, true, now + 60_001), true);
});

test("revocation is isolated to the exact guild and member", () => {
  const first = createPickerLink("guild-a", "member-1", config);
  const second = createPickerLink("guild-a", "member-2", config);
  const third = createPickerLink("guild-b", "member-1", config);

  assert.equal(revokePickerLink("guild-a", "member-1"), true);
  assert.equal(lookupPickerLink(first.token), null);
  assert.ok(lookupPickerLink(second.token));
  assert.ok(lookupPickerLink(third.token));
  assert.equal(revokePickerLink("guild-a", "member-1"), false);
});
