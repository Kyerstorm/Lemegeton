import test from "node:test";
import assert from "node:assert/strict";
import type { Guild, GuildMember, Role } from "discord.js";
import type { CustomRoleRecord, CustomRoleSettings } from "../helpers/custom-roles/custom-roles.js";
import { legacyRoleTakeoverProblem } from "../helpers/custom-roles/custom-roles.js";
import {
  customRoleChannelAllowed,
  customRoleCooldownMessage,
  customRoleEligibility,
  parseCustomRoleColor,
  parseCustomRoleWordList,
  validateCustomRoleAnchor,
  validateCustomRoleEmoji,
  validateCustomRoleName,
} from "../helpers/custom-roles/custom-role-validation.js";

const nameSettings: Pick<CustomRoleSettings, "blocked_words" | "removed_default_words"> = {
  blocked_words: [],
  removed_default_words: [],
};

test("role emoji accepts Unicode emoji and rejects empty or custom markup", () => {
  assert.equal(validateCustomRoleEmoji(" 🎮 "), "🎮");
  assert.equal(validateCustomRoleEmoji("👩🏽‍💻"), "👩🏽‍💻");
  assert.equal(validateCustomRoleEmoji(""), null);
  assert.equal(validateCustomRoleEmoji("<:custom:123456789012345678>"), null);
  assert.equal(validateCustomRoleEmoji("not an emoji"), null);
});

test("role colors normalize short and long hex values without permitting black", () => {
  assert.equal(parseCustomRoleColor("#abc"), 0xaabbcc);
  assert.equal(parseCustomRoleColor("12aBcD"), 0x12abcd);
  assert.equal(parseCustomRoleColor("#000000"), 0x010101);
  assert.equal(parseCustomRoleColor("purple"), null);
  assert.equal(parseCustomRoleColor("#12"), null);
});

test("role names reject empty, invisible, mass-mention and overlong values", () => {
  for (const raw of ["", " \u200b\u200d ", "@everyone", "Team @here", "x".repeat(101)]) {
    assert.equal(validateCustomRoleName(raw, nameSettings).name, null, raw);
  }
  assert.equal(validateCustomRoleName("  Silver   Comet  ", nameSettings).name, "Silver Comet");
});

test("role names reject protected words including common leetspeak and spaced evasions", () => {
  assert.match(validateCustomRoleName("M0d Squad", nameSettings).error ?? "", /moderator|mod/i);
  assert.match(validateCustomRoleName("s t a f f team", nameSettings).error ?? "", /staff/i);
  assert.match(validateCustomRoleName("b0t crew", nameSettings).error ?? "", /bot/i);
});

test("server roles and duplicate role names are reserved", () => {
  assert.match(validateCustomRoleName("Community Manager", nameSettings, [], ["Community Manager"]).error ?? "", /staff role/i);
  assert.match(validateCustomRoleName("existing-role", nameSettings, ["Existing Role"]).error ?? "", /already a server role/i);
});

test("blocked words are normalized and removed defaults are respected", () => {
  const blocked = { ...nameSettings, blocked_words: ["badword"] };
  assert.match(validateCustomRoleName("A BAD-WORD name", blocked).error ?? "", /blocked word/i);

  const allowAdmin = { ...nameSettings, removed_default_words: ["admin"] };
  assert.equal(validateCustomRoleName("Admin Central", allowAdmin).error, null);
});

test("word lists accept comma/newline input, normalize, and deduplicate", () => {
  assert.deepEqual(
    parseCustomRoleWordList("  rude, RUDE\nspoiler\n\nway-too-long-" + "x".repeat(45) + "\nvalid_2"),
    ["rude", "spoiler", "valid_2"],
  );
});

