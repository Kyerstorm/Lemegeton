import type { DatabaseConnection } from "../../src/utility/database/libsql/database.js";
import { query, queryOne, transaction } from "../../src/utility/database/libsql/database.js";
import { cleanText, isValidHttpsUrl } from "../security/security.js";

export interface TournamentCandidateInput {
  title: string;
  sourceUrl: string;
}

export interface TournamentMatch {
  id: string;
  round_number: number;
  match_number: number;
  candidate_a_id: string;
  candidate_a_title: string;
  candidate_a_url: string;
  candidate_a_seed: number;
  candidate_b_id: string;
  candidate_b_title: string;
  candidate_b_url: string;
  candidate_b_seed: number;
  votes_a: number;
  votes_b: number;
  status: "open" | "completed";
  winner_candidate_id: string | null;
  decision: "votes" | "seed_tiebreak" | "withdrawal" | null;
}

export interface CommunityTournament {
  id: string;
  title: string;
  description: string;
  status: "open" | "completed" | "cancelled";
  current_round: number;
  rounds_total: number;
  closes_at: Date;
  winner_candidate_id: string | null;
  matches: TournamentMatch[];
}

export interface TournamentAuditEntry {
  id: string;
  actor_id: string;
  action: "created" | "candidate_withdrawn" | "round_advanced" | "completed" | "cancelled";
  candidate_id: string | null;
  candidate_title: string | null;
  round_number: number | null;
  details: string;
  created_at: Date;
}

async function recordTournamentAudit(
  client: DatabaseConnection,
  input: {
    guildId: string;
    tournamentId: string;
    actorId: string;
    action: TournamentAuditEntry["action"];
    candidateId?: string | null;
    roundNumber?: number | null;
    details?: string;
  },
): Promise<void> {
  await client.query(
    "INSERT INTO community_tournament_audit_log " +
    "(guild_id, tournament_id, actor_id, action, candidate_id, round_number, details) " +
    "VALUES ($1,$2,$3,$4,$5,$6,$7)",
    [
      input.guildId, input.tournamentId, input.actorId, input.action,
      input.candidateId ?? null, input.roundNumber ?? null, input.details ?? "",
    ],
  );
}

export function normalizeTournamentCandidates(values: readonly TournamentCandidateInput[]): TournamentCandidateInput[] {
  if (![4, 8, 16].includes(values.length)) {
    throw new Error("A single-elimination tournament requires 4, 8 or 16 candidates.");
  }
  const seen = new Set<string>();
  return values.map((value) => {
    const title = cleanText(value.title, 180);
    const sourceUrl = isValidHttpsUrl(value.sourceUrl);
    const key = title.toLocaleLowerCase("en-US");
    if (!title || !sourceUrl || seen.has(key)) {
      throw new Error("Every tournament candidate needs a distinct title and a valid HTTPS source link.");
    }
    seen.add(key);
    return { title, sourceUrl };
  });
}

export function parseTournamentCandidates(value: string): TournamentCandidateInput[] {
  const lines = value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  return normalizeTournamentCandidates(lines.map((line) => {
    const separator = line.lastIndexOf("|");
    if (separator < 1) throw new Error("Use one candidate per line as Title | https://source.example/work.");
    return { title: line.slice(0, separator).trim(), sourceUrl: line.slice(separator + 1).trim() };
  }));
}

export function tournamentMatchups<T>(values: readonly T[]): Array<[T, T]> {
  if (values.length < 2 || values.length % 2 !== 0) throw new Error("Tournament rounds require an even number of at least two candidates.");
  const result: Array<[T, T]> = [];
  for (let index = 0; index < values.length; index += 2) {
    result.push([values[index]!, values[index + 1]!]);
  }
  return result;
}

export function resolveTournamentMatch(votesA: number, votesB: number, seedA: number, seedB: number): {
  winner: "a" | "b";
  decision: "votes" | "seed_tiebreak";
} {
  if (![votesA, votesB, seedA, seedB].every(Number.isInteger)
    || votesA < 0 || votesB < 0 || seedA < 1 || seedB < 1 || seedA === seedB) {
    throw new Error("Tournament votes and seeds must be valid non-negative counts and distinct positive seeds.");
  }
  if (votesA === votesB) return { winner: seedA < seedB ? "a" : "b", decision: "seed_tiebreak" };
  return { winner: votesA > votesB ? "a" : "b", decision: "votes" };
}

