import type { PoolClient } from "pg";
import { query, queryOne, transaction } from "../database.js";
import { AniListClient } from "./anilist.js";
import { TmdbClient } from "./tmdb.js";
import { cleanText, isValidHttpsUrl } from "./security.js";

export type DailyFormat = "question" | "quote" | "trivia" | "recommendation" | "archive_spotlight" | "mystery";
export type CommunityActivity = "watch" | "read" | "play" | "discuss";

export interface DailySchedule {
  guild_id: string;
  channel_id: string;
  time_zone: string;
  local_time: string;
  format: DailyFormat;
  enabled: boolean;
  next_run_at: Date;
}

export interface CommunitySession {
  id: string;
  guild_id: string;
  channel_id: string;
  creator_id: string;
  host_id: string;
  title: string;
  description: string;
  activity_type: CommunityActivity;
  media_title: string | null;
  media_url: string | null;
  scheduled_at: Date;
  capacity: number | null;
  status: string;
  thread_id: string | null;
  scheduled_event_id: string | null;
}

const DAILY_FORMATS = new Set<DailyFormat>(["question", "quote", "trivia", "recommendation", "archive_spotlight", "mystery"]);
const ACTIVITY_TYPES = new Set<CommunityActivity>(["watch", "read", "play", "discuss"]);

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

export async function createRanking(guildId: string, creatorId: string, title: string, description: string, closesAt: Date | null): Promise<string> {
  const row = await queryOne<{ id: string }>(
    `INSERT INTO community_rankings (guild_id, creator_id, title, description, status, closes_at)
     VALUES ($1, $2, $3, $4, 'open', $5) RETURNING id`,
    [guildId, creatorId, cleanText(title, 180), cleanText(description, 1_000), closesAt],
  );
  if (!row) throw new Error("The ranking could not be created.");
  return row.id;
}

export async function addRankingCandidate(
  guildId: string,
  rankingId: string,
  submittedBy: string,
  title: string,
  sourceUrl?: string,
): Promise<string> {
  const ranking = await queryOne<{ id: string }>(
    "SELECT id FROM community_rankings WHERE id = $1 AND guild_id = $2 AND status = 'open'",
    [rankingId, guildId],
  );
  if (!ranking) throw new Error("That open ranking was not found in this server.");
  const url = isValidHttpsUrl(sourceUrl);
  const row = await queryOne<{ id: string }>(
    `INSERT INTO community_ranking_candidates (ranking_id, title, source_url, submitted_by, status)
     VALUES ($1, $2, $3, $4, 'pending') RETURNING id`,
    [rankingId, cleanText(title, 200), url, submittedBy],
  );
  if (!row) throw new Error("The candidate could not be saved.");
  return row.id;
}

export async function reviewRankingCandidate(guildId: string, candidateId: string, approve: boolean): Promise<void> {
  const changed = await queryOne<{ id: string }>(
    `UPDATE community_ranking_candidates c SET status = $1
     FROM community_rankings r
     WHERE c.ranking_id = r.id AND r.guild_id = $2 AND c.id = $3 AND r.status = 'open'
       AND c.status = 'pending' RETURNING c.id`,
    [approve ? "approved" : "rejected", guildId, candidateId],
  );
  if (!changed) throw new Error("That pending candidate was not found.");
}

export async function voteForRanking(guildId: string, userId: string, rankingId: string, candidateId: string): Promise<void> {
  await transaction(async (client) => {
    const ranking = await client.query(
      "SELECT id, closes_at FROM community_rankings WHERE id = $1 AND guild_id = $2 AND status = 'open' FOR UPDATE",
      [rankingId, guildId],
    );
    const row = ranking.rows[0] as { id: string; closes_at: Date | null } | undefined;
    if (!row || (row.closes_at && row.closes_at.getTime() <= Date.now())) throw new Error("That ranking is closed.");
    const candidate = await client.query(
      `SELECT id FROM community_ranking_candidates
       WHERE id = $1 AND ranking_id = $2 AND status = 'approved'`,
      [candidateId, rankingId],
    );
    if (!candidate.rowCount) throw new Error("That approved candidate does not belong to this ranking.");
    await client.query(
      `INSERT INTO community_ranking_votes (ranking_id, user_id, candidate_id)
       VALUES ($1, $2, $3)
       ON CONFLICT (ranking_id, user_id) DO UPDATE SET candidate_id = EXCLUDED.candidate_id, updated_at = NOW()`,
      [rankingId, userId, candidateId],
    );
  });
}

