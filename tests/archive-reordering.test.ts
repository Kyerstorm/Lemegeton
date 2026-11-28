import test from "node:test";
import assert from "node:assert/strict";
import { moveArchiveItem, reorderVisibleArchiveItems } from "../helpers/archive/archive-collections.js";

test("archive ordering moves an item to a one-based position without mutating input", () => {
  const original = ["first", "second", "third", "fourth"];
  assert.deepEqual(moveArchiveItem(original, "third", 1), ["third", "first", "second", "fourth"]);
  assert.deepEqual(moveArchiveItem(original, "first", 3), ["second", "third", "first", "fourth"]);
  assert.deepEqual(original, ["first", "second", "third", "fourth"]);
});

test("archive ordering clamps the destination to the list length", () => {
  assert.deepEqual(moveArchiveItem(["first", "second"], "first", 99), ["second", "first"]);
});

test("archive ordering rejects invalid positions and entries outside the list", () => {
  assert.throws(() => moveArchiveItem(["first"], "first", 0), /position/);
  assert.throws(() => moveArchiveItem(["first"], "missing", 1), /not part/);
  assert.throws(() => moveArchiveItem(["first"], "first", 1.5), /position/);
});

test("reordering keeps currently hidden Archive references after visible entries", () => {
  assert.deepEqual(
    reorderVisibleArchiveItems([
      { entry_id: "visible-a", visible: true },
      { entry_id: "hidden-b", visible: false },
      { entry_id: "visible-c", visible: true },
      { entry_id: "hidden-d", visible: false },
    ], "visible-c", 1),
    ["visible-c", "visible-a", "hidden-b", "hidden-d"],
  );
});