export async function createCommunityTournament(input: {
  guildId: string;
  creatorId: string;
  title: string;
  description: string;
  closesAt: Date;
  candidates: readonly TournamentCandidateInput[];
  roundDurationHours?: number;
}): Promise<string> {
  if (!Number.isFinite(input.closesAt.getTime()) || input.closesAt.getTime() <= Date.now()) {
    throw new Error("The first tournament round must close in the future.");
  }
  const title = cleanText(input.title, 180);
  if (!title) throw new Error("A tournament title is required.");
  const candidates = normalizeTournamentCandidates(input.candidates);
  const roundDurationHours = input.roundDurationHours ?? 48;
  if (!Number.isInteger(roundDurationHours) || roundDurationHours < 1 || roundDurationHours > 168) {
    throw new Error("Tournament round duration must be between 1 and 168 hours.");
  }
  return transaction(async (client) => {
    const tournament = await client.query<{ id: string }>(
      "INSERT INTO community_tournaments " +
      "(guild_id, creator_id, title, description, rounds_total, round_duration_hours, closes_at) " +
      "VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id::text AS id",
      [input.guildId, input.creatorId, title, cleanText(input.description, 1_000),
        Math.log2(candidates.length), roundDurationHours, input.closesAt],
    );
    const tournamentId = tournament.rows[0]?.id;
    if (!tournamentId) throw new Error("The tournament could not be created.");
    const candidateIds: string[] = [];
    for (const [index, candidate] of candidates.entries()) {
      const inserted = await client.query<{ id: string }>(
        "INSERT INTO community_tournament_candidates " +
        "(tournament_id, title, source_url, submitted_by, seed) " +
        "VALUES ($1,$2,$3,$4,$5) RETURNING id::text AS id",
        [tournamentId, candidate.title, candidate.sourceUrl, input.creatorId, index + 1],
      );
      const candidateId = inserted.rows[0]?.id;
      if (!candidateId) throw new Error("A tournament candidate could not be saved.");
      candidateIds.push(candidateId);
    }
    for (const [index, [candidateA, candidateB]] of tournamentMatchups(candidateIds).entries()) {
      await client.query(
        "INSERT INTO community_tournament_matches " +
        "(tournament_id, round_number, match_number, candidate_a_id, candidate_b_id) " +
        "VALUES ($1,1,$2,$3,$4)",
        [tournamentId, index + 1, candidateA, candidateB],
      );
    }
    await recordTournamentAudit(client, {
      guildId: input.guildId,
      tournamentId,
      actorId: input.creatorId,
      action: "created",
      details: `${candidates.length} candidates seeded into a single-elimination bracket.`,
    });
    return tournamentId;
  });
}

export async function listCommunityTournaments(guildId: string, includeCompleted = false): Promise<Array<{
  id: string; title: string; status: string; current_round: number; rounds_total: number; closes_at: Date;
}>> {
  return query(
    "SELECT id::text, title, status, current_round, rounds_total, closes_at " +
    "FROM community_tournaments WHERE guild_id = $1 " +
    "AND (status = 'open' OR ($2::boolean AND status = 'completed')) " +
    "ORDER BY created_at DESC LIMIT 15",
    [guildId, includeCompleted],
  );
}

export async function getCommunityTournament(guildId: string, tournamentId: string): Promise<CommunityTournament | null> {
  const tournament = await queryOne<Omit<CommunityTournament, "matches">>(
    "SELECT id::text, title, description, status, current_round, rounds_total, " +
    "closes_at, winner_candidate_id::text FROM community_tournaments WHERE id = $1 AND guild_id = $2",
    [tournamentId, guildId],
  );
  if (!tournament) return null;
  const matches = await query<TournamentMatch>(
    "SELECT m.id::text, m.round_number, m.match_number, " +
    "a.id::text AS candidate_a_id, a.title AS candidate_a_title, a.source_url AS candidate_a_url, a.seed AS candidate_a_seed, " +
    "b.id::text AS candidate_b_id, b.title AS candidate_b_title, b.source_url AS candidate_b_url, b.seed AS candidate_b_seed, " +
    "COUNT(v.user_id) FILTER (WHERE v.candidate_id = a.id)::INT AS votes_a, " +
    "COUNT(v.user_id) FILTER (WHERE v.candidate_id = b.id)::INT AS votes_b, " +
    "m.status, m.winner_candidate_id::text, m.decision " +
    "FROM community_tournament_matches m " +
    "JOIN community_tournament_candidates a ON a.id = m.candidate_a_id " +
    "JOIN community_tournament_candidates b ON b.id = m.candidate_b_id " +
    "LEFT JOIN community_tournament_votes v ON v.match_id = m.id " +
    "WHERE m.tournament_id = $1 AND m.round_number <= $2 " +
    "GROUP BY m.id, a.id, b.id ORDER BY m.round_number ASC, m.match_number ASC",
    [tournamentId, tournament.current_round],
  );
  return { ...tournament, matches };
}

