import { PermissionFlagsBits, type Guild } from "discord.js";
import { query, queryOne } from "../../database.js";
import { DEFAULT_PROTECTED_WORDS, customRoleEligibility, validateCustomRoleName } from "./custom-role-validation.js";
export {
  HOLOGRAPHIC_COLORS,
  customRoleChannelAllowed,
  customRoleCooldownMessage,
  customRoleEligibility,
  parseCustomRoleColor,
  parseCustomRoleWordList,
  validateCustomRoleAnchor,
  validateCustomRoleEmoji,
  validateCustomRoleName,
} from "./custom-role-validation.js";

export interface CustomRoleSettings {
  guild_id: string;
  enabled: boolean;
  anchor_role_id: string | null;
  anchor_place: "above" | "below";
  command_channel_id: string | null;
  log_channel_id: string | null;
  cooldown_seconds: number;
  allowed_role_ids: string[];
  blocked_words: string[];
  removed_default_words: string[];
}

export interface CustomRoleRecord {
  guild_id: string;
  user_id: string;
  role_id: string | null;
  position_hint: number | null;
  status: "active" | "missing" | "saved";
  name: string | null;
  color_mode: string;
  primary_color: number | null;
  secondary_color: number | null;
  icon_emoji: string | null;
  icon_png?: Buffer | null;
  icon_crop?: string | null;
  icon_source_asset_id?: number | null;
  last_changed_at: string | null;
}

function stringList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String).filter(Boolean);
  if (typeof value !== "string") return [];
  try {
    const parsed: unknown = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.map(String).filter(Boolean) : [];
  } catch {
    return [];
  }
}

export async function getCustomRoleSettings(guildId: string): Promise<CustomRoleSettings> {
  const row = await queryOne<{
    guild_id: string; enabled: boolean; anchor_role_id: string | null; anchor_place: string | null;
    command_channel_id: string | null; log_channel_id: string | null; cooldown_seconds: number | null;
    allowed_role_ids: string | null; blocked_words: string | null; removed_default_words: string | null;
  }>(
    `SELECT guild_id, enabled, anchor_role_id, anchor_place, command_channel_id, log_channel_id,
            cooldown_seconds, allowed_role_ids, blocked_words, removed_default_words
       FROM custom_role_guild_settings WHERE guild_id = $1`,
    [guildId],
  );
  return {
    guild_id: guildId,
    enabled: row?.enabled ?? false,
    anchor_role_id: row?.anchor_role_id ?? null,
    anchor_place: row?.anchor_place === "above" ? "above" : "below",
    command_channel_id: row?.command_channel_id ?? null,
    log_channel_id: row?.log_channel_id ?? null,
    cooldown_seconds: Number(row?.cooldown_seconds ?? 0),
    allowed_role_ids: stringList(row?.allowed_role_ids),
    blocked_words: stringList(row?.blocked_words),
    removed_default_words: stringList(row?.removed_default_words),
  };
}

export async function updateCustomRoleSettings(
  guildId: string,
  patch: Partial<Omit<CustomRoleSettings, "guild_id">>,
): Promise<CustomRoleSettings> {
  const current = await getCustomRoleSettings(guildId);
  const next = { ...current, ...patch };
  await queryOne(
    `INSERT INTO custom_role_guild_settings (
       guild_id, enabled, anchor_role_id, anchor_place, command_channel_id, log_channel_id,
       cooldown_seconds, allowed_role_ids, blocked_words, removed_default_words, updated_at
     ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,NOW())
     ON CONFLICT (guild_id) DO UPDATE SET
       enabled=EXCLUDED.enabled, anchor_role_id=EXCLUDED.anchor_role_id, anchor_place=EXCLUDED.anchor_place,
       command_channel_id=EXCLUDED.command_channel_id, log_channel_id=EXCLUDED.log_channel_id,
       cooldown_seconds=EXCLUDED.cooldown_seconds, allowed_role_ids=EXCLUDED.allowed_role_ids,
       blocked_words=EXCLUDED.blocked_words, removed_default_words=EXCLUDED.removed_default_words,
       updated_at=NOW()
     RETURNING guild_id`,
    [guildId, next.enabled, next.anchor_role_id, next.anchor_place, next.command_channel_id,
      next.log_channel_id, next.cooldown_seconds, JSON.stringify(next.allowed_role_ids),
      JSON.stringify(next.blocked_words), JSON.stringify(next.removed_default_words)],
  );
  return next;
}

