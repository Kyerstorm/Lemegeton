import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { closeDatabase, initDatabase } from "../src/utility/database/libsql/database.js";
import {
  addIdentifyCandidate, addIdentifyEvidence, closeIdentifyCase, createIdentifyCase,
  findSimilarIdentifyCases, getIdentifyCase, getIdentifyCaseReport, listIdentifyCaseReports,
  listIdentifyCases, reportIdentifyCase, reviewIdentifyCaseReport, searchSolvedIdentifyCases,
  solveIdentifyCase, voteIdentifyCandidate,
} from "../helpers/community/identify.js";

test("identification cases, candidates and evidence are isolated by guild", async () => {
  const directory = await mkdtemp(join(tmpdir(), "lemegeton-identify-"));
  await initDatabase({ path: join(directory, "bot.db"), primaryGuildId: null });
  try {
    const caseId = await createIdentifyCase({
      guildId: "111111111111111111", ownerId: "222222222222222222",
      title: "Unknown animated series", description: "A character wore a red scarf.",
      mediaCategory: "anime", yearHint: "2000s",
    });
    const candidateId = await addIdentifyCandidate({
      guildId: "111111111111111111", caseId, submittedBy: "333333333333333333",
      title: "Example series", sourceUrl: "https://anilist.co/anime/123",
      provider: "anilist:anime", providerId: "123", explanation: "The red scarf appears in episode one.",
    });
    await addIdentifyEvidence({
      guildId: "111111111111111111", caseId, candidateId,
      submittedBy: "333333333333333333", description: "Episode still and official synopsis",
      sourceUrl: "https://example.com/evidence",
    });
    await voteIdentifyCandidate({
      guildId: "111111111111111111", caseId, candidateId,
      userId: "444444444444444444", stance: "support",
    });
    const loaded = await getIdentifyCase("111111111111111111", caseId);
    assert.equal(loaded?.candidates[0]?.support_count, 1);
    assert.equal(loaded?.evidence.length, 1);
    assert.equal(await getIdentifyCase("222222222222222222", caseId), null);
    assert.equal((await listIdentifyCases("222222222222222222")).length, 0);
    await reportIdentifyCase({
      guildId: "111111111111111111", caseId,
      reportedBy: "555555555555555555", reason: "Duplicate case",
    });
    const similar = await findSimilarIdentifyCases({
      guildId: "111111111111111111",
      title: "Unknown animated series",
      viewerId: "333333333333333333",
      excludeCaseId: caseId,
    });
    assert.equal(similar.length, 0);
    const reports = await listIdentifyCaseReports("111111111111111111");
    assert.equal(reports.length, 1);
    assert.equal(reports[0]?.case_id, caseId);
    assert.equal(await getIdentifyCaseReport("222222222222222222", reports[0]!.id), null);
    await assert.rejects(() => reviewIdentifyCaseReport({
      guildId: "111111111111111111",
      reportId: reports[0]!.id,
      reviewerId: "555555555555555555",
      decision: "dismissed",
    }), /reporter cannot review their own/);
    assert.equal(await reviewIdentifyCaseReport({
      guildId: "111111111111111111",
      reportId: reports[0]!.id,
      reviewerId: "666666666666666666",
      decision: "reviewed",
    }), true);
    assert.equal((await listIdentifyCaseReports("111111111111111111")).length, 0);
    await assert.rejects(() => closeIdentifyCase({
      guildId: "111111111111111111", caseId, actorId: "333333333333333333",
    }), /Only the case owner/);
    await solveIdentifyCase({
      guildId: "111111111111111111", caseId, candidateId, actorId: "222222222222222222",
    });
    assert.equal((await getIdentifyCase("111111111111111111", caseId))?.case.status, "solved");
    const solved = await searchSolvedIdentifyCases({
      guildId: "111111111111111111",
      queryText: "red scarf",
      viewerId: "222222222222222222",
    });
    assert.equal(solved.length, 1);
    assert.equal(solved[0]?.id, caseId);
  } finally {
    await closeDatabase();
    await rm(directory, { recursive: true, force: true });
  }
});

test("restricted identification cases stay within their owner or channel and managers", async () => {
  const directory = await mkdtemp(join(tmpdir(), "lemegeton-identify-restricted-"));
  await initDatabase({ path: join(directory, "bot.db"), primaryGuildId: null });
  try {
    const caseId = await createIdentifyCase({
      guildId: "111111111111111111",
      ownerId: "222222222222222222",
      channelId: "333333333333333333",
      visibility: "restricted",
      title: "Private memory",
      description: "A private clue about an obscure game.",
      mediaCategory: "game",
    });
    assert.equal(await getIdentifyCase("111111111111111111", caseId), null);
    assert.equal(await getIdentifyCase("111111111111111111", caseId, "444444444444444444", "555555555555555555"), null);
    assert.ok(await getIdentifyCase("111111111111111111", caseId, "444444444444444444", "333333333333333333"));
    assert.ok(await getIdentifyCase("111111111111111111", caseId, "222222222222222222", "555555555555555555"));
    assert.ok(await getIdentifyCase("111111111111111111", caseId, "666666666666666666", "555555555555555555", true));
    assert.equal((await listIdentifyCases("111111111111111111", 15, "444444444444444444", "555555555555555555")).length, 0);
    assert.equal((await listIdentifyCases("111111111111111111", 15, "444444444444444444", "333333333333333333")).length, 1);
    assert.equal((await listIdentifyCases("111111111111111111", 15, "666666666666666666", "555555555555555555", true)).length, 1);
    await assert.rejects(() => createIdentifyCase({
      guildId: "111111111111111111",
      ownerId: "222222222222222222",
      visibility: "restricted",
      title: "Missing channel",
      description: "A restricted case without a channel must be rejected.",
    }), /tied to its creating channel/);
  } finally {
    await closeDatabase();
    await rm(directory,{recursive:true,force:true});
  }
});
