import test from "node:test";
import assert from "node:assert/strict";
import { AniListClient, parseCreator } from "../helpers/integration/anilist.js";

test("AniList creator records preserve occupations and linked media",()=>{
 const creator=parseCreator({id:42,name:{full:"Example Creator"},siteUrl:"https://anilist.co/staff/42",image:{large:"https://s4.anilist.co/file/anilistcdn/staff/large/b42.jpg"},description:"A creator",primaryOccupations:["Writer","Illustrator"],yearsActive:[2000],staffMedia:{edges:[{staffRole:"Original Creator",node:{id:9,type:"MANGA",siteUrl:"https://anilist.co/manga/9",title:{english:"Example Comic"}}}]}});
 assert.ok(creator);assert.equal(creator.name,"Example Creator");assert.deepEqual(creator.occupations,["Writer","Illustrator"]);assert.deepEqual(creator.yearsActive,[2000]);assert.equal(creator.media[0]?.title,"Example Comic");
});

test("AniList creator parser rejects untrusted profile and media URLs",()=>{
 assert.equal(parseCreator({id:1,name:{full:"Creator"},siteUrl:"http://anilist.co/staff/1"}),null);
 const creator=parseCreator({id:1,name:{full:"Creator"},siteUrl:"https://anilist.co/staff/1",staffMedia:{edges:[{staffRole:"Writer",node:{id:2,type:"ANIME",siteUrl:"https://example.com/anime/2",title:{romaji:"Bad"}}}]}});
 assert.deepEqual(creator?.media,[]);
});

test("AniList creator workographies retain provider cover images", () => {
  const creator = parseCreator({
    id: 43,
    name: { full: "Illustrator" },
    siteUrl: "https://anilist.co/staff/43",
    staffMedia: { edges: [{
      staffRole: "Illustrator",
      node: {
        id: 12, type: "MANGA", siteUrl: "https://anilist.co/manga/12",
        title: { english: "Illustrated Work" },
        coverImage: { large: "https://s4.anilist.co/file/anilistcdn/manga/cover/12.jpg" },
      },
    }] },
  });
  assert.equal(creator?.media[0]?.image, "https://s4.anilist.co/file/anilistcdn/manga/cover/12.jpg");
});

test("AniList studio search returns source-linked studios and related works", async () => {
  const requests: Array<{ query: string; variables: Record<string, unknown> }> = [];
  const client = new AniListClient(undefined, 2_000, async (_input, init) => {
    requests.push(JSON.parse(String(init?.body)) as { query: string; variables: Record<string, unknown> });
    return new Response(JSON.stringify({ data: { Page: { studios: [{
      id: 21,
      name: "Example Animation",
      siteUrl: "https://anilist.co/studio/21",
      isAnimationStudio: true,
      media: { nodes: [{
        id: 55, type: "ANIME", isAdult: false,
        siteUrl: "https://anilist.co/anime/55",
        title: { english: "Example Series" },
        coverImage: { large: "https://s4.anilist.co/file/anilistcdn/anime/cover/55.jpg" },
      }] },
    }] } } }), { status: 200, headers: { "content-type": "application/json" } });
  });
  const studios = await client.searchStudios("Example Animation");
  assert.equal(studios.length, 1);
  assert.equal(studios[0]?.id, 21);
  assert.equal(studios[0]?.isAnimationStudio, true);
  assert.equal(studios[0]?.works[0]?.title, "Example Series");
  assert.match(requests[0]?.query ?? "", /studios\(search:\$search,sort:SEARCH_MATCH\)/);
  assert.deepEqual(requests[0]?.variables, { search: "Example Animation", page: 1, perPage: 10 });
});

test("AniList studio search rejects short or oversized terms without a provider request", async () => {
  const client = new AniListClient();
  assert.deepEqual(await client.searchStudios("x"), []);
  assert.deepEqual(await client.searchStudios("x".repeat(101)), []);
});
