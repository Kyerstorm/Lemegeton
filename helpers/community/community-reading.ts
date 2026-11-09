import type { PoolClient } from "pg";
import { query, queryOne, transaction } from "../../database.js";
import { cleanText, isValidHttpsUrl } from "../security/security.js";

export const READING_CATEGORIES = [
  "manga",
  "manhwa",
  "manhua",
  "webtoon",
  "light novel",
  "webnovel",
  "book",
] as const;

export type ReadingCategory = typeof READING_CATEGORIES[number];

export interface ReadingNomination {
  id: string;
  guild_id: string;
  channel_id: string;
  proposer_id: string;
  title: string;
  category: ReadingCategory;
  source_url: string | null;
  status: "open" | "selected" | "closed";
  scheduled_at: Date | null;
  thread_id: string | null;
  reminder_sent: boolean;
  created_at: Date;
  vote_count?: number;
}

export function normalizeReadingCategory(value: string): ReadingCategory | null {
  const category = value.trim().toLocaleLowerCase("en-US");
  return (READING_CATEGORIES as readonly string[]).includes(category)
    ? category as ReadingCategory
    : null;
}

export function parseReadingScheduleTime(value: string, now = new Date()): Date {
  const input = value.trim();
  if (!/(?:Z|[+-](?:0\d|1\d|2[0-3]):[0-5]\d)$/i.test(input)) {
    throw new Error("The scheduled time must include a timezone, for example 2026-12-12T19:00:00+00:00.");
  }
  const timestamp = Date.parse(input);
  if (!Number.isFinite(timestamp)) throw new Error("Enter a valid ISO-8601 date and time.");
  const scheduledAt = new Date(timestamp);
  if (scheduledAt.getTime() <= now.getTime()) throw new Error("The reading discussion must be scheduled in the future.");
  return scheduledAt;
}

export async function nominateReading(input: {
  guildId: string;
  channelId: string;
  proposerId: string;
  title: string;
  category: string;
  sourceUrl?: string;
}): Promise<string> {
  const title = cleanText(input.title, 200);
  const category = normalizeReadingCategory(input.category);
  const sourceUrl = isValidHttpsUrl(input.sourceUrl);
  if (!title) throw new Error("Enter a title to nominate.");
  if (!category) throw new Error("Choose manga, manhwa, manhua, webtoon, light novel, webnovel or book.");
  if (input.sourceUrl?.trim() && !sourceUrl) throw new Error("The source link must be a valid HTTPS URL without embedded credentials.");
  const row = await queryOne<{ id: string }>(
    `INSERT INTO community_reading_nominations
      (guild_id,channel_id,proposer_id,title,category,source_url,status)
     VALUES ($1,$2,$3,$4,$5,$6,'open') RETURNING id`,
    [input.guildId,input.channelId,input.proposerId,title,category,sourceUrl],
  );
  if (!row) throw new Error("The reading nomination could not be saved.");
  return row.id;
}

export async function listReadingNominations(guildId: string): Promise<ReadingNomination[]> {
  return query<ReadingNomination>(
    `SELECT n.*,COUNT(v.user_id)::INT AS vote_count
       FROM community_reading_nominations n
       LEFT JOIN community_reading_votes v
         ON v.guild_id = n.guild_id AND v.nomination_id = n.id
      WHERE n.guild_id = $1 AND n.status = 'open'
      GROUP BY n.id
      ORDER BY n.created_at DESC LIMIT 15`,
    [guildId],
  );
}

export async function voteForReading(guildId: string, userId: string, nominationId: string): Promise<void> {
  const row = await queryOne<{ nomination_id: string }>(
    `INSERT INTO community_reading_votes (guild_id,user_id,nomination_id)
     SELECT guild_id,$2,id
       FROM community_reading_nominations
      WHERE guild_id = $1 AND id = $3 AND status = 'open'
     ON CONFLICT (guild_id,user_id)
     DO UPDATE SET nomination_id = EXCLUDED.nomination_id,updated_at = NOW()
     RETURNING nomination_id`,
    [guildId,userId,nominationId],
  );
  if (!row) throw new Error("That open reading nomination was not found in this server.");
}

