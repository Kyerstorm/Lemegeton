import assert from "node:assert/strict";
import test from "node:test";
import { customEmoji, emoji, loadingMessage, providerEmoji, providerFooter, withEmoji } from "../helpers/emoji.js";

test("legacy palette names remain available without decorative emoji output", () => {
  assert.ok(Object.keys(emoji).length >= 100);
  assert.ok(Object.values(emoji).every(value => value === ""));
  assert.equal(customEmoji("check", "123456789012345678"), "");
  assert.equal(providerEmoji("Steam Store"), "");
  assert.equal(providerEmoji("Not A Provider"), "");
});

test("response helpers preserve readable text without adding symbols", () => {
  assert.equal(withEmoji("idea", "A useful suggestion"), "A useful suggestion");
  assert.equal(loadingMessage("Fetching media…"), "Fetching media…");
  assert.equal(providerFooter("Steam", "Ireland store metadata"), "Steam · Ireland store metadata");
  assert.ok(providerFooter("Steam", "Ireland store metadata").length <= 2_048);
});

test("provider footer fallback remains bounded and readable", () => {
  assert.equal(providerFooter(" ", ""), "Metadata provider");
  assert.ok(providerFooter("Steam", "x".repeat(3_000)).length <= 2_048);
});