export async function getCustomRoleRecord(guildId: string, userId: string): Promise<CustomRoleRecord | null> {
  return queryOne<CustomRoleRecord>(
    `SELECT guild_id, user_id, role_id, position_hint, status, name, color_mode, primary_color,
            secondary_color, icon_emoji, last_changed_at
       FROM custom_role_records WHERE guild_id = $1 AND user_id = $2`,
    [guildId, userId],
  );
}

export interface CustomRoleIconData {
  icon_png: Buffer | null;
  icon_crop: string | null;
  icon_source_asset_id: number | null;
}

export async function getCustomRoleIconData(guildId: string, userId: string): Promise<CustomRoleIconData | null> {
  return queryOne<CustomRoleIconData>(
    "SELECT icon_png, icon_crop, icon_source_asset_id FROM custom_role_records WHERE guild_id = $1 AND user_id = $2",
    [guildId, userId],
  );
}

export async function saveCustomRole(record: Omit<CustomRoleRecord, "last_changed_at">): Promise<void> {
  await queryOne(
    `INSERT INTO custom_role_records (
       guild_id, user_id, role_id, position_hint, status, name, color_mode, primary_color, secondary_color,
       icon_emoji, created_at, updated_at
     ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,NOW(),NOW())
     ON CONFLICT (guild_id,user_id) DO UPDATE SET
       role_id=EXCLUDED.role_id, position_hint=EXCLUDED.position_hint, status=EXCLUDED.status, name=EXCLUDED.name,
       color_mode=EXCLUDED.color_mode, primary_color=EXCLUDED.primary_color,
       secondary_color=EXCLUDED.secondary_color, icon_emoji=EXCLUDED.icon_emoji, updated_at=NOW()`,
    [record.guild_id, record.user_id, record.role_id, record.position_hint, record.status, record.name,
      record.color_mode, record.primary_color, record.secondary_color, record.icon_emoji],
  );
}

export async function updateCustomRole(
  guildId: string,
  userId: string,
  fields: { name?: string; color_mode?: string; primary_color?: number | null; secondary_color?: number | null; icon_emoji?: string | null; icon_png?: Buffer | null; icon_crop?: string | null; icon_source_asset_id?: number | null; position_hint?: number | null; status?: CustomRoleRecord["status"]; role_id?: string | null },
  changed = false,
): Promise<void> {
  const assignments: string[] = [];
  const values: unknown[] = [guildId, userId];
  const add = (column: string, value: unknown) => {
    values.push(value);
    assignments.push(`${column} = $${values.length}`);
  };
  if (fields.name !== undefined) add("name", fields.name);
  if (fields.color_mode !== undefined) add("color_mode", fields.color_mode);
  if (fields.primary_color !== undefined) add("primary_color", fields.primary_color);
  if (fields.secondary_color !== undefined) add("secondary_color", fields.secondary_color);
  if (fields.icon_emoji !== undefined) add("icon_emoji", fields.icon_emoji);
  if (fields.icon_png !== undefined) add("icon_png", fields.icon_png);
  if (fields.icon_crop !== undefined) add("icon_crop", fields.icon_crop);
  if (fields.icon_source_asset_id !== undefined) add("icon_source_asset_id", fields.icon_source_asset_id);
  if (fields.status !== undefined) add("status", fields.status);
  if (fields.role_id !== undefined) add("role_id", fields.role_id);
  if (fields.position_hint !== undefined) add("position_hint", fields.position_hint);
  if (changed) assignments.push("last_changed_at = NOW()");
  if (!assignments.length) return;
  assignments.push("updated_at = NOW()");
  await queryOne(
    `UPDATE custom_role_records SET ${assignments.join(", ")} WHERE guild_id = $1 AND user_id = $2 RETURNING guild_id`,
    values,
  );
}

