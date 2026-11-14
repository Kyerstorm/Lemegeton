import type { PoolClient } from "pg";
import { query, queryOne, transaction } from "../../database.js";
import { cleanText, isValidHttpsUrl } from "../security/security.js";

export interface QuizQuestion {
  id: string;
  question: string;
  correct_answer: string;
  accepted_answers: string[];
  options: string[];
  source_url: string;
  media_title: string | null;
}
export type GameMode = "individual" | "teams" | "cooperative";
export interface GameSession {
  id: string;
  guild_id: string;
  channel_id: string;
  message_id: string | null;
  pack_id: string;
  host_id: string;
  question_ids: string[];
  current_round: number;
  status: string;
  game_mode: GameMode;
  title: string;
}
export interface GameLeaderboardEntry {
  user_id: string | null;
  team_id: string | null;
  team_name: string | null;
  member_count: number;
  score: number;
  correct: number;
  answers: number;
}
function normalizeAnswer(value: string): string {
  return cleanText(value, 200).toLocaleLowerCase("en").replace(/[^\p{L}\p{N}]+/gu, " ").trim();
}
export function chooseBalancedTeam<T extends { id: string; member_count: number; team_number: number }>(teams: readonly T[]): T | null {
  return [...teams].sort((a, b) => a.member_count - b.member_count || a.team_number - b.team_number)[0] ?? null;
}
async function ensureGameParticipant(client: PoolClient, sessionId: string, userId: string, gameMode: GameMode): Promise<string | null> {
  const existingResult = await client.query<{ team_id: string | null; team_name: string | null }>(
    "SELECT p.team_id::text AS team_id, t.name AS team_name FROM community_game_participants p " +
    "LEFT JOIN community_game_teams t ON t.id = p.team_id AND t.session_id = p.session_id " +
    "WHERE p.session_id = $1 AND p.user_id = $2",
    [sessionId, userId],
  );
  const existing = existingResult.rows[0];
  if (gameMode === "individual") {
    if (!existing) await client.query(
      "INSERT INTO community_game_participants (session_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
      [sessionId, userId],
    );
    return null;
  }
  if (existing?.team_id) return existing.team_name;
  const teamRows = await client.query<{ id: string; name: string; team_number: number; member_count: number }>(
    "SELECT t.id::text AS id, t.name, t.team_number, COUNT(p.user_id)::int AS member_count " +
    "FROM community_game_teams t LEFT JOIN community_game_participants p ON p.team_id = t.id AND p.session_id = t.session_id " +
    "WHERE t.session_id = $1 GROUP BY t.id, t.name, t.team_number ORDER BY member_count, t.team_number",
    [sessionId],
  );
  const selected = gameMode === "cooperative" ? teamRows.rows.find(team => team.team_number === 1) ?? null : chooseBalancedTeam(teamRows.rows);
  if (!selected) throw new Error("The team setup for this game is incomplete.");
  if (existing) {
    await client.query("UPDATE community_game_participants SET team_id = $3 WHERE session_id = $1 AND user_id = $2", [sessionId, userId, selected.id]);
  } else {
    await client.query("INSERT INTO community_game_participants (session_id, user_id, team_id) VALUES ($1, $2, $3)", [sessionId, userId, selected.id]);
  }
  return selected.name;
}
export async function createQuizPack(guildId: string, creatorId: string, title: string, description: string, mode: "trivia" | "guessing" | "mystery" = "trivia"): Promise<string> {
  const cleanTitle = cleanText(title, 160);
  if (!cleanTitle) throw new Error("A question pack title is required.");
  const row = await queryOne<{ id: string }>(
    `INSERT INTO community_quiz_packs (guild_id, creator_id, title, description, mode, status)
     VALUES ($1, $2, $3, $4, $5, 'pending') RETURNING id`,
    [guildId, creatorId, cleanTitle, cleanText(description, 1_000), mode],
  );
  if (!row) throw new Error("The quiz pack could not be saved.");
  return row.id;
}
export async function addQuizQuestion(guildId: string, packId: string, contributorId: string, question: string, answer: string, acceptedAnswers: string[], sourceUrl: string, mediaTitle?: string, options: string[] = []): Promise<string> {
  const pack = await queryOne<{ id: string; status: string }>("SELECT id, status FROM community_quiz_packs WHERE id = $1 AND guild_id = $2", [packId, guildId]);
  if (!pack || pack.status === "rejected") throw new Error("That quiz pack was not found or was rejected.");
  const cleanQuestion = cleanText(question, 500);
  const cleanAnswer = cleanText(answer, 200);
  if (!cleanQuestion || !cleanAnswer) throw new Error("A question and correct answer are required.");
  const source = isValidHttpsUrl(sourceUrl, true)!;
  const accepted = [...new Set([cleanAnswer, ...acceptedAnswers.map((item) => cleanText(item, 200))].filter(Boolean))].slice(0, 10);
  if (options.length > 4 || options.some((item) => !cleanText(item, 150))) throw new Error("A multiple-choice question can have up to four non-empty options.");
  const row = await queryOne<{ id: string }>(
    `INSERT INTO community_quiz_questions
     (pack_id, contributor_id, media_title, question, correct_answer, accepted_answers, options, source_url, status)
     VALUES ($1, $2, $3, $4, $5, $6, $7::JSONB, $8, 'pending') RETURNING id`,
    [packId, contributorId, mediaTitle ? cleanText(mediaTitle, 200) : null, cleanQuestion, cleanAnswer, accepted, JSON.stringify(options.map((item) => cleanText(item, 150))), source],
  );
  if (!row) throw new Error("The question could not be saved.");
  return row.id;
}
export async function reviewQuizPack(guildId: string, packId: string, approve: boolean): Promise<void> {
  const row = await queryOne<{ id: string }>(
    "UPDATE community_quiz_packs SET status = $1 WHERE id = $2 AND guild_id = $3 AND status = 'pending' RETURNING id",
    [approve ? "approved" : "rejected", packId, guildId],
  );
  if (!row) throw new Error("That pending quiz pack was not found.");
}
export async function reviewQuizQuestion(guildId: string, questionId: string, reviewerId: string, approve: boolean): Promise<void> {
  const row = await queryOne<{ id: string }>(
    `UPDATE community_quiz_questions q SET status = $1, reviewed_by = $2
     FROM community_quiz_packs p WHERE q.pack_id = p.id AND p.guild_id = $3 AND q.id = $4
       AND p.status = 'approved' AND q.status = 'pending' RETURNING q.id`,
    [approve ? "approved" : "rejected", reviewerId, guildId, questionId],
  );
  if (!row) throw new Error("That pending question was not found in an approved pack in this server.");
}
export async function listQuizPacks(guildId: string, status = "approved"): Promise<Array<{ id: string; title: string; description: string; mode: string; question_count: number }>> {
  return query(
    `SELECT p.id, p.title, p.description, p.mode, COUNT(q.id)::INT AS question_count
     FROM community_quiz_packs p LEFT JOIN community_quiz_questions q ON q.pack_id = p.id AND q.status = 'approved'
     WHERE p.guild_id = $1 AND p.status = $2 GROUP BY p.id ORDER BY p.created_at DESC LIMIT 20`,
    [guildId, status],
  );
}
export async function pendingQuizQuestions(guildId: string): Promise<Array<{ id: string; pack_id: string; title: string; question: string; source_url: string }>> {
  return query(
    `SELECT q.id, q.pack_id, p.title, q.question, q.source_url
     FROM community_quiz_questions q JOIN community_quiz_packs p ON p.id = q.pack_id
     WHERE p.guild_id = $1 AND p.status = 'approved' AND q.status = 'pending'
     ORDER BY q.created_at ASC LIMIT 15`,
    [guildId],
  );
}
export async function startGame(guildId: string, channelId: string, hostId: string, packId: string, rounds = 5, gameMode: GameMode = "individual"): Promise<GameSession> {
  if (!["individual", "teams", "cooperative"].includes(gameMode)) throw new Error("Choose individual, teams or cooperative game mode.");
  const count = Math.min(10, Math.max(1, Math.floor(rounds)));
  return transaction(async (client: PoolClient) => {
    const packResult = await client.query("SELECT id, title, status FROM community_quiz_packs WHERE id = $1 AND guild_id = $2", [packId, guildId]);
    const pack = packResult.rows[0] as { id: string; title: string; status: string } | undefined;
    if (!pack || pack.status !== "approved") throw new Error("That quiz pack is not approved for play.");
    const questions = await client.query("SELECT id FROM community_quiz_questions WHERE pack_id = $1 AND status = 'approved' ORDER BY RANDOM() LIMIT $2", [packId, count]);
    const questionIds = questions.rows.map(row => String((row as { id: string }).id));
    if (!questionIds.length) throw new Error("That pack does not contain approved questions.");
    const inserted = await client.query(
      `INSERT INTO community_game_sessions (guild_id, channel_id, pack_id, host_id, question_ids, current_round, status, game_mode)
       VALUES ($1, $2, $3, $4, $5::BIGINT[], 0, 'active', $6) RETURNING *`,
      [guildId, channelId, packId, hostId, questionIds, gameMode],
    );
    const row = inserted.rows[0] as GameSession;
    if (gameMode === "individual") {
      await client.query("INSERT INTO community_game_participants (session_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING", [row.id, hostId]);
    } else {
      const definitions = gameMode === "cooperative" ? [{ team_number: 1, name: "Community Team" }] : [{ team_number: 1, name: "Team A" }, { team_number: 2, name: "Team B" }];
      let firstTeamId: string | null = null;
      for (const team of definitions) {
        const created = await client.query<{ id: string }>("INSERT INTO community_game_teams (session_id, team_number, name) VALUES ($1, $2, $3) RETURNING id::text AS id", [row.id, team.team_number, team.name]);
        if (team.team_number === 1) firstTeamId = created.rows[0]?.id ?? null;
      }
      if (!firstTeamId) throw new Error("The first game team could not be created.");
      await client.query("INSERT INTO community_game_participants (session_id, user_id, team_id) VALUES ($1, $2, $3)", [row.id, hostId, firstTeamId]);
    }
    return { ...row, title: pack.title };
  });
}
export async function joinGame(guildId: string, sessionId: string, userId: string): Promise<string | null> {
  return transaction(async client => {
    const result = await client.query<{ game_mode: GameMode; status: string }>("SELECT game_mode, status FROM community_game_sessions WHERE id = $1 AND guild_id = $2 FOR UPDATE", [sessionId, guildId]);
    const session = result.rows[0];
    if (!session || session.status !== "active") throw new Error("That active game was not found in this server.");
    return ensureGameParticipant(client, sessionId, userId, session.game_mode);
  });
}
export async function getGameSession(guildId: string, sessionId: string): Promise<GameSession | null> {
  return queryOne<GameSession & { title: string }>(
    `SELECT s.*, p.title FROM community_game_sessions s JOIN community_quiz_packs p ON p.id = s.pack_id
     WHERE s.id = $1 AND s.guild_id = $2`,
    [sessionId, guildId],
  );
}
export async function getCurrentGameQuestion(guildId: string, sessionId: string): Promise<QuizQuestion | null> {
  return queryOne<QuizQuestion>(
    `SELECT q.id, q.question, q.correct_answer, q.accepted_answers, q.options, q.source_url, q.media_title
     FROM community_game_sessions s JOIN community_quiz_questions q ON q.id = s.question_ids[s.current_round + 1]
     WHERE s.id = $1 AND s.guild_id = $2 AND s.status = 'active'`,
    [sessionId, guildId],
  );
}
export async function answerGameQuestion(guildId: string, sessionId: string, userId: string, answer: string): Promise<{ correct: boolean; round: number; total: number; sourceUrl: string; finished: boolean; teamName: string | null }> {
  return transaction(async client => {
    const result = await client.query("SELECT id, question_ids, current_round, status, game_mode FROM community_game_sessions WHERE id = $1 AND guild_id = $2 FOR UPDATE", [sessionId, guildId]);
    const session = result.rows[0] as { id: string; question_ids: string[]; current_round: number; status: string; game_mode: GameMode } | undefined;
    if (!session || session.status !== "active") throw new Error("That game is not active.");
    const questionId = session.question_ids[session.current_round];
    if (!questionId) throw new Error("The current round has no question.");
    const teamName = await ensureGameParticipant(client, sessionId, userId, session.game_mode);
    const questionResult = await client.query("SELECT correct_answer, accepted_answers, source_url FROM community_quiz_questions WHERE id = $1 AND status = 'approved'", [questionId]);
    const question = questionResult.rows[0] as { correct_answer: string; accepted_answers: string[]; source_url: string } | undefined;
    if (!question) throw new Error("The current question is no longer available.");
    const existing = await client.query("SELECT 1 FROM community_game_answers WHERE session_id = $1 AND round_number = $2 AND user_id = $3", [sessionId, session.current_round, userId]);
    if (existing.rowCount) throw new Error("You have already answered this round.");
    const correct = [question.correct_answer, ...(question.accepted_answers ?? [])].some(value => normalizeAnswer(value) === normalizeAnswer(answer));
    await client.query("INSERT INTO community_game_answers (session_id, round_number, question_id, user_id, answer, is_correct) VALUES ($1, $2, $3, $4, $5, $6)", [sessionId, session.current_round, questionId, userId, cleanText(answer, 200), correct]);
    return { correct, round: session.current_round + 1, total: session.question_ids.length, sourceUrl: question.source_url, finished: false, teamName };
  });
}
export async function advanceGame(guildId: string, sessionId: string, actorId: string, finish = false): Promise<{ round: number; total: number; finished: boolean }> {
  return transaction(async (client) => {
    const result = await client.query("SELECT host_id, question_ids, current_round, status FROM community_game_sessions WHERE id = $1 AND guild_id = $2 FOR UPDATE", [sessionId, guildId]);
    const session = result.rows[0] as { host_id: string; question_ids: string[]; current_round: number; status: string } | undefined;
    if (!session || session.status !== "active") throw new Error("That game is not active.");
    if (session.host_id !== actorId) throw new Error("Only the game host can advance or finish this game.");
    const nextRound = session.current_round + 1;
    const finished = finish || nextRound >= session.question_ids.length;
    await client.query(
      "UPDATE community_game_sessions SET current_round = $1, status = $2, finished_at = CASE WHEN $2 = 'finished' THEN NOW() ELSE finished_at END WHERE id = $3 AND guild_id = $4",
      [finished ? session.current_round : nextRound, finished ? "finished" : "active", sessionId, guildId],
    );
    return { round: finished ? session.question_ids.length : nextRound + 1, total: session.question_ids.length, finished };
  });
}
export async function getGameLeaderboard(guildId: string, sessionId: string): Promise<GameLeaderboardEntry[]> {
  const session = await queryOne<{ game_mode: GameMode }>("SELECT game_mode FROM community_game_sessions WHERE id = $1 AND guild_id = $2", [sessionId, guildId]);
  if (!session) return [];
  if (session.game_mode !== "individual") return query(
    `SELECT NULL::text AS user_id, t.id::text AS team_id, t.name AS team_name, COUNT(DISTINCT p.user_id)::int AS member_count,
       COALESCE(SUM(CASE WHEN a.is_correct THEN 100 ELSE 0 END), 0)::int AS score,
       COUNT(*) FILTER (WHERE a.is_correct)::int AS correct, COUNT(a.user_id)::int AS answers
     FROM community_game_teams t JOIN community_game_sessions s ON s.id = t.session_id AND s.guild_id = $2
     LEFT JOIN community_game_participants p ON p.team_id = t.id AND p.session_id = t.session_id
     LEFT JOIN community_game_answers a ON a.session_id = t.session_id AND a.user_id = p.user_id
     WHERE t.session_id = $1 GROUP BY t.id, t.name, t.team_number ORDER BY score DESC, correct DESC, t.team_number ASC`,
    [sessionId, guildId],
  );
  return query(
    `SELECT p.user_id::text AS user_id, NULL::text AS team_id, NULL::text AS team_name, 1::int AS member_count,
       COALESCE(SUM(CASE WHEN a.is_correct THEN 100 ELSE 0 END), 0)::int AS score,
       COUNT(*) FILTER (WHERE a.is_correct)::int AS correct, COUNT(a.user_id)::int AS answers
     FROM community_game_participants p JOIN community_game_sessions s ON s.id = p.session_id AND s.guild_id = $2
     LEFT JOIN community_game_answers a ON a.session_id = p.session_id AND a.user_id = p.user_id
     WHERE p.session_id = $1 GROUP BY p.user_id ORDER BY score DESC, correct DESC, p.user_id ASC LIMIT 25`,
    [sessionId, guildId],
  );
}