export async function getCommunityTournamentAudit(
  guildId: string,
  tournamentId: string,
  limit = 8,
): Promise<TournamentAuditEntry[]> {
  return query<TournamentAuditEntry>(
    "SELECT a.id::text, a.actor_id::text, a.action, a.candidate_id::text, c.title AS candidate_title, " +
    "a.round_number, a.details, a.created_at " +
    "FROM community_tournament_audit_log a " +
    "LEFT JOIN community_tournament_candidates c ON c.id = a.candidate_id " +
    "WHERE a.guild_id = $1 AND a.tournament_id = $2 " +
    "ORDER BY a.created_at DESC, a.id DESC LIMIT $3",
    [guildId, tournamentId, Math.max(1, Math.min(20, Math.floor(limit)))],
  );
}

export async function voteInCommunityTournament(
  guildId: string,
  userId: string,
  matchId: string,
  candidateId: string,
): Promise<void> {
  await transaction(async (client) => {
    const tournament = await client.query<{ status: string; closes_at: Date }>(
      "SELECT status, closes_at FROM community_tournaments " +
      "WHERE id = (SELECT tournament_id FROM community_tournament_matches WHERE id = $1) " +
      "AND guild_id = $2 FOR UPDATE",
      [matchId, guildId],
    );
    const tournamentRow = tournament.rows[0];
    const matchResult = tournamentRow
      ? await client.query<{
          id: string; status: string; candidate_a_id: string; candidate_b_id: string;
        }>(
          "SELECT id::text, status, candidate_a_id::text, candidate_b_id::text " +
          "FROM community_tournament_matches WHERE id = $1 FOR UPDATE",
          [matchId],
        )
      : { rows: [] as Array<{ id: string; status: string; candidate_a_id: string; candidate_b_id: string }> };
    const match = matchResult.rows[0]
      ? { ...matchResult.rows[0], tournament_status: tournamentRow!.status, closes_at: tournamentRow!.closes_at }
      : undefined;
    if (!match || match.status !== "open" || match.tournament_status !== "open"
      || new Date(match.closes_at).getTime() <= Date.now()) {
      throw new Error("That tournament match is closed or no longer available.");
    }
    if (candidateId !== match.candidate_a_id && candidateId !== match.candidate_b_id) {
      throw new Error("That candidate does not belong to this match.");
    }
    const existing = await client.query<{ candidate_id: string }>(
      "SELECT candidate_id::text FROM community_tournament_votes WHERE match_id = $1 AND user_id = $2",
      [matchId, userId],
    );
    if (existing.rows[0]) {
      if (existing.rows[0].candidate_id === candidateId) return;
      throw new Error("Tournament ballots are locked and cannot be changed.");
    }
    await client.query(
      "INSERT INTO community_tournament_votes (match_id, user_id, candidate_id) VALUES ($1,$2,$3)",
      [matchId, userId, candidateId],
    );
  });
}

export async function withdrawCommunityTournamentCandidate(
  guildId: string,
  tournamentId: string,
  candidateId: string,
  actorId: string,
  isManager: boolean,
  reason = "",
): Promise<void> {
  await transaction(async client => {
    const selectedTournament = await client.query<{ creator_id: string; status: string; current_round: number }>(
      "SELECT creator_id::text, status, current_round FROM community_tournaments " +
      "WHERE id = $1 AND guild_id = $2 FOR UPDATE",
      [tournamentId, guildId],
    );
    const tournament = selectedTournament.rows[0];
    if (!tournament || tournament.status !== "open") {
      throw new Error("That open tournament was not found in this server.");
    }
    if (tournament.creator_id !== actorId && !isManager) {
      throw new Error("Only the tournament creator or a server manager can withdraw a candidate.");
    }

    const selectedCandidate = await client.query<{ id: string; title: string; status: string }>(
      "SELECT id::text, title, status FROM community_tournament_candidates " +
      "WHERE id = $1 AND tournament_id = $2 FOR UPDATE",
      [candidateId, tournamentId],
    );
    const candidate = selectedCandidate.rows[0];
    if (!candidate || candidate.status !== "active") {
      throw new Error("That active tournament candidate was not found.");
    }

    const selectedMatch = await client.query<{
      id: string; candidate_a_id: string; candidate_b_id: string;
    }>(
      "SELECT id::text, candidate_a_id::text, candidate_b_id::text " +
      "FROM community_tournament_matches WHERE tournament_id = $1 AND round_number = $2 " +
      "AND status = 'open' AND (candidate_a_id = $3 OR candidate_b_id = $3) FOR UPDATE",
      [tournamentId, tournament.current_round, candidateId],
    );
    const match = selectedMatch.rows[0];
    if (!match) throw new Error("That candidate is not in an open match in the current round.");

    const ballots = await client.query<{ count: number }>(
      "SELECT COUNT(*)::INT AS count FROM community_tournament_votes WHERE match_id = $1",
      [match.id],
    );
    if (Number(ballots.rows[0]?.count ?? 0) > 0) {
      throw new Error("A candidate cannot withdraw after a ballot has been cast in its match.");
    }

    const winnerId = match.candidate_a_id === candidateId ? match.candidate_b_id : match.candidate_a_id;
    await client.query(
      "UPDATE community_tournament_candidates SET status = 'withdrawn' WHERE id = $1 AND status = 'active'",
      [candidateId],
    );
    await client.query(
      "UPDATE community_tournament_matches SET status = 'completed', winner_candidate_id = $1, " +
      "decision = 'withdrawal', completed_at = NOW() WHERE id = $2 AND status = 'open'",
      [winnerId, match.id],
    );
    await recordTournamentAudit(client, {
      guildId,
      tournamentId,
      actorId,
      action: "candidate_withdrawn",
      candidateId,
      roundNumber: tournament.current_round,
      details: cleanText(reason, 300) || "Withdrawn by tournament creator or a server manager.",
    });
  });
}

