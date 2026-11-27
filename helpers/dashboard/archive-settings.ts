import { ChannelType, type Guild } from "discord.js";
import {
  ARCHIVE_CATEGORIES,
  getArchiveSettings,
  normalizeArchiveDashboardSettings,
  saveArchiveDashboardSettings as persistArchiveDashboardSettings,
  type ArchiveSettings,
} from "../archive/archive.js";
import { DashboardBridgeError, isDashboardActorId, requireGuildManager } from "./permissions.js";

export async function getDashboardArchiveSettings(guild: Guild): Promise<Record<string, unknown>> {
  const [settings, channels, roles] = await Promise.all([
    getArchiveSettings(guild.id),
    guild.channels.fetch(),
    guild.roles.fetch(),
  ]);
  return {
    settings,
    categories: ARCHIVE_CATEGORIES.map(({ label, value }) => ({ label, value })),
    upload_types: [
      { label: "Images", value: "image" },
      { label: "Audio", value: "audio" },
      { label: "Video", value: "video" },
    ],
    channels: [...channels.values()]
      .filter((channel): channel is NonNullable<typeof channel> => channel !== null
        && (channel.type === ChannelType.GuildText || channel.type === ChannelType.GuildAnnouncement))
      .map(channel => ({ id: channel.id, name: channel.name, type: channel.type }))
      .sort((left, right) => left.name.localeCompare(right.name)),
    roles: [...roles.values()]
      .filter(role => role.id !== guild.id && !role.managed)
      .map(role => ({ id: role.id, name: role.name }))
      .sort((left, right) => left.name.localeCompare(right.name)),
  };
}

export async function saveDashboardArchiveSettings(
  guild: Guild,
  actorId: string,
  input: unknown,
): Promise<ArchiveSettings> {
  if (!isDashboardActorId(actorId)) {
    throw new DashboardBridgeError("A valid dashboard actor is required.", 400);
  }
  await requireGuildManager(guild, actorId);
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new DashboardBridgeError("A valid Archive settings object is required.", 400);
  }

  let settings: ArchiveSettings;
  try {
    settings = normalizeArchiveDashboardSettings(guild.id, input as ArchiveSettings);
  } catch (error) {
    throw new DashboardBridgeError(error instanceof Error ? error.message : "Archive settings are invalid.", 400);
  }

  const [channels, roles] = await Promise.all([guild.channels.fetch(), guild.roles.fetch()]);
  const channelIds = [
    settings.uploadChannelId,
    settings.legacyStorageChannelId,
    settings.moderationChannelId,
  ].filter((id): id is string => id !== null);
  for (const channelId of channelIds) {
    const channel = channels.get(channelId);
    if (!channel || (channel.type !== ChannelType.GuildText && channel.type !== ChannelType.GuildAnnouncement)) {
      throw new DashboardBridgeError("Every selected Archive channel must be a text or announcement channel in this server.", 400);
    }
  }
  if (settings.moderatorRoleId) {
    const role = roles.get(settings.moderatorRoleId);
    if (!role || role.id === guild.id || role.managed) {
      throw new DashboardBridgeError("The Archive moderator role must be a selectable role in this server.", 400);
    }
  }

  return persistArchiveDashboardSettings(guild.id, actorId, settings);
}
