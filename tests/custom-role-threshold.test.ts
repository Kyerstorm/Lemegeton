import test from "node:test";
import assert from "node:assert/strict";
import { parseCustomRoleMassArchiveThreshold } from "../helpers/custom-roles/custom-role-lifecycle.js";

test("Custom Roles mass-archive threshold preserves default, zero floor and valid overrides", () => {
  assert.equal(parseCustomRoleMassArchiveThreshold(undefined), 10);
  assert.equal(parseCustomRoleMassArchiveThreshold("10"), 10);
  assert.equal(parseCustomRoleMassArchiveThreshold("3"), 3);
  assert.equal(parseCustomRoleMassArchiveThreshold("0"), 0);
  assert.equal(parseCustomRoleMassArchiveThreshold("-1"), 0);
  assert.equal(parseCustomRoleMassArchiveThreshold("invalid"), 10);
  assert.equal(parseCustomRoleMassArchiveThreshold("3.5"), 10);
});
