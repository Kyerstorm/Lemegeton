import { query, queryOne, transaction } from "../database.js";
import { cleanText, isValidHttpsUrl } from "./security.js";

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
