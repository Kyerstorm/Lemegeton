import { queryOne } from "../database.js";

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
