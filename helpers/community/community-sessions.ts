import { query, queryOne, transaction } from "../../src/utility/database/libsql/database.js";
import { AniListClient } from "../integration/anilist.js";
import { TmdbClient } from "../integration/tmdb.js";
import { IgdbClient } from "../integration/igdb.js";
import { cleanText, isValidHttpsUrl } from "../security/security.js";
import type { CommunityActivity, CommunitySession } from "./community.js";

const ACTIVITY_TYPES = new Set<CommunityActivity>(["watch", "read", "play", "discuss"]);

export interface CommunitySessionNomination {
  id: string;
  guild_id: string;
  channel_id: string;
  proposer_id: string;
  title: string;
  description: string;
  activity_type: CommunityActivity;
  media_title: string | null;
  media_url: string | null;
  scheduled_at: Date;
  capacity: number | null;
  created_at: Date;
}

export interface NormalizedSessionNomination {
  title: string;
  description: string;
  activity: CommunityActivity;
  mediaTitle: string | null;
  mediaUrl: string | null;
  scheduledAt: Date;
  capacity: number | null;
}

export function normalizeCommunitySessionNomination(input: {
  title: string;
  description: string;
  activity: string;
  mediaTitle?: string;
  mediaUrl?: string;
  scheduledAt: Date;
  capacity?: number | null;
}): NormalizedSessionNomination {
  const title = cleanText(input.title, 180);
  if (!title) throw new Error("A session nomination needs a title.");
  if (!ACTIVITY_TYPES.has(input.activity as CommunityActivity)) throw new Error("Choose Watch, Read, Play or Discuss.");
  if (!Number.isFinite(input.scheduledAt.getTime()) || input.scheduledAt.getTime() <= Date.now()) {
    throw new Error("A session nomination must have a future date and time.");
  }
  const capacity = input.capacity ?? null;
  if (capacity !== null && (!Number.isInteger(capacity) || capacity < 2 || capacity > 200)) {
    throw new Error("Session capacity must be between 2 and 200.");
  }
  const mediaUrl = input.mediaUrl ? isValidHttpsUrl(input.mediaUrl) : null;
  if (input.mediaUrl && !mediaUrl) throw new Error("The linked media URL must be HTTPS.");
  return {
    title,
    description: cleanText(input.description, 1_000),
    activity: input.activity as CommunityActivity,
    mediaTitle: input.mediaTitle ? cleanText(input.mediaTitle, 200) : null,
    mediaUrl,
    scheduledAt: input.scheduledAt,
    capacity,
  };
}

export async function submitCommunitySessionNomination(input: {
  guildId: string; channelId: string; proposerId: string; title: string; description: string;
  activity: string; mediaTitle?: string; mediaUrl?: string; scheduledAt: Date; capacity?: number | null;
}): Promise<string> {
  const normalized = normalizeCommunitySessionNomination(input);
  const row = await queryOne<{ id: string }>(
    "INSERT INTO community_session_nominations " +
    "(guild_id, channel_id, proposer_id, title, description, activity_type, media_title, media_url, scheduled_at, capacity) " +
    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING id::text AS id",
    [input.guildId, input.channelId, input.proposerId, normalized.title, normalized.description,
      normalized.activity, normalized.mediaTitle, normalized.mediaUrl, normalized.scheduledAt, normalized.capacity],
  );
  if (!row) throw new Error("The community session nomination could not be saved.");
  return row.id;
}

export async function listPendingCommunitySessionNominations(guildId: string): Promise<CommunitySessionNomination[]> {
  return query<CommunitySessionNomination>(
    "SELECT id::text, guild_id::text, channel_id::text, proposer_id::text, title, description, activity_type, " +
    "media_title, media_url, scheduled_at, capacity, created_at " +
    "FROM community_session_nominations WHERE guild_id = $1 AND status = 'pending' " +
    "ORDER BY created_at ASC LIMIT 10",
    [guildId],
  );
}