export async function addCustomRoleBlockedWord(
  guildId: string,
  raw: string,
): Promise<{ ok: boolean; message: string }> {
  const word = raw.normalize("NFKC").replace(/\s+/g, " ").trim().toLocaleLowerCase();
  if (!word || word.length > 40 || !/[\p{L}\p{N}]/u.test(word)) {
    return { ok: false, message: "Blocked words must be 1–40 characters and include a letter or number." };
  }
  const settings = await getCustomRoleSettings(guildId);
  if ((DEFAULT_PROTECTED_WORDS as readonly string[]).includes(word)) {
    if (!settings.removed_default_words.includes(word)) {
      return { ok: false, message: "**" + word + "** is already a built-in protected word." };
    }
    await updateCustomRoleSettings(guildId, {
      removed_default_words: settings.removed_default_words.filter(item => item !== word),
    });
    return { ok: true, message: "Built-in protected word **" + word + "** is back on." };
  }
  if (settings.blocked_words.includes(word)) return { ok: false, message: "**" + word + "** is already blocked." };
  await updateCustomRoleSettings(guildId, { blocked_words: [...settings.blocked_words, word] });
  return { ok: true, message: "Blocked **" + word + "** anywhere in custom role names." };
}

export async function removeCustomRoleBlockedWord(
  guildId: string,
  raw: string,
): Promise<{ ok: boolean; message: string }> {
  const word = raw.normalize("NFKC").replace(/\s+/g, " ").trim().toLocaleLowerCase();
  const settings = await getCustomRoleSettings(guildId);
  if (settings.blocked_words.includes(word)) {
    await updateCustomRoleSettings(guildId, { blocked_words: settings.blocked_words.filter(item => item !== word) });
    return { ok: true, message: "Unblocked **" + word + "**." };
  }
  if ((DEFAULT_PROTECTED_WORDS as readonly string[]).includes(word)) {
    if (settings.removed_default_words.includes(word)) return { ok: false, message: "Built-in word **" + word + "** is already off." };
    await updateCustomRoleSettings(guildId, { removed_default_words: [...settings.removed_default_words, word] });
    return { ok: true, message: "Built-in protected word **" + word + "** is now off." };
  }
  return { ok: false, message: "**" + (word || raw) + "** isn't on the blocked list." };
}


export interface CustomRolePendingRemoval {
  id: string;
  guild_id: string;
  user_ids: string[];
  reason: string;
  status: "pending" | "confirmed" | "cancelled" | "withdrawn";
  log_channel_id: string | null;
  log_message_id: string | null;
}

function parseSnowflakeList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String).filter(item => /^\d{17,20}$/.test(item));
  if (typeof value === "string") {
    try {
      const parsed: unknown = JSON.parse(value);
      return Array.isArray(parsed) ? parsed.map(String).filter(item => /^\d{17,20}$/.test(item)) : [];
    } catch {
      return [];
    }
  }
  return [];
}

export async function listCustomRoleRecords(guildId: string): Promise<CustomRoleRecord[]> {
  return query<CustomRoleRecord>(
    `SELECT guild_id, user_id, role_id, position_hint, status, name, color_mode, primary_color,
            secondary_color, icon_emoji, last_changed_at
       FROM custom_role_records WHERE guild_id = $1 ORDER BY user_id`,
    [guildId],
  );
}

export async function markCustomRoleMissing(
  guildId: string,
  userId: string,
  roleId: string,
): Promise<void> {
  await query(
    `UPDATE custom_role_records SET status = 'missing', role_id = NULL, updated_at = NOW()
       WHERE guild_id = $1 AND user_id = $2 AND role_id = $3 AND status = 'active'`,
    [guildId, userId, roleId],
  );
}

export async function getOpenCustomRolePending(guildId: string): Promise<CustomRolePendingRemoval | null> {
  const row = await queryOne<Omit<CustomRolePendingRemoval, "user_ids"> & { user_ids: unknown }>(
    `SELECT id::text, guild_id::text, user_ids, reason, status, log_channel_id::text, log_message_id::text
       FROM custom_role_pending_removals WHERE guild_id = $1 AND status = 'pending'
       ORDER BY id DESC LIMIT 1`,
    [guildId],
  );
  return row ? { ...row, user_ids: parseSnowflakeList(row.user_ids) } : null;
}