export async function closeRanking(guildId: string, rankingId: string, actorId: string, isManager: boolean): Promise<void> {
  const ranking = await queryOne<{ creator_id: string }>(
    "SELECT creator_id FROM community_rankings WHERE id = $1 AND guild_id = $2 AND status = 'open'",
    [rankingId, guildId],
  );
  if (!ranking) throw new Error("That open ranking was not found.");
  if (ranking.creator_id !== actorId && !isManager) throw new Error("Only the ranking creator or a server manager can close it.");
  await query("UPDATE community_rankings SET status = 'closed', closed_at = NOW() WHERE id = $1 AND guild_id = $2 AND status = 'open'", [rankingId, guildId]);
}

export async function rankingResults(guildId: string, rankingId: string): Promise<Array<{ id: string; title: string; votes: number }>> {
  return query(
    `SELECT c.id, c.title, COUNT(v.user_id)::INT AS votes
     FROM community_rankings r
     JOIN community_ranking_candidates c ON c.ranking_id = r.id AND c.status = 'approved'
     LEFT JOIN community_ranking_votes v ON v.candidate_id = c.id AND v.ranking_id = r.id
     WHERE r.id = $1 AND r.guild_id = $2
     GROUP BY c.id ORDER BY votes DESC, c.created_at ASC LIMIT 25`,
    [rankingId, guildId],
  );
}

export async function createCommunitySession(input: {
  guildId: string; channelId: string; creatorId: string; title: string; description: string;
  activity: CommunityActivity; mediaTitle?: string; mediaUrl?: string; scheduledAt: Date; capacity?: number;
}): Promise<string> {
  if (!ACTIVITY_TYPES.has(input.activity)) throw new Error("Choose Watch, Read, Play or Discuss.");
  if (input.scheduledAt.getTime() <= Date.now()) throw new Error("The session must be scheduled for a future date.");
  const url = isValidHttpsUrl(input.mediaUrl);
  const row = await queryOne<{ id: string }>(
    `INSERT INTO community_sessions
     (guild_id, channel_id, creator_id, host_id, title, description, activity_type, media_title, media_url, scheduled_at, capacity)
     VALUES ($1, $2, $3, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING id`,
    [
      input.guildId, input.channelId, input.creatorId, cleanText(input.title, 180),
      cleanText(input.description, 1_000), input.activity,
      input.mediaTitle ? cleanText(input.mediaTitle, 200) : null,
      url, input.scheduledAt, input.capacity ?? null,
    ],
  );
  if (!row) throw new Error("The session could not be scheduled.");
  return row.id;
}

export async function setSessionRsvp(
  guildId: string,
  sessionId: string,
  userId: string,
  attending: boolean,
): Promise<"going" | "waitlist" | "cancelled"> {
  return transaction(async (client) => {
    const result = await client.query(
      "SELECT id, capacity, status FROM community_sessions WHERE id = $1 AND guild_id = $2 FOR UPDATE",
      [sessionId, guildId],
    );
    const session = result.rows[0] as { id: string; capacity: number | null; status: string } | undefined;
    if (!session || !["scheduled", "open"].includes(session.status)) throw new Error("That session is not open for RSVP.");
    if (!attending) {
      await client.query(
        "UPDATE community_session_rsvps SET status = 'cancelled', updated_at = NOW() WHERE session_id = $1 AND user_id = $2 AND status IN ('going','waitlist')",
        [sessionId, userId],
      );
      if (session.capacity) {
        const next = await client.query(
          `SELECT user_id FROM community_session_rsvps
           WHERE session_id = $1 AND status = 'waitlist'
           ORDER BY updated_at ASC LIMIT 1 FOR UPDATE`,
          [sessionId],
        );
        if (next.rows[0]) {
          await client.query(
            "UPDATE community_session_rsvps SET status = 'going', updated_at = NOW() WHERE session_id = $1 AND user_id = $2",
            [sessionId, (next.rows[0] as { user_id: string }).user_id],
          );
        }
      }
      return "cancelled";
    }
    const existing = await client.query(
      "SELECT status FROM community_session_rsvps WHERE session_id = $1 AND user_id = $2",
      [sessionId, userId],
    );
    if (existing.rows[0] && (existing.rows[0] as { status: string }).status === "going") return "going";
    const count = await client.query(
      "SELECT COUNT(*)::INT AS count FROM community_session_rsvps WHERE session_id = $1 AND status = 'going'",
      [sessionId],
    );
    const full = session.capacity !== null && Number((count.rows[0] as { count: number }).count) >= session.capacity;
    const status = full ? "waitlist" : "going";
    await client.query(
      `INSERT INTO community_session_rsvps (session_id, user_id, status)
       VALUES ($1, $2, $3)
       ON CONFLICT (session_id, user_id) DO UPDATE SET status = EXCLUDED.status, updated_at = NOW()`,
      [sessionId, userId, status],
    );
    return status;
  });
}

