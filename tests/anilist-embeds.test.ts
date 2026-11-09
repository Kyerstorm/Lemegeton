import test from "node:test";
import assert from "node:assert/strict";
import { AniListClient } from "../helpers/providers/anilist.js";
import { parseAniListUrl } from "../helpers/embeds/anilist.js";
import {
  buildErrorEmbed,
  buildInfoEmbed,
  buildMediaEmbed,
  buildRelationsEmbeds,
  buildStatsEmbed,
  buildSuccessEmbed,
  buildTagsEmbed,
  buildTrendingEmbed,
  buildUserFavoritesEmbed,
  buildUserProfileEmbed,
} from "../helpers/embeds/core.js";

test("AniList URL parser recognizes media and supported profile sections", () => {
  assert.deepEqual(parseAniListUrl("https://anilist.co/anime/123/example-title"), {
    kind: "media", id: 123, type: "ANIME",
  });
  assert.deepEqual(parseAniListUrl("https://www.anilist.co/manga/456"), {
    kind: "media", id: 456, type: "MANGA",
  });
  assert.deepEqual(parseAniListUrl("https://anilist.co/user/VireonNoctis/"), {
    kind: "user", username: "VireonNoctis", section: "overview",
  });
  assert.equal(parseAniListUrl("https://anilist.co/user/example/stats")?.kind, "user");
  assert.equal(parseAniListUrl("https://anilist.co/user/example/statistics")?.kind, "user");
  assert.equal(parseAniListUrl("https://anilist.co/user/example/favorites")?.kind, "user");
  assert.equal(parseAniListUrl("https://anilist.co/user/example/activity")?.kind, "user");
});

test("AniList URL parser recognizes character, staff, studio, review and activity routes", () => {
  assert.deepEqual(parseAniListUrl("https://anilist.co/character/101"), {kind:"entity",id:101,entityKind:"CHARACTER"});
  assert.deepEqual(parseAniListUrl("https://anilist.co/staff/202/example"), {kind:"entity",id:202,entityKind:"STAFF"});
  assert.deepEqual(parseAniListUrl("https://anilist.co/studio/303"), {kind:"entity",id:303,entityKind:"STUDIO"});
  assert.deepEqual(parseAniListUrl("https://anilist.co/review/404"), {kind:"review",id:404});
  assert.deepEqual(parseAniListUrl("https://anilist.co/activity/505"), {kind:"activity",id:505});
  assert.equal(parseAniListUrl("https://anilist.co/staff/nope"), null);
  assert.equal(parseAniListUrl("https://anilist.co/activity/0"), null);
});

test("AniList public entity, review and activity methods use provider IDs and normalize safe links", async () => {
  const replies: unknown[] = [
    { data: { Character: {
      id: 101, name: { full: "Example Character" }, siteUrl: "https://anilist.co/character/101",
      image: { large: "https://s4.anilist.co/file/anilistcdn/character/large/101.jpg" },
      description: "A character",
      media: { nodes: [{ id: 11, type: "ANIME", isAdult: false, title: { romaji: "Example Show" }, siteUrl: "https://anilist.co/anime/11" }] },
    } } },
    { data: { Staff: {
      id: 202, name: { full: "Example Creator" }, siteUrl: "https://anilist.co/staff/202",
      image: { large: "https://s4.anilist.co/file/anilistcdn/staff/large/202.jpg" },
      primaryOccupations: ["Writer"], yearsActive: [2010],
      staffMedia: { edges: [{ staffRole: "Original Creator", node: {
        id: 12, type: "MANGA", isAdult: false, title: { romaji: "Example Manga" }, siteUrl: "https://anilist.co/manga/12",
      } }] },
    } } },
    { data: { Studio: {
      id: 303, name: "Example Studio", siteUrl: "https://anilist.co/studio/303",
      media: { nodes: [{ id: 13, type: "ANIME", isAdult: false, title: { romaji: "Studio Work" }, siteUrl: "https://anilist.co/anime/13" }] },
    } } },
    { data: { Review: {
      id: 404, summary: "Short summary", body: "Review body", score: 85, rating: 4,
      ratingAmount: 20, createdAt: 1_700_000_000, siteUrl: "https://anilist.co/review/404",
      user: { name: "Reviewer", siteUrl: "https://anilist.co/user/Reviewer" },
      media: { id: 14, type: "ANIME", isAdult: false, title: { romaji: "Reviewed Anime" }, siteUrl: "https://anilist.co/anime/14" },
    } } },
    { data: { Activity: {
      id: 505, siteUrl: "https://anilist.co/activity/505", createdAt: 1_700_000_100,
      text: "Public post", user: { name: "Poster", siteUrl: "https://anilist.co/user/Poster" },
    } } },
  ];
  let index = 0;
  const client = new AniListClient("https://graphql.anilist.co", 1_000, async (_input, init) => {
    const payload = replies[index++];
    assert.ok(payload);
    return new Response(JSON.stringify(payload), {status:200,headers:{"content-type":"application/json"}});
  });
  const character = await client.getPublicEntity(101,"CHARACTER");
  assert.equal(character?.name,"Example Character");
  assert.equal(character?.works[0]?.title,"Example Show");
  const staff = await client.getPublicEntity(202,"STAFF");
  assert.equal(staff?.roles[0],"Writer");
  assert.equal(staff?.works[0]?.role,"Original Creator");
  const studio = await client.getPublicEntity(303,"STUDIO");
  assert.equal(studio?.name,"Example Studio");
  assert.equal(studio?.works[0]?.type,"ANIME");
  const review = await client.getReviewById(404);
  assert.equal(review?.mediaTitle,"Reviewed Anime");
  assert.equal(review?.userName,"Reviewer");
  const activity = await client.getActivityById(505);
  assert.equal(activity?.text,"Public post");
  assert.equal(activity?.userName,"Poster");
});
test("AniList URL parser ignores personal list routes and unsafe or malformed URLs", () => {
  for (const route of ["animelist", "anime", "anime-list", "mangalist", "manga", "manga-list"]) {
    assert.equal(parseAniListUrl("https://anilist.co/user/example/" + route), null);
  }
  assert.equal(parseAniListUrl("https://evil.example/anime/1"), null);
  assert.equal(parseAniListUrl("http://anilist.co/anime/1"), null);
  assert.equal(parseAniListUrl("https://anilist.co/anime/0"), null);
  assert.equal(parseAniListUrl("https://anilist.co/anime/not-a-number"), null);
  assert.equal(parseAniListUrl("not a URL"), null);
});

