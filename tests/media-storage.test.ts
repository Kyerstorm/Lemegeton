import test from "node:test";
import assert from "node:assert/strict";
import { archiveAssetCleanupBackoffSeconds, archiveStorageProvider, classifyArchiveUpload, configureMediaStorage, getArchiveUploadMaxBytes } from "../helpers/media/media-storage.js";

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
