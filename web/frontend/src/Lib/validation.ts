import type { ArchiveSettings } from "../Types/dashboard";

const DISCORD_SNOWFLAKE = /^\d{17,20}$/;
const ARCHIVE_CATEGORIES = new Set([
  "panels",
  "quotes",
  "fanworks",
  "moodboards",
  "soundtracks",
  "scenes",
  "recommendation-board",
  "theories",
]);
const ARCHIVE_UPLOAD_TYPES = new Set(["image", "audio", "video"]);

export function isDiscordSnowflake(value: unknown): value is string {
  return typeof value === "string" && DISCORD_SNOWFLAKE.test(value);
}

export function validateArchiveSettings(settings: ArchiveSettings, guildId: string): string | null {
  if (!Array.isArray(settings.enabledCategories)
    || settings.enabledCategories.length === 0
    || !settings.enabledCategories.every(value => ARCHIVE_CATEGORIES.has(value))) {
    return "Keep at least one valid Archive category enabled.";
  }
  if (!Array.isArray(settings.uploadTypes)
    || !settings.uploadTypes.every(value => ARCHIVE_UPLOAD_TYPES.has(value))) {
    return "Choose only supported Archive upload types.";
  }
  for (const id of [settings.uploadChannelId, settings.legacyStorageChannelId, settings.moderationChannelId]) {
    if (id !== null && !isDiscordSnowflake(id)) return "Choose valid channels from this server.";
  }
  if (settings.moderatorRoleId !== null
    && (!isDiscordSnowflake(settings.moderatorRoleId) || settings.moderatorRoleId === guildId)) {
    return "Choose a valid Archive moderator role.";
  }
  return null;
}

export function validateServerSettingsUpdate(update: {
  leave_action?: unknown;
  language_code?: unknown;
}): string | null {
  const hasRetention = Object.prototype.hasOwnProperty.call(update, "leave_action");
  const hasLanguage = Object.prototype.hasOwnProperty.call(update, "language_code");
  if (!hasRetention && !hasLanguage) return "Choose a server setting to update.";
  if (hasRetention && update.leave_action !== "delete" && update.leave_action !== "retain") {
    return "Choose whether to delete or retain this server's data.";
  }
  if (hasLanguage && (typeof update.language_code !== "string" || !/^[a-z]{2,3}$/.test(update.language_code))) {
    return "Choose a supported server language.";
  }
  return null;
}

export function previewCommandAccess(policy: {
  role_mode: "everyone" | "include" | "exclude";
  role_ids: string[];
  channel_mode: "all" | "include" | "exclude";
  channel_ids: string[];
}, memberRoleIds: string[], channelId: string): boolean {
  const hasRole = policy.role_ids.some(id => memberRoleIds.includes(id));
  const roleAllowed = policy.role_mode === "everyone"
    || (policy.role_mode === "include" && hasRole)
    || (policy.role_mode === "exclude" && !hasRole);
  const channelAllowed = policy.channel_mode === "all"
    || (policy.channel_mode === "include" && policy.channel_ids.includes(channelId))
    || (policy.channel_mode === "exclude" && !policy.channel_ids.includes(channelId));
  return roleAllowed && channelAllowed;
}