test("AniList detail query normalizes the sections needed by the media embed family", async () => {
  const payload = {
    data: {
      Media: {
        id: 123,
        type: "ANIME",
        isAdult: false,
        title: { romaji: "Example Anime", english: "Example", native: "例" },
        description: "<p>Synopsis text.</p>",
        siteUrl: "https://anilist.co/anime/123/example",
        coverImage: { large: "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/123.jpg" },
        bannerImage: "https://s4.anilist.co/file/anilistcdn/media/anime/banner/123.jpg",
        averageScore: 87,
        status: "FINISHED",
        format: "TV",
        startDate: { year: 2024, month: 1, day: 2 },
        endDate: { year: 2024, month: 4, day: 2 },
        episodes: 12,
        genres: ["Adventure", "Fantasy"],
        studios: { nodes: [{ name: "Studio One" }] },
        popularity: 120_000,
        favourites: 5_000,
        source: "MANGA",
        staff: {
          edges: [{
            role: "Director",
            node: {
              id: 22,
              name: { full: "Example Director" },
              siteUrl: "https://anilist.co/staff/22",
              image: { large: "https://s4.anilist.co/file/anilistcdn/staff/large/22.jpg" },
            },
          }],
        },
        characters: {
          edges: [{
            role: "MAIN",
            node: {
              id: 33,
              name: { full: "Example Hero" },
              image: { large: "https://s4.anilist.co/file/anilistcdn/character/large/33.jpg" },
              isAdult: false,
            },
          }],
        },
        tags: [{ name: "Found Family", rank: 90, isMediaSpoiler: false, isAdult: false }],
        stats: {
          statusDistribution: [{ status: "CURRENT", amount: 10 }],
          scoreDistribution: [{ score: 85, amount: 15 }],
        },
        recommendations: {
          edges: [{
            node: {
              mediaRecommendation: {
                id: 222,
                title: { romaji: "Related Anime" },
                siteUrl: "https://anilist.co/anime/222",
                coverImage: { large: "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/222.jpg" },
                isAdult: false,
              },
            },
          }],
        },
        relations: {
          edges: [{
            relationType: "SOURCE",
            node: { id: 456, type: "MANGA", isAdult: false, siteUrl: "https://anilist.co/manga/456", title: { romaji: "Source Manga" } },
          }],
        },
        trailer: { id: "abc12345", site: "youtube" },
      },
    },
  };
  const client = new AniListClient("https://graphql.anilist.co", 1_000, async (_input, init) => {
    const request = JSON.parse(String(init?.body)) as { query: string; variables: Record<string, unknown> };
    assert.match(request.query, /MediaDetails/);
    assert.deepEqual(request.variables, { id: 123, type: "ANIME" });
    return new Response(JSON.stringify(payload), { status: 200, headers: { "content-type": "application/json" } });
  });
  const media = await client.getMediaById(123, "ANIME");
  assert.ok(media);
  assert.equal(media.title.romaji, "Example Anime");
  assert.equal(media.staffCredits[0]?.name, "Example Director");
  assert.equal(media.staffCredits[0]?.role, "Director");
  assert.equal(media.characters[0]?.name, "Example Hero");
  assert.equal(media.tags[0]?.isSpoiler, false);
  assert.equal(media.stats.scoreDistribution[0]?.score, 85);
  assert.equal(media.recommendations[0]?.title, "Related Anime");
  assert.equal(media.relations[0]?.category, "manga");
  assert.equal(media.trailer?.url, "https://youtu.be/abc12345");

  const embed = buildMediaEmbed(media).toJSON();
  assert.equal(embed.title?.includes("Example Anime"), true);
  assert.equal(embed.url, "https://anilist.co/anime/123/example");
  assert.ok(embed.fields?.some(field => field.name === "Studio" && field.value.includes("Studio One")));
  assert.ok(embed.fields?.some(field => field.name === "Main Characters" && field.value.includes("Example Hero")));
  assert.ok(buildRelationsEmbeds(media).length > 0);
  assert.ok(buildStatsEmbed(media).data.fields?.length);
  assert.ok(buildTagsEmbed(media).data.description?.includes("Found Family"));
  assert.ok(buildTrendingEmbed([media], "Trending", "Popular this week").data.fields?.length);
});

