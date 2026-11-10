import test from "node:test";
import assert from "node:assert/strict";
import { AniListClient } from "../helpers/providers/anilist.js";

test("AniList detail preserves full release metadata on related titles", async () => {
  let query = "";
  const client = new AniListClient(
    "https://anilist.example/graphql",
    1_000,
    async (_input, init) => {
      const request = JSON.parse(String(init?.body)) as { query: string };
      query = request.query;
      return new Response(JSON.stringify({
        data: {
          Media: {
            id: 42,
            type: "ANIME",
            isAdult: false,
            title: { english: "Middle", romaji: "Middle" },
            siteUrl: "https://anilist.co/anime/42",
            startDate: { year: 2020, month: 2, day: 1 },
            relations: {
              edges: [{
                relationType: "PREQUEL",
                node: {
                  id: 41,
                  type: "ANIME",
                  isAdult: false,
                  title: { english: "Earlier", romaji: "Earlier" },
                  siteUrl: "https://anilist.co/anime/41",
                  status: "FINISHED",
                  startDate: { year: 2018, month: 4, day: 12 },
                },
              }],
            },
          },
        },
      }), { status: 200, headers: { "content-type": "application/json" } });
    },
  );

  const result = await client.getMediaById(42, "ANIME");

  assert.match(query, /relations\\{edges\\{/);\n  assert.match(query, /status startDate\\{year month day\\}/);
  assert.equal(result?.relations[0]?.relation, "PREQUEL");
  assert.equal(result?.relations[0]?.status, "FINISHED");
  assert.deepEqual(result?.relations[0]?.startDate, { year: 2018, month: 4, day: 12 });
});
