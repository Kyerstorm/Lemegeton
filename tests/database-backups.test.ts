import test from "node:test";
import assert from "node:assert/strict";
import { databaseBackupObjectKey, databaseRehearsalName } from "../helpers/runtime/database-backups.js";

test("database backup keys are dated and UUID-scoped", () => {
  const id = "2a5e2b81-45e8-4e95-ae0d-3f9491d2dcde";
  assert.equal(databaseBackupObjectKey(id, new Date("2026-11-16T12:00:00.000Z")),
    "database-backups/2026/11/" + id + ".dump");
  assert.throws(() => databaseBackupObjectKey("../unsafe", new Date()), /valid backup UUID/);
  assert.throws(() => databaseBackupObjectKey(id, new Date("invalid")), /backup date is invalid/);
});

test("restore rehearsal database identifiers are UUID-scoped and generated safely", () => {
  const name = databaseRehearsalName("2a5e2b81-45e8-4e95-ae0d-3f9491d2dcde");
  assert.match(name, /^lemegeton_rehearsal_[0-9a-f]{32}$/);
  assert.throws(() => databaseRehearsalName("../unsafe"), /valid backup UUID/);
});
