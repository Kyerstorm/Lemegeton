import test from "node:test";
import assert from "node:assert/strict";
import { canCollectionShowEntry } from "../helpers/archive/archive-collections.js";
import { canChangeArchiveVisibility } from "../helpers/archive/archive.js";

test("global collections and Trails only include globally visible Archive entries", () => {
  assert.equal(canCollectionShowEntry("global", "11111111111111111", "global", "22222222222222222", "33333333333333333"), true);
  assert.equal(canCollectionShowEntry("global", "11111111111111111", "server", "11111111111111111", "11111111111111111"), false);
});

test("server collections can include global and same-guild entries only", () => {
  assert.equal(canCollectionShowEntry("server", "11111111111111111", "global", "22222222222222222", "11111111111111111"), true);
  assert.equal(canCollectionShowEntry("server", "11111111111111111", "server", "11111111111111111", "11111111111111111"), true);
  assert.equal(canCollectionShowEntry("server", "11111111111111111", "server", "22222222222222222", "11111111111111111"), false);
  assert.equal(canCollectionShowEntry("server", "11111111111111111", "server", "11111111111111111", "22222222222222222"), false);
  assert.equal(canCollectionShowEntry("server", "22222222222222222", "global", "33333333333333333", "11111111111111111"), false);
});

test("Archive publication transitions require global moderation for promotion and preserve ownership for demotion", () => {
  assert.equal(canChangeArchiveVisibility("server", "global", "owner", "owner", false, false), false);
  assert.equal(canChangeArchiveVisibility("server", "global", "owner", "moderator", true, false), false);
  assert.equal(canChangeArchiveVisibility("server", "global", "owner", "global-mod", false, true), true);
  assert.equal(canChangeArchiveVisibility("global", "server", "owner", "owner", false, false), true);
  assert.equal(canChangeArchiveVisibility("global", "server", "owner", "moderator", true, false), true);
  assert.equal(canChangeArchiveVisibility("global", "server", "owner", "other", false, false), false);
  assert.equal(canChangeArchiveVisibility("global", "server", "owner", "global-mod", false, true), true);
  assert.equal(canChangeArchiveVisibility("server", "server", "owner", "other", false, false), true);
});
