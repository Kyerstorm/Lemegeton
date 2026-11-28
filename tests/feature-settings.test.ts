import test from "node:test";
import assert from "node:assert/strict";
import { FEATURE_NAMES, isFeatureName } from "../helpers/runtime/settings.js";

test("every configurable feature command is recognized by the common interaction gate", () => {
  assert.deepEqual(FEATURE_NAMES, ["discover", "archive", "community", "play", "profile", "custom-role", "music", "expedition", "casebook"]);
  for (const feature of FEATURE_NAMES) assert.equal(isFeatureName(feature), true);
});

test("non-feature commands remain outside the feature-toggle gate", () => {
  for (const command of ["settings", "language", "help", "privacy", "feedback", "log", "moderators"]) {
    assert.equal(isFeatureName(command), false);
  }
});
