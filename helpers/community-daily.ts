import type { PoolClient } from "pg";
import { query, queryOne, transaction } from "../database.js";
import { cleanText, isValidHttpsUrl } from "./security.js";
import type { DailyFormat, DailySchedule } from "./community.js";

const DAILY_FORMATS = new Set<DailyFormat>(["question", "quote", "trivia", "recommendation", "archive_spotlight", "mystery"]);

function localParts(date: Date, timeZone: string): { date: string; time: string } {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return {
    date: `${values.year}-${values.month}-${values.day}`,
    time: `${values.hour}:${values.minute}`,
  };
}

export function nextLocalOccurrence(timeZone: string, localTime: string, after = new Date()): Date {
  try {
    new Intl.DateTimeFormat("en-US", { timeZone }).format(after);
  } catch {
    throw new Error("Enter a valid IANA timezone such as Europe/Dublin or America/New_York.");
  }
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(localTime)) {
    throw new Error("Enter the daily schedule time as HH:MM in 24-hour format.");
  }
  const start = Math.floor(after.getTime() / 60_000) * 60_000 + 60_000;
  // Find the next actual local minute. This naturally follows DST transitions.
  for (let minute = 0; minute < 72 * 60; minute += 1) {
    const candidate = new Date(start + minute * 60_000);
    if (localParts(candidate, timeZone).time === localTime) return candidate;
  }
  throw new Error("Could not find the next local schedule time.");
}

export async function saveDailySchedule(
  guildId: string,
  actorId: string,
  channelId: string,
  timeZone: string,
  localTime: string,
  format: DailyFormat,
): Promise<Date> {
  if (!DAILY_FORMATS.has(format)) throw new Error("Choose a supported Daily Drop format.");
  const nextRunAt = nextLocalOccurrence(timeZone, localTime);
  await query(
    `INSERT INTO community_daily_schedules
     (guild_id, channel_id, time_zone, local_time, format, enabled, next_run_at, created_by, updated_at)
     VALUES ($1, $2, $3, $4, $5, TRUE, $6, $7, NOW())
     ON CONFLICT (guild_id) DO UPDATE SET
       channel_id = EXCLUDED.channel_id,
       time_zone = EXCLUDED.time_zone,
       local_time = EXCLUDED.local_time,
       format = EXCLUDED.format,
       enabled = TRUE,
       next_run_at = EXCLUDED.next_run_at,
       created_by = EXCLUDED.created_by,
       updated_at = NOW()`,
    [guildId, channelId, timeZone, localTime, format, nextRunAt, actorId],
  );
  return nextRunAt;
}

export async function disableDailySchedule(guildId: string): Promise<void> {
  await query("UPDATE community_daily_schedules SET enabled = FALSE, updated_at = NOW() WHERE guild_id = $1", [guildId]);
}

export async function submitDailyItem(
  guildId: string,
  userId: string,
  format: DailyFormat,
  title: string,
  content: string,
  sourceUrl?: string,
): Promise<string> {
  if (!DAILY_FORMATS.has(format) || format === "archive_spotlight") {
    throw new Error("Choose a contributor-written prompt, question, quote, trivia item, recommendation or mystery clue.");
  }
  const cleanTitle = cleanText(title, 200);
  const body = content.trim();
  if (!cleanTitle || !body) throw new Error("A title and content are required.");
  if (body.length > 1_500) throw new Error("Daily Drop content is limited to 1,500 characters.");
  if (format === "quote" && body.length > 280) {
    throw new Error("Quotes are limited to 280 characters. Do not submit lyrics, chapters or long copyrighted passages.");
  }
  const link = isValidHttpsUrl(sourceUrl);
  const row = await queryOne<{ id: string }>(
    `INSERT INTO community_daily_items (guild_id, format, title, content, source_url, created_by, status)
     VALUES ($1, $2, $3, $4, $5, $6, 'pending') RETURNING id`,
    [guildId, format, cleanTitle, body, link, userId],
  );
  if (!row) throw new Error("The Daily Drop submission could not be saved.");
  return row.id;
}

export async function reviewDailyItem(
  guildId: string,
  itemId: string,
  reviewerId: string,
  approve: boolean,
): Promise<void> {
  const changed = await queryOne<{ id: string }>(
    `UPDATE community_daily_items SET status = $1, reviewed_by = $2
     WHERE id = $3 AND guild_id = $4 AND status = 'pending' RETURNING id`,
    [approve ? "approved" : "rejected", reviewerId, itemId, guildId],
  );
  if (!changed) throw new Error("That pending Daily Drop item was not found in this server.");
}

export async function dueDailySchedules(): Promise<DailySchedule[]> {
  return query<DailySchedule>(
    `SELECT guild_id, channel_id, time_zone, local_time, format, enabled, next_run_at
     FROM community_daily_schedules
     WHERE enabled = TRUE AND next_run_at <= NOW()
     ORDER BY next_run_at ASC LIMIT 50`,
  );
}