export async function advanceCommunityTournament(
  guildId: string,
  tournamentId: string,
  actorId: string,
  isManager: boolean,
  now = new Date(),
): Promise<{ status: "open" | "completed"; round: number; winnerTitle: string | null }> {
  return transaction(async (client) => {
    const selected = await client.query<{
      id: string; creator_id: string; status: string; current_round: number;
      rounds_total: number; round_duration_hours: number; closes_at: Date;
    }>(
      "SELECT id::text, creator_id::text, status, current_round, rounds_total, " +
      "round_duration_hours, closes_at FROM community_tournaments " +
      "WHERE id = $1 AND guild_id = $2 FOR UPDATE",
      [tournamentId, guildId],
    );
    const tournament = selected.rows[0];
    if (!tournament || tournament.status !== "open") throw new Error("That open tournament was not found in this server.");
    if (tournament.creator_id !== actorId && !isManager) {
      throw new Error("Only the tournament creator or a server manager can advance it.");
    }
    if (new Date(tournament.closes_at).getTime() > now.getTime() && !isManager) {
      throw new Error("The round is still open. A server manager may close it early.");
    }
    const matches = await client.query<{
      id: string; candidate_a_id: string; candidate_b_id: string;
      seed_a: number; seed_b: number; status: string;
      winner_candidate_id: string | null; decision: string | null;
    }>(
      "SELECT m.id::text, m.candidate_a_id::text, m.candidate_b_id::text, " +
      "a.seed AS seed_a, b.seed AS seed_b, m.status, m.winner_candidate_id::text, m.decision " +
      "FROM community_tournament_matches m " +
      "JOIN community_tournament_candidates a ON a.id = m.candidate_a_id " +
      "JOIN community_tournament_candidates b ON b.id = m.candidate_b_id " +
      "WHERE m.tournament_id = $1 AND m.round_number = $2 " +
      "ORDER BY m.match_number FOR UPDATE OF m",
      [tournamentId, tournament.current_round],
    );
    if (!matches.rowCount) throw new Error("The current round has no matches to advance.");
    const winners: string[] = [];
    let withdrawalByes = 0;
    let voteDecisions = 0;
    let seedTiebreaks = 0;
    for (const match of matches.rows) {
      if (match.status === "completed") {
        if (match.decision !== "withdrawal" || !match.winner_candidate_id) {
          throw new Error("The current round contains an unexpected completed match.");
        }
        winners.push(match.winner_candidate_id);
        withdrawalByes += 1;
        continue;
      }
      const voteRows = await client.query<{ candidate_id: string; count: number }>(
        "SELECT candidate_id::text, COUNT(*)::INT AS count FROM community_tournament_votes " +
        "WHERE match_id = $1 GROUP BY candidate_id",
        [match.id],
      );
      const counts = new Map(voteRows.rows.map(row => [row.candidate_id, Number(row.count)]));
      const result = resolveTournamentMatch(
        counts.get(match.candidate_a_id) ?? 0,
        counts.get(match.candidate_b_id) ?? 0,
        Number(match.seed_a),
        Number(match.seed_b),
      );
      if (result.decision === "votes") voteDecisions += 1;
      else seedTiebreaks += 1;
      const winnerId = result.winner === "a" ? match.candidate_a_id : match.candidate_b_id;
      const loserId = result.winner === "a" ? match.candidate_b_id : match.candidate_a_id;
      winners.push(winnerId);
      await client.query(
        "UPDATE community_tournament_matches SET winner_candidate_id = $1, decision = $2, " +
        "status = 'completed', completed_at = $3 WHERE id = $4 AND status = 'open'",
        [winnerId, result.decision, now, match.id],
      );
      await client.query(
        "UPDATE community_tournament_candidates SET status = 'eliminated' " +
        "WHERE id = $1 AND status = 'active'",
        [loserId],
      );
    }
    if (Number(tournament.current_round) >= Number(tournament.rounds_total)) {
      const winnerId = winners[0];
      const champion = await client.query<{ title: string }>(
        "UPDATE community_tournament_candidates SET status = 'champion' WHERE id = $1 RETURNING title",
        [winnerId],
      );
      await client.query(
        "UPDATE community_tournaments SET status = 'completed', winner_candidate_id = $1, closed_at = $2 WHERE id = $3",
        [winnerId, now, tournamentId],
      );
      await recordTournamentAudit(client, {
        guildId,
        tournamentId,
        actorId,
        action: "completed",
        roundNumber: tournament.current_round,
        details: `Champion: ${champion.rows[0]?.title ?? "unavailable"}.`,
      });
      return { status: "completed", round: Number(tournament.current_round), winnerTitle: champion.rows[0]?.title ?? null };
    }
    for (const [index, [candidateA, candidateB]] of tournamentMatchups(winners).entries()) {
      await client.query(
        "INSERT INTO community_tournament_matches " +
        "(tournament_id, round_number, match_number, candidate_a_id, candidate_b_id) " +
        "VALUES ($1,$2,$3,$4,$5)",
        [tournamentId, Number(tournament.current_round) + 1, index + 1, candidateA, candidateB],
      );
    }
    const nextRound = Number(tournament.current_round) + 1;
    await client.query(
      "UPDATE community_tournaments SET current_round = $1, closes_at = $2 WHERE id = $3 AND guild_id = $4",
      [nextRound, new Date(now.getTime() + Number(tournament.round_duration_hours) * 60 * 60 * 1000), tournamentId, guildId],
    );
    await recordTournamentAudit(client, {
      guildId,
      tournamentId,
      actorId,
      action: "round_advanced",
      roundNumber: nextRound,
      details: JSON.stringify({ previousRound: Number(tournament.current_round), voteDecisions, seedTiebreaks, withdrawalByes }),
    });
    return { status: "open", round: nextRound, winnerTitle: null };
  });
}