export async function createCustomRolePending(
  guildId: string,
  userIds: string[],
  reason: string,
): Promise<CustomRolePendingRemoval> {
  const row = await queryOne<Omit<CustomRolePendingRemoval, "user_ids"> & { user_ids: unknown }>(
    `INSERT INTO custom_role_pending_removals (guild_id, user_ids, reason)
       VALUES ($1, $2::jsonb, $3)
       RETURNING id::text, guild_id::text, user_ids, reason, status, log_channel_id::text, log_message_id::text`,
    [guildId, JSON.stringify([...new Set(userIds)]), reason],
  );
  if (!row) throw new Error("The pending custom role removal could not be saved.");
  return { ...row, user_ids: parseSnowflakeList(row.user_ids) };
}

export async function updateCustomRolePendingUsers(id: string, userIds: string[]): Promise<void> {
  await query(
    "UPDATE custom_role_pending_removals SET user_ids = $2::jsonb WHERE id = $1 AND status = 'pending'",
    [id, JSON.stringify([...new Set(userIds)])],
  );
}

export async function resolveCustomRolePending(
  id: string,
  guildId: string,
  status: Exclude<CustomRolePendingRemoval["status"], "pending">,
  actorId: string,
): Promise<boolean> {
  const row = await queryOne<{ id: string }>(
    `UPDATE custom_role_pending_removals
        SET status = $3, resolved_by = $4, resolved_at = NOW()
      WHERE id = $1 AND guild_id = $2 AND status = 'pending'
      RETURNING id::text`,
    [id, guildId, status, actorId],
  );
  return Boolean(row);
}

export async function snoozeCustomRoleUsers(guildId: string, userIds: string[], hours = 24): Promise<void> {
  for (const userId of new Set(userIds)) {
    await query(
      `INSERT INTO custom_role_archive_snoozes (guild_id, user_id, until)
         VALUES ($1, $2, NOW() + ($3::text || ' hours')::interval)
         ON CONFLICT (guild_id, user_id) DO UPDATE SET until = EXCLUDED.until`,
      [guildId, userId, hours],
    );
  }
}

export async function customRoleSnoozedUsers(guildId: string): Promise<{ active: Set<string>; expired: Set<string> }> {
  const rows = await query<{ user_id: string; is_active: boolean }>(
    `SELECT user_id::text, (until > NOW()) AS is_active
       FROM custom_role_archive_snoozes WHERE guild_id = $1`,
    [guildId],
  );
  return {
    active: new Set(rows.filter(row => row.is_active).map(row => row.user_id)),
    expired: new Set(rows.filter(row => !row.is_active).map(row => row.user_id)),
  };
}

export async function clearCustomRoleSnoozes(guildId: string, userIds: string[]): Promise<void> {
  if (!userIds.length) return;
  await query(
    "DELETE FROM custom_role_archive_snoozes WHERE guild_id = $1 AND user_id = ANY($2::bigint[])",
    [guildId, userIds],
  );
}

export async function deleteCustomRoleRecord(
  guildId: string,
  userId: string,
): Promise<{ icon_source_asset_id: number | null } | null> {
  return queryOne<{ icon_source_asset_id: number | null }>(
    "DELETE FROM custom_role_records WHERE guild_id = $1 AND user_id = $2 RETURNING icon_source_asset_id",
    [guildId, userId],
  );
}

export async function removeCustomRolePendingUser(
  guildId: string,
  userId: string,
  actorId: string,
): Promise<void> {
  const pending = await getOpenCustomRolePending(guildId);
  if (!pending || !pending.user_ids.includes(userId)) return;
  const remaining = pending.user_ids.filter(id => id !== userId);
  if (remaining.length) {
    await updateCustomRolePendingUsers(pending.id, remaining);
  } else {
    await resolveCustomRolePending(pending.id, guildId, "withdrawn", actorId);
  }
}

export interface LegacyCustomRoleImportEntry {
  user_id: string;
  role_id: string;
  role_name: string | null;
  reason: string | null;
}

export interface LegacyCustomRoleImportPlan {
  total: number;
  take_over: LegacyCustomRoleImportEntry[];
  not_qualifying: LegacyCustomRoleImportEntry[];
  skipped: LegacyCustomRoleImportEntry[];
}

const LEGACY_MODERATION_PERMISSIONS = [
  PermissionFlagsBits.Administrator,
  PermissionFlagsBits.ManageGuild,
  PermissionFlagsBits.ManageRoles,
  PermissionFlagsBits.ManageMessages,
  PermissionFlagsBits.KickMembers,
  PermissionFlagsBits.BanMembers,
  PermissionFlagsBits.ModerateMembers,
] as const;

