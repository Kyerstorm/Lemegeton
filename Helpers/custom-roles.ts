import { type Guild, type GuildMember, type Role } from "discord.js";
import { queryOne } from "../database.js";

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
  status: "active" | "missing" | "saved";
  name: string | null;
  color_mode: string;
  primary_color: number | null;
  secondary_color: number | null;
  last_changed_at: string | null;
}

const DEFAULT_PROTECTED_WORDS = [
  "admin", "administrator", "mod", "moderator", "staff", "owner", "dev", "developer",
  "helper", "support", "manager", "booster", "server booster", "nitro", "discord",
  "official", "bot", "verified", "partner", "team",
] as const;
const HEX_COLOR = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i;
const LEET: Record<string, string> = { "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "@": "a", "$": "s", "!": "i", "|": "l" };

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

function normalizeName(value: string): string {
  return value.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
    .replace(/[0134578@$!|]/g, character => LEET[character] ?? character);
}

function nameTokens(value: string): string[] {
  return normalizeName(value).split(/[^a-z0-9]+/).filter(Boolean);
}

function containsProtectedWord(name: string, word: string): boolean {
  const nameTokensValue = nameTokens(name);
  const wordTokens = nameTokens(word);
  if (!wordTokens.length) return false;
  for (let index = 0; index <= nameTokensValue.length - wordTokens.length; index += 1) {
    const candidate = nameTokensValue.slice(index, index + wordTokens.length);
    const last = candidate[candidate.length - 1] ?? "";
    const expected = wordTokens[wordTokens.length - 1] ?? "";
    if (candidate.slice(0, -1).join(" ") === wordTokens.slice(0, -1).join(" ")
      && (last === expected || last === `${expected}s` || last === `${expected}es`)) return true;
  }
  return wordTokens.length > 1 && nameTokensValue.join("") === wordTokens.join("");
}

export function parseCustomRoleColor(input: string): number | null {
  const match = HEX_COLOR.exec(input.trim());
  if (!match) return null;
  const digits = match[1] ?? "";
  const expanded = digits.length === 3 ? [...digits].map(value => value + value).join("") : digits;
  const value = Number.parseInt(expanded, 16);
  return value === 0 ? 0x010101 : value;
}

export function validateCustomRoleName(
  raw: string,
  settings: Pick<CustomRoleSettings, "blocked_words" | "removed_default_words">,
  reservedNames: string[] = [],
  protectedRoleNames: string[] = [],
): { name: string | null; error: string | null } {
  const name = raw.replace(/\s+/g, " ").trim();
  if (!name || !name.replace(/[\s\u200b-\u200f\u202a-\u202e\ufeff]/g, "")) {
    return { name: null, error: "Your role name can't be empty or only invisible characters." };
  }
  if (name.length > 100) return { name: null, error: "Role names can be at most 100 characters." };
  const folded = name.toLocaleLowerCase();
  if (folded.includes("@everyone") || folded.includes("@here")) {
    return { name: null, error: "Role names can't contain @everyone or @here." };
  }
  const normalized = nameTokens(name).join(" ");
  for (const reserved of reservedNames) {
    if (reserved.toLocaleLowerCase() === folded || nameTokens(reserved).join(" ") === normalized) {
      return { name: null, error: `There's already a server role called **${reserved}**, so you can't use that name.` };
    }
  }
  for (const roleName of protectedRoleNames) {
    if (nameTokens(roleName).join("").length > 1 && containsProtectedWord(name, roleName)) {
      return { name: null, error: `Role names can't include **${roleName}** because it's a staff role in this server.` };
    }
  }
  const removed = new Set(settings.removed_default_words.map(word => word.toLowerCase()));
  for (const word of DEFAULT_PROTECTED_WORDS) {
    if (!removed.has(word) && containsProtectedWord(name, word)) {
      return { name: null, error: `Role names can't include the word **${word}**.` };
    }
  }
  const squashed = normalizeName(name).replace(/[^a-z0-9]/g, "");
  for (const word of settings.blocked_words) {
    const blocked = normalizeName(word).replace(/[^a-z0-9]/g, "");
    if (blocked && squashed.includes(blocked)) return { name: null, error: "That name contains a blocked word. Please choose another." };
  }
  return { name, error: null };
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
    `SELECT guild_id, user_id, role_id, status, name, color_mode, primary_color,
            secondary_color, last_changed_at
       FROM custom_role_records WHERE guild_id = $1 AND user_id = $2`,
    [guildId, userId],
  );
}