export async function cancelCommunityTournament(
  guildId: string,
  tournamentId: string,
  actorId: string,
  isManager: boolean,
): Promise<void> {
  return transaction(async (client) => {
    const row = await client.query<{ creator_id: string }>(
      "SELECT creator_id::text FROM community_tournaments WHERE id = $1 AND guild_id = $2 AND status = 'open' FOR UPDATE",
      [tournamentId, guildId],
    );
    if (!row.rows[0] || (row.rows[0].creator_id !== actorId && !isManager)) {
      throw new Error("Only the tournament creator or a server manager can cancel it.");
    }
    await client.query(
      "UPDATE community_tournaments SET status = 'cancelled', closed_at = NOW() WHERE id = $1 AND guild_id = $2 AND status = 'open'",
      [tournamentId, guildId],
    );
    await recordTournamentAudit(client, {
      guildId,
      tournamentId,
      actorId,
      action: "cancelled",
      details: "Tournament cancelled by its creator or a server manager.",
    });
  });
}

export type CommunitySeasonItemType = "daily_drop" | "ranking" | "session" | "tournament" | "spotlight" | "collection" | "trail" | "challenge" | "puzzle";

const SEASON_ITEM_TYPES = new Set<CommunitySeasonItemType>([
  "daily_drop", "ranking", "session", "tournament", "spotlight", "collection", "trail", "challenge", "puzzle",
]);

export function normalizeSeasonItemType(value: string): CommunitySeasonItemType {
  if (!SEASON_ITEM_TYPES.has(value as CommunitySeasonItemType)) {
    throw new Error("Choose a supported season item: Daily Drop, ranking, session, tournament, spotlight, collection, Trail, challenge or puzzle.");
  }
  return value as CommunitySeasonItemType;
}

