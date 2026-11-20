import test from "node:test";
import assert from "node:assert/strict";
import {
  archiveAssetCleanupBackoffSeconds,
  archiveStorageProvider,
  archiveUploadChannelIsPrivate,
  archiveStorageChannelIsPrivate,
  classifyArchiveUpload,
  configureMediaStorage,
  downloadArchiveUpload,
  getArchiveUploadMaxBytes,
} from "../helpers/media/media-storage.js";

test("legacy-configured guilds keep Discord storage while new guilds use private S3", () => {
  assert.equal(archiveStorageProvider("123456789012345678"), "discord");
  assert.equal(archiveStorageProvider(null), "s3");
});
 
test("private asset cleanup uses capped exponential retry delays", () => {
  assert.equal(archiveAssetCleanupBackoffSeconds(1), 60);
  assert.equal(archiveAssetCleanupBackoffSeconds(2), 120);
  assert.equal(archiveAssetCleanupBackoffSeconds(3), 240);
  assert.equal(archiveAssetCleanupBackoffSeconds(12), 86_400);
  assert.equal(archiveAssetCleanupBackoffSeconds(99), 86_400);
  assert.equal(archiveAssetCleanupBackoffSeconds(0), 60);
});

test("Archive media upload limit follows typed runtime configuration", () => {
  const defaults = {
    archiveUploadMaxBytes: 20 * 1024 * 1024,
    s3Region: "us-east-1",
    s3Bucket: null,
    s3SignedUrlTtlSeconds: 900,
  } as const;
  configureMediaStorage({ ...defaults, archiveUploadMaxBytes: 256 });
  try {
    assert.equal(getArchiveUploadMaxBytes(), 256);
    assert.equal(
      classifyArchiveUpload("panels", { name: "panel.png", contentType: "image/png", bytes: Buffer.alloc(256) }).kind,
      "image",
    );
    assert.throws(
      () => classifyArchiveUpload("panels", { name: "panel.png", contentType: "image/png", bytes: Buffer.alloc(257) }),
      /between 1 byte and 20 MB/,
    );
  } finally {
    configureMediaStorage(defaults);
  }
});

test("Archive upload channels must hide the source attachments from everyone and allow the bot to delete uploads", () => {
  assert.equal(archiveUploadChannelIsPrivate(false, true, true, true), true);
  assert.equal(archiveUploadChannelIsPrivate(true, true, true, true), false);
  assert.equal(archiveUploadChannelIsPrivate(false, false, true, true), false);
  assert.equal(archiveUploadChannelIsPrivate(false, true, false, true), false);
  assert.equal(archiveUploadChannelIsPrivate(false, true, true, false), false);
});

test("Archive attachment downloads accept only the Discord CDN and reject redirects or oversized streams", async () => {
  await assert.rejects(
    downloadArchiveUpload("https://example.com/file.png", async () => new Response("x") as Response),
    /Discord's attachment CDN/,
  );
  const defaults = {
    archiveUploadMaxBytes: 4,
    s3Region: "us-east-1",
    s3Bucket: null,
    s3SignedUrlTtlSeconds: 900,
  } as const;
  configureMediaStorage(defaults);
  try {
    const fetcher: typeof fetch = async () => new Response(new Uint8Array([1, 2, 3, 4]));
    assert.deepEqual(
      await downloadArchiveUpload("https://cdn.discordapp.com/attachments/1/2/file.png", fetcher),
      Buffer.from([1, 2, 3, 4]),
    );
    const oversized: typeof fetch = async () => new Response(new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new Uint8Array([1, 2, 3]));
        controller.enqueue(new Uint8Array([4, 5]));
        controller.close();
      },
    }));
    await assert.rejects(
      downloadArchiveUpload("https://cdn.discordapp.com/attachments/1/2/file.png", oversized),
      /limited to 4 bytes/,
    );
  } finally {
    configureMediaStorage({
      archiveUploadMaxBytes: 20 * 1024 * 1024,
      s3Region: "us-east-1",
      s3Bucket: null,
      s3SignedUrlTtlSeconds: 900,
    });
  }
});

test("Legacy Archive storage channels must remain private and writable by the bot", () => {
  assert.equal(archiveStorageChannelIsPrivate(false, true, true, true), true);
  assert.equal(archiveStorageChannelIsPrivate(true, true, true, true), false);
  assert.equal(archiveStorageChannelIsPrivate(false, false, true, true), false);
  assert.equal(archiveStorageChannelIsPrivate(false, true, false, true), false);
  assert.equal(archiveStorageChannelIsPrivate(false, true, true, false), false);
});
