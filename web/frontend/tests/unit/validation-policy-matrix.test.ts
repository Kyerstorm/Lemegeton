import { describe, expect, it } from "vitest";
import { dashboardRoutes } from "../../src/Lib/routes";
import { previewCommandAccess } from "../../src/Lib/validation";

const guildId = "123456789012345678";
const roleId = "234567890123456789";
const channelId = "345678901234567890";

describe("guild route builders", () => {
  const routeCases: Array<[string, () => string, string]> = [
    ["overview", () => dashboardRoutes.guildOverview(guildId), "/api/guilds/" + guildId + "/overview"],
    ["settings", () => dashboardRoutes.guildSettings(guildId), "/api/guilds/" + guildId + "/settings"],
    ["archive", () => dashboardRoutes.archiveSettings(guildId), "/api/guilds/" + guildId + "/archive-settings"],
    ["commands", () => dashboardRoutes.guildCommands(guildId), "/api/guilds/" + guildId + "/commands"],
    ["access", () => dashboardRoutes.commandAccess(guildId), "/api/guilds/" + guildId + "/command-access"],
    ["audit", () => dashboardRoutes.guildAudit(guildId), "/api/guilds/" + guildId + "/audit"],
    ["database", () => dashboardRoutes.guildDatabase(guildId), "/api/guilds/" + guildId + "/database"],
    ["atlas", () => dashboardRoutes.guildAtlas(guildId), "/api/guilds/" + guildId + "/atlas"],
    ["sync", () => dashboardRoutes.guildSync(guildId), "/api/guilds/" + guildId + "/sync"],
    ["reset", () => dashboardRoutes.guildReset(guildId), "/api/guilds/" + guildId + "/reset"],
  ];

  it.each(routeCases)("%s stays scoped to its validated guild", (_name, build, expected) => {
    expect(build()).toBe(expected);
  });

  it("encodes command names as a single path segment", () => {
    expect(dashboardRoutes.command(guildId, "archive/export")).toBe(
      "/api/guilds/" + guildId + "/commands/archive%2Fexport",
    );
    expect(dashboardRoutes.commandAccessFor(guildId, "archive/export")).toBe(
      "/api/guilds/" + guildId + "/command-access/archive%2Fexport",
    );
  });

  it("rejects invalid guild IDs for every guild-scoped route", () => {
    const builders = [
      () => dashboardRoutes.guildOverview("../guild"),
      () => dashboardRoutes.guildSettings("../guild"),
      () => dashboardRoutes.archiveSettings("../guild"),
      () => dashboardRoutes.guildCommands("../guild"),
      () => dashboardRoutes.commandAccess("../guild"),
      () => dashboardRoutes.guildAudit("../guild"),
      () => dashboardRoutes.guildDatabase("../guild"),
      () => dashboardRoutes.guildAtlas("../guild"),
      () => dashboardRoutes.guildSync("../guild"),
      () => dashboardRoutes.guildReset("../guild"),
      () => dashboardRoutes.command("../guild", "browse"),
      () => dashboardRoutes.commandAccessFor("../guild", "browse"),
    ];
    for (const build of builders) expect(build).toThrow(TypeError);
  });
});

describe("command access policy combinations", () => {
  const cases = [
    { name: "everyone and all channels allow", role_mode: "everyone", role_ids: [], channel_mode: "all", channel_ids: [], roles: [], channel: channelId, expected: true },
    { name: "included role allows a match", role_mode: "include", role_ids: [roleId], channel_mode: "all", channel_ids: [], roles: [roleId], channel: channelId, expected: true },
    { name: "included role denies a non-match", role_mode: "include", role_ids: [roleId], channel_mode: "all", channel_ids: [], roles: [], channel: channelId, expected: false },
    { name: "excluded role permits a non-match", role_mode: "exclude", role_ids: [roleId], channel_mode: "all", channel_ids: [], roles: [], channel: channelId, expected: true },
    { name: "excluded role denies a match", role_mode: "exclude", role_ids: [roleId], channel_mode: "all", channel_ids: [], roles: [roleId], channel: channelId, expected: false },
    { name: "included channel allows a match", role_mode: "everyone", role_ids: [], channel_mode: "include", channel_ids: [channelId], roles: [], channel: channelId, expected: true },
    { name: "included channel denies a non-match", role_mode: "everyone", role_ids: [], channel_mode: "include", channel_ids: [channelId], roles: [], channel: "456789012345678901", expected: false },
    { name: "excluded channel denies a match", role_mode: "everyone", role_ids: [], channel_mode: "exclude", channel_ids: [channelId], roles: [], channel: channelId, expected: false },
    { name: "excluded channel permits a non-match", role_mode: "everyone", role_ids: [], channel_mode: "exclude", channel_ids: [channelId], roles: [], channel: "456789012345678901", expected: true },
    { name: "empty include list denies access", role_mode: "include", role_ids: [], channel_mode: "all", channel_ids: [], roles: [roleId], channel: channelId, expected: false },
  ] as const;

  it.each(cases)("$name", ({ role_mode, role_ids, channel_mode, channel_ids, roles, channel, expected }) => {
    expect(previewCommandAccess(
      { role_mode, role_ids: [...role_ids], channel_mode, channel_ids: [...channel_ids] },
      [...roles],
      channel,
    )).toBe(expected);
  });
});