export async function prepareDailyDelivery(schedule: DailySchedule): Promise<{ deliveryId: string; itemId: string; title: string; content: string; sourceUrl: string | null } | null> {
  return transaction(async (client: PoolClient) => {
    const lock = await client.query(
      `SELECT * FROM community_daily_schedules
       WHERE guild_id = $1 AND enabled = TRUE AND next_run_at <= NOW()
       FOR UPDATE SKIP LOCKED`,
      [schedule.guild_id],
    );
    const current = lock.rows[0] as DailySchedule | undefined;
    if (!current) return null;

    const existing = await client.query(
      "SELECT id FROM community_daily_deliveries WHERE guild_id = $1 AND scheduled_for = $2",
      [schedule.guild_id, current.next_run_at],
    );
    if (existing.rowCount) {
      const next = nextLocalOccurrence(current.time_zone, current.local_time, new Date(current.next_run_at));
      await client.query("UPDATE community_daily_schedules SET next_run_at = $1 WHERE guild_id = $2", [next, current.guild_id]);
      return null;
    }

    const itemResult = current.format === "archive_spotlight"
      ? await client.query(
          `SELECT id, title, content, source_url FROM community_daily_items
           WHERE guild_id = $1 AND status = 'approved'
           ORDER BY RANDOM() LIMIT 1`,
          [current.guild_id],
        )
      : await client.query(
          `SELECT id, title, content, source_url FROM community_daily_items
           WHERE guild_id = $1 AND status = 'approved' AND format = $2
           ORDER BY created_at DESC LIMIT 1`,
          [current.guild_id, current.format],
        );
    const item = itemResult.rows[0] as { id: string; title: string; content: string; source_url: string | null } | undefined;

    let selected = item;
    if (!selected && current.format === "archive_spotlight") {
      const archive = await client.query(
        `SELECT id, title, content, source_url, created_by FROM community_archive_entries
         WHERE created_guild_id = $1 AND visibility = 'server' AND status = 'approved'
           AND id NOT IN (
             SELECT item_id FROM community_daily_deliveries
             WHERE guild_id = $1 AND item_id IS NOT NULL AND created_at > NOW() - INTERVAL '30 days'
           )
         ORDER BY RANDOM() LIMIT 1`,
        [current.guild_id],
      );
      const row = archive.rows[0] as { id: string; title: string; content: string; source_url: string | null; created_by: string } | undefined;
      if (row) {
        const created = await client.query(
          `INSERT INTO community_daily_items (guild_id, format, title, content, source_url, created_by, status)
           VALUES ($1, 'archive_spotlight', $2, $3, $4, $5, 'approved') RETURNING id`,
          [current.guild_id, row.title, row.content, row.source_url, row.created_by],
        );
        selected = created.rows[0] ? { ...row, id: (created.rows[0] as { id: string }).id } : undefined;
      }
    }

    const scheduledFor = new Date(current.next_run_at);
    const next = nextLocalOccurrence(current.time_zone, current.local_time, scheduledFor);
    await client.query(
      "UPDATE community_daily_schedules SET next_run_at = $1 WHERE guild_id = $2",
      [next, current.guild_id],
    );
    if (!selected) return null;

    const delivery = await client.query(
      `INSERT INTO community_daily_deliveries
       (guild_id, scheduled_for, channel_id, item_id, status, attempts, next_attempt_at)
       VALUES ($1, $2, $3, $4, 'pending', 0, NOW())
       ON CONFLICT (guild_id, scheduled_for) DO NOTHING RETURNING id`,
      [current.guild_id, scheduledFor, current.channel_id, selected.id],
    );
    if (!delivery.rows[0]) return null;
    return {
      deliveryId: String((delivery.rows[0] as { id: string }).id),
      itemId: selected.id,
      title: selected.title,
      content: selected.content,
      sourceUrl: selected.source_url,
    };
  });
}

export async function dueDailyDeliveries(): Promise<Array<{
  id: string; guild_id: string; channel_id: string; item_id: string; title: string; content: string; source_url: string | null;
}>> {
  return query(
    `SELECT d.id, d.guild_id, d.channel_id, d.item_id, i.title, i.content, i.source_url
     FROM community_daily_deliveries d
     JOIN community_daily_items i ON i.id = d.item_id
     WHERE d.status = 'pending' AND d.next_attempt_at <= NOW()
     ORDER BY d.created_at ASC LIMIT 20`,
  );
}

export async function markDailyDelivery(
  deliveryId: string,
  status: "sent" | "pending",
  messageId?: string,
  error?: string,
): Promise<void> {
  await query(
    `UPDATE community_daily_deliveries
     SET status = $1, message_id = COALESCE($2, message_id),
         attempts = attempts + 1,
         last_error = $3,
         next_attempt_at = CASE WHEN $1 = 'pending' THEN NOW() + LEAST(attempts + 1, 10) * INTERVAL '1 minute' ELSE next_attempt_at END
     WHERE id = $4 AND status = 'pending'`,
    [status, messageId ?? null, error ? cleanText(error, 500) : null, deliveryId],
  );
}
