import test from "node:test";
import assert from "node:assert/strict";
import { orderCommunityShowcaseEntries, type CommunityShowcaseEntry } from "../helpers/community/community-showcase.js";

function entry(id: string, createdAt: string): CommunityShowcaseEntry {
  return {
    id,
    kind: "collection",
    title: "Collection " + id,
    description: "",
    creator_id: "12345678901234567",
    created_at: new Date(createdAt),
    item_count: 1,
    result_title: null,
    detail_label: null,
    source_url: null,
  };
}

test("Community Showcase orders the newest published records first without mutating input", () => {
  const input = [entry("old", "2026-11-01T00:00:00Z"), entry("new", "2026-11-14T00:00:00Z"), entry("middle", "2026-11-07T00:00:00Z")];
  const ordered = orderCommunityShowcaseEntries(input);
  assert.deepEqual(ordered.map(item => item.id), ["new", "middle", "old"]);
  assert.deepEqual(input.map(item => item.id), ["old", "new", "middle"]);
});

test("Community Showcase result limits are bounded to 1–25 entries", () => {
  const input = Array.from({ length: 30 }, (_, index) => entry(String(index), new Date(2026, 0, index + 1).toISOString()));
  assert.equal(orderCommunityShowcaseEntries(input, 0).length, 15);
  assert.equal(orderCommunityShowcaseEntries(input, -5).length, 1);
  assert.equal(orderCommunityShowcaseEntries(input, 1).length, 1);
  assert.equal(orderCommunityShowcaseEntries(input, 200).length, 25);
});

test("Community Showcase includes contribution and event record kinds in chronological order", () => {
  const input: CommunityShowcaseEntry[] = [
    { ...entry("ranking", "2026-11-01T00:00:00Z"), kind: "ranking" },
    { ...entry("creation", "2026-11-14T00:00:00Z"), kind: "creation", result_title: "soundtracks", detail_label: "game", source_url: "https://example.com/source" },
    { ...entry("session", "2026-11-10T00:00:00Z"), kind: "session", result_title: "watch" },
    { ...entry("discussion", "2026-11-12T00:00:00Z"), kind: "discussion", result_title: "Media discussion" },
  ];
  assert.deepEqual(orderCommunityShowcaseEntries(input).map(item => item.id), ["creation", "discussion", "session", "ranking"]);
  assert.equal(input[1]?.source_url, "https://example.com/source");
});