test("eligibility accepts boosters and configured allowed roles only", () => {
  const settings = { allowed_role_ids: ["role-allowed"] } as CustomRoleSettings;
  const booster = { premiumSince: new Date(), roles: { cache: [] } } as unknown as GuildMember;
  const allowed = { premiumSince: null, roles: { cache: [{ id: "role-allowed" }] } } as unknown as GuildMember;
  const denied = { premiumSince: null, roles: { cache: [{ id: "role-other" }] } } as unknown as GuildMember;

  assert.equal(customRoleEligibility(booster, settings), true);
  assert.equal(customRoleEligibility(allowed, settings), true);
  assert.equal(customRoleEligibility(denied, settings), false);
});

test("custom-role command channel allows its configured channel and category parent", () => {
  const settings = { command_channel_id: "channel-1" } as CustomRoleSettings;
  assert.equal(customRoleChannelAllowed("channel-1", "category-1", settings), true);
  assert.equal(customRoleChannelAllowed("thread-1", "channel-1", settings), true);
  assert.equal(customRoleChannelAllowed("other", "category-1", settings), false);
  assert.equal(customRoleChannelAllowed("any", null, { ...settings, command_channel_id: null }), true);
});

test("anchor validation rejects everyone and roles at or above the bot role", () => {
  const guildId = "guild-1";
  const guild = {
    id: guildId,
    members: { me: { roles: { highest: { position: 5 } } } },
  } as unknown as Guild;
  const everyone = { id: guildId, position: 0 } as Role;
  const tooHigh = { id: "role-high", position: 5 } as Role;
  const safe = { id: "role-safe", position: 4 } as Role;

  assert.match(validateCustomRoleAnchor(guild, everyone) ?? "", /@everyone/);
  assert.match(validateCustomRoleAnchor(guild, tooHigh) ?? "", /above the anchor role/i);
  assert.equal(validateCustomRoleAnchor(guild, safe), null);
  assert.match(validateCustomRoleAnchor({ id: guildId, members: { me: null } } as unknown as Guild, safe) ?? "", /resolve my server role/i);
});

test("role cooldown reports only positive remaining time", () => {
  const now = Date.parse("2026-11-09T12:00:00.000Z");
  const record = {
    last_changed_at: new Date(now - 61_000).toISOString(),
  } as CustomRoleRecord;
  assert.equal(customRoleCooldownMessage(record, 300, now), "You can change your role again in about 4 minutes.");
  assert.equal(customRoleCooldownMessage(record, 60, now), null);
  assert.equal(customRoleCooldownMessage({ last_changed_at: null } as CustomRoleRecord, 300, now), null);
  assert.equal(customRoleCooldownMessage(record, 0, now), null);
});

test("legacy booster-role takeover rejects unsafe or privileged roles", () => {
  const settings = {
    anchor_role_id: "anchor-role",
    allowed_role_ids: ["allowed-role"],
  } as CustomRoleSettings;
  const role = (id: string, overrides: Record<string, unknown> = {}) => ({
    id,
    managed: false,
    position: 3,
    permissions: { has: () => false },
    ...overrides,
  }) as unknown as Role;

  assert.equal(legacyRoleTakeoverProblem("guild-1", role("safe-role"), settings, 5), null);
  assert.match(legacyRoleTakeoverProblem("guild-1", role("guild-1"), settings, 5) ?? "", /@everyone/);
  assert.match(legacyRoleTakeoverProblem("guild-1", role("managed-role", { managed: true }), settings, 5) ?? "", /managed/);
  assert.match(legacyRoleTakeoverProblem("guild-1", role("high-role", { position: 5 }), settings, 5) ?? "", /highest role/);
  assert.match(legacyRoleTakeoverProblem("guild-1", role("moderator-role", { permissions: { has: () => true } }), settings, 5) ?? "", /moderation or administration/);
  assert.match(legacyRoleTakeoverProblem("guild-1", role("anchor-role"), settings, 5) ?? "", /anchor/);
  assert.match(legacyRoleTakeoverProblem("guild-1", role("allowed-role"), settings, 5) ?? "", /eligibility role/);
  assert.match(legacyRoleTakeoverProblem("guild-1", role("role"), settings, null) ?? "", /highest role/);
});
