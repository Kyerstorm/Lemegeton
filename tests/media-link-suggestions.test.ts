import test from "node:test";
import assert from "node:assert/strict";
import { normalizeMediaLinkSuggestion } from "../helpers/media-link-suggestions.js";

const valid = {
  sourceTitle: "  Source   Work ",
  sourceCategory: "ANIME",
  sourceUrl: "https://example.com/source",
  relationship: "adaptation",
  targetTitle: "Target Work",
  targetCategory: "MANGA",
  targetUrl: "https://example.com/target",
  evidence: "The publisher confirms this is an adaptation of the source work.",
};

test("media relationship input is normalized before it can enter the review queue", () => {
  const result = normalizeMediaLinkSuggestion(valid);
  assert.ok(result);
  assert.equal(result.sourceTitle, "Source Work");
  assert.equal(result.targetTitle, "Target Work");
  assert.equal(result.sourceCategory, "ANIME");
  assert.equal(result.relationship, "adaptation");
  assert.equal(result.evidence, valid.evidence);
});

test("media relationship input rejects identical titles and unsupported categories", () => {
  assert.equal(normalizeMediaLinkSuggestion({ ...valid, targetTitle: " source-work " }), null);
  assert.equal(normalizeMediaLinkSuggestion({ ...valid, targetCategory: "unsupported" }), null);
});

test("media relationship input requires safe HTTPS URLs without embedded credentials", () => {
  assert.equal(normalizeMediaLinkSuggestion({ ...valid, sourceUrl: "http://example.com/source" }), null);
  assert.equal(normalizeMediaLinkSuggestion({ ...valid, targetUrl: "https://user:pass@example.com/item" }), null);
  assert.equal(normalizeMediaLinkSuggestion({ ...valid, sourceUrl: "not-a-url" }), null);
});

test("media relationship input accepts only the known relationship vocabulary", () => {
  assert.equal(normalizeMediaLinkSuggestion({ ...valid, relationship: "scraped from" }), null);
  assert.equal(normalizeMediaLinkSuggestion({ ...valid, relationship: " SEQUEL " })?.relationship, "sequel");
});

test("media relationship input requires evidence and caps its stored length", () => {
  assert.equal(normalizeMediaLinkSuggestion({ ...valid, evidence: "too short" }), null);
  const long = normalizeMediaLinkSuggestion({ ...valid, evidence: "x".repeat(2_000) });
  assert.equal(long?.evidence.length, 1_500);
});
