import { queryOne } from "../../database.js";

/** Moderator-only operational commands are confined to one configured server. */
export function isModeratorCommandGuild(guildId: string | null, configuredGuildId: string | null): boolean {
  return Boolean(guildId && configuredGuildId && guildId === configuredGuildId);
}

/** Bot-wide moderators are deliberately separate from each guild's role permissions. */
export async function isBotModerator(userId: string): Promise<boolean> {
  const administratorId = process.env.ADMIN_DISCORD_ID?.trim();
  if (administratorId && administratorId === userId) return true;
  const moderator = await queryOne<{ discord_id: string }>(
    "SELECT discord_id FROM bot_moderators WHERE discord_id = $1",
    [userId],
  );
  return moderator !== null;
}
