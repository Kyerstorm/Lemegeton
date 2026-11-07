import type { Guild, GuildMember, Role } from "discord.js";
import type { CustomRoleRecord, CustomRoleSettings } from "./custom-roles.js";

export const DEFAULT_PROTECTED_WORDS = [
  "admin", "administrator", "mod", "moderator", "staff", "owner", "dev", "developer",
  "helper", "support", "manager", "booster", "server booster", "nitro", "discord",
  "official", "bot", "verified", "partner", "team",
] as const;
const HEX_COLOR = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i;
export const HOLOGRAPHIC_COLORS = [11127295, 16759788, 16761760] as const;
const STANDARD_EMOJI = /^(?:\p{Extended_Pictographic}(?:\uFE0F|\uFE0E)?\p{Emoji_Modifier}?(?:\u200D\p{Extended_Pictographic}(?:\uFE0F|\uFE0E)?\p{Emoji_Modifier}?)*|\p{Regional_Indicator}{2}|[0-9#*]\uFE0F?\u20E3)$/u;
const LEET: Record<string, string> = { "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "@": "a", "$": "s", "!": "i", "|": "l" };

export const HOLOGRAPHIC_COLORS = [11127295, 16759788, 16761760] as const;

function normalizeName(value: string): string {
  return value.normalize("NFKD").replace(/[\p{Cf}\p{Cc}\p{Mn}\p{Me}]/gu, "").toLowerCase()
    .replace(/[0134578@$!|]/g, character => LEET[character] ?? character);
}

function nameTokens(value: string): string[] {
  return normalizeName(value).split(/[^a-z0-9]+/).filter(Boolean);
}

function mergeSingleLetters(tokens: string[]): string[] {
  const merged: string[] = [];
  let run = "";
  for (const token of tokens) {
    if (token.length === 1) {
      run += token;
      continue;
    }
    if (run) merged.push(run);
    run = "";
    merged.push(token);
  }
  if (run) merged.push(run);
  return merged;
}

function containsProtectedWord(name: string, word: string): boolean {
  const split = nameTokens(name);
  const wordTokens = nameTokens(word);
  if (!wordTokens.length) return false;
  const joinedPerWord = normalizeName(name).split(/\s+/)
    .map(token => token.replace(/[^a-z0-9]/g, "")).filter(Boolean);
  const views = [split, mergeSingleLetters(split), joinedPerWord];
  const phrase = wordTokens.join("");
  for (const view of views) {
    for (let index = 0; index <= view.length - wordTokens.length; index += 1) {
      const candidate = view.slice(index, index + wordTokens.length);
      const last = candidate[candidate.length - 1] ?? "";
      const expected = wordTokens[wordTokens.length - 1] ?? "";
      if (candidate.slice(0, -1).join(" ") === wordTokens.slice(0, -1).join(" ")
        && (last === expected || last === expected + "s" || last === expected + "es")) return true;
    }
    if (wordTokens.length > 1 && view.some(token =>
      token === phrase || token === phrase + "s" || token === phrase + "es",
    )) return true;
  }
  return false;
}

export function validateCustomRoleEmoji(input: string): string | null {
  const emoji = input.trim();
  return emoji && emoji.length <= 32 && !emoji.startsWith("<") && STANDARD_EMOJI.test(emoji) ? emoji : null;
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

export function parseCustomRoleWordList(raw: string): string[] {
  const seen = new Set<string>();
  const words: string[] = [];
  for (const part of raw.replace(/,/g, "\n").split(/\r?\n/)) {
    const word = part.normalize("NFKC").replace(/\s+/g, " ").trim().toLocaleLowerCase();
    if (!word || word.length > 40 || !/[\p{L}\p{N}]/u.test(word) || seen.has(word)) continue;
    seen.add(word);
    words.push(word);
  }
  return words;
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