export async function saveCustomRole(record: Omit<CustomRoleRecord, "last_changed_at">): Promise<void> {
  await queryOne(
    `INSERT INTO custom_role_records (
       guild_id, user_id, role_id, status, name, color_mode, primary_color, secondary_color,
       created_at, updated_at
     ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,NOW(),NOW())
     ON CONFLICT (guild_id,user_id) DO UPDATE SET
       role_id=EXCLUDED.role_id, status=EXCLUDED.status, name=EXCLUDED.name,
       color_mode=EXCLUDED.color_mode, primary_color=EXCLUDED.primary_color,
       secondary_color=EXCLUDED.secondary_color, updated_at=NOW()`,
    [record.guild_id, record.user_id, record.role_id, record.status, record.name,
      record.color_mode, record.primary_color, record.secondary_color],
  );
}

export async function updateCustomRole(
  guildId: string,
  userId: string,
  fields: { name?: string; primary_color?: number | null; status?: CustomRoleRecord["status"]; role_id?: string | null },
  changed = false,
): Promise<void> {
  const assignments: string[] = [];
  const values: unknown[] = [guildId, userId];
  const add = (column: string, value: unknown) => {
    values.push(value);
    assignments.push(`${column} = $${values.length}`);
  };
  if (fields.name !== undefined) add("name", fields.name);
  if (fields.primary_color !== undefined) add("primary_color", fields.primary_color);
  if (fields.status !== undefined) add("status", fields.status);
  if (fields.role_id !== undefined) add("role_id", fields.role_id);
  if (changed) assignments.push("last_changed_at = NOW()");
  if (!assignments.length) return;
  assignments.push("updated_at = NOW()");
  await queryOne(
    `UPDATE custom_role_records SET ${assignments.join(", ")} WHERE guild_id = $1 AND user_id = $2 RETURNING guild_id`,
    values,
  );
}

export function customRoleEligibility(member: GuildMember, settings: CustomRoleSettings): boolean {
  return Boolean(member.premiumSince) || member.roles.cache.some(role => settings.allowed_role_ids.includes(role.id));
}

export function customRoleChannelAllowed(channelId: string, parentId: string | null, settings: CustomRoleSettings): boolean {
  return !settings.command_channel_id || settings.command_channel_id === channelId || settings.command_channel_id === parentId;
}

export function validateCustomRoleAnchor(guild: Guild, role: Role): string | null {
  if (role.id === guild.id) return "@everyone can't be the anchor.";
  const botMember = guild.members.me;
  if (!botMember) return "I couldn't resolve my server role. Try again shortly.";
  if (role.position >= botMember.roles.highest.position) return "My highest role must be above the anchor role. Move my role higher in Server Settings → Roles.";
  return null;
}

export function customRoleCooldownMessage(record: CustomRoleRecord, cooldownSeconds: number, now = Date.now()): string | null {
  if (!record.last_changed_at || cooldownSeconds <= 0) return null;
  const remaining = cooldownSeconds - Math.floor((now - new Date(record.last_changed_at).getTime()) / 1000);
  if (remaining <= 0) return null;
  const minutes = Math.ceil(remaining / 60);
  return `You can change your role again in about ${minutes} minute${minutes === 1 ? "" : "s"}.`;
}
