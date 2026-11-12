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

    const roleBytes = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10, 4, 5, 6]);
    const roleAssetId = await storeCustomRoleIconSource(guildId, userId, roleBytes, "image/png");
    assert.deepEqual(await readCustomRoleIconSource(roleAssetId, guildId), roleBytes);
    assert.equal(await readCustomRoleIconSource(roleAssetId, "987654321098765433"), null);
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
