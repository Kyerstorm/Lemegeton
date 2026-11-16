import test from "node:test";
import assert from "node:assert/strict";
import { renderAtlasGraphSnapshot } from "../helpers/media/atlas-renderer.js";
import type { AtlasGraphResult, AtlasGraphPath } from "../helpers/integration/atlas.js";

const graph: AtlasGraphResult = {
  rootId: "root",
  truncated: false,
  directRelationships: [],
  nodes: [
    { id: "root", title: "Root Media", category: "ANIME", url: "https://example.com/root", depth: 0 },
    { id: "child", title: "Adapted Work", category: "MANGA", url: "https://example.com/child", depth: 1, sourceKind: "provider", relationType: "adaptation", sourceLabel: "AniList" },
    { id: "grandchild", title: "Related Book", category: "BOOK", url: "https://example.com/book", depth: 2, sourceKind: "community", relationType: "related work", sourceLabel: "Server archive" },
  ],
  edges: [
    { from: "root", to: "child", relationType: "adaptation", sourceLabel: "AniList", sourceKind: "provider" },
    { from: "child", to: "grandchild", relationType: "related work", sourceLabel: "Server archive", sourceKind: "community" },
  ],
};
const path: AtlasGraphPath = {
  nodes: graph.nodes,
  edges: graph.edges,
};

test("Atlas graph export renders multi-hop nodes and path highlights as a PNG", async () => {
  const image = await renderAtlasGraphSnapshot("Root Media", "ANIME", graph, path);
  assert.ok(image.length > 1000);
  assert.deepEqual([...image.subarray(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10]);
});

test("Atlas graph export handles a truncated graph without a path", async () => {
  const image = await renderAtlasGraphSnapshot("Root Media", "ANIME", { ...graph, truncated: true }, null);
  assert.deepEqual([...image.subarray(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10]);
});
