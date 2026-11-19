import test from "node:test";
import assert from "node:assert/strict";
import { IgdbClient } from "../helpers/integration/igdb.js";

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

test("IGDB genre search resolves genre names to IDs before filtering games", async () => {
  const requests: Array<{ url: string; body: string }> = [];
  const fetcher: typeof fetch = async (input, init) => {
    const url = String(input);
    if (url.startsWith("https://id.twitch.tv/oauth2/token")) {
      return jsonResponse({ access_token: "test-token", expires_in: 3600 });
    }
    const body = typeof init?.body === "string" ? init.body : "";
    requests.push({ url, body });
    if (url.endsWith("/genres")) {
      return jsonResponse([{ id: 1, name: "Fantasy" }, { id: 2, name: "Adventure" }]);
    }
    if (url.endsWith("/games")) {
      return jsonResponse([{
        id: 99,
        name: "Example Quest",
        slug: "example-quest",
        genres: [{ id: 1, name: "Fantasy" }],
      }]);
    }
    return new Response(null, { status: 404 });
  };
  const client = new IgdbClient("test-client", "test-secret", fetcher);

  const results = await client.searchByGenres(["Fantasy", "Adventure"]);

  assert.equal(results.length, 1);
  assert.equal(results[0]?.title, "Example Quest");
  assert.deepEqual(results[0]?.genres, ["Fantasy"]);
  const genreRequest = requests.find(request => request.url.endsWith("/genres"));
  const gameRequest = requests.find(request => request.url.endsWith("/games"));
  assert.match(genreRequest?.body ?? "", /fields id,name; limit 100;/);
  assert.match(gameRequest?.body ?? "", /where genres = \(1,2\)/);
});

test("IGDB genre search skips game queries when no provider genre IDs match", async () => {
  let gameRequests = 0;
  const fetcher: typeof fetch = async input => {
    const url = String(input);
    if (url.startsWith("https://id.twitch.tv/oauth2/token")) {
      return jsonResponse({ access_token: "test-token", expires_in: 3600 });
    }
    if (url.endsWith("/genres")) {
      return jsonResponse([{ id: 4, name: "Strategy" }]);
    }
    if (url.endsWith("/games")) gameRequests += 1;
    return jsonResponse([]);
  };
  const client = new IgdbClient("test-client", "test-secret", fetcher);

  assert.deepEqual(await client.searchByGenres(["Fantasy"]), []);
  assert.equal(gameRequests, 0);
});