test("AniList detail parser rejects adult media and invalid IDs", async () => {
  const client = new AniListClient("https://graphql.anilist.co", 1_000, async () =>
    new Response(JSON.stringify({ data: { Media: { id: 1, type: "ANIME", isAdult: true } } }), { status: 200 }),
  );
  assert.equal(await client.getMediaById(1, "ANIME"), null);
  await assert.rejects(() => client.getMediaById(0, "ANIME"), /positive integer/);
});

test("shared embed builders produce consistent titled status and profile embeds", () => {
  assert.ok(buildErrorEmbed("Failure", "Try again").data.title?.startsWith("❌"));
  assert.ok(buildSuccessEmbed("Saved", "Done").data.title?.startsWith("✅"));
  assert.ok(buildInfoEmbed("Details", "Info").data.title?.startsWith("ℹ️"));
  const user = {
    id: 7,
    name: "ExampleUser",
    url: "https://anilist.co/user/ExampleUser",
    avatar: "https://s4.anilist.co/file/anilistcdn/user/avatar/large/7.jpg",
    banner: null,
    about: "A public AniList profile",
    anime: { count: 20, meanScore: 83, episodesWatched: 240, minutesWatched: 3_000, chaptersRead: null, volumesRead: null, genres: [], statuses: [], formats: [] },
    manga: { count: 10, meanScore: 78, episodesWatched: null, minutesWatched: null, chaptersRead: 400, volumesRead: 40, genres: [], statuses: [], formats: [] },
    favorites: {
      anime: [{ id: 1, title: "Example Anime", url: "https://anilist.co/anime/1", image: null }],
      manga: [],
      characters: [],
      staff: [],
      studios: [],
    },
  };
  assert.equal(buildUserProfileEmbed(user).data.url, user.url);
  assert.equal(buildUserFavoritesEmbed(user).data.fields?.length, 5);
});

test("AniList genre discovery uses provider genres, optional tags and adult exclusion", async () => {
  const requests: Array<{ query: string; variables: Record<string, unknown> }> = [];
  const client = new AniListClient("https://graphql.anilist.co", 1_000, async (_input, init) => {
    requests.push(JSON.parse(String(init?.body)) as { query: string; variables: Record<string, unknown> });
    return new Response(JSON.stringify({ data: { Page: { media: [{
      id: 321, type: "ANIME", isAdult: false, title: { english: "Fantasy Work" },
      siteUrl: "https://anilist.co/anime/321", genres: ["Fantasy"],
      tags: [{ name: "Found Family", rank: 90, isMediaSpoiler: false, isAdult: false }],
    }] } } }), { status: 200, headers: { "content-type": "application/json" } });
  });
  const results = await client.searchByGenres("ANIME", ["Fantasy"], ["Found Family"]);
  assert.equal(results[0]?.title.english, "Fantasy Work");
  assert.deepEqual(requests[0]?.variables, { type: "ANIME", genres: ["Fantasy"], tags: ["Found Family"], format: null });
  assert.match(requests[0]?.query ?? "", /isAdult:false/);
  assert.deepEqual(await client.searchByGenres("ANIME", []), []);
});
