import test from "node:test";
import assert from "node:assert/strict";
import { validateSpotlightWindow } from "../helpers/archive/archive-curation.js";

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