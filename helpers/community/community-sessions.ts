import { query, queryOne, transaction } from "../../database.js";
import { AniListClient } from "../providers/anilist.js";
import { TmdbClient } from "../providers/tmdb.js";
import { cleanText, isValidHttpsUrl } from "../security/security.js";
import type { CommunityActivity, CommunitySession } from "./community.js";

const ACTIVITY_TYPES = new Set<CommunityActivity>(["watch", "read", "play", "discuss"]);

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
    query<{ id: string; title: string; closed_at: Date | null }>("SELECT id, title, closed_at FROM community_rankings WHERE guild_id = $1 AND status = 'closed' ORDER BY closed_at DESC LIMIT 5", [guildId]),
    query<{ id: string; title: string; activity_type: string; scheduled_at: Date }>("SELECT id, title, activity_type, scheduled_at FROM community_sessions WHERE guild_id = $1 AND scheduled_at < NOW() ORDER BY scheduled_at DESC LIMIT 5", [guildId]),
    query<{ id: string; title: string; status: string; created_at: Date }>("SELECT id, title, status, created_at FROM community_discussions WHERE guild_id = $1 ORDER BY created_at DESC LIMIT 5", [guildId]),
  ]);
  return { closedRankings, pastSessions, discussions };
}

export async function upcomingProviderReleases(
  anilist: AniListClient,
  tmdb: TmdbClient,
  from: Date,
  to: Date,
  region = "IE",
  categories: readonly ("anime" | "tv" | "movies")[] = ["anime", "tv", "movies"],
): Promise<Array<{ title: string; when: Date; provider: string; url: string }>> {
  if (from.getTime() > to.getTime()) throw new Error("The release calendar start must be before its end.");
  const include = new Set(categories);
  const fromDay = from.toISOString().slice(0, 10);
  const toDay = to.toISOString().slice(0, 10);
  const requests = await Promise.all([
    include.has("anime") ? anilist.upcomingAirings(from, to) : Promise.resolve([]),
    include.has("movies") ? tmdb.upcomingMovies(region) : Promise.resolve([]),
    include.has("tv") ? tmdb.upcomingTvEpisodes(from, to) : Promise.resolve([]),
  ]);
  const results: Array<{ title: string; when: Date; provider: string; url: string }> = [];
  const airings = requests[0];
  {
    for (const airing of airings) {
      const when = new Date(airing.airingAt * 1000);
      if (when >= from && when <= to) {
        results.push({ title: `${airing.title} · Episode ${airing.episode}`, when, provider: "AniList", url: airing.url });
      }
    }
  }
  const movies = requests[1];
  {
    for (const movie of movies) {
      if (!movie.releaseDate) continue;
      const when = new Date(`${movie.releaseDate}T00:00:00.000Z`);
      if (Number.isFinite(when.getTime()) && movie.releaseDate >= fromDay && movie.releaseDate <= toDay) {
        results.push({ title: movie.title, when, provider: `TMDB Movies · ${region.toUpperCase()}`, url: movie.sourceUrl });
      }
    }
  }
  const episodes = requests[2];
  {
    for (const release of episodes) {
      const airDate = release.episode.airDate;
      if (!airDate || airDate < fromDay || airDate > toDay) continue;
      const when = new Date(`${airDate}T00:00:00.000Z`);
      if (!Number.isFinite(when.getTime())) continue;
      results.push({
        title: `${release.showTitle} · S${release.episode.seasonNumber ?? "?"} E${release.episode.episodeNumber} · ${release.episode.name}`,
        when,
        provider: "TMDB TV",
        url: release.episode.sourceUrl,
      });
    }
  }
  return results.sort((a, b) => a.when.getTime() - b.when.getTime()).slice(0, 30);
}

export function formatActivity(activity: CommunityActivity): string {
  return activity[0]!.toUpperCase() + activity.slice(1);
}