export async function reviewCommunitySessionNomination(
  guildId: string,
  nominationId: string,
  reviewerId: string,
  approve: boolean,
): Promise<{ status: "approved" | "rejected"; sessionId: string | null; channelId: string }> {
  return transaction(async client => {
    const result = await client.query<{
      id: string; guild_id: string; channel_id: string; proposer_id: string; title: string; description: string;
      activity_type: CommunityActivity; media_title: string | null; media_url: string | null;
      scheduled_at: Date; capacity: number | null;
    }>(
      "SELECT id::text, guild_id::text, channel_id::text, proposer_id::text, title, description, activity_type, " +
      "media_title, media_url, scheduled_at, capacity FROM community_session_nominations " +
      "WHERE id = $1 AND guild_id = $2 AND status = 'pending' FOR UPDATE",
      [nominationId, guildId],
    );
    const nomination = result.rows[0];
    if (!nomination) throw new Error("That pending session nomination was not found in this server.");
    if (!approve) {
      await client.query(
        "UPDATE community_session_nominations SET status = 'rejected', reviewed_by = $3, reviewed_at = NOW() WHERE id = $1 AND guild_id = $2",
        [nominationId, guildId, reviewerId],
      );
      return { status: "rejected", sessionId: null, channelId: nomination.channel_id };
    }
    const inserted = await client.query<{ id: string }>(
      "INSERT INTO community_sessions " +
      "(guild_id, channel_id, creator_id, host_id, title, description, activity_type, media_title, media_url, scheduled_at, capacity) " +
      "VALUES ($1,$2,$3,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING id::text AS id",
      [guildId, nomination.channel_id, nomination.proposer_id, nomination.title, nomination.description,
        nomination.activity_type, nomination.media_title, nomination.media_url, nomination.scheduled_at, nomination.capacity],
    );
    const sessionId = inserted.rows[0]?.id;
    if (!sessionId) throw new Error("The approved session could not be scheduled.");
    await client.query(
      "UPDATE community_session_nominations SET status = 'approved', reviewed_by = $3, reviewed_at = NOW(), session_id = $4 " +
      "WHERE id = $1 AND guild_id = $2 AND status = 'pending'",
      [nominationId, guildId, reviewerId, sessionId],
    );
    return { status: "approved", sessionId, channelId: nomination.channel_id };
  });
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


export interface UpcomingCommunitySession {
  id: string;
  title: string;
  channel_id: string;
  activity_type: CommunityActivity;
  scheduled_at: Date;
  media_url: string | null;
}

export type CommunityCalendarScope = "all" | "releases" | "community" | "anime" | "tv" | "movies" | "games";
export type CommunityCalendarCategory = "anime" | "tv" | "movies" | "games" | "community";

export interface CommunityCalendarEntry {
  title: string;
  when: Date;
  source: string;
  sourceUrl: string | null;
  channelId: string | null;
  kind: "release" | "community";
  category: CommunityCalendarCategory;
}

export function normalizeCommunityCalendarSelection(value: string): { days: 7 | 14 | 30; scope: CommunityCalendarScope } {
  const [rawDays, rawScope] = value.split("|");
  const days = Number(rawDays);
  const scopes = new Set<CommunityCalendarScope>(["all", "releases", "community", "anime", "tv", "movies", "games"]);
  return {
    days: days === 7 || days === 30 ? days : 14,
    scope: scopes.has(rawScope as CommunityCalendarScope) ? rawScope as CommunityCalendarScope : "all",
  };
}

export function formatCommunityCalendarTime(date: Date, timeZone: string): string {
  if (!Number.isFinite(date.getTime())) throw new Error("Calendar entries must contain valid dates.");
  try {
    return new Intl.DateTimeFormat("en-IE", {
      timeZone,
      weekday: "short",
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      timeZoneName: "short",
    }).format(date);
  } catch {
    throw new Error("The calendar timezone must be a valid IANA timezone.");
  }
}

export async function upcomingCommunitySessions(
  guildId: string,
  from: Date,
  to: Date,
): Promise<UpcomingCommunitySession[]> {
  if (!Number.isFinite(from.getTime()) || !Number.isFinite(to.getTime()) || from.getTime() > to.getTime()) {
    throw new Error("The community calendar window must contain valid dates in ascending order.");
  }
  return query<UpcomingCommunitySession>(
    `SELECT id::text, title, channel_id::text, activity_type, scheduled_at, media_url
     FROM community_sessions
     WHERE guild_id = $1 AND status IN ('scheduled','open')
       AND scheduled_at >= $2 AND scheduled_at <= $3
     ORDER BY scheduled_at ASC LIMIT 50`,
    [guildId, from, to],
  );
}

export function mergeCommunityCalendarEntries(
  providerEntries: readonly { title: string; when: Date; provider: string; url: string; category: "anime" | "tv" | "movies" | "games" }[],
  sessions: readonly UpcomingCommunitySession[],
): CommunityCalendarEntry[] {
  const entries: CommunityCalendarEntry[] = [
    ...providerEntries.map((item) => ({
      title: item.title,
      when: item.when,
      source: item.provider,
      sourceUrl: item.url,
      channelId: null,
      kind: "release" as const,
      category: item.category,
    })),
    ...sessions.map((session) => ({
      title: session.title,
      when: session.scheduled_at,
      source: "Community · " + formatActivity(session.activity_type),
      sourceUrl: session.media_url,
      channelId: session.channel_id,
      kind: "community" as const,
      category: "community" as const,
    })),
  ];
  return entries
    .filter((item) => Number.isFinite(item.when.getTime()))
    .sort((left, right) => left.when.getTime() - right.when.getTime())
    .slice(0, 100);
}

export function filterCommunityCalendarEntries(
  entries: readonly CommunityCalendarEntry[],
  scope: CommunityCalendarScope,
): CommunityCalendarEntry[] {
  if (scope === "all") return [...entries];
  if (scope === "releases") return entries.filter(item => item.kind === "release");
  if (scope === "community") return entries.filter(item => item.kind === "community");
  return entries.filter(item => item.kind === "release" && item.category === scope);
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

export interface ProviderReleaseCalendarResult {
  results: Array<{ title: string; when: Date; provider: string; url: string; category: "anime" | "tv" | "movies" | "games" }>;
  unavailableProviders: string[];
}

export async function upcomingProviderReleases(
  anilist: AniListClient,
  tmdb: TmdbClient,
  from: Date,
  to: Date,
  region = "IE",
  categories: readonly ("anime" | "tv" | "movies" | "games")[] = ["anime", "tv", "movies"],
  igdb?: IgdbClient,
): Promise<ProviderReleaseCalendarResult> {
  if (from.getTime() > to.getTime()) throw new Error("The release calendar start must be before its end.");
  const include = new Set(categories);
  const fromDay = from.toISOString().slice(0, 10);
  const toDay = to.toISOString().slice(0, 10);
  const requests = await Promise.allSettled([
    include.has("anime") ? anilist.upcomingAirings(from, to) : Promise.resolve([]),
    include.has("movies") ? tmdb.upcomingMovies(region) : Promise.resolve([]),
    include.has("tv") ? tmdb.upcomingTvEpisodes(from, to) : Promise.resolve([]),
    include.has("games") ? (igdb ? igdb.upcomingReleaseDates(from, to) : Promise.reject(new Error("IGDB is not configured for game release dates."))) : Promise.resolve([]),
  ]);
  const unavailableProviders: string[] = [];
  const airings = requests[0].status === "fulfilled" ? requests[0].value : (unavailableProviders.push("AniList"), []);
  const movies = requests[1].status === "fulfilled" ? requests[1].value : (unavailableProviders.push("TMDB Movies"), []);
  const episodes = requests[2].status === "fulfilled" ? requests[2].value : (unavailableProviders.push("TMDB TV"), []);
  const gameReleases = requests[3].status === "fulfilled" ? requests[3].value : (unavailableProviders.push("IGDB Game Releases"), []);
  const results: ProviderReleaseCalendarResult["results"] = [];
  for (const airing of airings) {
    const when = new Date(airing.airingAt * 1000);
    if (when >= from && when <= to) {
      results.push({ title: `${airing.title} · Episode ${airing.episode}`, when, provider: "AniList", url: airing.url, category: "anime" });
    }
  }
  for (const movie of movies) {
    if (!movie.releaseDate) continue;
    const when = new Date(`${movie.releaseDate}T00:00:00.000Z`);
    if (Number.isFinite(when.getTime()) && movie.releaseDate >= fromDay && movie.releaseDate <= toDay) {
      results.push({ title: movie.title, when, provider: `TMDB Movies · ${region.toUpperCase()}`, url: movie.sourceUrl, category: "movies" });
    }
  }
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
      category: "tv",
    });
  }
  for (const release of gameReleases) {
    results.push({
      title: release.title + (release.platform ? " · " + release.platform : ""),
      when: release.when,
      provider: "IGDB" + (release.region ? " · " + release.region : ""),
      url: release.sourceUrl,
      category: "games",
    });
  }
  return {
    results: results.sort((a, b) => a.when.getTime() - b.when.getTime()).slice(0, 50),
    unavailableProviders,
  };
}

export function formatActivity(activity: CommunityActivity): string {
  return activity[0]!.toUpperCase() + activity.slice(1);
}
