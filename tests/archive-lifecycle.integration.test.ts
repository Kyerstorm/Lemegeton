import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { closeDatabase, initDatabase, query } from "../src/utility/database/libsql/database.js";
import {
  addEntryToCollection,
  addEntryToTrail,
  getArchiveTrailSteps,
  getCollectionItems,
  listArchiveCollections,
  listArchiveTrails,
  saveArchiveCollection,
  saveArchiveTrail,
} from "../helpers/archive/archive-collections.js";
import { configureArchiveAccess } from "../helpers/archive/archive-access.js";
import {
  createArchiveCollectionSpotlight,
  createArchiveSpotlight,
  listArchiveCollectionSpotlights,
  listArchiveSpotlights,
} from "../helpers/archive/archive-curation.js";
import { changeArchiveEntryVisibility, submitArchiveEntry } from "../helpers/archive/archive.js";

const guildA = "987654321098765432";
const guildB = "987654321098765433";
const ownerId = "123456789012345678";

async function createApprovedEntry(guildId: string, title: string, visibility: "server" | "global"): Promise<string> {
  const entryId = await submitArchiveEntry({
    guildId,
    userId: ownerId,
    category: "theories",
    title,
    content: "A short, attributed community theory.",
    mediaType: "Manga",
    tags: ["community"],
    spoiler: false,
    visibility,
    needsUpload: false,
  });
  await query("UPDATE community_archive_entries SET status = 'approved' WHERE id = $1", [entryId]);
  return entryId;
}

async function createCuratedViews(
  guildId: string,
  title: string,
  entryId: string,
  visibility: "server" | "global",
  startsAt: Date,
  endsAt: Date,
): Promise<{ collectionId: string; trailId: string; entrySpotlightId: string; collectionSpotlightId: string }> {
  const collectionId = await saveArchiveCollection(guildId, ownerId, title + " collection", "", visibility);
  await addEntryToCollection(guildId, ownerId, collectionId, entryId, "Curated reference");
  const trailId = await saveArchiveTrail(guildId, ownerId, title + " Trail", "A curated path.", visibility);
  await addEntryToTrail(guildId, ownerId, trailId, entryId, "The next step.");
  const entrySpotlightId = await createArchiveSpotlight({
    guildId,
    curatorId: ownerId,
    entryId,
    visibility,
    startsAt,
    endsAt,
  });
  const collectionSpotlightId = await createArchiveCollectionSpotlight({
    guildId,
    curatorId: ownerId,
    collectionId,
    visibility,
    startsAt,
    endsAt,
    canModerateServer: true,
  });
  return { collectionId, trailId, entrySpotlightId, collectionSpotlightId };
}

async function assertCuratedVisibility(
  guildId: string,
  entryId: string,
  views: Awaited<ReturnType<typeof createCuratedViews>>,
  visible: boolean,
  collectionVisible: boolean,
  now: Date,
): Promise<void> {
  const items = await getCollectionItems(guildId, views.collectionId);
  assert.equal(items.some(item => item.id === entryId), visible, "collection items must re-check entry visibility and approval");
  const steps = await getArchiveTrailSteps(guildId, views.trailId);
  assert.equal(steps.some(step => step.entry.id === entryId), visible, "Trail steps must re-check entry visibility and approval");
  const entrySpotlights = await listArchiveSpotlights(guildId, now);
  assert.equal(entrySpotlights.some(item => item.id === views.entrySpotlightId), visible, "entry spotlights must re-check entry visibility and approval");
  const collectionSpotlights = await listArchiveCollectionSpotlights(guildId, now);
  assert.equal(
    collectionSpotlights.some(item => item.id === views.collectionSpotlightId),
    visible,
    "collection spotlights must disappear when they contain no visible approved entries",
  );

  const collection = (await listArchiveCollections(guildId)).find(item => item.id === views.collectionId);
  const trail = (await listArchiveTrails(guildId)).find(item => item.id === views.trailId);
  if (!collectionVisible) {
    assert.equal(collection, undefined, "server collections must not cross guild boundaries");
    assert.equal(trail, undefined, "server Trails must not cross guild boundaries");
  } else {
    assert.ok(collection);
    assert.ok(trail);
    assert.equal(collection.entry_count, visible ? 1 : 0);
    assert.equal(trail.step_count, visible ? 1 : 0);
  }
}

test("curated Archive views immediately drop private, cross-guild, and unapproved entries", async () => {
  const directory = await mkdtemp(join(tmpdir(), "lemegeton-archive-lifecycle-"));
  const now = new Date();
  const startsAt = new Date(now.getTime() - 10_000);
  const endsAt = new Date(now.getTime() + 30 * 60_000);

  try {
    await initDatabase({ path: join(directory, "bot.db"), primaryGuildId: guildA });
    configureArchiveAccess([ownerId]);

    const privateEntry = await createApprovedEntry(guildA, "Private after curation", "global");
    const privateViews = await createCuratedViews(guildA, "Private after curation", privateEntry, "global", startsAt, endsAt);
    await assertCuratedVisibility(guildA, privateEntry, privateViews, true, true, now);
    await assertCuratedVisibility(guildB, privateEntry, privateViews, true, true, now);

    await changeArchiveEntryVisibility(guildA, ownerId, privateEntry, "server", false);
    await assertCuratedVisibility(guildA, privateEntry, privateViews, false, true, now);
    await assertCuratedVisibility(guildB, privateEntry, privateViews, false, true, now);

    const crossGuildEntry = await createApprovedEntry(guildA, "Moved to another guild", "server");
    const crossGuildViews = await createCuratedViews(guildA, "Moved to another guild", crossGuildEntry, "server", startsAt, endsAt);
    await assertCuratedVisibility(guildA, crossGuildEntry, crossGuildViews, true, true, now);
    await assertCuratedVisibility(guildB, crossGuildEntry, crossGuildViews, false, false, now);
    await query(
      "UPDATE community_archive_entries SET created_guild_id = $1 WHERE id = $2",
      [guildB, crossGuildEntry],
    );
    await assertCuratedVisibility(guildA, crossGuildEntry, crossGuildViews, false, true, now);
    await assertCuratedVisibility(guildB, crossGuildEntry, crossGuildViews, false, false, now);

    const unapprovedEntry = await createApprovedEntry(guildA, "No longer approved", "server");
    const unapprovedViews = await createCuratedViews(guildA, "No longer approved", unapprovedEntry, "server", startsAt, endsAt);
    await assertCuratedVisibility(guildA, unapprovedEntry, unapprovedViews, true, true, now);
    await assertCuratedVisibility(guildB, unapprovedEntry, unapprovedViews, false, false, now);
    await query(
      "UPDATE community_archive_entries SET status = 'pending' WHERE id = $1",
      [unapprovedEntry],
    );
    await assertCuratedVisibility(guildA, unapprovedEntry, unapprovedViews, false, true, now);
    await assertCuratedVisibility(guildB, unapprovedEntry, unapprovedViews, false, false, now);
  } finally {
    configureArchiveAccess([]);
    await closeDatabase().catch(() => undefined);
    await rm(directory, { recursive: true, force: true });
  }
});
