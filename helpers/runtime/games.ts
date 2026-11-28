import type { DatabaseConnection } from "../../src/utility/database/libsql/database.js";
import { query, queryOne, transaction } from "../../src/utility/database/libsql/database.js";
import { cleanText, isValidHttpsUrl } from "../security/security.js";

export type QuizDifficulty = "easy" | "standard" | "hard" | "expert";
export type MediaClueCategory = "title" | "creator" | "release" | "franchise" | "adaptation" | "game" | "genre" | "format" | "studio" | "platform" | "character" | "series" | "word" | "connection" | "relationship" | "chronology";
export type QuizPackMode = "trivia" | "guessing" | "mystery" | "challenge" | "puzzle";
export interface MediaClue { category: MediaClueCategory; text: string; }
export interface QuizQuestion {
  id: string;
  question: string;
  correct_answer: string;
  accepted_answers: string[];
  options: string[];
  source_url: string;
  media_title: string | null;
  difficulty: QuizDifficulty;
  clues: MediaClue[];
  pack_mode: QuizPackMode;
}
export interface EditableQuizQuestion { id: string; contributor_id: string; question: string; correct_answer: string; accepted_answers: string[]; source_url: string; difficulty: QuizDifficulty; revision: number; }
export interface QuizPackSummary {
  id: string; creator_id: string; title: string; description: string; mode: QuizPackMode;
  status: string; question_count: number; pending_count: number;
}
export interface ActiveGameSession {
  id: string; channel_id: string; message_id: string | null; host_id: string; title: string;
  mode: QuizPackMode; game_mode: GameMode; current_round: number; question_count: number;
  participant_count: number; created_at: Date | string;
}
export interface QuizQuestionRevision { revision: number; snapshot: { question: string; correct_answer: string; accepted_answers: string[]; source_url: string; difficulty: QuizDifficulty }; changed_by: string; changed_at: string; }
export type GameMode = "individual" | "teams" | "cooperative";
export interface GameSession {
  id: string;
  guild_id: string;
  clue_index: number;
  channel_id: string;
  message_id: string | null;
  pack_id: string;
  host_id: string;
  question_ids: string[];
  current_round: number;
  status: string;
  game_mode: GameMode;
  pack_mode: QuizPackMode;
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
export function normalizeMediaClues(values: readonly string[]): MediaClue[] {
  const allowed = new Set<MediaClueCategory>(["title", "creator", "release", "franchise", "adaptation", "game", "genre", "format", "studio", "platform", "character", "series", "word", "connection", "relationship", "chronology"]);
  const entries = values.flatMap(value => value.split(/\r?\n|\|/)).map(value => value.trim()).filter(Boolean);
  if (entries.length > 8) throw new Error("A guessing or mystery question can have up to eight clues.");
  return entries.map(entry => {
    const match = entry.match(/^([a-z]+)\s*:\s*(.+)$/i);
    const category = match?.[1]?.toLowerCase() as MediaClueCategory | undefined;
    const text = match?.[2] ? cleanText(match[2], 180) : "";
    if (!category || !allowed.has(category)) throw new Error("Clues must use a supported category such as title, creator, release, franchise, adaptation or game, followed by a colon.");
    if (!text) throw new Error("Each clue must include text after its category.");
    return { category, text };
  });
}
export function normalizeQuizDifficulty(value: string): QuizDifficulty {
  const valueNormalized = value.trim().toLowerCase();
  if (valueNormalized === "easy" || valueNormalized === "standard" || valueNormalized === "hard" || valueNormalized === "expert") return valueNormalized;
  throw new Error("Choose easy, standard, hard or expert difficulty.");
}
function normalizeAnswer(value: string): string {
  return cleanText(value, 200).toLocaleLowerCase("en").replace(/[^\p{L}\p{N}]+/gu, " ").trim();
}
export function normalizeMultipleChoiceOptions(correctAnswer: string, values: readonly string[]): string[] {
  if (!values.length) return [];
  const options = values.map(value => cleanText(value, 150));
  if (options.length < 2 || options.length > 4 || options.some(value => !value)) {
    throw new Error("Multiple-choice trivia needs two to four non-empty choices.");
  }
  const keys = options.map(normalizeAnswer);
  if (new Set(keys).size !== keys.length) throw new Error("Multiple-choice options must be distinct.");
  if (!keys.includes(normalizeAnswer(correctAnswer))) {
    throw new Error("The correct answer must be included in the multiple-choice options.");
  }
  return options;
}
export function resolveQuizAnswer(
  answer: string, correctAnswer: string, acceptedAnswers: readonly string[] = [], options: readonly string[] = [],
): boolean {
  const trimmed = answer.trim();
  const candidate = /^[1-4]$/.test(trimmed) ? options[Number(trimmed) - 1] ?? trimmed : trimmed;
  return [correctAnswer, ...acceptedAnswers].some(value => normalizeAnswer(value) === normalizeAnswer(candidate));
}
export function chooseBalancedTeam<T extends { id: string; member_count: number; team_number: number }>(teams: readonly T[]): T | null {
  return [...teams].sort((a, b) => a.member_count - b.member_count || a.team_number - b.team_number)[0] ?? null;
}
async function ensureGameParticipant(client: DatabaseConnection, sessionId: string, userId: string, gameMode: GameMode): Promise<string | null> {
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
export function normalizeQuizPackMode(value: string): QuizPackMode {
  if (value === "trivia" || value === "guessing" || value === "mystery" || value === "challenge" || value === "puzzle") return value;
  throw new Error("Choose trivia, guessing, mystery, challenge or puzzle.");
}
export function validateQuizQuestionClues(mode: QuizPackMode, clues: readonly MediaClue[]): void {
  if (mode === "trivia") {
    if (clues.length) throw new Error("Trivia questions use an answer prompt, not layered media clues.");
    return;
  }
  if (mode === "guessing") {
    if (!clues.length) throw new Error("Guessing questions need at least one category-labelled identification clue.");
    return;
  }
  if (mode === "mystery") {
    if (clues.length < 2 || new Set(clues.map(clue => clue.category)).size < 2) {
      throw new Error("Mystery questions need at least two clues from different categories.");
    }
    return;
  }
  if (!clues.length) throw new Error("This media game mode needs at least one category-labelled clue.");
  if (mode === "puzzle" && !clues.some(clue =>
    ["word", "connection", "relationship", "chronology", "franchise", "adaptation"].includes(clue.category),
  )) {
    throw new Error("Puzzle packs need at least one word, connection, relationship, chronology, franchise or adaptation clue.");
  }
}
export async function createQuizPack(guildId: string, creatorId: string, title: string, description: string, mode: QuizPackMode = "trivia"): Promise<string> {
  mode = normalizeQuizPackMode(mode);
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
export async function addQuizQuestion(guildId: string, packId: string, contributorId: string, question: string, answer: string, acceptedAnswers: string[], sourceUrl: string, mediaTitle?: string, options: string[] = [], difficulty = "standard", clueEntries: string[] = []): Promise<string> {
  const pack = await queryOne<{ id: string; status: string; mode: QuizPackMode }>("SELECT id, status, mode FROM community_quiz_packs WHERE id = $1 AND guild_id = $2", [packId, guildId]);
  if (!pack || pack.status === "rejected") throw new Error("That quiz pack was not found or was rejected.");
  const cleanQuestion = cleanText(question, 500), cleanAnswer = cleanText(answer, 200);
  if (!cleanQuestion || !cleanAnswer) throw new Error("A question and correct answer are required.");
  const source = isValidHttpsUrl(sourceUrl, true);
  if (!source) throw new Error("A valid HTTPS source is required.");
  const cleanDifficulty = normalizeQuizDifficulty(difficulty);
  const clues = pack.mode === "trivia" ? [] : normalizeMediaClues(clueEntries.length ? clueEntries : acceptedAnswers);
  validateQuizQuestionClues(pack.mode, clues);
  const accepted = pack.mode === "trivia" ? [...new Set([cleanAnswer, ...acceptedAnswers.map(item => cleanText(item, 200))].filter(Boolean))].slice(0, 10) : [cleanAnswer];
  if (pack.mode !== "trivia" && options.length) throw new Error("Multiple-choice options are supported for Trivia packs only.");
  const cleanOptions = normalizeMultipleChoiceOptions(cleanAnswer, options);
  const row = await queryOne<{ id: string }>(
    `INSERT INTO community_quiz_questions (pack_id, contributor_id, media_title, question, correct_answer, accepted_answers, options, source_url, difficulty, clues, status)
     VALUES ($1,$2,$3,$4,$5,$6,$7::JSONB,$8,$9,$10::JSONB,'pending') RETURNING id`,
    [packId, contributorId, mediaTitle ? cleanText(mediaTitle, 200) : null, cleanQuestion, cleanAnswer, accepted, JSON.stringify(cleanOptions), source, cleanDifficulty, JSON.stringify(clues)],
  );
  if (!row) throw new Error("The question could not be saved.");
  return row.id;
}

export async function getQuizQuestionForEditing(
  guildId: string,
  questionId: string,
  actorId: string,
  canManage: boolean,
): Promise<EditableQuizQuestion> {
  const question = await queryOne<EditableQuizQuestion>(
    `SELECT q.id::text AS id, q.contributor_id::text AS contributor_id, q.question,
            q.correct_answer, q.accepted_answers, q.source_url, q.difficulty, q.revision
       FROM community_quiz_questions q
       JOIN community_quiz_packs p ON p.id = q.pack_id
      WHERE q.id = $1 AND p.guild_id = $2`,
    [questionId, guildId],
  );
  if (!question || (!canManage && question.contributor_id !== actorId)) {
    throw new Error("Only the original contributor or a server manager can edit this question.");
  }
  return question;
}

export async function editQuizQuestion(
  guildId: string,
  questionId: string,
  actorId: string,
  canManage: boolean,
  questionText: string,
  answer: string,
  acceptedAnswers: string[],
  sourceUrl: string,
  difficulty: string,
): Promise<number> {
  const cleanQuestion = cleanText(questionText, 500);
  const cleanAnswer = cleanText(answer, 200);
  if (!cleanQuestion || !cleanAnswer) throw new Error("A question and correct answer are required.");
  const source = isValidHttpsUrl(sourceUrl, true);
  if (!source) throw new Error("A valid HTTPS source is required.");
  const cleanDifficulty = normalizeQuizDifficulty(difficulty);
  const accepted = [...new Set([cleanAnswer, ...acceptedAnswers.map(item => cleanText(item, 200))].filter(Boolean))].slice(0, 10);

  return transaction(async client => {
    const result = await client.query<EditableQuizQuestion>(
      `SELECT q.id::text AS id, q.contributor_id::text AS contributor_id, q.question,
              q.correct_answer, q.accepted_answers, q.source_url, q.difficulty, q.revision
         FROM community_quiz_questions q
         JOIN community_quiz_packs p ON p.id = q.pack_id
        WHERE q.id = $1 AND p.guild_id = $2
        FOR UPDATE OF q`,
      [questionId, guildId],
    );
    const current = result.rows[0];
    if (!current || (!canManage && current.contributor_id !== actorId)) {
      throw new Error("Only the original contributor or a server manager can edit this question.");
    }
    const active = await client.query(
      "SELECT 1 FROM community_game_sessions WHERE guild_id = $1 AND status = 'active' AND $2::BIGINT = ANY(question_ids) LIMIT 1",
      [guildId, questionId],
    );
    if (active.rowCount) {
      throw new Error("This question is part of an active game and cannot be edited until the game finishes.");
    }
    await client.query(
      `INSERT INTO community_quiz_question_revisions (question_id, revision, snapshot, changed_by)
       VALUES ($1, $2, jsonb_build_object(
         'question', $3, 'correct_answer', $4, 'accepted_answers', $5::TEXT[],
         'source_url', $6, 'difficulty', $7
       ), $8)`,
      [questionId, current.revision, current.question, current.correct_answer, current.accepted_answers, current.source_url, current.difficulty, actorId],
    );
    const updated = await client.query<{ revision: number }>(
      `UPDATE community_quiz_questions
       SET question = $1, correct_answer = $2, accepted_answers = $3,
           source_url = $4, difficulty = $5, revision = revision + 1,
           status = 'pending', reviewed_by = NULL
       WHERE id = $6 RETURNING revision`,
      [cleanQuestion, cleanAnswer, accepted, source, cleanDifficulty, questionId],
    );
    const revision = updated.rows[0]?.revision;
    if (!revision) throw new Error("The question revision could not be saved.");
    return revision;
  });
}

export async function getQuizQuestionRevisionHistory(
  guildId: string,
  questionId: string,
  actorId: string,
  canManage: boolean,
): Promise<{ currentRevision: number; revisions: QuizQuestionRevision[] }> {
  const current = await queryOne<{ contributor_id: string; revision: number }>(
    `SELECT q.contributor_id::text AS contributor_id, q.revision
       FROM community_quiz_questions q
       JOIN community_quiz_packs p ON p.id = q.pack_id
      WHERE q.id = $1 AND p.guild_id = $2`,
    [questionId, guildId],
  );
  if (!current || (!canManage && current.contributor_id !== actorId)) {
    throw new Error("Only the original contributor or a server manager can view this question's history.");
  }
  const revisions = await query<QuizQuestionRevision>(
    `SELECT revision, snapshot, changed_by::text AS changed_by, changed_at::text AS changed_at
       FROM community_quiz_question_revisions
      WHERE question_id = $1
      ORDER BY revision DESC LIMIT 10`,
    [questionId],
  );
  return { currentRevision: current.revision, revisions };
}

export async function updateQuizPack(
  guildId: string, packId: string, actorId: string, canManage: boolean, title: string, description: string,
): Promise<void> {
  const cleanTitle = cleanText(title, 160);
  if (!cleanTitle) throw new Error("A question pack title is required.");
  const row = await queryOne<{ id: string }>(
    `UPDATE community_quiz_packs SET title=$1,description=$2
      WHERE id=$3 AND guild_id=$4 AND status IN ('pending','approved') AND (creator_id=$5 OR $6::boolean)
      RETURNING id::text AS id`,
    [cleanTitle, cleanText(description, 1_000), packId, guildId, actorId, canManage],
  );
  if (!row) throw new Error("That editable pack was not found, or you do not own it.");
}
export async function bulkReviewQuizQuestions(
  guildId: string, reviewerId: string, actions: readonly { id: string; approve: boolean }[],
): Promise<number> {
  if (!actions.length || actions.length > 12) throw new Error("Choose between one and twelve questions for bulk review.");
  const ids = actions.map(action => action.id);
  if (ids.some(id => !/^\d{1,20}$/.test(id)) || new Set(ids).size !== ids.length) {
    throw new Error("Bulk review contains an invalid or duplicate question.");
  }
  return transaction(async client => {
    let reviewed = 0;
    for (const action of actions) {
      const result = await client.query(
        `UPDATE community_quiz_questions q SET status=$1,reviewed_by=$2
          FROM community_quiz_packs p
          WHERE q.pack_id=p.id AND p.guild_id=$3 AND p.status='approved'
            AND q.id=$4 AND q.status='pending'
          RETURNING q.id`,
        [action.approve ? "approved" : "rejected", reviewerId, guildId, action.id],
      );
      if (result.rowCount !== 1) throw new Error("A selected question is no longer pending in an approved server pack. No questions were changed.");
      reviewed += 1;
    }
    return reviewed;
  });
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
export async function listQuizPacks(guildId: string, status = "approved"): Promise<QuizPackSummary[]> {
  if (!["all", "pending", "approved", "rejected"].includes(status)) throw new Error("Choose all, pending, approved or rejected pack status.");
  return query<QuizPackSummary>(
    `SELECT p.id::text AS id,p.creator_id::text AS creator_id,p.title,p.description,p.mode,p.status,
            COUNT(q.id) FILTER (WHERE q.status='approved' AND (p.mode='trivia' OR jsonb_array_length(q.clues)>0))::INT AS question_count,
            COUNT(q.id) FILTER (WHERE q.status='pending')::INT AS pending_count
       FROM community_quiz_packs p LEFT JOIN community_quiz_questions q ON q.pack_id=p.id
      WHERE p.guild_id=$1 AND ($2='all' OR p.status=$2)
      GROUP BY p.id ORDER BY p.created_at DESC LIMIT 25`,
    [guildId, status],
  );
}
export async function pendingQuizQuestions(guildId: string): Promise<Array<{ id: string; pack_id: string; title: string; question: string; source_url: string; difficulty: QuizDifficulty; mode: QuizPackMode }>> {
  return query(
    `SELECT q.id::text AS id,q.pack_id::text AS pack_id,p.title,q.question,q.source_url,q.difficulty,p.mode
       FROM community_quiz_questions q JOIN community_quiz_packs p ON p.id=q.pack_id
      WHERE p.guild_id=$1 AND p.status='approved' AND q.status='pending'
      ORDER BY q.created_at ASC LIMIT 12`,
    [guildId],
  );
}
export async function startGame(guildId: string, channelId: string, hostId: string, packId: string, rounds = 5, gameMode: GameMode = "individual"): Promise<GameSession> {
  if (!["individual", "teams", "cooperative"].includes(gameMode)) throw new Error("Choose individual, teams or cooperative game mode.");
  if (!Number.isFinite(rounds) || !Number.isInteger(rounds) || rounds < 1 || rounds > 10) throw new Error("A game must contain between one and ten rounds.");
  const count = rounds;
  return transaction(async (client: DatabaseConnection) => {
    const packResult = await client.query("SELECT id, title, status, mode FROM community_quiz_packs WHERE id = $1 AND guild_id = $2", [packId, guildId]);
    const pack = packResult.rows[0] as { id: string; title: string; status: string; mode: QuizPackMode } | undefined;
    if (!pack || pack.status !== "approved") throw new Error("That quiz pack is not approved for play.");
    const questions = await client.query("SELECT q.id FROM community_quiz_questions q WHERE q.pack_id = $1 AND q.status = 'approved' AND ($2 = 'trivia' OR jsonb_array_length(q.clues) > 0) ORDER BY RANDOM() LIMIT $3 FOR SHARE OF q", [packId, pack.mode, count]);
    const questionIds = questions.rows.map(row => String((row as { id: string }).id));
    if (!questionIds.length) throw new Error("That pack does not contain approved questions.");
    const inserted = await client.query(
      `INSERT INTO community_game_sessions (guild_id, channel_id, pack_id, host_id, question_ids, current_round, status, game_mode)
       VALUES ($1, $2, $3, $4, $5::BIGINT[], 0, 'active', $6) RETURNING *`,
      [guildId, channelId, packId, hostId, questionIds, gameMode],
    );
    const row = inserted.rows[0] as unknown as GameSession;
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
    return { ...row, title: pack.title, pack_mode: pack.mode };
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
export async function listActiveGameSessions(guildId: string): Promise<ActiveGameSession[]> {
  return query<ActiveGameSession>(
    `SELECT s.id::text AS id,s.channel_id::text AS channel_id,s.message_id::text AS message_id,
            s.host_id::text AS host_id,p.title,p.mode,s.game_mode,s.current_round,
            cardinality(s.question_ids)::INT AS question_count,
            COUNT(DISTINCT participant.user_id)::INT AS participant_count,s.created_at
       FROM community_game_sessions s JOIN community_quiz_packs p ON p.id=s.pack_id
       LEFT JOIN community_game_participants participant ON participant.session_id=s.id
      WHERE s.guild_id=$1 AND s.status='active' AND p.guild_id=$1
      GROUP BY s.id,p.title,p.mode
      ORDER BY s.created_at DESC LIMIT 20`,
    [guildId],
  );
}
export async function cancelGameSession(guildId: string, sessionId: string, hostId: string): Promise<boolean> {
  const row = await queryOne<{ id: string }>(
    `UPDATE community_game_sessions SET status='cancelled',finished_at=NOW()
      WHERE id=$1 AND guild_id=$2 AND host_id=$3 AND status='active'
      RETURNING id::text AS id`,
    [sessionId,guildId,hostId],
  );
  return Boolean(row);
}
export async function getGameSession(guildId: string, sessionId: string): Promise<GameSession | null> {
  return queryOne<GameSession & { title: string }>(
    `SELECT s.*, p.title, p.mode AS pack_mode FROM community_game_sessions s JOIN community_quiz_packs p ON p.id = s.pack_id
     WHERE s.id = $1 AND s.guild_id = $2`,
    [sessionId, guildId],
  );
}
export async function getCurrentGameQuestion(guildId: string, sessionId: string): Promise<QuizQuestion | null> {
  return queryOne<QuizQuestion>(
    `SELECT q.id, q.question, q.correct_answer, q.accepted_answers, q.options, q.source_url, q.media_title, q.difficulty, q.clues, p.mode AS pack_mode
     FROM community_game_sessions s JOIN community_quiz_questions q ON q.id = s.question_ids[s.current_round + 1]
     JOIN community_quiz_packs p ON p.id = s.pack_id
     WHERE s.id = $1 AND s.guild_id = $2 AND s.status = 'active'`,
    [sessionId, guildId],
  );
}
export async function answerGameQuestion(guildId: string, sessionId: string, userId: string, answer: string, expectedRound?: number): Promise<{ correct: boolean; round: number; total: number; sourceUrl: string; finished: boolean; teamName: string | null }> {
  return transaction(async client => {
    const result = await client.query("SELECT id, question_ids, current_round, status, game_mode FROM community_game_sessions WHERE id = $1 AND guild_id = $2 FOR UPDATE", [sessionId, guildId]);
    const session = result.rows[0] as { id: string; question_ids: string[]; current_round: number; status: string; game_mode: GameMode } | undefined;
    if (!session || session.status !== "active") throw new Error("That game is not active.");
    if (expectedRound !== undefined && session.current_round !== expectedRound) {
      throw new Error("That answer form belongs to an earlier round. Use the current game message.");
    }
    const questionId = session.question_ids[session.current_round];
    if (!questionId) throw new Error("The current round has no question.");
    const teamName = await ensureGameParticipant(client, sessionId, userId, session.game_mode);
    const questionResult = await client.query("SELECT correct_answer, accepted_answers, options, source_url FROM community_quiz_questions WHERE id = $1 AND status = 'approved'", [questionId]);
    const question = questionResult.rows[0] as { correct_answer: string; accepted_answers: string[]; options: string[]; source_url: string } | undefined;
    if (!question) throw new Error("The current question is no longer available.");
    const existing = await client.query("SELECT 1 FROM community_game_answers WHERE session_id = $1 AND round_number = $2 AND user_id = $3", [sessionId, session.current_round, userId]);
    if (existing.rowCount) throw new Error("You have already answered this round.");
    const correct = resolveQuizAnswer(answer, question.correct_answer, question.accepted_answers ?? [], question.options ?? []);
    await client.query("INSERT INTO community_game_answers (session_id, round_number, question_id, user_id, answer, is_correct) VALUES ($1, $2, $3, $4, $5, $6)", [sessionId, session.current_round, questionId, userId, cleanText(answer, 200), correct]);
    return { correct, round: session.current_round + 1, total: session.question_ids.length, sourceUrl: question.source_url, finished: false, teamName };
  });
}
export async function advanceGame(guildId: string, sessionId: string, actorId: string, finish = false, expectedRound?: number): Promise<{ round: number; total: number; finished: boolean }> {
  return transaction(async (client) => {
    const result = await client.query("SELECT host_id, question_ids, current_round, status FROM community_game_sessions WHERE id = $1 AND guild_id = $2 FOR UPDATE", [sessionId, guildId]);
    const session = result.rows[0] as { host_id: string; question_ids: string[]; current_round: number; status: string } | undefined;
    if (!session || session.status !== "active") throw new Error("That game is not active.");
    if (session.host_id !== actorId) throw new Error("Only the game host can advance or finish this game.");
    if (expectedRound !== undefined && session.current_round !== expectedRound) {
      throw new Error("That control belongs to an earlier round. Refresh the current game message.");
    }
    const nextRound = session.current_round + 1;
    const finished = finish || nextRound >= session.question_ids.length;
    await client.query(
      "UPDATE community_game_sessions SET current_round = $1, status = $2::varchar, clue_index = CASE WHEN $2::varchar = 'active' THEN 0 ELSE clue_index END, finished_at = CASE WHEN $2::varchar = 'finished' THEN NOW() ELSE finished_at END WHERE id = $3 AND guild_id = $4",
      [finished ? session.current_round : nextRound, finished ? "finished" : "active", sessionId, guildId],
    );
    return { round: finished ? session.question_ids.length : nextRound + 1, total: session.question_ids.length, finished };
  });
}
export async function revealGameClue(guildId: string, sessionId: string, actorId: string, expectedRound?: number, expectedClueIndex?: number): Promise<{ clue: MediaClue; number: number; total: number }> {
  return transaction(async client => {
    const result = await client.query<{ host_id: string; question_ids: string[]; current_round: number; clue_index: number; status: string }>(
      "SELECT host_id, question_ids, current_round, clue_index, status FROM community_game_sessions WHERE id = $1 AND guild_id = $2 FOR UPDATE",
      [sessionId, guildId],
    );
    const session = result.rows[0];
    if (!session || session.status !== "active") throw new Error("That game is not active.");
    if (session.host_id !== actorId) throw new Error("Only the game host can reveal clues.");
    if (expectedRound !== undefined && session.current_round !== expectedRound) {
      throw new Error("That clue control belongs to an earlier round. Refresh the current game message.");
    }
    if (expectedClueIndex !== undefined && session.clue_index !== expectedClueIndex) {
      throw new Error("That clue has already been revealed. Use the current game message.");
    }
    const questionId = session.question_ids[session.current_round];
    if (!questionId) throw new Error("The current round has no question.");
    const question = await client.query<{ clues: MediaClue[] }>("SELECT clues FROM community_quiz_questions WHERE id = $1 AND status = 'approved'", [questionId]);
    const clues = question.rows[0]?.clues ?? [];
    const clue = clues[session.clue_index];
    if (!clue) throw new Error("There are no more clues for this question.");
    await client.query("UPDATE community_game_sessions SET clue_index = clue_index + 1 WHERE id = $1 AND guild_id = $2", [sessionId, guildId]);
    return { clue, number: session.clue_index + 1, total: clues.length };
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