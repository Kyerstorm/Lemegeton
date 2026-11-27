import test from "node:test";
import assert from "node:assert/strict";
import { formatMetadataSourceReference } from "../helpers/media/media-provenance.js";

test("metadata provenance exposes the stable provider ID and HTTPS source record", () => {
  assert.equal(formatMetadataSourceReference("AniList", 12345, "https://anilist.co/anime/12345"),
    "Record ID: 12345\n[Open AniList record](https://anilist.co/anime/12345)");
});

test("metadata provenance keeps the ID but rejects unsafe or malformed source links", () => {
  assert.equal(formatMetadataSourceReference("Google Books", "volume-1", "javascript:alert(1)"),
    "Record ID: volume-1\nSource link unavailable");
  assert.equal(formatMetadataSourceReference("TMDB", 42, "https://user:pass@example.com/item/42"),
    "Record ID: 42\nSource link unavailable");
});

test("metadata provenance sanitizes labels and missing identifiers", () => {
  assert.equal(formatMetadataSourceReference("[Provider]\n", "\n", "not a URL"),
    "Record ID: Unavailable\nSource link unavailable");
});
