import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { closeDatabase, initDatabase, query } from "../src/utility/database/libsql/database.js";
import {
  advanceGame,
  answerGameQuestion,
  revealGameClue,
} from "../helpers/runtime/games.js";

const guildId = "987654321098765432";
const hostId = "123456789012345671";
const playerId = "123456789012345672";

test("game controls reject stale rounds and concurrent duplicate clue/advance/answer actions", async () => {
  const directory = await mkdtemp(join(tmpdir(), "lemegeton-game-idempotency-"));

  try {
    await initDatabase({ path: join(directory, "bot.db"), primaryGuildId: guildId });

    const pack = await query<{ id: string }>(
      "INSERT INTO community_quiz_packs (guild_id, creator_id, title, mode, status) " +
      "VALUES ($1,$2,'Idempotency fixture','mystery','approved') RETURNING id::text AS id",
      [guildId, hostId],
    );
    const firstQuestion = await query<{ id: string }>(
      "INSERT INTO community_quiz_questions " +
      "(pack_id, contributor_id, question, correct_answer, source_url, status, clues) " +
      "VALUES ($1,$2,'Which media is described by the first clue?','Answer one','https://example.com/one','approved',$3::jsonb) " +
      "RETURNING id::text AS id",
      [pack[0]!.id, hostId, JSON.stringify([{ category: "title", text: "First round clue" }])],
    );
    const secondQuestion = await query<{ id: string }>(
      "INSERT INTO community_quiz_questions " +
      "(pack_id, contributor_id, question, correct_answer, source_url, status, clues) " +
      "VALUES ($1,$2,'Which media is described by the second clue?','Answer two','https://example.com/two','approved',$3::jsonb) " +
      "RETURNING id::text AS id",
      [pack[0]!.id, hostId, JSON.stringify([{ category: "creator", text: "Second round clue" }])],
    );
    const session = await query<{ id: string }>(
      "INSERT INTO community_game_sessions " +
      "(guild_id, channel_id, pack_id, host_id, question_ids, current_round, status, game_mode) " +
      "VALUES ($1,$2,$3,$4,$5,0,'active','individual') RETURNING id::text AS id",
      [guildId, "987654321098765432", pack[0]!.id, hostId, JSON.stringify([firstQuestion[0]!.id, secondQuestion[0]!.id])],
    );
    const sessionId = session[0]!.id;

    const clueAttempts = await Promise.allSettled([
      revealGameClue(guildId, sessionId, hostId, 0, 0),
      revealGameClue(guildId, sessionId, hostId, 0, 0),
    ]);
    assert.equal(clueAttempts.filter(item => item.status === "fulfilled").length, 1);
    assert.equal(clueAttempts.filter(item => item.status === "rejected").length, 1);
    const clueState = await query<{ clue_index: number }>(
      "SELECT clue_index FROM community_game_sessions WHERE id = $1",
      [sessionId],
    );
    assert.equal(clueState[0]?.clue_index, 1);

    const advanceAttempts = await Promise.allSettled([
      advanceGame(guildId, sessionId, hostId, false, 0),
      advanceGame(guildId, sessionId, hostId, false, 0),
    ]);
    assert.equal(advanceAttempts.filter(item => item.status === "fulfilled").length, 1);
    assert.equal(advanceAttempts.filter(item => item.status === "rejected").length, 1);
    const roundState = await query<{ current_round: number }>(
      "SELECT current_round FROM community_game_sessions WHERE id = $1",
      [sessionId],
    );
    assert.equal(roundState[0]?.current_round, 1);

    await assert.rejects(
      answerGameQuestion(guildId, sessionId, playerId, "Answer one", 0),
      /earlier round/i,
    );
    const answerAttempts = await Promise.allSettled([
      answerGameQuestion(guildId, sessionId, playerId, "Answer two", 1),
      answerGameQuestion(guildId, sessionId, playerId, "Answer two", 1),
    ]);
    assert.equal(answerAttempts.filter(item => item.status === "fulfilled").length, 1);
    assert.equal(answerAttempts.filter(item => item.status === "rejected").length, 1);
    const answers = await query<{ count: number }>(
      "SELECT COUNT(*)::INT AS count FROM community_game_answers WHERE session_id = $1 AND round_number = 1 AND user_id = $2",
      [sessionId, playerId],
    );
    assert.equal(answers[0]?.count, 1);

    await assert.rejects(
      revealGameClue(guildId, sessionId, hostId, 0, 1),
      /earlier round/i,
    );
  } finally {
    await closeDatabase().catch(() => undefined);
    await rm(directory, { recursive: true, force: true });
  }
});
