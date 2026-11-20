import test from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { Pool } from "pg";
import { closeDatabase, initDatabase, query } from "../database.js";
import type { DatabaseConfig } from "../helpers/runtime/config.js";
import {
  advanceGame,
  answerGameQuestion,
  revealGameClue,
} from "../helpers/runtime/games.js";

const databaseUrl = process.env.TEST_DATABASE_URL?.trim();
const guildId = "987654321098765432";
const hostId = "123456789012345671";
const playerId = "123456789012345672";

function testDatabaseSsl(parsedUrl: URL): boolean {
  const mode = parsedUrl.searchParams.get("sslmode")?.toLowerCase();
  if (mode === "disable") return false;
  if (mode && ["require", "verify-ca", "verify-full", "prefer", "allow"].includes(mode)) return true;
  const host = parsedUrl.hostname.replace(/^\[|\]$/g, "").toLowerCase();
  return !["localhost", "127.0.0.1", "::1"].includes(host);
}

test("game controls reject stale rounds and concurrent duplicate clue/advance/answer actions", {
  skip: databaseUrl ? false : "TEST_DATABASE_URL is required",
}, async () => {
  assert.ok(databaseUrl);
  const admin = new Pool({ connectionString: databaseUrl, ssl: testDatabaseSsl(new URL(databaseUrl)) });
  const schema = "lemegeton_game_idempotency_" + randomUUID().replaceAll("-", "");

  try {
    await admin.query(`CREATE SCHEMA "${schema}"`);
    const scopedUrl = new URL(databaseUrl);
    scopedUrl.searchParams.set("options", "-c search_path=" + schema);
    const parsedUrl = new URL(databaseUrl);
    const config: DatabaseConfig = {
      connectionString: scopedUrl.toString(),
      host: parsedUrl.hostname,
      port: Number(parsedUrl.port || 5432),
      database: decodeURIComponent(parsedUrl.pathname.replace(/^\//, "")),
      user: decodeURIComponent(parsedUrl.username),
      password: decodeURIComponent(parsedUrl.password),
      ssl: testDatabaseSsl(parsedUrl),
      poolSize: 4,
      primaryGuildId: guildId,
    };
    await initDatabase(config);

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
      "VALUES ($1,$2,$3,$4,ARRAY[$5::BIGINT,$6::BIGINT],0,'active','individual') RETURNING id::text AS id",
      [guildId, "987654321098765432", pack[0]!.id, hostId, firstQuestion[0]!.id, secondQuestion[0]!.id],
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
    await admin.query(`DROP SCHEMA IF EXISTS "${schema}" CASCADE`).catch(() => undefined);
    await admin.end();
  }
});
