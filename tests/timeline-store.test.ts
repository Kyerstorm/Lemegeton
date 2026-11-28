import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { closeDatabase, initDatabase } from "../src/utility/database/libsql/database.js";
import {
  saveTimelineEvents,
  listTimelineEvents,
  createTimelineCorrectionRequest,
  listTimelineCorrectionRequests,
  reviewTimelineCorrectionRequest,
  listApprovedTimelineCorrections,
} from "../helpers/media/timeline-store.js";
import { normalizeTimelineDate } from "../helpers/media/timeline-events.js";

test("timeline provider events persist by provider identity and sequence type", async () => {
  const directory = await mkdtemp(join(tmpdir(), "lemegeton-timeline-store-"));
  await initDatabase({ path: join(directory, "bot.db"), primaryGuildId: null });
  try {
    await saveTimelineEvents({
      provider: "anilist:anime", providerId: "123",
      sequenceType: "release",
      events: [{
        id: "anilist:123", title: "Example series", description: null,
        date: normalizeTimelineDate("2020"), eventType: "First release",
        sequenceType: "release", sourceName: "AniList", sourceUrl: "https://anilist.co/anime/123",
      }],
    });
    const events = await listTimelineEvents("anilist:anime", "123", "release");
    assert.equal(events.length, 1);
    assert.equal(events[0]?.date.precision, "year");
    assert.equal(events[0]?.date.value, "2020");
    assert.equal((await listTimelineEvents("anilist:anime", "123", "publication")).length, 0);
  } finally {
    await closeDatabase();
    await rm(directory, { recursive: true, force: true });
  }
});

test("timeline correction submissions are guild scoped and require HTTPS evidence", async () => {
  const directory = await mkdtemp(join(tmpdir(), "lemegeton-timeline-correction-"));
  await initDatabase({ path: join(directory, "bot.db"), primaryGuildId: null });
  try {
    const result = await createTimelineCorrectionRequest({
      guildId: "111111111111111111",
      provider: "anilist:anime",
      providerId: "123",
      entityTitle: "Example series",
      sequenceType: "release",
      eventKey: "anilist:123",
      proposedDate: "2020-04",
      evidenceUrl: "https://example.com/evidence",
      createdBy: "222222222222222222",
    });
    assert.ok(result);
    assert.equal((await listTimelineCorrectionRequests("111111111111111111")).length, 1);
    assert.equal((await listTimelineCorrectionRequests("222222222222222222")).length, 0);
    await assert.rejects(() => reviewTimelineCorrectionRequest({
      guildId: "111111111111111111",
      requestId: result!,
      reviewerId: "222222222222222222",
      decision: "approved",
    }), /cannot review their own/);
    assert.equal(await reviewTimelineCorrectionRequest({
      guildId: "111111111111111111",
      requestId: result!,
      reviewerId: "333333333333333333",
      decision: "approved",
      note: "Evidence confirms the month.",
    }), true);
    assert.equal((await listTimelineCorrectionRequests("111111111111111111")).length, 0);
    const approved = await listApprovedTimelineCorrections({
      guildId: "111111111111111111",
      provider: "anilist:anime",
      providerId: "123",
      sequenceType: "release",
      eventKey: "anilist:123",
    });
    assert.equal(approved[0]?.proposed_value, "2020-04");
    assert.equal(approved[0]?.evidence_url, "https://example.com/evidence");
    assert.equal(await reviewTimelineCorrectionRequest({
      guildId: "222222222222222222",
      requestId: result!,
      reviewerId: "444444444444444444",
      decision: "rejected",
    }), false);
    await assert.rejects(() => createTimelineCorrectionRequest({
      guildId: "111111111111111111",
      provider: "anilist:anime",
      providerId: "123",
      entityTitle: "Example series",
      sequenceType: "release",
      eventKey: "anilist:123",
      proposedDate: "2020-04",
      evidenceUrl: "http://example.com/evidence",
      createdBy: "222222222222222222",
    }), /HTTPS/);
  } finally {
    await closeDatabase();
    await rm(directory, { recursive: true, force: true });
  }
});
