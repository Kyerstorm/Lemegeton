import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { closeDatabase, initDatabase } from "../src/utility/database/libsql/database.js";
import {
  addExchangeCandidate, addExchangeClarification, closeExchangeRequest, createExchangeRequest,
  findSimilarExchangeRequests, getExchangeCandidateReport, getExchangeRequest, listExchangeCandidateReports,
  listExchangeRequests, rateExchangeCandidate, removeExchangeCandidate, reportExchangeCandidate,
  reviewExchangeCandidateReport, setExchangeCandidateShortlist, setExchangeRequestVisibility,
} from "../helpers/community/exchange.js";

test("exchange requests and recommendations stay in their guild", async () => {
  const directory = await mkdtemp(join(tmpdir(), "lemegeton-exchange-"));
  await initDatabase({ path: join(directory, "bot.db"), primaryGuildId: null });
  try {
    const requestId = await createExchangeRequest({
      guildId: "111111111111111111", ownerId: "222222222222222222",
      title: "Short science fiction", description: "Looking for a short science fiction story.",
      mediaCategory: "book", preferences: "Standalone, thoughtful", exclusions: "No long series",
    });
    const candidateId = await addExchangeCandidate({
      guildId: "111111111111111111", requestId, submittedBy: "333333333333333333",
      title: "Example story", sourceUrl: "https://example.com/story",
      explanation: "A compact standalone with a similar theme.", caveat: "More reflective than action-focused.",
    });
    assert.equal((await getExchangeRequest("222222222222222222", requestId)), null);
    assert.equal((await listExchangeRequests("222222222222222222")).length, 0);
    await assert.rejects(() => setExchangeCandidateShortlist({
      guildId: "111111111111111111", requestId, candidateId,
      ownerId: "333333333333333333", shortlisted: true,
    }), /Only the request owner/);
    await setExchangeCandidateShortlist({
      guildId: "111111111111111111", requestId, candidateId,
      ownerId: "222222222222222222", shortlisted: true,
    });
    assert.equal((await getExchangeRequest("111111111111111111", requestId))?.candidates[0]?.is_shortlisted, 1);
    await assert.rejects(() => closeExchangeRequest({
      guildId: "111111111111111111", requestId, actorId: "333333333333333333",
    }), /Only the request owner/);
    await closeExchangeRequest({ guildId: "111111111111111111", requestId, actorId: "222222222222222222", solved: true });
    assert.equal((await listExchangeRequests("111111111111111111")).length, 0);
  } finally {
    await closeDatabase();
    await rm(directory,{recursive:true,force:true});
  }
});

