import test from "node:test";
import assert from "node:assert/strict";
import {
  archiveMediaTypesForCategory, createAtlasDiscordUrl,
  atlasNodeIdentity, atlasProviderIdentity, buildAtlasGraph, filterAtlasGraph, filterAtlasRelations, findAtlasPath,
  normalizeAtlasCategory, normalizeAtlasTitle, safeAtlasUrl,
  type AtlasRelation,
} from "../helpers/integration/atlas.js";

test("Atlas accepts typed community nodes without conflating them with media categories", () => {
  assert.equal(normalizeAtlasCategory("anime"), "ANIME");
  assert.equal(normalizeAtlasCategory("light novel"), "LIGHT_NOVEL");
  assert.equal(normalizeAtlasCategory("archive_entry"), "ARCHIVE_ENTRY");
  assert.equal(normalizeAtlasCategory("archive-collection"), "ARCHIVE_COLLECTION");
  assert.equal(normalizeAtlasCategory("discussion"), "DISCUSSION");
  assert.equal(normalizeAtlasCategory("activity"), "ACTIVITY");
  assert.equal(normalizeAtlasCategory("creator"), "CREATOR");
  assert.equal(normalizeAtlasCategory("franchise"), "FRANCHISE");
  assert.equal(normalizeAtlasCategory("not-a-node"), null);
});

test("Atlas archive media matching remains category-aware", () => {
  assert.deepEqual(archiveMediaTypesForCategory("MANGA"), ["manga", "manhwa", "manhua", "webtoon"]);
  assert.deepEqual(archiveMediaTypesForCategory("LIGHT_NOVEL"), ["light novel", "light_novel"]);
  assert.deepEqual(archiveMediaTypesForCategory("GAME"), ["game", "video game"]);
  assert.deepEqual(archiveMediaTypesForCategory("CREATOR"), []);
});

test("Atlas title, HTTPS URL and Discord deep-link normalization are bounded", () => {
  assert.equal(normalizeAtlasTitle("  FRIEREN: Beyond Journey's End  "), "frieren beyond journey s end");
  assert.equal(safeAtlasUrl("https://anilist.co/manga/1"), "https://anilist.co/manga/1");
  assert.equal(safeAtlasUrl("http://example.com"), null);
  assert.equal(safeAtlasUrl("https://user:pass@example.com"), null);
  assert.equal(createAtlasDiscordUrl("12345678901234567", "22345678901234567"),
    "https://discord.com/channels/12345678901234567/22345678901234567");
  assert.equal(createAtlasDiscordUrl("guild", "channel"), null);
});


test("Atlas expands a deterministic bounded multi-hop graph and ignores cycles", async () => {
  const lookups: string[] = [];
  const relations = (title: string): AtlasRelation[] => {
    if (title === "Alpha") return [
      { title: "Beta", category: "MANGA", url: "https://example.com/beta", relationType: "adaptation", source: "AniList", sourceKind: "provider" as const },
      { title: "Gamma", category: "GAME", url: "https://example.com/gamma", relationType: "related", source: "Community", sourceKind: "community" as const },
    ];
    if (title === "Beta") return [
      { title: "Alpha", category: "ANIME", url: "https://example.com/alpha", relationType: "Incoming: Adaptation", source: "AniList", sourceKind: "provider" as const },
      { title: "Delta", category: "BOOK", url: "https://example.com/delta", relationType: "source material", source: "Google Books", sourceKind: "provider" as const },
    ];
    if (title === "Gamma") return [
      { title: "Delta", category: "BOOK", url: "https://example.com/delta", relationType: "related", source: "Community", sourceKind: "community" as const },
    ];
    return [];
  };
  const graph = await buildAtlasGraph(
    { title: "Alpha", category: "ANIME", url: "https://example.com/alpha" },
    async node => { lookups.push(node.title); return relations(node.title); },
    { maxDepth: 2, maxNodes: 8, perNodeLimit: 8 },
  );

  assert.deepEqual(lookups, ["Alpha", "Beta", "Gamma"]);
  assert.equal(graph.nodes.length, 4);
  assert.equal(graph.edges.length, 4);
  assert.equal(graph.nodes.find(node => node.title === "Delta")?.depth, 2);
  assert.equal(graph.directRelationships.length, 2);
  assert.equal(graph.truncated, false);
});

