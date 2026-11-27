import type { Guild } from "discord.js";
import { query } from "../../src/utility/database/libsql/database.js";
import {
  canConfigureGuildLeaveAction,
  getGuildRetentionSettings,
  isGuildLeaveAction,
  saveGuildSetupSettings,
  setGuildLeaveAction,
} from "../runtime/guild-retention.js";
import {
  getGuildLanguage,
  getSupportedLanguage,
  setGuildLanguage,
  SUPPORTED_LANGUAGES,
} from "../runtime/languages.js";
import { DashboardBridgeError, guildActorCanManage, isDashboardActorId, requireGuildMember } from "./permissions.js";

export interface ServerSettingsUpdate {
  leave_action?: unknown;
  language_code?: unknown;
}

export async function getDashboardServerSettings(guild: Guild, actorId: string): Promise<Record<string, unknown>> {
  await requireGuildMember(guild, actorId);
  const [retention, language, canManageServer] = await Promise.all([
    getGuildRetentionSettings(guild.id),
    getGuildLanguage(guild.id),
    guildActorCanManage(guild, actorId),
  ]);
  if (!canManageServer && retention.invited_by !== actorId) {
    throw new DashboardBridgeError("You do not have permission to manage this server's setup.", 403);
  }
  return {
    settings: {
      leave_action: retention.leave_action,
      language_code: language?.code ?? "",
    },
    setup_complete: Boolean(retention.leave_action && language),
    can_choose_retention: canConfigureGuildLeaveAction(retention.invited_by, actorId, canManageServer),
    can_manage_server: canManageServer,
    languages: SUPPORTED_LANGUAGES.map(({ code, label }) => ({ code, label })),
  };
}

export async function saveDashboardServerSettings(
  guild: Guild,
  actorId: string,
  update: ServerSettingsUpdate,
): Promise<Record<string, unknown>> {
  if (!isDashboardActorId(actorId)) {
    throw new DashboardBridgeError("A valid dashboard actor is required.", 400);
  }
  const hasRetention = Object.prototype.hasOwnProperty.call(update, "leave_action");
  const hasLanguage = Object.prototype.hasOwnProperty.call(update, "language_code");
  if (!hasRetention && !hasLanguage) {
    throw new DashboardBridgeError("Choose a server setting to update.", 400);
  }

  await requireGuildMember(guild, actorId);
  const [current, canManageServer] = await Promise.all([
    getGuildRetentionSettings(guild.id),
    guildActorCanManage(guild, actorId),
  ]);
  if (hasRetention) {
    if (!isGuildLeaveAction(update.leave_action)) {
      throw new DashboardBridgeError("Choose whether to delete or retain this server's data.", 400);
    }
    if (!canConfigureGuildLeaveAction(current.invited_by, actorId, canManageServer)) {
      throw new DashboardBridgeError("Only the person who invited Lemegeton or a member with Manage Server permission can change data retention.", 403);
    }
  }
  if (hasLanguage) {
    if (typeof update.language_code !== "string" || !getSupportedLanguage(update.language_code)) {
      throw new DashboardBridgeError("Choose a language from the supported language list.", 400);
    }
    if (!canManageServer) {
      throw new DashboardBridgeError("Manage Server or Administrator permission is required to change the server language.", 403);
    }
  }

  if (hasRetention && hasLanguage) {
    await saveGuildSetupSettings(
      guild.id,
      actorId,
      update.leave_action as "delete" | "retain",
      update.language_code as string,
    );
  } else if (hasRetention) {
    await setGuildLeaveAction(guild.id, update.leave_action as "delete" | "retain", actorId);
  } else {
    await setGuildLanguage(guild.id, update.language_code as string, actorId);
  }

  return getDashboardServerSettings(guild, actorId);
}

export async function invitedDashboardGuildIds(actorId: string): Promise<string[]> {
  if (!isDashboardActorId(actorId)) return [];
  const rows = await query<{ guild_id: string }>(
    "SELECT guild_id::text FROM guild_retention_settings WHERE invited_by = $1 ORDER BY created_at ASC",
    [actorId],
  );
  return rows.map(row => row.guild_id);
}
