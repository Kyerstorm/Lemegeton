import test from "node:test";
import assert from "node:assert/strict";
import { parseIgdbUpcomingRelease } from "../helpers/integration/igdb.js";

test("IGDB release dates retain source, platform, region and safe artwork", () => {
  const release = parseIgdbUpcomingRelease({
    date: 1798761600,
    region: { name: "Worldwide" },
    platform: { name: "PC" },
    game: {
      id: 20, name: "Example Game", slug: "example-game",
      cover: { url: "//images.igdb.com/igdb/image/upload/t_cover_big/example.jpg" },
    },
  });
  assert.ok(release);
  assert.equal(release.title, "Example Game");
  assert.equal(release.region, "Worldwide");
  assert.equal(release.platform, "PC");
  assert.equal(release.sourceUrl, "https://www.igdb.com/games/example-game");
  assert.equal(release.image, "https://images.igdb.com/igdb/image/upload/t_cover_big/example.jpg");
});

test("IGDB release parser rejects invalid dates and unlinked games", () => {
  assert.equal(parseIgdbUpcomingRelease({ date: 0, game: { id: 1, name: "Bad" } }), null);
  assert.equal(parseIgdbUpcomingRelease({ date: 1798761600, game: { id: 0, name: "Bad" } }), null);
});
