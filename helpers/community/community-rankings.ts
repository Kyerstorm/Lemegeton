import { query, queryOne, transaction } from "../../database.js";
import { cleanText, isValidHttpsUrl } from "../security/security.js";
import { secureRandBelow } from "../security/crypto-random.js";
import type { AniListMediaNightCandidate } from "../integration/anilist.js";

export type MediaNightMood = "all" | "cozy" | "comedy" | "adventure" | "mystery" | "romance" | "drama";

const UNSUITABLE_MEDIA_TAGS = new Set([
  "adult", "ecchi", "erotica", "explicit", "gore", "hentai", "incest",
  "nudity", "nsfw", "pornographic", "rape", "sexual assault", "sexual violence",
]);

const MOOD_TERMS: Record<Exclude<MediaNightMood, "all">, string[]> = {
  cozy: ["slice of life", "iyashikei", "healing", "food"],
  comedy: ["comedy", "parody", "gag humor", "お笑い"],
  adventure: ["adventure", "travel", "survival", "action", "exploration"],
  mystery: ["mystery", "detective", "crime", "thriller", "suspense"],
  romance: ["romance", "romantic", "love"],
  drama: ["drama", "coming of age", "psychological"],
};

export function filterMediaNightCandidates(
  candidates: readonly AniListMediaNightCandidate[],
  mood: MediaNightMood,
): AniListMediaNightCandidate[] {
  return candidates.filter((candidate) => {
    const tags = candidate.tags.map((tag) => tag.trim().toLowerCase());
    if (tags.some((tag) => UNSUITABLE_MEDIA_TAGS.has(tag))) return false;
    if (mood === "all") return true;
    const metadata = [...candidate.genres, ...candidate.tags].map((item) => item.toLowerCase());
    return MOOD_TERMS[mood].some((term) => metadata.some((item) => item.includes(term)));
  });
}

export function sampleMediaNightCandidates(
  candidates: readonly AniListMediaNightCandidate[],
  count = 5,
): AniListMediaNightCandidate[] {
  const pool = [...candidates];
  const size = Math.min(Math.max(0, Math.floor(count)), pool.length);
  for (let index = 0; index < size; index += 1) {
    const selected = index + secureRandBelow(pool.length - index);
    [pool[index], pool[selected]] = [pool[selected]!, pool[index]!];
  }
  return pool.slice(0, size);
}

export async function createMediaNight(input: {
  guildId: string;
  channelId: string;
  creatorId: string;
  title: string;
  description: string;
  closesAt: Date;
  candidates: readonly AniListMediaNightCandidate[];
}): Promise<{ id: string; candidates: Array<{ id: string; title: string; url: string; year: number | null }> }> {
  if (input.closesAt.getTime() <= Date.now()) throw new Error("Media Night must end in the future.");
  const candidates = input.candidates.slice(0, 5);
  if (candidates.length < 2) throw new Error("Media Night needs at least two distinct provider-backed candidates.");
  const unique = new Map(candidates.map((item) => [item.title.trim().toLowerCase(), item]));
  if (unique.size < 2) throw new Error("Media Night candidates must have distinct titles.");
  return transaction(async (client) => {
    const session = await client.query<{ id: string }>(
      `INSERT INTO community_rankings
       (guild_id, creator_id, title, description, status, closes_at, kind, allow_vote_changes, channel_id)
       VALUES ($1, $2, $3, $4, 'open', $5, 'media_night', FALSE, $6) RETURNING id::text`,
      [input.guildId, input.creatorId, cleanText(input.title, 180), cleanText(input.description, 1_000), input.closesAt, input.channelId],
    );
    const rankingId = session.rows[0]?.id;
    if (!rankingId) throw new Error("The Media Night session could not be created.");
    const insertedCandidates: Array<{ id: string; title: string; url: string; year: number | null }> = [];
    for (const candidate of unique.values()) {
      const url = isValidHttpsUrl(candidate.url);
      if (!url || !url.startsWith("https://anilist.co/")) throw new Error("A Media Night candidate did not have a trusted AniList source.");
      const inserted = await client.query<{ id: string }>(
        `INSERT INTO community_ranking_candidates (ranking_id, title, source_url, submitted_by, status)
         VALUES ($1, $2, $3, $4, 'approved') RETURNING id::text`,
        [rankingId, cleanText(candidate.title, 200), url, input.creatorId],
      );
      const candidateId = inserted.rows[0]?.id;
      if (!candidateId) throw new Error("A Media Night candidate could not be saved.");
      insertedCandidates.push({ id: candidateId, title: cleanText(candidate.title, 200), url, year: candidate.year });
    }
    return { id: rankingId, candidates: insertedCandidates };
  });
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
      "SELECT id, closes_at, allow_vote_changes FROM community_rankings WHERE id = $1 AND guild_id = $2 AND status = 'open' FOR UPDATE",
      [rankingId, guildId],
    );
    const row = ranking.rows[0] as { id: string; closes_at: Date | null; allow_vote_changes: boolean } | undefined;
    if (!row || (row.closes_at && new Date(row.closes_at).getTime() <= Date.now())) throw new Error("That ranking is closed.");
    const candidate = await client.query(
      `SELECT id FROM community_ranking_candidates
       WHERE id = $1 AND ranking_id = $2 AND status = 'approved'`,
      [candidateId, rankingId],
    );
    if (!candidate.rowCount) throw new Error("That approved candidate does not belong to this ranking.");
    if (!row.allow_vote_changes) {
      const existing = await client.query(
        "SELECT candidate_id FROM community_ranking_votes WHERE ranking_id = $1 AND user_id = $2",
        [rankingId, userId],
      );
      const previous = existing.rows[0] as { candidate_id: string } | undefined;
      if (previous) {
        if (String(previous.candidate_id) !== candidateId) throw new Error("Your Media Night vote is locked and cannot be changed.");
        return;
      }
    }
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


export async function claimDueMediaNightResults(): Promise<Array<{
  id: string;
  guild_id: string;
  channel_id: string;
  title: string;
}>> {
  return transaction(async (client) => {
    await client.query(
      `UPDATE community_rankings
         SET status = 'closed', closed_at = COALESCE(closed_at, NOW())
       WHERE kind = 'media_night' AND status = 'open' AND closes_at <= NOW()`,
    );
    const due = await client.query<{ id: string; guild_id: string; channel_id: string; title: string }>(
      `SELECT id::text, guild_id::text, channel_id::text, title
         FROM community_rankings
        WHERE kind = 'media_night' AND status = 'closed' AND channel_id IS NOT NULL
          AND results_sent_at IS NULL
          AND (results_next_attempt_at IS NULL OR results_next_attempt_at <= NOW())
        ORDER BY closed_at ASC LIMIT 20
        FOR UPDATE SKIP LOCKED`,
    );
    const rows = due.rows;
    for (const row of rows) {
      await client.query(
        `UPDATE community_rankings
            SET results_attempts = results_attempts + 1,
                results_next_attempt_at = NOW() + INTERVAL '5 minutes'
          WHERE id = $1 AND results_sent_at IS NULL`,
        [row.id],
      );
    }
    return rows;
  });
}

export async function markMediaNightResultPublished(rankingId: string): Promise<void> {
  await query(
    `UPDATE community_rankings
        SET results_sent_at = NOW(), results_next_attempt_at = NULL
      WHERE id = $1 AND kind = 'media_night' AND status = 'closed' AND results_sent_at IS NULL`,
    [rankingId],
  );
}
