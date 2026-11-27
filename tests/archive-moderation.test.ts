import test from "node:test";
import assert from "node:assert/strict";
import { canModerateArchiveStatus } from "../helpers/archive/archive-moderation.js";
import { configureArchiveAccess, isGlobalArchiveModerator } from "../helpers/archive/archive-access.js";

test("Archive moderation only removes approved entries while pending entries can be reviewed", () => {
  assert.equal(canModerateArchiveStatus("pending", "approve"), true);
  assert.equal(canModerateArchiveStatus("pending_upload", "reject"), true);
  assert.equal(canModerateArchiveStatus("approved", "remove"), true);
  assert.equal(canModerateArchiveStatus("approved", "approve"), false);
  assert.equal(canModerateArchiveStatus("approved", "reject"), false);
  assert.equal(canModerateArchiveStatus("rejected", "remove"), false);
  assert.equal(canModerateArchiveStatus("removed", "remove"), false);
});

test("Global Archive moderators are loaded from validated runtime configuration", () => {
  configureArchiveAccess([
    "111111111111111111",
    "not-a-discord-id",
    "222222222222222222",
    "111111111111111111",
  ]);
  assert.equal(isGlobalArchiveModerator("111111111111111111"), true);
  assert.equal(isGlobalArchiveModerator("222222222222222222"), true);
  assert.equal(isGlobalArchiveModerator("333333333333333333"), false);
  configureArchiveAccess([]);
  assert.equal(isGlobalArchiveModerator("111111111111111111"), false);
});
