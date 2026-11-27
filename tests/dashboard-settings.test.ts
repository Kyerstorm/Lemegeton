import test from "node:test";
import assert from "node:assert/strict";
import type { Guild } from "discord.js";
import {
  DashboardBridgeError,
  guildActorCanManage,
  isDashboardActorId,
  requireGuildManager,
  requireGuildMember,
} from "../helpers/dashboard/permissions.js";

const OWNER = "12345678901234567";
const MANAGER = "22345678901234567";
const MEMBER = "32345678901234567";

function mockGuild(options: {
  ownerId?: string;
  members?: Record<string, { manage?: boolean } | null>;
} = {}): Guild {
  return {
    ownerId: options.ownerId ?? OWNER,
    members: {
      fetch: async (id: string) => {
        const member = options.members?.[id];
        if (!member) throw new Error("Unknown member");
        return {
          permissions: {
            has: () => Boolean(member.manage),
          },
        };
      },
    },
  } as unknown as Guild;
}

test("dashboard actor IDs accept only Discord snowflakes", () => {
  assert.equal(isDashboardActorId(OWNER), true);
  assert.equal(isDashboardActorId("12345678901234567890"), true);
  assert.equal(isDashboardActorId("1234567890123456"), false);
  assert.equal(isDashboardActorId("12345678901234567x"), false);
  assert.equal(isDashboardActorId(12345678901234567), false);
});

test("guild owner and current managers can manage dashboard settings", async () => {
  const guild = mockGuild({ members: { [MANAGER]: { manage: true } } });
  assert.equal(await guildActorCanManage(guild, OWNER), true);
  assert.equal(await guildActorCanManage(guild, MANAGER), true);
  await requireGuildManager(guild, OWNER);
  await requireGuildManager(guild, MANAGER);
});

test("ordinary members cannot change dashboard settings and departed members lose access", async () => {
  const guild = mockGuild({ members: { [MEMBER]: { manage: false } } });
  assert.equal(await guildActorCanManage(guild, MEMBER), false);
  await assert.rejects(requireGuildManager(guild, MEMBER), (error: unknown) => (
    error instanceof DashboardBridgeError && error.status === 403
  ));
  await assert.rejects(requireGuildMember(guild, "42345678901234567"), (error: unknown) => (
    error instanceof DashboardBridgeError && error.status === 403
  ));
});