export function validateSeasonWindow(startsAt: Date, endsAt: Date, now = new Date()): void {
  if (!Number.isFinite(startsAt.getTime()) || !Number.isFinite(endsAt.getTime())) {
    throw new Error("Season start and end must be valid dates.");
  }
  if (startsAt.getTime() < now.getTime() - 60_000) throw new Error("A season cannot start in the past.");
  if (endsAt.getTime() <= startsAt.getTime() || endsAt.getTime() - startsAt.getTime() > 180 * 24 * 60 * 60 * 1000) {
    throw new Error("A season must last between one minute and 180 days.");
  }
}

export async function createCommunitySeason(input: {
  guildId: string; creatorId: string; title: string; description: string; startsAt: Date; endsAt: Date;
}): Promise<string> {
  validateSeasonWindow(input.startsAt, input.endsAt);
  const title = cleanText(input.title, 160);
  if (!title) throw new Error("A Community Season title is required.");
  const row = await queryOne<{ id: string }>(
    "INSERT INTO community_seasons (guild_id, creator_id, title, description, starts_at, ends_at) " +
    "VALUES ($1,$2,$3,$4,$5,$6) RETURNING id::text AS id",
    [input.guildId, input.creatorId, title, cleanText(input.description, 1_000), input.startsAt, input.endsAt],
  );
  if (!row) throw new Error("The Community Season could not be created.");
  return row.id;
}

export async function listCommunitySeasons(guildId: string): Promise<Array<{
  id: string; title: string; description: string; starts_at: Date; ends_at: Date; status: string; item_count: number;
}>> {
  const rows = await query<{
    id: string; title: string; description: string; starts_at: Date; ends_at: Date; status: string;
  }>(
    "SELECT id::text, title, description, starts_at, ends_at, " +
    "CASE WHEN status = 'open' AND ends_at <= NOW() THEN 'completed' ELSE status END AS status " +
    "FROM community_seasons WHERE guild_id = $1 ORDER BY starts_at DESC LIMIT 15",
    [guildId],
  );
  return Promise.all(rows.map(async season => ({
    ...season,
    item_count: (await getCommunitySeason(guildId, season.id))?.items.length ?? 0,
  })));
}

const SEASON_ITEM_LOOKUPS: Record<CommunitySeasonItemType, string> = {
  daily_drop: "SELECT i.id FROM community_daily_items i WHERE i.id = $1 AND i.guild_id = $2 AND i.status = 'approved' " +
    "AND EXISTS (SELECT 1 FROM community_daily_deliveries d WHERE d.guild_id = $2 AND d.item_id = i.id AND d.status = 'sent' AND d.scheduled_for >= $3 AND d.scheduled_for < $4)",
  ranking: "SELECT id FROM community_rankings WHERE id = $1 AND guild_id = $2 AND kind = 'ranking' AND status = 'closed' AND closed_at >= $3 AND closed_at < $4",
  session: "SELECT id FROM community_sessions WHERE id = $1 AND guild_id = $2 AND status IN ('scheduled','open','closed') AND scheduled_at >= $3 AND scheduled_at < $4",
  tournament: "SELECT id FROM community_tournaments WHERE id = $1 AND guild_id = $2 AND status = 'completed' AND closed_at >= $3 AND closed_at < $4",
  spotlight: "SELECT p.id FROM community_archive_spotlights p JOIN community_archive_entries e ON e.id = p.entry_id " +
    "WHERE p.id = $1 AND p.guild_id = $2 AND p.visibility = 'server' AND p.status = 'published' " +
    "AND e.status = 'approved' AND (e.visibility = 'global' OR (e.visibility = 'server' AND e.created_guild_id = $2)) " +
    "AND p.starts_at < $4 AND p.ends_at > $3",
  collection: "SELECT id FROM archive_collections WHERE id = $1 AND guild_id = $2 AND visibility = 'server' AND status = 'active' AND created_at >= $3 AND created_at < $4",
  trail: "SELECT id FROM archive_trails WHERE id = $1 AND guild_id = $2 AND visibility = 'server' AND status = 'active' AND created_at >= $3 AND created_at < $4",
  challenge: "SELECT id FROM community_quiz_packs q WHERE q.id = $1 AND q.guild_id = $2 AND q.status = 'approved' AND q.mode = 'challenge' " +
    "AND EXISTS (SELECT 1 FROM community_game_sessions s WHERE s.guild_id = $2 AND s.pack_id = q.id AND s.status = 'finished' AND s.finished_at >= $3 AND s.finished_at < $4)",
  puzzle: "SELECT id FROM community_quiz_packs q WHERE q.id = $1 AND q.guild_id = $2 AND q.status = 'approved' AND q.mode = 'puzzle' " +
    "AND EXISTS (SELECT 1 FROM community_game_sessions s WHERE s.guild_id = $2 AND s.pack_id = q.id AND s.status = 'finished' AND s.finished_at >= $3 AND s.finished_at < $4)",
};

