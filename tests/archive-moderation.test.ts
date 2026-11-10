import test from "node:test";
import assert from "node:assert/strict";
import { canModerateArchiveStatus } from "../helpers/archive/archive-moderation.js";

test("Archive moderation only removes approved entries while pending entries can be reviewed", () => {
  assert.equal(canModerateArchiveStatus("pending", "approve"), true);
  assert.equal(canModerateArchiveStatus("pending_upload", "reject"), true);
  assert.equal(canModerateArchiveStatus("approved", "remove"), true);
  assert.equal(canModerateArchiveStatus("approved", "approve"), false);
  assert.equal(canModerateArchiveStatus("approved", "reject"), false);
  assert.equal(canModerateArchiveStatus("rejected", "remove"), false);
  assert.equal(canModerateArchiveStatus("removed", "remove"), false);
});