export async function planLegacyCustomRoleImport(guild: Guild): Promise<LegacyCustomRoleImportPlan> {
  let legacyRows: Array<{ user_id: string; role_id: string }>;
  try {
    legacyRows = await query<{ user_id: string; role_id: string }>(
      "SELECT discord_id::text AS user_id, role_id::text AS role_id " +
        "FROM booster_roles WHERE guild_id = $1 ORDER BY created_at ASC, discord_id ASC",
      [guild.id],
    );
  } catch (error) {
    if ((error as { code?: string } | null)?.code === "42P01") {
      throw new Error("The legacy booster_roles table is not present in this PostgreSQL database. No import was attempted.");
    }
    throw error;
  }

  let members;
  try {
    members = await guild.members.fetch();
    await guild.roles.fetch();
  } catch (error) {
    throw new Error("I couldn't verify the full member and role lists, so I won't import old booster roles. " +
      (error instanceof Error ? error.message : "Try again once Server Members Intent and role access are available."));
  }
  const settings = await getCustomRoleSettings(guild.id);
  const records = await listCustomRoleRecords(guild.id);
  const recordsByUser = new Map(records.map(record => [record.user_id, record]));
  const recordedRoleIds = new Set(records.flatMap(record => record.role_id ? [record.role_id] : []));
  const botMember = guild.members.me ?? await guild.members.fetchMe().catch(() => null);
  const result: LegacyCustomRoleImportPlan = { total: legacyRows.length, take_over: [], not_qualifying: [], skipped: [] };
  const seenRoleIds = new Set<string>();

  for (const row of legacyRows) {
    const userId = String(row.user_id);
    const roleId = String(row.role_id);
    const role = guild.roles.cache.get(roleId) ?? null;
    const entry: LegacyCustomRoleImportEntry = {
      user_id: userId,
      role_id: roleId,
      role_name: role?.name ?? null,
      reason: null,
    };
    const current = recordsByUser.get(userId);
    if (!/^\d{17,20}$/.test(userId) || !/^\d{17,20}$/.test(roleId)) {
      entry.reason = "Legacy record has an invalid Discord ID.";
      result.skipped.push(entry);
    } else if (current?.role_id === roleId && current.status === "active") {
      entry.reason = "Already imported.";
      result.skipped.push(entry);
    } else if (current?.role_id && guild.roles.cache.has(current.role_id)) {
      entry.reason = "Member already has another active Custom Role.";
      result.skipped.push(entry);
    } else if (!role) {
      entry.reason = "The old Discord role no longer exists.";
      result.skipped.push(entry);
    } else if (role.id === guild.id) {
      entry.reason = "The old role is @everyone.";
      result.skipped.push(entry);
    } else if (role.managed) {
      entry.reason = "The old role is managed by Discord or an integration.";
      result.skipped.push(entry);
    } else if (!botMember || role.position >= botMember.roles.highest.position) {
      entry.reason = "The old role is at or above the bot's highest role.";
      result.skipped.push(entry);
    } else if (LEGACY_MODERATION_PERMISSIONS.some(permission => role.permissions.has(permission))) {
      entry.reason = "The old role has moderation or administration permissions.";
      result.skipped.push(entry);
    } else if (role.id === settings.anchor_role_id) {
      entry.reason = "The old role is the configured Custom Roles anchor.";
      result.skipped.push(entry);
    } else if (settings.allowed_role_ids.includes(role.id)) {
      entry.reason = "The old role is configured as an eligibility role.";
      result.skipped.push(entry);
    } else if (recordedRoleIds.has(roleId) || seenRoleIds.has(roleId)) {
      entry.reason = "That Discord role is already linked to another Custom Role record.";
      result.skipped.push(entry);
    } else {
      seenRoleIds.add(roleId);
      const member = members.get(userId) ?? null;
      if (!member || !customRoleEligibility(member, settings)) {
        entry.reason = member ? "Member no longer qualifies for Custom Roles." : "Member is no longer in this server.";
        result.not_qualifying.push(entry);
      } else {
        result.take_over.push(entry);
      }
    }
  }
  return result;
}