export async function getCommunitySession(guildId: string, sessionId: string): Promise<CommunitySession | null> {
  return queryOne<CommunitySession>("SELECT * FROM community_sessions WHERE id = $1 AND guild_id = $2", [sessionId, guildId]);
}

export async function createSpoilerDiscussion(input: {
  guildId: string; channelId: string; creatorId: string; title: string; prompt: string;
  mediaTitle?: string; mediaUrl?: string; spoilerBoundary?: string; spoilerWarning?: string; closesAt?: Date;
}): Promise<string> {
  const url = isValidHttpsUrl(input.mediaUrl);
  const row = await queryOne<{ id: string }>(
    `INSERT INTO community_discussions
     (guild_id, channel_id, creator_id, title, prompt, media_title, media_url, spoiler_boundary, spoiler_warning, closes_at)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING id`,
    [
      input.guildId, input.channelId, input.creatorId, cleanText(input.title, 180),
      cleanText(input.prompt, 1_500), input.mediaTitle ? cleanText(input.mediaTitle, 200) : null,
      url, input.spoilerBoundary ? cleanText(input.spoilerBoundary, 120) : null,
      cleanText(input.spoilerWarning, 500), input.closesAt ?? null,
    ],
  );
  if (!row) throw new Error("The discussion could not be created.");
  return row.id;
}

export async function closeDiscussion(guildId: string, discussionId: string, actorId: string, isManager: boolean): Promise<string | null> {
  const row = await queryOne<{ creator_id: string; thread_id: string | null }>(
    "SELECT creator_id, thread_id FROM community_discussions WHERE id = $1 AND guild_id = $2 AND status = 'open'",
    [discussionId, guildId],
  );
  if (!row) throw new Error("That open discussion was not found.");
  if (row.creator_id !== actorId && !isManager) throw new Error("Only the discussion creator or a server manager can close it.");
  await query("UPDATE community_discussions SET status = 'closed' WHERE id = $1 AND guild_id = $2", [discussionId, guildId]);
  return row.thread_id;
}

export async function listUpcomingSessions(guildId: string): Promise<CommunitySession[]> {
  return query<CommunitySession>(
    `SELECT * FROM community_sessions WHERE guild_id = $1 AND status IN ('scheduled','open')
     AND scheduled_at >= NOW() ORDER BY scheduled_at ASC LIMIT 15`,
    [guildId],
  );
}

export async function getCommunityHistory(guildId: string): Promise<{
  closedRankings: Array<{ id: string; title: string; closed_at: Date | null }>;
  pastSessions: Array<{ id: string; title: string; activity_type: string; scheduled_at: Date }>;
  discussions: Array<{ id: string; title: string; status: string; created_at: Date }>;
}> {
  const [closedRankings, pastSessions, discussions] = await Promise.all([
    query("SELECT id, title, closed_at FROM community_rankings WHERE guild_id = $1 AND status = 'closed' ORDER BY closed_at DESC LIMIT 5", [guildId]),
    query("SELECT id, title, activity_type, scheduled_at FROM community_sessions WHERE guild_id = $1 AND scheduled_at < NOW() ORDER BY scheduled_at DESC LIMIT 5", [guildId]),
    query("SELECT id, title, status, created_at FROM community_discussions WHERE guild_id = $1 ORDER BY created_at DESC LIMIT 5", [guildId]),
  ]);
  return { closedRankings, pastSessions, discussions };
}

export async function upcomingProviderReleases(
  anilist: AniListClient,
  tmdb: TmdbClient,
  from: Date,
  to: Date,
): Promise<Array<{ title: string; when: Date; provider: string; url: string }>> {
  const [airings, movies] = await Promise.allSettled([
    anilist.upcomingAirings(from, to),
    tmdb.upcomingMovies(),
  ]);
  const results: Array<{ title: string; when: Date; provider: string; url: string }> = [];
  if (airings.status === "fulfilled") {
    for (const airing of airings.value) {
      const when = new Date(airing.airingAt * 1000);
      if (when >= from && when <= to) {
        results.push({ title: `${airing.title} · Episode ${airing.episode}`, when, provider: "AniList", url: airing.url });
      }
    }
  }
  if (movies.status === "fulfilled") {
    for (const movie of movies.value) {
      if (!movie.releaseDate) continue;
      const when = new Date(`${movie.releaseDate}T00:00:00.000Z`);
      if (when >= from && when <= to) results.push({ title: movie.title, when, provider: "TMDB", url: movie.sourceUrl });
    }
  }
  return results.sort((a, b) => a.when.getTime() - b.when.getTime()).slice(0, 20);
}

export function formatActivity(activity: CommunityActivity): string {
  return activity[0]!.toUpperCase() + activity.slice(1);
}
