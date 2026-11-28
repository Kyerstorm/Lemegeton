import test from "node:test";
import assert from "node:assert/strict";
import { canFeatureArchiveCollection, completeArchiveCategoryIndex, validateSpotlightWindow } from "../helpers/archive/archive-curation.js";

test("Archive spotlight windows require a valid future start and a positive bounded duration", () => {
  const now = new Date("2026-11-13T12:00:00.000Z");
  assert.doesNotThrow(() => validateSpotlightWindow(
    new Date("2026-11-13T12:00:00.000Z"),
    new Date("2026-11-20T12:00:00.000Z"),
    now,
  ));
  assert.throws(() => validateSpotlightWindow(new Date("invalid"), new Date("2026-11-20T12:00:00.000Z"), now), /valid dates/i);
  assert.throws(() => validateSpotlightWindow(new Date("2026-11-12T12:00:00.000Z"), new Date("2026-11-20T12:00:00.000Z"), now), /past/i);
  assert.throws(() => validateSpotlightWindow(now, now, now), /one minute/i);
  assert.throws(() => validateSpotlightWindow(now, new Date("2027-01-01T00:00:00.000Z"), now), /30 days/i);
});
test("Archive category index returns every category and preserves empty categories", () => {
  const index = completeArchiveCategoryIndex([
    { archive_type: "panels", entry_count: 4 },
    { archive_type: "soundtracks", entry_count: 2 },
    { archive_type: "unknown-legacy-category", entry_count: 99 },
  ]);
  assert.equal(index.length, 8);
  assert.equal(index.find(item => item.category === "panels")?.entry_count, 4);
  assert.equal(index.find(item => item.category === "soundtracks")?.entry_count, 2);
  assert.equal(index.find(item => item.category === "quotes")?.entry_count, 0);
  assert.ok(index.every(item => item.entry_count >= 0));
});

test("Archive collection spotlight authorization distinguishes server and global scope", () => {
  assert.equal(canFeatureArchiveCollection("server", "owner", "owner", "server", false, false), true);
  assert.equal(canFeatureArchiveCollection("server", "owner", "moderator", "server", true, false), true);
  assert.equal(canFeatureArchiveCollection("server", "owner", "member", "server", false, false), false);
  assert.equal(canFeatureArchiveCollection("global", "owner", "global-mod", "global", false, true), true);
  assert.equal(canFeatureArchiveCollection("server", "owner", "global-mod", "global", false, true), false);
  assert.equal(canFeatureArchiveCollection("global", "owner", "member", "global", true, false), false);
});