export async function addCommunitySeasonItem(
  guildId: string, actorId: string, seasonId: string, rawType: string, itemId: string, isManager = false,
): Promise<void> {
  const itemType = normalizeSeasonItemType(rawType);
  if (!/^[1-9]\d{0,18}$/.test(itemId) || (itemId.length === 19 && itemId > "9223372036854775807")) throw new Error("Enter a valid existing record ID.");
  await transaction(async (client) => {
    const season = await client.query<{ id: string; creator_id: string; starts_at: Date; ends_at: Date }>(
      "SELECT id::text, creator_id::text, starts_at, ends_at FROM community_seasons " +
      "WHERE id = $1 AND guild_id = $2 AND status = 'open' AND ends_at > NOW() FOR UPDATE",
      [seasonId, guildId],
    );
    const seasonRow = season.rows[0];
    if (!seasonRow || (seasonRow.creator_id !== actorId && !isManager)) {
      throw new Error("Only the season creator or a server manager can add records to an active season.");
    }
    const item = await client.query(SEASON_ITEM_LOOKUPS[itemType], [
      itemId, guildId, seasonRow.starts_at, seasonRow.ends_at,
    ]);
    if (!item.rowCount) {
      throw new Error("The selected record is not approved, visible and dated within this Community Season.");
    }
    await client.query(
      "INSERT INTO community_season_items (season_id, item_type, item_id, added_by) " +
      "VALUES ($1,$2,$3,$4) ON CONFLICT (season_id, item_type, item_id) DO NOTHING",
      [seasonId, itemType, itemId, actorId],
    );
  });
}

export async function closeCommunitySeason(
  guildId: string, actorId: string, seasonId: string, isManager: boolean,
): Promise<void> {
  await transaction(async (client) => {
    const row = await client.query<{ creator_id: string }>(
      "SELECT creator_id::text FROM community_seasons WHERE id = $1 AND guild_id = $2 AND status = 'open' FOR UPDATE",
      [seasonId, guildId],
    );
    if (!row.rows[0] || (row.rows[0].creator_id !== actorId && !isManager)) {
      throw new Error("Only the season creator or a server manager can close it.");
    }
    await client.query(
      "UPDATE community_seasons SET status = 'completed' WHERE id = $1 AND guild_id = $2 AND status = 'open'",
      [seasonId, guildId],
    );
  });
}

export interface CommunitySeasonItem {
  item_type: CommunitySeasonItemType;
  item_id: string;
  title: string;
  added_by: string | null;
  occurred_at: Date;
  source: "period" | "linked";
}