test("Exchange visibility, provider feedback, clarifications and reports stay guild-scoped", async () => {
  const directory = await mkdtemp(join(tmpdir(), "lemegeton-exchange-workflow-"));
  await initDatabase({ path: join(directory, "bot.db"), primaryGuildId: null });
  try {
    const requestId = await createExchangeRequest({
      guildId: "111111111111111111",
      ownerId: "222222222222222222",
      title: "Short science fiction",
      description: "A thoughtful standalone short story.",
      mediaCategory: "book",
    });
    const candidateId = await addExchangeCandidate({
      guildId: "111111111111111111",
      requestId,
      submittedBy: "333333333333333333",
      title: "The Example",
      sourceUrl: "https://example.com/example",
      explanation: "It is short, standalone and thematically similar.",
    });

    const duplicateRequestId = await createExchangeRequest({
      guildId: "111111111111111111",
      ownerId: "777777777777777777",
      title: "Short science fiction",
      description: "A second request with a similar title.",
    });
    const suggestions = await findSimilarExchangeRequests({
      guildId: "111111111111111111",
      viewerId: "444444444444444444",
      title: "Short science fiction",
      excludeRequestId: requestId,
    });
    assert.equal(suggestions.length, 1);
    assert.equal(suggestions[0]?.id, duplicateRequestId);

    await addExchangeClarification({
      guildId: "111111111111111111",
      requestId,
      authorId: "333333333333333333",
      candidateId,
      message: "Would a translated edition still fit?",
    });
    const ownerView = await getExchangeRequest("111111111111111111", requestId, "222222222222222222");
    assert.equal(ownerView?.clarifications.length, 1);
    assert.equal(ownerView?.clarifications[0]?.message, "Would a translated edition still fit?");
    for (let index = 1; index < 10; index += 1) {
      await addExchangeClarification({
        guildId: "111111111111111111",
        requestId,
        authorId: "333333333333333333",
        message: "Follow-up " + index,
      });
    }
    await assert.rejects(() => addExchangeClarification({
      guildId: "111111111111111111",
      requestId,
      authorId: "333333333333333333",
      message: "The eleventh clarification should be rate limited.",
    }), /no longer available/);

    await rateExchangeCandidate({
      guildId: "111111111111111111",
      requestId,
      candidateId,
      ownerId: "222222222222222222",
      feedback: "good_match",
    });
    assert.equal((await getExchangeRequest("111111111111111111", requestId, "222222222222222222"))?.candidates[0]?.owner_feedback, "good_match");
    await assert.rejects(() => rateExchangeCandidate({
      guildId: "111111111111111111",
      requestId,
      candidateId,
      ownerId: "333333333333333333",
      feedback: "not_match",
    }), /Only the request owner/);

    const reportId = await reportExchangeCandidate({
      guildId: "111111111111111111",
      requestId,
      candidateId,
      reportedBy: "444444444444444444",
      reason: "This recommendation is unrelated to the request.",
    });
    await assert.rejects(() => reportExchangeCandidate({
      guildId: "111111111111111111",
      requestId,
      candidateId,
      reportedBy: "444444444444444444",
      reason: "Duplicate report.",
    }), /already been reported/);
    const reports = await listExchangeCandidateReports("111111111111111111");
    assert.equal(reports.length, 1);
    assert.equal((await getExchangeCandidateReport("222222222222222222", reportId)), null);
    await assert.rejects(() => reviewExchangeCandidateReport({
      guildId: "111111111111111111",
      reportId,
      reviewerId: "444444444444444444",
      decision: "dismissed",
    }), /cannot review their own/);
    assert.equal(await reviewExchangeCandidateReport({
      guildId: "111111111111111111",
      reportId,
      reviewerId: "555555555555555555",
      decision: "reviewed",
    }), true);
    assert.equal((await listExchangeCandidateReports("111111111111111111")).length, 0);

    await setExchangeRequestVisibility({
      guildId: "111111111111111111",
      requestId,
      ownerId: "222222222222222222",
      visibility: "restricted",
    });
    assert.equal(await getExchangeRequest("111111111111111111", requestId, "333333333333333333"), null);
    assert.equal((await listExchangeRequests("111111111111111111", 15, "333333333333333333")).length, 0);
    assert.ok(await getExchangeRequest("111111111111111111", requestId, "222222222222222222"));
    await assert.rejects(() => addExchangeCandidate({
      guildId: "111111111111111111",
      requestId,
      submittedBy: "333333333333333333",
      title: "Hidden request attempt",
      sourceUrl: "https://example.com/hidden",
      explanation: "Attempt to submit into a restricted request.",
    }), /not found in this server/);
    await assert.rejects(() => setExchangeRequestVisibility({
      guildId: "111111111111111111",
      requestId,
      ownerId: "333333333333333333",
      visibility: "guild",
    }), /Only the owner/);
    await removeExchangeCandidate({
      guildId: "111111111111111111",
      requestId,
      candidateId,
      actorId: "555555555555555555",
      canModerate: true,
    });
    assert.equal((await getExchangeRequest("111111111111111111", requestId, "222222222222222222"))?.candidates.length, 0);
  } finally {
    await closeDatabase();
    await rm(directory,{recursive:true,force:true});
  }
});
