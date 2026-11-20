import test from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { Pool } from "pg";
import {
  CreateBucketCommand,
  DeleteBucketCommand,
  DeleteObjectCommand,
  ListObjectsV2Command,
  S3Client,
} from "@aws-sdk/client-s3";
import {
  closeDatabase,
  initDatabase,
  queryOne,
} from "../database.js";
import type { DatabaseConfig } from "../helpers/runtime/config.js";
import { configureArchiveAccess } from "../helpers/archive/archive-access.js";
import {
  addArchiveReport,
  reviewArchiveReport,
} from "../helpers/archive/archive-moderation.js";
import {
  attachArchiveAssetToEntry,
  changeArchiveEntryVisibility,
  deleteArchiveEntry,
  finishArchiveUpload,
  removeArchiveEntryAsset,
  replaceArchiveEntryAsset,
  submitArchiveEntry,
} from "../helpers/archive/archive.js";
import {
  saveArchiveCollection,
  saveArchiveTrail,
  changeArchiveCollectionVisibility,
  changeArchiveTrailVisibility,
} from "../helpers/archive/archive-collections.js";
import {
  configureMediaStorage,
  deleteArchiveAsset,
  deleteCustomRoleIconSource,
  processArchiveAssetCleanup,
  readCustomRoleIconSource,
  storeCustomRoleIconSource,
  signedArchiveAssetUrl,
  storeArchiveUpload,
} from "../helpers/media/media-storage.js";

const databaseUrl = process.env.TEST_DATABASE_URL?.trim();
const endpoint = process.env.S3_TEST_ENDPOINT_URL?.trim();
const accessKeyId = process.env.S3_TEST_ACCESS_KEY_ID?.trim();
const secretAccessKey = process.env.S3_TEST_SECRET_ACCESS_KEY?.trim();

