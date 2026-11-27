import assert from "node:assert/strict";
import test from "node:test";
import {
  clamp,
  contrast,
  duration,
  formatSize,
  hexToRgb,
  hsvToRgb,
  normalizeHex,
  rgbToHex,
  rgbToHsv,
} from "../web/frontend/src/Components/Features/CustomRoles/picker-utils.ts";

test("picker hex normalization matches the bot's accepted color formats", () => {
  assert.equal(normalizeHex("#abc"), "#AABBCC");
  assert.equal(normalizeHex("12abef"), "#12ABEF");
  assert.equal(normalizeHex("#000000"), "#010101");
  assert.equal(normalizeHex("invalid"), null);
});

test("picker RGB and HSV conversion preserves an RGB color", () => {
  const hex = "#336699";
  const roundTrip = rgbToHex(hsvToRgb(rgbToHsv(hexToRgb(hex))));

  assert.equal(roundTrip, hex);
});

test("picker color contrast is symmetric and computes black against white", () => {
  const forward = contrast("#000000", "#FFFFFF");
  const reverse = contrast("#FFFFFF", "#000000");

  assert.equal(forward, reverse);
  assert.ok(forward > 20.9);
});

test("picker display helpers clamp values and format durations and file sizes", () => {
  assert.equal(clamp(12, 0, 10), 10);
  assert.equal(clamp(-2, 0, 10), 0);
  assert.equal(duration(90_061), "1d 1h 1m 1s");
  assert.equal(duration(-5), "0s");
  assert.equal(formatSize(1_024), "1 KB");
  assert.equal(formatSize(1_048_576), "1 MB");
});