test("Atlas graph limits node count and marks omitted branches as truncated", async () => {
  const graph = await buildAtlasGraph(
    { title: "Root", category: "ANIME" },
    async node => node.depth === 0
      ? [1, 2, 3].map(index => ({
          title: "Node " + index, category: "MANGA", url: null,
          relationType: "related", source: "Fixture", sourceKind: "provider" as const,
        }))
      : [],
    { maxDepth: 2, maxNodes: 3, perNodeLimit: 8 },
  );
  assert.equal(graph.nodes.length, 3);
  assert.equal(graph.truncated, true);
});

test("Atlas node identity keeps work categories and distinct editions separate", () => {
  assert.notEqual(atlasNodeIdentity("Example", "ANIME"), atlasNodeIdentity("Example", "MANGA"));
  assert.notEqual(
    atlasNodeIdentity("Example", "BOOK", "https://books.example/edition/1"),
    atlasNodeIdentity("Example", "BOOK", "https://books.example/edition/2"),
  );
});


test("Atlas canonicalizes stable provider identities without merging different work categories", () => {
  assert.equal(
    atlasNodeIdentity("Old title", "ANIME", "https://anilist.co/anime/123/old-title"),
    atlasNodeIdentity("New title", "ANIME", "https://anilist.co/anime/123/new-title"),
  );
  assert.notEqual(
    atlasNodeIdentity("Example", "ANIME", "https://anilist.co/anime/123"),
    atlasNodeIdentity("Example", "MANGA", "https://anilist.co/manga/123"),
  );
  assert.equal(atlasProviderIdentity("MOVIE", "https://www.themoviedb.org/movie/550-example"), JSON.stringify(["tmdb","movie","MOVIE","550"]));
  assert.equal(atlasProviderIdentity("TV", "https://www.themoviedb.org/tv/1399-example"), JSON.stringify(["tmdb","tv","TV","1399"]));
  assert.equal(atlasProviderIdentity("GAME", "https://store.steampowered.com/app/620/portal/"), JSON.stringify(["steam","app","620"]));
  assert.equal(atlasProviderIdentity("BOOK", "https://books.google.com/books?id=abc_123&printsec=frontcover"), JSON.stringify(["google-books","abc_123"]));
  assert.equal(atlasProviderIdentity("BOOK", "https://example.com/book/123"), null);
});

test("Atlas filtering keeps only matching category, relationship and provenance edges", async () => {
  const graph = await buildAtlasGraph(
    { title: "Root", category: "ANIME", url: "https://anilist.co/anime/1" },
    async () => [
      { title: "Manga One", category: "MANGA", url: "https://anilist.co/manga/2", relationType: "adaptation", source: "AniList", sourceKind: "provider" },
      { title: "Game One", category: "GAME", url: "https://store.steampowered.com/app/3", relationType: "related", source: "Server proposal", sourceKind: "community" },
    ],
    { maxDepth: 1, maxNodes: 5, perNodeLimit: 5 },
  );
  const filtered = filterAtlasGraph(graph, { category: "MANGA", sourceKind: "provider" });
  assert.equal(filtered.nodes.length, 2);
  assert.equal(filtered.edges.length, 1);
  assert.equal(filtered.directRelationships.length, 1);
  assert.equal(filtered.directRelationships[0]?.title, "Manga One");
  assert.deepEqual(filterAtlasRelations(graph.directRelationships, {
    query: "ani list", relationshipType: "adaptation",
  }).map(item => item.title), ["Manga One"]);
});

test("Atlas pathfinding returns the shortest bounded path and ignores unreachable targets", async () => {
  const graph = await buildAtlasGraph(
    { title: "A", category: "ANIME", url: "https://example.com/a" },
    async node => node.title === "A"
      ? [
          { title: "B", category: "MANGA", url: "https://example.com/b", relationType: "adaptation", source: "AniList", sourceKind: "provider" },
          { title: "C", category: "GAME", url: "https://example.com/c", relationType: "related", source: "Community", sourceKind: "community" },
        ]
      : node.title === "B"
        ? [{ title: "D", category: "BOOK", url: "https://example.com/d", relationType: "source material", source: "Google Books", sourceKind: "provider" }]
        : node.title === "C"
          ? [{ title: "D", category: "BOOK", url: "https://example.com/d", relationType: "inspiration", source: "Community", sourceKind: "community" }]
          : [],
    { maxDepth: 3, maxNodes: 10, perNodeLimit: 5 },
  );
  const path = findAtlasPath(graph, { title: "D", category: "BOOK", url: "https://example.com/d" });
  assert.ok(path);
  assert.equal(path.edges.length, 2);
  assert.equal(path.nodes[0]?.title, "A");
  assert.equal(path.nodes.at(-1)?.title, "D");
  assert.equal(findAtlasPath(graph, { title: "Missing", category: "BOOK" }), null);
});
