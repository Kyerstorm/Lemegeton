import test from "node:test";
import assert from "node:assert/strict";
import { archiveAssetCleanupBackoffSeconds } from "../helpers/media/media-storage.js";

test("private asset cleanup uses capped exponential retry delays", () => {
  assert.equal(archiveAssetCleanupBackoffSeconds(1), 60);
  assert.equal(archiveAssetCleanupBackoffSeconds(2), 120);
  assert.equal(archiveAssetCleanupBackoffSeconds(3), 240);
  assert.equal(archiveAssetCleanupBackoffSeconds(12), 86_400);
  assert.equal(archiveAssetCleanupBackoffSeconds(99), 86_400);
  assert.equal(archiveAssetCleanupBackoffSeconds(0), 60);
});
