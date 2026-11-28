import { describe, expect, it } from "vitest";
import { dashboardRoutes } from "../../src/Lib/routes";
import {
  isDiscordSnowflake,
  previewCommandAccess,
  validateArchiveSettings,
  validateServerSettingsUpdate,
} from "../../src/Lib/validation";
import type { ArchiveSettings, CommandAccessPolicy } from "../../src/Types/dashboard";

const guildId = "123456789012345678";
const roleId = "234567890123456789";
const channelId = "345678901234567890";

describe("dashboard routes", () => {
  it("builds guild-scoped endpoints from validated snowflakes", () => {
    expect(dashboardRoutes.guildSettings(guildId)).toBe("/api/guilds/123456789012345678/settings");
    expect(dashboardRoutes.command(guildId, "media search")).toBe(
      "/api/guilds/123456789012345678/commands/media%20search",
    );
    expect(dashboardRoutes.commandAccessFor(guildId, "browse")).toBe(
      "/api/guilds/123456789012345678/command-access/browse",
    );
  });

  it("rejects invalid guild identifiers and command names", () => {
    expect(() => dashboardRoutes.guildOverview("../other-guild")).toThrow(TypeError);
    expect(() => dashboardRoutes.command(guildId, "  ")).toThrow(TypeError);
    expect(() => dashboardRoutes.command(guildId, "x".repeat(101))).toThrow(TypeError);
  });
});

describe("Discord snowflakes", () => {
  it("accepts only 17–20 digit strings", () => {
    expect(isDiscordSnowflake(guildId)).toBe(true);
    expect(isDiscordSnowflake("12345678901234567")).toBe(true);
    expect(isDiscordSnowflake("123456789012345678901")).toBe(false);
    expect(isDiscordSnowflake(123456789012345678)).toBe(false);
    expect(isDiscordSnowflake("12345678901234567x")).toBe(false);
  });
});

describe("archive settings validation", () => {
  const settings: ArchiveSettings = {
    enabledCategories: ["quotes", "soundtracks"],
    uploadTypes: ["image", "video"],
    uploadChannelId: channelId,
    legacyStorageChannelId: null,
    moderationChannelId: null,
    moderatorRoleId: roleId,
  };

  it("accepts supported categories, upload types and server-owned IDs", () => {
    expect(validateArchiveSettings(settings, guildId)).toBeNull();
  });

  it("requires at least one known category", () => {
    expect(validateArchiveSettings({ ...settings, enabledCategories: [] }, guildId)).toBe(
      "Keep at least one valid Archive category enabled.",
    );
    expect(validateArchiveSettings({ ...settings, enabledCategories: ["unknown"] }, guildId)).not.toBeNull();
  });

  it("rejects unsupported upload types and malformed channel IDs", () => {
    expect(validateArchiveSettings({ ...settings, uploadTypes: ["executable"] }, guildId)).toBe(
      "Choose only supported Archive upload types.",
    );
    expect(validateArchiveSettings({ ...settings, uploadChannelId: "not-a-channel" }, guildId)).toBe(
      "Choose valid channels from this server.",
    );
  });

  it("does not accept the guild ID as a moderator role", () => {
    expect(validateArchiveSettings({ ...settings, moderatorRoleId: guildId }, guildId)).toBe(
      "Choose a valid Archive moderator role.",
    );
  });
});

describe("server settings validation", () => {
  it("requires an explicit supported setting", () => {
    expect(validateServerSettingsUpdate({})).toBe("Choose a server setting to update.");
    expect(validateServerSettingsUpdate({ leave_action: "archive" })).toBe(
      "Choose whether to delete or retain this server's data.",
    );
    expect(validateServerSettingsUpdate({ language_code: "EN" })).toBe(
      "Choose a supported server language.",
    );
  });

  it("accepts valid retention and language updates", () => {
    expect(validateServerSettingsUpdate({ leave_action: "retain" })).toBeNull();
    expect(validateServerSettingsUpdate({ leave_action: "delete", language_code: "en" })).toBeNull();
    expect(validateServerSettingsUpdate({ language_code: "jpn" })).toBeNull();
  });
});

describe("command access preview policy", () => {
  const policy: CommandAccessPolicy = {
    role_mode: "include",
    role_ids: [roleId],
    channel_mode: "include",
    channel_ids: [channelId],
    revision: 4,
  };

  it("requires both the role and channel rules to allow access", () => {
    expect(previewCommandAccess(policy, [roleId], channelId)).toBe(true);
    expect(previewCommandAccess(policy, [], channelId)).toBe(false);
    expect(previewCommandAccess(policy, [roleId], "456789012345678901")).toBe(false);
  });

  it("supports everyone and exclusion modes", () => {
    expect(previewCommandAccess({
      ...policy, role_mode: "everyone", channel_mode: "all",
    }, [], "456789012345678901")).toBe(true);
    expect(previewCommandAccess({
      ...policy, role_mode: "exclude", channel_mode: "exclude",
    }, [], "456789012345678901")).toBe(true);
    expect(previewCommandAccess({
      ...policy, role_mode: "exclude",
    }, [roleId], channelId)).toBe(false);
    expect(previewCommandAccess({
      ...policy, channel_mode: "exclude",
    }, [roleId], channelId)).toBe(false);
  });

  it("treats empty include lists as deny-all", () => {
    expect(previewCommandAccess({
      ...policy, role_ids: [],
    }, [roleId], channelId)).toBe(false);
    expect(previewCommandAccess({
      ...policy, channel_ids: [],
    }, [roleId], channelId)).toBe(false);
  });
});