export async function selectNextReading(
  guildId: string,
  nominationId?: string,
): Promise<ReadingNomination> {
  return transaction(async (client: PoolClient) => {
    const locked = await client.query(
      `SELECT id FROM community_reading_nominations
        WHERE guild_id = $1 AND status = 'open'
        ORDER BY created_at ASC FOR UPDATE`,
      [guildId],
    );
    if (!locked.rowCount) throw new Error("There are no open reading nominations in this server.");
    const winner = nominationId
      ? await client.query(
          `SELECT n.*,COUNT(v.user_id)::INT AS vote_count
             FROM community_reading_nominations n
             LEFT JOIN community_reading_votes v
               ON v.guild_id = n.guild_id AND v.nomination_id = n.id
            WHERE n.guild_id = $1 AND n.id = $2 AND n.status = 'open'
            GROUP BY n.id`,
          [guildId,nominationId],
        )
      : await client.query(
          `SELECT n.*,COUNT(v.user_id)::INT AS vote_count
             FROM community_reading_nominations n
             LEFT JOIN community_reading_votes v
               ON v.guild_id = n.guild_id AND v.nomination_id = n.id
            WHERE n.guild_id = $1 AND n.status = 'open'
            GROUP BY n.id
            ORDER BY COUNT(v.user_id) DESC,n.created_at ASC LIMIT 1`,
          [guildId],
        );
    const selected = winner.rows[0] as ReadingNomination | undefined;
    if (!selected) throw new Error("That open reading nomination was not found in this server.");
    await client.query(
      `UPDATE community_reading_nominations
          SET status = CASE WHEN id = $1 THEN 'selected' ELSE 'closed' END
        WHERE guild_id = $2 AND status = 'open'`,
      [selected.id,guildId],
    );
    return selected;
  });
}

export async function attachReadingDiscussion(input: {
  guildId: string;
  nominationId: string;
  channelId: string;
  threadId: string;
  scheduledAt: Date;
}): Promise<void> {
  const updated = await queryOne<{ id: string }>(
    `UPDATE community_reading_nominations
        SET channel_id = $1,thread_id = $2,scheduled_at = $3,reminder_sent = FALSE,
            last_reminder_attempt_at = NULL
      WHERE guild_id = $4 AND id = $5 AND status = 'selected'
      RETURNING id`,
    [input.channelId,input.threadId,input.scheduledAt,input.guildId,input.nominationId],
  );
  if (!updated) throw new Error("The selected reading changed before its discussion could be scheduled.");
}

export async function claimDueReadingReminders(): Promise<Array<{
  guild_id: string;
  nomination_id: string;
  thread_id: string;
  title: string;
  scheduled_at: Date;
}>> {
  return transaction(async (client: PoolClient) => {
    const due = await client.query(
      `SELECT guild_id,id AS nomination_id,thread_id,title,scheduled_at
         FROM community_reading_nominations
        WHERE status = 'selected' AND thread_id IS NOT NULL AND scheduled_at <= NOW()
          AND reminder_sent = FALSE
          AND (last_reminder_attempt_at IS NULL OR last_reminder_attempt_at < NOW() - INTERVAL '5 minutes')
        ORDER BY scheduled_at ASC LIMIT 20 FOR UPDATE SKIP LOCKED`,
    );
    const rows = due.rows as Array<{ guild_id: string; nomination_id: string; thread_id: string; title: string; scheduled_at: Date }>;
    for (const row of rows) {
      await client.query(
        "UPDATE community_reading_nominations SET last_reminder_attempt_at = NOW() WHERE guild_id = $1 AND id = $2",
        [row.guild_id,row.nomination_id],
      );
    }
    return rows;
  });
}

export async function markReadingReminderSent(guildId: string, nominationId: string): Promise<void> {
  await query(
    "UPDATE community_reading_nominations SET reminder_sent = TRUE WHERE guild_id = $1 AND id = $2 AND status = 'selected'",
    [guildId,nominationId],
  );
}