export async function getCommunitySeason(guildId: string, seasonId: string): Promise<{
  id: string; title: string; description: string; starts_at: Date; ends_at: Date; status: string;
  items: CommunitySeasonItem[];
} | null> {
  const season = await queryOne<{
    id: string; title: string; description: string; starts_at: Date; ends_at: Date; status: string;
  }>(
    "SELECT id::text, title, description, starts_at, ends_at, " +
    "CASE WHEN status = 'open' AND ends_at <= NOW() THEN 'completed' ELSE status END AS status " +
    "FROM community_seasons WHERE id = $1 AND guild_id = $2",
    [seasonId, guildId],
  );
  if (!season) return null;
  const items = await query<{
    item_type: CommunitySeasonItemType;
    item_id: string;
    title: string;
    added_by: string | null;
    occurred_at: Date;
    source: "period" | "linked";
  }>(
    `WITH season AS (
       SELECT id, guild_id, starts_at, ends_at
       FROM community_seasons WHERE id = $1 AND guild_id = $2
     ),
     automatic_items AS (
       SELECT 'daily_drop'::VARCHAR(24) AS item_type, i.id::TEXT AS item_id, i.title,
              NULL::TEXT AS added_by, MIN(d.scheduled_for) AS occurred_at, 'period'::TEXT AS source
       FROM season
       JOIN community_daily_deliveries d ON d.guild_id = season.guild_id
         AND d.status = 'sent' AND d.scheduled_for >= season.starts_at AND d.scheduled_for < season.ends_at
       JOIN community_daily_items i ON i.id = d.item_id AND i.guild_id = season.guild_id AND i.status = 'approved'
       GROUP BY i.id, i.title
       UNION ALL
       SELECT 'ranking', r.id::TEXT, r.title, NULL::TEXT, r.closed_at, 'period'::TEXT
       FROM season JOIN community_rankings r ON r.guild_id = season.guild_id
       WHERE r.kind = 'ranking' AND r.status = 'closed'
         AND r.closed_at >= season.starts_at AND r.closed_at < season.ends_at
       UNION ALL
       SELECT 'session', s.id::TEXT, s.title, NULL::TEXT, s.scheduled_at, 'period'::TEXT
       FROM season JOIN community_sessions s ON s.guild_id = season.guild_id
       WHERE s.status IN ('scheduled','open','closed')
         AND s.scheduled_at >= season.starts_at AND s.scheduled_at < season.ends_at
       UNION ALL
       SELECT q.mode::VARCHAR(24), q.id::TEXT, q.title, NULL::TEXT, MIN(g.finished_at), 'period'::TEXT
       FROM season
       JOIN community_game_sessions g ON g.guild_id = season.guild_id
         AND g.status = 'finished' AND g.finished_at >= season.starts_at AND g.finished_at < season.ends_at
       JOIN community_quiz_packs q ON q.id = g.pack_id AND q.guild_id = season.guild_id
         AND q.status = 'approved' AND q.mode IN ('challenge','puzzle')
       GROUP BY q.id, q.mode, q.title
       UNION ALL
       SELECT 'spotlight', p.id::TEXT, e.title, NULL::TEXT, GREATEST(p.starts_at, season.starts_at), 'period'::TEXT
       FROM season JOIN community_archive_spotlights p ON p.guild_id = season.guild_id
       JOIN community_archive_entries e ON e.id = p.entry_id AND e.status = 'approved'
         AND (e.visibility = 'global' OR (e.visibility = 'server' AND e.created_guild_id = season.guild_id))
       WHERE p.visibility = 'server' AND p.status = 'published'
         AND p.starts_at < season.ends_at AND p.ends_at > season.starts_at
     ),
     linked_items AS (
       SELECT i.item_type::VARCHAR(24) AS item_type, i.item_id::TEXT AS item_id,
              COALESCE(d.title, r.title, s.title, t.title, pe.title, c.title, a.title, q.title) AS title,
              i.added_by::TEXT AS added_by, i.created_at AS occurred_at, 'linked'::TEXT AS source
       FROM community_season_items i
       JOIN season ON season.id = i.season_id
       LEFT JOIN community_daily_items d ON i.item_type = 'daily_drop' AND d.id = i.item_id
         AND d.guild_id = season.guild_id AND d.status = 'approved'
       LEFT JOIN community_rankings r ON i.item_type = 'ranking' AND r.id = i.item_id
         AND r.guild_id = season.guild_id AND r.status = 'closed'
       LEFT JOIN community_sessions s ON i.item_type = 'session' AND s.id = i.item_id
         AND s.guild_id = season.guild_id AND s.status IN ('closed','cancelled')
       LEFT JOIN community_tournaments t ON i.item_type = 'tournament' AND t.id = i.item_id
         AND t.guild_id = season.guild_id AND t.status = 'completed'
       LEFT JOIN community_archive_spotlights p ON i.item_type = 'spotlight' AND p.id = i.item_id
         AND p.guild_id = season.guild_id AND p.visibility = 'server' AND p.status = 'published'
       LEFT JOIN community_archive_entries pe ON pe.id = p.entry_id
         AND pe.status = 'approved' AND (pe.visibility = 'global' OR (pe.visibility = 'server' AND pe.created_guild_id = season.guild_id))
       LEFT JOIN archive_collections c ON i.item_type = 'collection' AND c.id = i.item_id
         AND c.guild_id = season.guild_id AND c.visibility = 'server' AND c.status = 'active'
       LEFT JOIN archive_trails a ON i.item_type = 'trail' AND a.id = i.item_id
         AND a.guild_id = season.guild_id AND a.visibility = 'server' AND a.status = 'active'
       LEFT JOIN community_quiz_packs q ON i.item_type IN ('challenge','puzzle') AND q.id = i.item_id
         AND q.guild_id = season.guild_id AND q.status = 'approved' AND q.mode = i.item_type
       WHERE i.season_id = $1
         AND COALESCE(d.id,r.id,s.id,t.id,pe.id,c.id,a.id,q.id) IS NOT NULL
         AND NOT EXISTS (
           SELECT 1 FROM automatic_items auto
           WHERE auto.item_type = i.item_type AND auto.item_id = i.item_id::TEXT
         )
     )
     SELECT * FROM automatic_items
     UNION ALL
     SELECT * FROM linked_items
     ORDER BY occurred_at ASC, item_type ASC, item_id ASC
     LIMIT 100`,
    [seasonId, guildId],
  );
  return { ...season, items };
}