test("private S3 upload, signed retrieval, and failed-delete recovery", {
  skip: databaseUrl && endpoint && accessKeyId && secretAccessKey
    ? false
    : "TEST_DATABASE_URL and the S3-compatible test service are required",
}, async () => {
  assert.ok(databaseUrl && endpoint && accessKeyId && secretAccessKey);
  const admin = new Pool({ connectionString: databaseUrl });
  const schema = "lemegeton_s3_" + randomUUID().replaceAll("-", "");
  const bucket = "lemegeton-test-" + randomUUID().replaceAll("-", "").slice(0, 20);
  const guildId = "987654321098765432";
  const userId = "123456789012345678";
  const bytes = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10, 1, 2, 3]);
  const goodConfig = {
    archiveUploadMaxBytes: 20 * 1024 * 1024,
    s3EndpointUrl: endpoint,
    s3Region: "us-east-1",
    s3AccessKeyId: accessKeyId,
    s3SecretAccessKey: secretAccessKey,
    s3Bucket: bucket,
    s3SignedUrlTtlSeconds: 900,
  };
  const objectClient = new S3Client({
    endpoint,
    region: "us-east-1",
    forcePathStyle: true,
    credentials: { accessKeyId, secretAccessKey },
  });
  let bucketCreated = false;

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
      ssl: false,
      poolSize: 2,
      primaryGuildId: guildId,
    };
    await initDatabase(config);

    let bucketError: unknown;
    for (let attempt = 0; attempt < 20; attempt += 1) {
      try {
        await objectClient.send(new CreateBucketCommand({ Bucket: bucket }));
        bucketCreated = true;
        bucketError = undefined;
        break;
      } catch (error) {
        bucketError = error;
        await new Promise(resolve => setTimeout(resolve, 500));
      }
    }
    if (bucketError) throw bucketError;

    configureMediaStorage(goodConfig);
    const assetId = await storeArchiveUpload(
      guildId,
      userId,
      "panels",
      { name: "panel.png", contentType: "image/png", bytes },
      ["image"],
    );
    const saved = await queryOne<{
      provider: string;
      is_private: boolean;
      guild_id: string;
      bucket_name: string;
    }>(
      "SELECT provider, is_private, guild_id::text, bucket_name FROM media_assets WHERE id = $1",
      [assetId],
    );
    assert.deepEqual(saved, {
      provider: "s3",
      is_private: true,
      guild_id: guildId,
      bucket_name: bucket,
    });

    const signedUrl = await signedArchiveAssetUrl(assetId, undefined, guildId);
    assert.ok(signedUrl);
    assert.ok(new URL(signedUrl).searchParams.has("X-Amz-Signature"));
    const downloaded = await fetch(signedUrl);
    assert.equal(downloaded.status, 200);
    assert.deepEqual(Buffer.from(await downloaded.arrayBuffer()), bytes);
    assert.equal(await signedArchiveAssetUrl(assetId, undefined, "987654321098765433"), null);

    // A pending entry attaches privately, then replacement/removal releases the old object.
    const lifecycleEntry = await submitArchiveEntry({
      guildId, userId, category: "panels", title: "Lifecycle panel", content: "",
      mediaType: "Manga", tags: [], spoiler: false, visibility: "server",
      needsUpload: true, chapterNumber: "1",
    });
    const firstPanelBytes = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10, 11]);
    const firstPanelAsset = await storeArchiveUpload(
      guildId, userId, "panels",
      { name: "first-panel.png", contentType: "image/png", bytes: firstPanelBytes },
      ["image"],
    );
    assert.ok(await queryOne(
      "SELECT asset_id FROM media_asset_cleanup_queue WHERE asset_id = $1",
      [firstPanelAsset],
    ));
    await attachArchiveAssetToEntry(guildId, userId, lifecycleEntry, firstPanelAsset, "first-panel.png");
    assert.equal(await queryOne(
      "SELECT asset_id FROM media_asset_cleanup_queue WHERE asset_id = $1",
      [firstPanelAsset],
    ), null);
    await finishArchiveUpload(guildId, userId, lifecycleEntry);

    const replacementBytes = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10, 12]);
    const replacementAsset = await storeArchiveUpload(
      guildId, userId, "panels",
      { name: "replacement.png", contentType: "image/png", bytes: replacementBytes },
      ["image"],
    );
    await replaceArchiveEntryAsset(guildId, userId, lifecycleEntry, 1, replacementAsset, "replacement.png");
    assert.equal(await queryOne("SELECT id FROM media_assets WHERE id = $1", [firstPanelAsset]), null);
    assert.equal((await queryOne<{ media_asset_id: string }>(
      "SELECT media_asset_id::text FROM community_archive_entries WHERE id = $1",
      [lifecycleEntry],
    ))?.media_asset_id, String(replacementAsset));

    await removeArchiveEntryAsset(guildId, userId, lifecycleEntry, 1);
    assert.equal(await queryOne("SELECT id FROM media_assets WHERE id = $1", [replacementAsset]), null);
    assert.equal((await queryOne<{ media_asset_id: string | null }>(
      "SELECT media_asset_id::text FROM community_archive_entries WHERE id = $1",
      [lifecycleEntry],
    ))?.media_asset_id, null);
    assert.equal((await queryOne<{ count: string }>(
      "SELECT COUNT(*)::text AS count FROM community_archive_entry_assets WHERE entry_id = $1",
      [lifecycleEntry],
    ))?.count, "0");

    // A legacy direct-only primary asset remains attached when a secondary attachment is removed.
    const legacyEntry = await submitArchiveEntry({
      guildId, userId, category: "panels", title: "Legacy primary panel", content: "",
      mediaType: "Manga", tags: [], spoiler: false, visibility: "server",
      needsUpload: true, chapterNumber: "N/A",
    });
    const legacyPrimary = await storeArchiveUpload(
      guildId, userId, "panels",
      { name: "legacy-primary.png", contentType: "image/png", bytes },
      ["image"],
    );
    await admin.query(
      'UPDATE "' + schema + '".community_archive_entries ' +
      "SET media_asset_id = $1, attachment_filename = 'legacy-primary.png', " +
      "attachment_content_type = 'image/png', status = 'pending' WHERE id = $2",
      [legacyPrimary, legacyEntry],
    );
    await admin.query(
      'DELETE FROM "' + schema + '".media_asset_cleanup_queue WHERE asset_id = $1',
      [legacyPrimary],
    );
    const secondaryAsset = await storeArchiveUpload(
      guildId, userId, "panels",
      { name: "legacy-secondary.png", contentType: "image/png", bytes: replacementBytes },
      ["image"],
    );
    await admin.query(
      'INSERT INTO "' + schema + '".community_archive_entry_assets (entry_id, asset_id, position, uploaded_by) ' +
      "VALUES ($1, $2, 2, $3)",
      [legacyEntry, secondaryAsset, userId],
    );
    await removeArchiveEntryAsset(guildId, userId, legacyEntry, 2);
    assert.equal((await queryOne<{ media_asset_id: string }>(
      'SELECT media_asset_id::text FROM "' + schema + '".community_archive_entries WHERE id = $1',
      [legacyEntry],
    ))?.media_asset_id, String(legacyPrimary));
    assert.deepEqual(await queryOne<{ asset_id: string; position: number }>(
      'SELECT asset_id::text, position FROM "' + schema + '".community_archive_entry_assets WHERE entry_id = $1',
      [legacyEntry],
    ), { asset_id: String(legacyPrimary), position: 1 });
    assert.equal(await queryOne(
      'SELECT id FROM "' + schema + '".media_assets WHERE id = $1',
      [legacyPrimary],
    ) !== null, true);
    assert.equal(await queryOne(
      'SELECT id FROM "' + schema + '".media_assets WHERE id = $1',
      [secondaryAsset],
    ), null);

    // Report removal updates the report, entry and asset references as one transition.
    const reportedEntry = await submitArchiveEntry({
      guildId, userId, category: "panels", title: "Reported panel", content: "",
      mediaType: "Manga", tags: [], spoiler: false, visibility: "server",
      needsUpload: true, chapterNumber: "2",
    });
    const reportedAsset = await storeArchiveUpload(
      guildId, userId, "panels",
      { name: "reported.png", contentType: "image/png", bytes },
      ["image"],
    );
    await attachArchiveAssetToEntry(guildId, userId, reportedEntry, reportedAsset, "reported.png");
    await finishArchiveUpload(guildId, userId, reportedEntry);
    await admin.query(
      'UPDATE "' + schema + '".community_archive_entries SET status = \'approved\' WHERE id = $1',
      [reportedEntry],
    );
    await addArchiveReport(guildId, "222222222222222222", reportedEntry, "Broken attribution");
    const report = await queryOne<{ id: string }>(
      "SELECT id::text FROM community_archive_reports WHERE entry_id = $1",
      [reportedEntry],
    );
    assert.ok(report);
    await reviewArchiveReport(guildId, report.id, "333333333333333333", "remove", "Removed after review");
    assert.equal((await queryOne<{ status: string }>(
      "SELECT status FROM community_archive_entries WHERE id = $1",
      [reportedEntry],
    ))?.status, "removed");
    assert.equal((await queryOne<{ status: string }>(
      "SELECT status FROM community_archive_reports WHERE id = $1",
      [report.id],
    ))?.status, "actioned");
    assert.equal(await queryOne(
      "SELECT asset_id FROM community_archive_entry_assets WHERE entry_id = $1",
      [reportedEntry],
    ), null);
    assert.ok(await queryOne(
      "SELECT asset_id FROM media_asset_cleanup_queue WHERE asset_id = $1",
      [reportedAsset],
    ));
    await admin.query(
      'UPDATE "' + schema + '".media_asset_cleanup_queue SET next_attempt_at = NOW() WHERE asset_id = $1',
      [reportedAsset],
    );
    assert.deepEqual(await processArchiveAssetCleanup(10), { attempted: 1, failed: 0 });
    assert.equal(await queryOne("SELECT id FROM media_assets WHERE id = $1", [reportedAsset]), null);

    // Global collection/Trail creation is enforced by the configured moderator set.
    configureArchiveAccess([]);
    await assert.rejects(
      saveArchiveCollection(guildId, userId, "Unauthorized global collection", "", "global"),
      /configured global Archive moderators/,
    );
    await assert.rejects(
      saveArchiveTrail(guildId, userId, "Unauthorized global Trail", "", "global"),
      /configured global Archive moderators/,
    );
    configureArchiveAccess([userId]);

    // Publication scope transitions cannot promote collections or Trails containing server-only entries.
    await admin.query(
      'UPDATE "' + schema + '".community_archive_entries SET status = \'approved\', media_asset_id = NULL, visibility = \'server\' WHERE id = $1',
      [lifecycleEntry],
    );
    configureArchiveAccess([]);
    await assert.rejects(
      changeArchiveEntryVisibility(guildId, "222222222222222222", lifecycleEntry, "global", true),
      /configured global Archive moderators/,
    );
    configureArchiveAccess([userId]);
    const collection = await admin.query<{ id: string }>(
      'INSERT INTO "' + schema + '".archive_collections (guild_id, owner_id, title, visibility) ' +
      "VALUES ($1, $2, 'Scope test collection', 'server') RETURNING id::text",
      [guildId, userId],
    );
    await admin.query(
      'INSERT INTO "' + schema + '".archive_collection_items (collection_id, entry_id, added_by) VALUES ($1, $2, $3)',
      [collection.rows[0]!.id, lifecycleEntry, userId],
    );
    await assert.rejects(
      changeArchiveCollectionVisibility(guildId, userId, collection.rows[0]!.id, "global", true),
      /server-only entries/,
    );
    const trail = await admin.query<{ id: string }>(
      'INSERT INTO "' + schema + '".archive_trails (guild_id, owner_id, title, visibility) ' +
      "VALUES ($1, $2, 'Scope test Trail', 'server') RETURNING id::text",
      [guildId, userId],
    );
    await admin.query(
      'INSERT INTO "' + schema + '".archive_trail_steps (trail_id, step_number, entry_id, added_by) VALUES ($1, 1, $2, $3)',
      [trail.rows[0]!.id, lifecycleEntry, userId],
    );
    await assert.rejects(
      changeArchiveTrailVisibility(guildId, userId, trail.rows[0]!.id, "global", true),
      /server-only entries/,
    );
    await changeArchiveEntryVisibility(guildId, userId, lifecycleEntry, "global", false);
    assert.equal((await queryOne<{ visibility: string }>(
      "SELECT visibility FROM community_archive_entries WHERE id = $1",
      [lifecycleEntry],
    ))?.visibility, "global");
    await changeArchiveCollectionVisibility(guildId, userId, collection.rows[0]!.id, "global", false);
    await changeArchiveTrailVisibility(guildId, userId, trail.rows[0]!.id, "global", false);
    assert.equal((await queryOne<{ visibility: string }>(
      'SELECT visibility FROM "' + schema + '".archive_collections WHERE id = $1',
      [collection.rows[0]!.id],
    ))?.visibility, "global");
    assert.equal((await queryOne<{ visibility: string }>(
      'SELECT visibility FROM "' + schema + '".archive_trails WHERE id = $1',
      [trail.rows[0]!.id],
    ))?.visibility, "global");

    // Deleting an entry also cleans its direct media_asset_id reference.
    const deletedEntry = await submitArchiveEntry({
      guildId, userId, category: "panels", title: "Deleted panel", content: "",
      mediaType: "Manga", tags: [], spoiler: false, visibility: "server",
      needsUpload: true, chapterNumber: "3",
    });
    const deletedAsset = await storeArchiveUpload(
      guildId, userId, "panels",
      { name: "deleted.png", contentType: "image/png", bytes },
      ["image"],
    );
    await attachArchiveAssetToEntry(guildId, userId, deletedEntry, deletedAsset, "deleted.png");
    await finishArchiveUpload(guildId, userId, deletedEntry);
    await deleteArchiveEntry(guildId, userId, deletedEntry, false, false);
    assert.equal(await queryOne("SELECT id FROM media_assets WHERE id = $1", [deletedAsset]), null);

    const roleBytes = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10, 4, 5, 6]);
    const roleAssetId = await storeCustomRoleIconSource(guildId, userId, roleBytes, "image/png");
    assert.deepEqual(await readCustomRoleIconSource(roleAssetId, guildId), roleBytes);
    assert.equal(await readCustomRoleIconSource(roleAssetId, "987654321098765433"), null);
    assert.equal(await signedArchiveAssetUrl(roleAssetId, undefined, guildId), null);
    const roleAsset = await queryOne<{ provider: string; namespace: string; is_private: boolean }>(
      "SELECT provider, namespace, is_private FROM media_assets WHERE id = $1",
      [roleAssetId],
    );
    assert.deepEqual(roleAsset, { provider: "s3", namespace: `custom-roles/${guildId}`, is_private: true });
    assert.equal(await deleteCustomRoleIconSource(roleAssetId, guildId), true);
    assert.equal(await readCustomRoleIconSource(roleAssetId, guildId), null);

    configureMediaStorage({
      ...goodConfig,
      s3EndpointUrl: "http://127.0.0.1:1",
    });
    await assert.rejects(
      storeArchiveUpload(
        guildId,
        userId,
        "panels",
        { name: "failed.png", contentType: "image/png", bytes },
        ["image"],
      ),
      /private media upload failed/i,
    );

    await assert.rejects(deleteArchiveAsset(assetId));
    const queued = await queryOne<{ attempts: number }>(
      "SELECT attempts FROM media_asset_cleanup_queue WHERE asset_id = $1",
      [assetId],
    );
    assert.equal(Number(queued?.attempts), 1);

    configureMediaStorage(goodConfig);
    await admin.query(
      'UPDATE "' + schema + '".media_asset_cleanup_queue SET next_attempt_at = NOW() WHERE asset_id = $1',
      [assetId],
    );
    const cleanup = await processArchiveAssetCleanup(10);
    assert.deepEqual(cleanup, { attempted: 1, failed: 0 });
    assert.equal(
      await queryOne("SELECT id FROM media_assets WHERE id = $1", [assetId]),
      null,
    );
    assert.equal(
      await queryOne("SELECT asset_id FROM media_asset_cleanup_queue WHERE asset_id = $1", [assetId]),
      null,
    );

    const leftover = await objectClient.send(new ListObjectsV2Command({ Bucket: bucket }));
    assert.equal(leftover.KeyCount ?? 0, 0);
  } finally {
    configureArchiveAccess([]);
    configureMediaStorage(goodConfig);
    await closeDatabase().catch(() => undefined);
    if (bucketCreated) {
      const leftovers = await objectClient.send(new ListObjectsV2Command({ Bucket: bucket })).catch(() => null);
      for (const item of leftovers?.Contents ?? []) {
        // Test objects are private and the bucket is unique to this run.
        if (item.Key) await objectClient.send(new DeleteObjectCommand({ Bucket: bucket, Key: item.Key })).catch(() => undefined);
      }
      await objectClient.send(new DeleteBucketCommand({ Bucket: bucket })).catch(() => undefined);
    }
    objectClient.destroy();
    await admin.query(`DROP SCHEMA IF EXISTS "${schema}" CASCADE`).catch(() => undefined);
    await admin.end();
  }
});
